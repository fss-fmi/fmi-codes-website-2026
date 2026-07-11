# Kubernetes migration (see issue #25)

Tracks the phased move off `docker-compose.yml` onto a locally-hosted k3s cluster.
Sub-issues: #26 (cluster), #27 (Postgres + Redis Sentinel), #28 (app tier),
#29 (ingress/TLS), #30 (CI/CD), #31 (config/secrets).

## Phase 1 — local cluster (#26)

Two scripts, run inside a **WSL2 Ubuntu** shell:

| Script | What it does |
| --- | --- |
| `install-tools-wsl2.sh` | Installs the CLIs — `kubectl`, `helm`, `k9s` — each pinned to a specific version and checksum-verified. The "npm install" of this workflow. |
| `bootstrap-wsl2-k3s.sh` | Stands up k3s (pinned version, Traefik disabled — Phase 4 installs `ingress-nginx`), wires up `kubectl`/Helm, and creates the app namespace from `namespace.yaml`. |

```bash
# 1. Get the tooling (one-shot, idempotent)
bash infra/k8s/install-tools-wsl2.sh

# 2. Stand up the cluster + namespace (idempotent)
bash infra/k8s/bootstrap-wsl2-k3s.sh
```

Re-running either is safe — every step is idempotent. Override the namespace
with `NAMESPACE=my-ns bash infra/k8s/bootstrap-wsl2-k3s.sh` if needed (that path
labels an on-the-fly namespace instead of applying `namespace.yaml`). Tool and
cluster versions are pinned via `*_VERSION` env vars at the top of each script —
override them to upgrade (e.g. `K3S_VERSION=v1.37.0+k3s1 bash …`).

How long `bootstrap-wsl2-k3s.sh` waits for the cluster is tunable, too:
`API_TIMEOUT` (default 300s) for the API server to serve `/readyz`, `NODE_TIMEOUT`
(default 180s) for the node to go Ready, and `CRASH_LOOP_MAX_RESTARTS` (default 3)
— if the k3s systemd unit restarts that many times while waiting, the script
stops early and prints `systemctl status` + the journal tail, since a
crash-looping k3s won't fix itself by waiting longer.

> **Supply-chain note:** `install-tools-wsl2.sh` downloads each binary pinned to a
> version and verifies it against the vendor-published SHA256 before installing —
> nothing is piped into a shell. `bootstrap-wsl2-k3s.sh` runs the official k3s
> installer from `get.k3s.io` (pinned via `INSTALL_K3S_VERSION`); that installer
> runs under `sudo` and GPG-verifies the k3s binary it fetches. If you'd rather
> not run a remote installer as root, install k3s from a downloaded release binary
> out of band.

### Why k3s (not kind)

Both are fine local Kubernetes distros; they optimise for different things:

- **k3s** — a single lightweight binary that installs as a system service, so the
  cluster comes back after a reboot. Closest to a "real" cluster and meant to
  stay up — the right fit for a semi-persistent local deployment.
- **kind** — Kubernetes-in-Docker, great for disposable per-test dev clusters you
  spin up and throw away. Doesn't naturally persist across reboots.

Because this deployment is meant to stay running, **k3s is the default.** It ships
the Flannel CNI and a bundled kubectl, so there's nothing extra to install for
networking in this phase.

## Test the cluster

After bootstrapping, confirm it's healthy:

```bash
kubectl config current-context   # confirm it points at the k3s cluster (usually "default")
kubectl get nodes -o wide        # a single node, STATUS Ready
kubectl get pods -A              # core k3s pods (coredns, metrics-server, local-path) Running
kubectl get namespace fmi-codes  # STATUS Active
```

Nothing is deployed into `fmi-codes` yet — that starts in Phase 2 (#27). For now a
Ready node + the `fmi-codes` namespace is the whole deliverable.

### Verify the acceptance criteria (#26)

- **A node is Ready** — `kubectl get nodes` shows `STATUS Ready`.
- **The namespace exists** — `kubectl get namespace fmi-codes` shows `Active`.
- **Survives a host reboot — _only if_ WSL2 systemd is enabled.** k3s installs as
  a systemd service, so on a host with systemd it restarts on boot:

  ```bash
  sudo systemctl is-enabled k3s   # -> enabled
  sudo systemctl status k3s       # -> active (running)
  ```

  **But default WSL2 has systemd off**, so out of the box this criterion does
  _not_ hold — k3s won't auto-start when you relaunch WSL. Two options:
  - Enable systemd once (`/etc/wsl.conf` → `[boot]\nsystemd=true`, then
    `wsl --shutdown` from Windows), after which the checks above pass and k3s
    survives relaunch; or
  - Leave systemd off and just re-run `bootstrap-wsl2-k3s.sh` after each WSL
    relaunch — it's idempotent and brings the cluster back in seconds.

## Troubleshooting: bootstrap says the API "did not come up"

`systemctl status k3s` showing **`active (running)`** only means the `k3s server`
process is alive — not that the API server is serving `:6443`. If bootstrap
reports the API didn't come up, check the journal (the script now prints it
automatically on failure):

```bash
sudo systemctl status k3s        # watch "active since … ; Ns ago"
sudo journalctl -u k3s -e --no-pager
```

If the `since … ; Ns ago` uptime keeps resetting to a few seconds — or you see
`activating (auto-restart)` with `Main PID … (code=exited)` — k3s is
**crash-looping**, not just slow. Common WSL2 fixes:

- **Missing iptables tools** (`Host iptables-save/iptables-restore tools not found`
  in the k3s log): `sudo apt-get install -y iptables`.
- **Stale cluster state from a prior boot:** `sudo /usr/local/bin/k3s-killall.sh`
  then `sudo rm -rf /var/lib/rancher/k3s`, and re-run bootstrap.
- **Too little memory for WSL2:** raise the limit in `%USERPROFILE%\.wslconfig`
  (e.g. `[wsl2]` → `memory=4GB`), then `wsl --shutdown` from Windows.

## Phase 2 — stateful services (#27)

Moves the Postgres + Redis Sentinel tier off `docker-compose.yml` and into the
cluster as managed stateful workloads, using the upstream Bitnami Helm charts.

| File | What it is |
| --- | --- |
| `postgresql-values.yaml` | Bitnami `postgresql` chart values — single primary, PVC-backed, DB `fmi_hackathon_2026`, user `fmi_app`, schema loaded from a ConfigMap. |
| `redis-values.yaml` | Bitnami `redis` chart values — `sentinel.enabled`, 1 master + 2 replicas + 3 sentinels, master set `mymaster`, quorum 2. Mirrors the docker-compose topology from #23. |
| `deploy-stateful.sh` | Idempotent deploy: creates the DB/Redis Secrets (once), syncs `schema.sql` into a ConfigMap, adds the Bitnami repo, and `helm upgrade --install`s both charts into `fmi-codes`. |

```bash
# Cluster must already be up (Phase 1). Then:
bash infra/k8s/deploy-stateful.sh
```

**Secrets are generated in-cluster, never committed.** On first run the script
creates two `Secret`s with random 32-char passwords — `fmi-codes-db`
(`password`, `postgres-password`) and `fmi-codes-redis` (`redis-password`) — and
the charts consume them via `existingSecret`. Re-runs detect the existing Secrets
and leave them untouched, so passwords never rotate out from under a running
datastore. Read a password back with:

```bash
kubectl -n fmi-codes get secret fmi-codes-db \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

**Schema init.** Rather than duplicating the 600-line `backend/database/schema.sql`
into the values file, the script loads it into the `postgres-initdb` ConfigMap and
points the chart at it (`primary.initdb.scriptsConfigMap`). Postgres runs it once
on first boot of an empty data directory — exactly like the `docker-entrypoint-initdb.d`
mount it replaces. `schema.sql` stays the single source of truth.

Chart and image versions are pinned via env vars at the top of the script
(`POSTGRES_CHART_VERSION`, `REDIS_CHART_VERSION`) and in the values files
(`image.tag`) — override to upgrade.

> **Why `bitnamilegacy/*` images.** In August 2025 Bitnami moved its free Docker
> catalog: the images the charts point at by default (`docker.io/bitnami/postgresql`,
> `…/redis`, `…/redis-sentinel`, plus the `os-shell`/`kubectl` helper images) were
> removed from the free tier and archived under `docker.io/bitnamilegacy/*`. The
> values files therefore override every image `repository` to the `bitnamilegacy`
> namespace so the charts actually pull. `bitnamilegacy` is frozen (no future
> security patches) — a later phase should migrate to the maintained Bitnami Secure
> images or self-built images. Do **not** "correct" these back to `bitnami/*`; that
> tag no longer resolves and the pods will `ErrImagePull`. Newer chart versions also
> refuse non-`bitnami/*` images unless `global.security.allowInsecureImages: true`
> is set — the values files set it for this reason (see bitnami/charts#30850).

> **WSL + Docker Desktop gotcha.** If Docker Desktop wrote `"credsStore": "desktop.exe"`
> into your WSL `~/.docker/config.json`, Helm's chart fetch (and any OCI pull) fails
> with `fork/exec /usr/bin/docker-credential-desktop.exe: exec format error` — a
> Linux process can't run the Windows `.exe` credential helper. `deploy-stateful.sh`
> sidesteps this by running under a throwaway empty `DOCKER_CONFIG` for the duration,
> so no credential helper is ever invoked (the public charts/images need no auth).
> Nothing to configure — it just works.

### Connection coordinates (for Phase 3's app tier)

| Service | In-cluster address |
| --- | --- |
| Postgres | `postgres.fmi-codes.svc.cluster.local:5432` (DB `fmi_hackathon_2026`, user `fmi_app`) |
| Redis Sentinel | `redis.fmi-codes.svc.cluster.local:26379` (master set `mymaster`) |

These map straight onto the env vars the backend already reads
(`backend/app/services/redis_client.py`): set `REDIS_SENTINELS=redis.fmi-codes.svc.cluster.local:26379`
and `REDIS_MASTER_NAME=mymaster` and the app picks up HA discovery with no code
change — the same Sentinel path exercised by docker-compose in #23.

### Verify the acceptance criteria (#27)

**Everything Running and Ready** — one Postgres pod, one Redis master, two
replicas, and the Sentinel containers:

```bash
kubectl -n fmi-codes get pods
```

**Data survives a pod restart** — write a row, delete the pod, confirm it's still
there after the StatefulSet recreates it against the same PVC:

```bash
DB_PW=$(kubectl -n fmi-codes get secret fmi-codes-db -o jsonpath='{.data.password}' | base64 -d)
kubectl -n fmi-codes exec -it postgres-0 -- \
  env PGPASSWORD="$DB_PW" psql -U fmi_app -d fmi_hackathon_2026 \
  -c "INSERT INTO universities (name, is_seed) VALUES ('persistence-probe', false) ON CONFLICT DO NOTHING;"
kubectl -n fmi-codes delete pod postgres-0
kubectl -n fmi-codes wait --for=condition=Ready pod/postgres-0 --timeout=120s
kubectl -n fmi-codes exec -it postgres-0 -- \
  env PGPASSWORD="$DB_PW" psql -U fmi_app -d fmi_hackathon_2026 \
  -c "SELECT name FROM universities WHERE name = 'persistence-probe';"
```

**Sentinel failover** — kill the master and watch a replica get promoted. Ask any
Sentinel who the current master is, delete that master pod, then ask again — the
reported master address should change:

```bash
kubectl -n fmi-codes exec -it redis-node-0 -c sentinel -- \
  redis-cli -p 26379 sentinel master mymaster
# note the ip/port, delete the master pod backing it, wait ~10s, then re-run the
# same command from a *different* node — Sentinel should report the promoted replica:
kubectl -n fmi-codes exec -it redis-node-1 -c sentinel -- \
  redis-cli -p 26379 sentinel master mymaster
```

**Reachability from a throwaway debug pod** in the same namespace, before Phase 3:

```bash
REDIS_PW=$(kubectl -n fmi-codes get secret fmi-codes-redis -o jsonpath='{.data.redis-password}' | base64 -d)
kubectl -n fmi-codes run redis-probe --rm -it --restart=Never \
  --image=bitnamilegacy/redis:7.4.3-debian-12-r0 -- \
  redis-cli -h redis.fmi-codes.svc.cluster.local -p 26379 \
  -a "$REDIS_PW" sentinel master mymaster
```

## Connect k9s

[k9s](https://k9scli.io/) is a terminal UI for the cluster — browse pods, tail
logs, exec into containers, all from the keyboard. It reads the same
`~/.kube/config` the bootstrap sets up, so once the cluster is running:

```bash
k9s                 # opens on the current context
k9s -n fmi-codes    # jump straight to the app namespace
```

Handy keys once inside: `:pods`, `:svc`, `:ns` to switch resource views, `l` to
tail logs on a selected pod, `s` to shell in, `d` to describe, `Ctrl-C`/`:q` to
quit. If it opens against the wrong cluster, fix `kubectl config current-context`
first — k9s follows kubectl.

## Tear down

```bash
# Remove just the Phase 2 stateful releases (keeps the cluster):
helm -n fmi-codes uninstall redis postgres
# Helm leaves PVCs behind on purpose so data isn't lost by accident — drop them
# explicitly to reclaim the storage and force a fresh schema init next deploy:
kubectl -n fmi-codes delete pvc -l app.kubernetes.io/instance=postgres
kubectl -n fmi-codes delete pvc -l app.kubernetes.io/instance=redis

# Or nuke the whole cluster — k3s ships an uninstaller that removes the service
# and all cluster state:
/usr/local/bin/k3s-uninstall.sh
```

Manifests and Helm values for later phases land in this directory as each phase
is implemented.
