# Kubernetes migration (see issue #25)

Tracks the phased move off `docker-compose.yml` onto a locally-hosted k3s cluster.
Sub-issues: #26 (cluster), #27 (Postgres + Redis Sentinel), #28 (app tier),
#29 (ingress/TLS), #30 (CI/CD), #31 (config/secrets).

## Platform support

These scripts run on **Debian/Ubuntu Linux** and on **WSL2 (Ubuntu)** — the k3s
cluster and all tooling are Linux-native. They are **not** portable to macOS (no
k3s, no `apt-get`) or to Windows `cmd`/PowerShell (they're bash). "Runnable on
Windows" means *inside WSL2*, not native Windows.

- **Real Linux server** → `init-linux.sh`.
- **Windows dev box (WSL2)** → `init-windows.sh` — it runs `init-linux.sh`, then
  prints the extra Windows-side host-resolution steps a Windows browser needs.

## Directory layout

```
infra/k8s/
  scripts/       all the executable bash — init-linux, init-windows, deploy, config, rotate, bootstrap, install, flux-bootstrap
  base/          environment-agnostic manifests, split into two Kustomize builds:
                   base/app/     namespace, backend, frontend
                   base/ingress/ security-headers, certificate, ingress
  overlays/      per-environment Kustomize overlays layered on base:
                   overlays/prod/     namespace fmi-codes, host fmicodes.com, Let's Encrypt issuer
                   overlays/staging/  namespace fmi-codes-staging, host staging.fmicodes.com, self-signed issuer
  helm-values/   Bitnami chart values — postgresql, redis
  secrets/       prod secrets.enc.yaml (SOPS-encrypted; staging's lives under overlays/staging/secrets/; .sops.yaml is at the repo root)
  flux/          Flux GitOps resources — source, image automation (Phase 6)
  README.md      this file
```

### Environments (staging / prod)

Both environments run on the same k3s node, isolated at the namespace level, and are
built from one shared `base/` via Kustomize overlays. An overlay is selected with
`ENV=prod` (default) or `ENV=staging` on the deploy scripts, or by the Kustomize path
Flux reconciles.

| | prod | staging |
| --- | --- | --- |
| namespace | `fmi-codes` | `fmi-codes-staging` |
| host / origin | `fmicodes.com` | `staging.fmicodes.com` |
| DB/Redis service FQDNs | `*.fmi-codes.svc` | `*.fmi-codes-staging.svc` |
| TLS issuer | Let's Encrypt `ClusterIssuer` | self-signed namespaced `Issuer` |
| image tags | `<ts>-<sha>` (promoted from staging) | `<ts>-<sha>` (Flux-bumped) |

Both environments use one image-tag scheme: `<ts>-<sha>`, where `<ts>` is a Unix epoch
and `<sha>` the short commit hash, produced by `docker-cd.yaml` on every push to `main`
(plus a moving `latest`). There is no `staging` branch and no separate staging tag —
staging simply tracks the newest tag automatically, and prod runs whatever tag was last
promoted from staging. See "Phase 6 — GitOps continuous deploy" below for the full flow.

Everything else — replicas, resource limits, probes, security context, feature-flag
defaults, `FLASK_ENV`, security headers — is identical across the two, by design:
staging exists to catch problems before they reach prod, so it must mirror prod. The
prod overlay renders byte-identical to the pre-overlay flat manifests; verify with:

```bash
kubectl kustomize infra/k8s/overlays/prod
kubectl kustomize infra/k8s/overlays/prod/ingress
kubectl kustomize infra/k8s/overlays/staging
kubectl kustomize infra/k8s/overlays/staging/ingress
```

Staging uses a self-signed certificate deliberately — it avoids spending the Let's
Encrypt issuance budget on a throwaway environment, at the cost of a browser trust
warning. Flux reconciliation of the staging overlay is wired up in a later phase; the
overlay renders valid manifests now but is not yet reconciled automatically.

Two caveats for when staging goes live on the shared node. The `add-headers` setting
on the single cluster-wide `ingress-nginx` controller can point at only one
`namespace/security-headers` ConfigMap, so staging needs its own controller (own
`ingressClassName`) rather than sharing prod's — otherwise the last deploy wins the
header config for both. And staging has its **own** SOPS app secret
(`overlays/staging/secrets/secrets.enc.yaml`, namespace `fmi-codes-staging`),
encrypted with a **separate age key** from prod — see "Staging/prod secret isolation
(two age keys)" below.

Scripts resolve their siblings via a computed `K8S_DIR` (the `infra/k8s` root), so
they work regardless of where you invoke them from — `bash infra/k8s/scripts/init-linux.sh`
from the repo root is the normal entrypoint.

## Quick start — bring up everything

One command runs the whole sequence in order (tooling → cluster → stateful tier →
app tier → ingress). Pick the entrypoint for your host:

```bash
# On a Debian/Ubuntu Linux server:
bash infra/k8s/scripts/init-linux.sh

# On a Windows dev box (from inside a WSL2 Ubuntu shell):
bash infra/k8s/scripts/init-windows.sh
```

`init-windows.sh` is a thin wrapper: it runs `init-linux.sh` (passing through any
args, including `--from`), then prints the WSL2→Windows hosts-file steps. Both are
idempotent and resumable — if a step fails, fix the cause and continue with
`--from N` (N = 1-5) instead of redoing earlier steps. Steps 1-2 (k3s install,
`/usr/local/bin` writes) need interactive sudo, so run it in a terminal. The
phase-by-phase breakdown below explains what each step does and how to run them
individually.

## Changing a config value

To change a **non-secret** backend setting (feature flags, `FRONTEND_ORIGIN`,
Redis/DB coordinates) and roll the backend so pods pick it up:

```bash
bash infra/k8s/scripts/apply-config.sh FRONTEND_ORIGIN https://fmicodes.com
bash infra/k8s/scripts/apply-config.sh REGISTRATION_OPEN true
bash infra/k8s/scripts/apply-config.sh          # re-apply the overlay from disk, then roll
```

It patches the `fmi-codes-backend-config` ConfigMap and restarts the backend.
**Secrets are refused** here — the script points you at `rotate-secret.sh` (app
secrets) or `deploy-stateful.sh` (PVC-coupled DB/Redis passwords) instead. A live
patch drifts from git, so also edit the source of truth and commit it (the script
reminds you): env-specific keys (`FRONTEND_ORIGIN`, `DB_HOST`, `REDIS_SENTINELS`)
live in `overlays/<env>/backend-config-patch.yaml`; all other keys live in
`base/app/backend.yaml`. Pass `RESTART=false` to skip the rollout when batching
changes, or `ENV=staging` to target the staging namespace.

## Phase 1 — local cluster (#26)

Two scripts, run inside a Linux (or **WSL2 Ubuntu**) shell:

| Script | What it does |
| --- | --- |
| `scripts/install-tools.sh` | Installs the CLIs — `kubectl`, `helm`, `k9s`, `sops`, `age`, `flux` — each pinned to a specific version and checksum-verified. The "npm install" of this workflow. |
| `scripts/bootstrap-k3s.sh` | Stands up k3s (pinned version, Traefik disabled — Phase 4 installs `ingress-nginx`), wires up `kubectl`/Helm, and creates the app namespace from `base/app/namespace.yaml`. |

```bash
# 1. Get the tooling (one-shot, idempotent)
bash infra/k8s/scripts/install-tools.sh

# 2. Stand up the cluster + namespace (idempotent)
bash infra/k8s/scripts/bootstrap-k3s.sh
```

Re-running either is safe — every step is idempotent. Override the namespace
with `NAMESPACE=my-ns bash infra/k8s/scripts/bootstrap-k3s.sh` if needed (that path
labels an on-the-fly namespace instead of applying `base/app/namespace.yaml`). Tool and
cluster versions are pinned via `*_VERSION` env vars at the top of each script —
override them to upgrade (e.g. `K3S_VERSION=v1.37.0+k3s1 bash …`).

How long `bootstrap-k3s.sh` waits for the cluster is tunable, too:
`API_TIMEOUT` (default 300s) for the API server to serve `/readyz`, `NODE_TIMEOUT`
(default 180s) for the node to go Ready, and `CRASH_LOOP_MAX_RESTARTS` (default 3)
— if the k3s systemd unit restarts that many times while waiting, the script
stops early and prints `systemctl status` + the journal tail, since a
crash-looping k3s won't fix itself by waiting longer.

> **Supply-chain note:** `install-tools.sh` downloads each binary pinned to a
> version and verifies it against the vendor-published SHA256 before installing —
> nothing is piped into a shell. `bootstrap-k3s.sh` runs the official k3s
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
  - Leave systemd off and just re-run `bootstrap-k3s.sh` after each WSL
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
| `helm-values/postgresql-values.yaml` | Prod Bitnami `postgresql` chart values — single primary, PVC-backed, DB `fmi_hackathon_2026`, user `fmi_app`, schema loaded from a ConfigMap. |
| `helm-values/redis-values.yaml` | Prod Bitnami `redis` chart values — `sentinel.enabled`, 1 master + 3 replicas + sentinels, master set `mymaster`, quorum 2. Mirrors the docker-compose topology from #23. |
| `overlays/staging/postgresql-values.yaml` | Staging Postgres values — identical to prod except DB `fmi_hackathon_2026_staging`. Same `fullnameOverride: postgres`, so the service FQDN differs only by namespace (`postgres.fmi-codes-staging.svc`). |
| `overlays/staging/redis-values.yaml` | Staging Redis values — identical to prod (same topology, `fullnameOverride: redis`, master set `mymaster`). Namespace isolation separates it from prod. |
| `deploy-stateful.sh` | Idempotent deploy: creates the DB/Redis Secrets (once), syncs `schema.sql` into a ConfigMap, adds the Bitnami repo, and `helm upgrade --install`s both charts. `ENV=prod` (default) targets `fmi-codes` with the `helm-values/*.yaml`; `ENV=staging` targets `fmi-codes-staging` with the `overlays/staging/*.yaml`. |

```bash
# Cluster must already be up (Phase 1). Then:
bash infra/k8s/scripts/deploy-stateful.sh              # prod (fmi-codes)
ENV=staging bash infra/k8s/scripts/deploy-stateful.sh  # staging (fmi-codes-staging)
```

Staging gets its own Postgres and Redis so schema migrations, data wipes, and config
experiments never touch the prod database. Both environments run the same topology and
share `schema.sql`; the only functional difference is the staging DB name
(`fmi_hackathon_2026_staging`). Because staging deploys into a separate namespace, its
PVCs, services, and in-cluster secrets are already isolated from prod — the release
names (`postgres`, `redis`) and master set (`mymaster`) stay the same, matching the
service FQDNs the staging app tier already expects (`overlays/staging/backend-config-patch.yaml`).

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
> **This is a stopgap, not the destination:** `bitnamilegacy` is frozen and receives
> no security patches, so migrating to maintained images is tracked in #35 — do not
> let later phases adopt this as the permanent approach.

> **WSL + Docker Desktop gotcha.** If Docker Desktop wrote `"credsStore": "desktop.exe"`
> into your WSL `~/.docker/config.json`, Helm's chart fetch (and any OCI pull) fails
> with `fork/exec /usr/bin/docker-credential-desktop.exe: exec format error` — a
> Linux process can't run the Windows `.exe` credential helper. `deploy-stateful.sh`
> sidesteps this by running under a throwaway empty `DOCKER_CONFIG` for the duration,
> so no credential helper is ever invoked (the public charts/images need no auth).
> Nothing to configure — it just works.

### The PVC is the real source of truth (read before re-running)

Re-running `deploy-stateful.sh` is idempotent for the Helm releases, the generated
Secrets, and the schema ConfigMap — but **the PersistentVolumeClaims outlive all of
them, and two things get baked into the PVC at first boot: the schema and the DB
password.** That has two consequences worth knowing before you re-run or tear down:

- **Schema changes apply to a fresh DB only.** `schema.sql` runs via Postgres
  `initdb`, which fires exactly once — on an empty data directory. Editing
  `schema.sql` and re-running the script re-applies the ConfigMap and shows a happy
  `helm upgrade`, but the running DB **keeps the old schema**. To pick up schema
  changes you must drop the Postgres PVC (see Tear down) for a clean re-init, or
  introduce a real migration tool in a later phase. There is no in-place schema
  update here.
- **A Secret and its PVC are a matched pair.** The DB/Redis password is written into
  the PVC when the datastore first initializes. If you delete the generated Secret
  but leave the PVC (or vice versa), the next run generates a *new* random password
  in the Secret while the PVC still holds the *old* one → `password authentication
  failed`. **Always delete the Secret and its PVC together**, never one without the
  other.

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

## Phase 3 — stateless app tier (#28)

The backend (Flask/gunicorn) and frontend (nginx) run as ordinary, disposable
`Deployment`s fronted by `ClusterIP` `Service`s in the same `fmi-codes`
namespace. Nothing here is stateful — pods are cattle, killed and rescheduled
freely — so all persistence stays in the Phase 2 Postgres/Redis tier, reached
purely over env vars.

```bash
# Cluster + stateful tier must already be up (Phases 1–2). Then:
./deploy-app.sh
```

`deploy-app.sh` refuses to run until the Phase 2 namespace and the
`fmi-codes-db` / `fmi-codes-redis` secrets exist, so the #28 "depends on Phase 2"
ordering is enforced rather than assumed.

### What gets created

| Object | Name | Notes |
| --- | --- | --- |
| ConfigMap | `fmi-codes-backend-config` | Non-secret backend env — Postgres/Redis coordinates, feature flags |
| Deployment + Service | `backend` | 2 replicas of `fssfmi/fmi-codes-backend:latest`, ClusterIP on 5001 |
| Deployment + Service | `frontend` | 2 replicas of `fssfmi/fmi-codes-frontend:latest`, ClusterIP on 80 |
| Secret | `fmi-codes-app` | App secrets (`SECRET_KEY`, `JWT_SECRET_KEY`, …) — created by the script if absent |

### Why the backend Service is named `backend`

The frontend image's `nginx.conf` proxies `/api/` and `/static/` to a fixed
upstream. In docker-compose that host was the `app` service; in k8s it resolves
to the backend `Service` name. To keep a single nginx image working in **both**
environments with no per-target build, the upstream is `http://backend:5001` and:

- the k8s backend `Service` is named `backend`, and
- the compose `app` service carries a `backend` network alias.

So the same image resolves `backend` correctly whether it runs under compose or
k8s — no application code changes, matching the #28 constraint.

### Config and secrets model

Non-secret env lives in the `fmi-codes-backend-config` ConfigMap and is pulled in
with `envFrom`. Passwords are injected with `secretKeyRef`:

- `DB_PASSWORD` ← `fmi-codes-db` / `password` (reused from Phase 2)
- `REDIS_PASSWORD` ← `fmi-codes-redis` / `redis-password` (reused from Phase 2)
- `SECRET_KEY`, `JWT_SECRET_KEY`, `ADMIN_PASSWORD_HASH`, `MAIL_PASSWORD`,
  `DISCORD_BUG_WEBHOOK_URL` ← `fmi-codes-app`

`DATABASE_URL` is deliberately left unset — `backend/config.py` composes it from
the `DB_*` pieces when it's absent.

On first create the script generates strong random `SECRET_KEY` / `JWT_SECRET_KEY`
and leaves `ADMIN_PASSWORD_HASH`, `MAIL_PASSWORD`, `DISCORD_BUG_WEBHOOK_URL` empty.
The backend runs `production` config, which hard-fails at startup unless
`ADMIN_PASSWORD_HASH` is set, so patch a real bcrypt hash in before expecting the
pods to go Ready:

```bash
HASH=$(python -c "import bcrypt;print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt(12)).decode())")
kubectl -n fmi-codes patch secret fmi-codes-app \
  -p "{\"data\":{\"ADMIN_PASSWORD_HASH\":\"$(printf '%s' "$HASH" | base64 -w0)\"}}"
kubectl -n fmi-codes rollout restart deployment/backend
```

Phase 5 (#31) supersedes this manual patch flow with a git-committed,
SOPS-encrypted source of truth for `fmi-codes-app` and a one-command rotation
helper — see the Phase 5 section below.

### Health probes

The backend exposes two endpoints (added in this phase, on the `/api` blueprint):

- `GET /api/health` — **liveness**. Returns 200 whenever the process can serve a
  request; touches no dependencies, so a Postgres/Redis blip never kills a
  healthy pod.
- `GET /api/health/ready` — **readiness**. Runs a pooled `SELECT 1` and pings
  Redis. Postgres is the hard dependency: if it fails the pod returns 503 and is
  pulled from the Service until the DB recovers. Redis is fail-open by design, so
  its status is reported but never gates readiness.

The frontend probes `GET /` (nginx serving `index.html`).

### Verify the acceptance criteria (#28)

**Pods Running and Ready** — two backend, two frontend:

```bash
kubectl -n fmi-codes get pods -l app.kubernetes.io/part-of=fmi-codes-website-2026
```

**Self-heal with no downtime** — delete one backend pod and watch k8s reschedule
it while the other replica keeps serving:

```bash
kubectl -n fmi-codes delete pod \
  $(kubectl -n fmi-codes get pod -l app.kubernetes.io/name=fmi-codes-backend \
    -o jsonpath='{.items[0].metadata.name}')
kubectl -n fmi-codes get pods -l app.kubernetes.io/name=fmi-codes-backend -w
```

**Postgres + Redis reachable via env only** — the readiness endpoint exercises
both real dependencies from inside a backend pod:

```bash
kubectl -n fmi-codes exec deploy/backend -- \
  python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/api/health/ready').read())"
```

A `200` with `{"db": "ok", "redis": "ok"}` proves the app connected to the Phase 2
tier with nothing but env-var changes.

## Phase 4 — networking: Ingress + TLS (#29)

Phase 1 stood up k3s with **Traefik disabled** on purpose — this phase brings the
cluster's own ingress. It replaces the in-container routing the frontend's
`nginx.conf` was doing (proxying `/api/` and `/static/` to the backend) with a
cluster-native `Ingress`, and terminates TLS at the edge.

| File | What it is |
| --- | --- |
| `ingress.yaml` | The `Ingress` (host `fmicodes.com`, path rules below), its `tls:` block, the `security-headers` ConfigMap, and the cert-manager Let's Encrypt `ClusterIssuer` + `Certificate`. |
| `deploy-ingress.sh` | Idempotent deploy: `helm upgrade --install`s `ingress-nginx` and `cert-manager`, applies `ingress.yaml`, waits for the cert to be issued. |

```bash
# Cluster + stateful + app tiers must already be up (Phases 1–3). Then:
bash infra/k8s/scripts/deploy-ingress.sh
```

`deploy-ingress.sh` refuses to run until the Phase 3 `backend` and `frontend`
Services exist, so the "depends on Phase 3" ordering is enforced, not assumed.

### Routing

The path rules mirror the old `nginx.conf` `location` precedence exactly:

| Path | Backend |
| --- | --- |
| `/api` | `backend:5001` |
| `/static` | `backend:5001` |
| `/` (catch-all) | `frontend:80` |

The frontend container still exists and still serves the SPA (with its own
`try_files` fallback for client-side routes); the Ingress just fronts it. The
`/api/` and `/static/` `proxy_pass` blocks stay in `frontend/nginx.conf` so the
same image keeps working under `docker-compose`, where there is no Ingress.

### Security headers move to the edge

The security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`,
`Permissions-Policy`, `Content-Security-Policy`, `Strict-Transport-Security`) used to
live in `frontend/nginx.conf`, where they only attached to responses the frontend
served — `/api/` and `/static/` responses proxied straight through shipped **without**
them. They now live in the `security-headers` ConfigMap, wired into the controller via
`controller.config.add-headers=fmi-codes/security-headers`, so **every** response
through the Ingress carries them uniformly. The `add_header` lines were removed from
`frontend/nginx.conf` to avoid duplicate headers.

This uses ingress-nginx's supported `add-headers` mechanism, **not**
`configuration-snippet` annotations. Snippet annotations are disabled by default
(`allow-snippet-annotations: false`) since a controller-side injection hardening —
`add-headers` needs none of that loosened, so the controller keeps its default
posture.

On a first deploy the controller starts before `deploy-ingress.sh` applies the
ConfigMap (the manifest also carries the cert-manager resources, which can't apply
until cert-manager's CRDs exist). The controller watches the named header ConfigMap
and hot-reloads when it appears, so it self-heals within seconds — no restart
needed.

### TLS: Let's Encrypt via cert-manager

cert-manager provisions a real TLS certificate from Let's Encrypt using an HTTP-01
ACME challenge. The `fmi-codes-letsencrypt` `ClusterIssuer` handles the ACME account
and challenge lifecycle; cert-manager auto-renews the cert before expiry
(`renewBefore: 720h`). No `curl -k` needed — the cert is browser-trusted.

For the challenge to succeed, port 80 on the server must be reachable from the
internet and `fmicodes.com` must resolve to the server's IP in public DNS before
`deploy-ingress.sh` runs.

### HTTP → HTTPS redirect

ingress-nginx's `ssl-redirect` defaults to `true` and fires automatically once an
Ingress rule has a TLS cert, so HTTP requests get a `308` to HTTPS with no extra
config. The Ingress sets `nginx.ingress.kubernetes.io/ssl-redirect: "true"`
explicitly for clarity.

### Resolve the host

The Ingress matches on `Host: fmicodes.com`. For local testing, point that name
at the ingress controller's external address (the deploy script prints the exact
line):

```bash
INGRESS_IP=$(kubectl -n ingress-nginx get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "$INGRESS_IP fmicodes.com" | sudo tee -a /etc/hosts
```

On the production server, set the `fmicodes.com` A record in DNS instead.

### Verify the acceptance criteria (#29)

**Routing** — `/api/...` hits the backend, everything else the frontend:

```bash
curl https://fmicodes.com/api/health   # backend JSON, HTTP 200
curl https://fmicodes.com/             # the SPA's index.html
```

**Security headers present** on every response, including the backend routes that
shipped naked before:

```bash
curl -I https://fmicodes.com/api/health
# expect: X-Frame-Options, X-Content-Type-Options, Content-Security-Policy,
#         Strict-Transport-Security, Referrer-Policy, Permissions-Policy
```

**HTTPS works and HTTP redirects to it:**

```bash
curl -I http://fmicodes.com/              # HTTP/1.1 308, Location: https://fmicodes.com/
```

## Phase 5 — externalize config & secrets (#31)

Phases 3–4 already moved runtime config off the `.env` file and into k8s-native
objects: non-secret env lives in the `fmi-codes-backend-config` ConfigMap (pulled
with `envFrom`), and every sensitive value is injected via `secretKeyRef`. The
backend reads it all through `os.environ.get(...)` in `backend/config.py` — no
`.env` file ships in the container image. Phase 5 closes the loop by giving the
**app secret a git-committed, encrypted single source of truth** with
one-command rotation, so the team can edit secrets in one place without ever
committing plaintext.

| File | What it is |
| --- | --- |
| `.sops.yaml` | SOPS creation rule (repo root): which files to encrypt, which YAML keys, and the age recipients allowed to decrypt. |
| `secrets.enc.yaml` | The `fmi-codes-app` `Secret` manifest with its **values encrypted** by SOPS. Safe to commit to a public repo. |
| `rotate-secret.sh` | One-command rotation of a single secret key: re-encrypt, re-apply, restart backend. |

### The model: SOPS + age

[SOPS](https://github.com/getsops/sops) encrypts only the *values* of a YAML
file, leaving the keys and structure readable, so a git diff shows *which* secret
changed without revealing *what* it changed to. [age](https://github.com/FiloSottile/age)
is the encryption backend: each developer holds an age **key pair**, and SOPS
encrypts the file to every recipient's **public** key listed in `.sops.yaml`.
Any recipient can decrypt, edit, and re-encrypt; nobody else can read a thing.

Because encryption targets a *list* of recipients, this scales to a team with no
shared password — you add and remove people by editing the recipient list, not by
rotating a passphrase everyone has to re-learn.

```yaml
# secrets.enc.yaml — values are ciphertext, key names stay readable
stringData:
    SECRET_KEY: ENC[AES256_GCM,data:…]
    JWT_SECRET_KEY: ENC[AES256_GCM,data:…]
    ADMIN_PASSWORD_HASH: ENC[AES256_GCM,data:…]
    MAIL_PASSWORD: ""
    DISCORD_BUG_WEBHOOK_URL: ""
```

> **Never commit a raw k8s Secret.** A plain `Secret` manifest's `data:` values
> are base64, **not** encryption — `base64 -d` reveals them instantly. On a public
> repo that is an immediate credential leak. Only the SOPS-encrypted
> `secrets.enc.yaml` belongs in git; a decrypted copy must never be written into
> the repo tree.

### Why DB and Redis passwords are NOT in SOPS

`secrets.enc.yaml` owns **only** the `fmi-codes-app` secret (the five app-level
values). The `fmi-codes-db` and `fmi-codes-redis` passwords stay generated
in-cluster by `deploy-stateful.sh` (Phase 2) and are deliberately excluded,
because they are **PVC-coupled**: a datastore's password is baked into its
PersistentVolumeClaim at first boot (see "The PVC is the real source of truth"
above). If SOPS owned those and applied a value that differed from what the PVC
was initialized with, you'd get `password authentication failed`. Keeping them
in-cluster keeps the Secret and its PVC a matched pair — the one thing that
section warns you never to break.

### The age private key

The private key lives **outside the repo** at the SOPS default path,
`~/.config/sops/age/keys.txt`, and is `chmod 600`. It is never committed —
`.gitignore` also blocks stray `*.agekey` / `keys.txt` files as a backstop. Only
your **public** key (the `age1…` recipient) is committed, in `.sops.yaml`.

`install-tools.sh` installs `sops`, `age`, and `age-keygen` alongside the
other CLIs (pinned + checksum-verified). Generate your key once:

```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
age-keygen -y ~/.config/sops/age/keys.txt   # prints your public recipient (age1…)
```

Back this file up somewhere safe (a password manager). Lose every recipient's
private key and the committed secrets become permanently undecryptable — you'd
have to regenerate every value from scratch.

### Staging/prod secret isolation (two age keys)

Staging and prod each own a **separate** app secret encrypted with a **separate**
age key, so a leak of one environment's key never exposes the other's secrets.

| | prod | staging |
| --- | --- | --- |
| encrypted file | `infra/k8s/secrets/secrets.enc.yaml` | `infra/k8s/overlays/staging/secrets/secrets.enc.yaml` |
| Secret namespace | `fmi-codes` | `fmi-codes-staging` |
| age recipient (public) | `age1txhwhk6d5nph0sqf68e7yw5a0er572847jc4f60gmen5rfrx65xs0feuhh` | `age15zg0ymdvkt87hdvsj4xg582h0zsdgdrnkkk6msc76xtcrcyxyvcsljz0w5` |
| operator private key | `SOPS_AGE_KEY_STAGING` (CI) / a line in `~/.config/sops/age/keys.txt` | same file, second line |

`.sops.yaml` routes each file to its own recipient with two `creation_rules` (the
staging path rule is listed first so its more-specific path matches before the prod
rule). SOPS picks the rule by the file path being encrypted, so `sops` on either file
automatically encrypts to the right key — no per-file flags:

```yaml
creation_rules:
  - path_regex: infra/k8s/overlays/staging/secrets/secrets\.enc\.yaml$
    age: age15zg0ymdvkt87hdvsj4xg582h0zsdgdrnkkk6msc76xtcrcyxyvcsljz0w5
  - path_regex: infra/k8s/secrets/secrets\.enc\.yaml$
    age: age1txhwhk6d5nph0sqf68e7yw5a0er572847jc4f60gmen5rfrx65xs0feuhh
```

The isolation is enforced by age itself: the staging key is **not** a recipient of the
prod file and vice versa, so each key decrypts exactly one environment. Verify both
directions:

```bash
sops -d infra/k8s/overlays/staging/secrets/secrets.enc.yaml   # staging key: succeeds
sops -d infra/k8s/secrets/secrets.enc.yaml                    # staging key alone: fails
```

**An operator who manages both environments keeps both private keys in one keyring.**
`sops` reads every key line in `~/.config/sops/age/keys.txt`, so append the staging
key as a second line and one file decrypts both:

```bash
cat >> ~/.config/sops/age/keys.txt <<'KEY'
# staging
AGE-SECRET-KEY-1... (staging private key)
KEY
```

Or point `SOPS_AGE_KEY_FILE` at a file that holds the key(s) you need for a given run.

The deploy/rotate scripts are environment-aware via `ENV`: `ENV=staging` targets the
staging file and the `fmi-codes-staging` namespace, `ENV=prod` (default) targets prod.
Both scripts assert the decrypted manifest's `namespace:` matches the environment they
were asked to act on and refuse to apply across environments, so pointing the wrong
`ENV` at a file can't silently write one environment's secret into the other's
namespace.

```bash
ENV=staging bash infra/k8s/scripts/deploy-app.sh
ENV=staging bash infra/k8s/scripts/rotate-secret.sh JWT_SECRET_KEY
```

The **staging private key is stored as the `SOPS_AGE_KEY_STAGING` GitHub Actions
secret** (repo → Settings → Secrets and variables → Actions), mirroring how the prod
key will be provided to CI. No workflow consumes it yet — staging CI image builds
(#56) and staging Flux reconciliation (#57) wire it in later; storing it now keeps the
key material out of the repo and ready for those phases. `bootstrap.sh` remains
prod-only (it hardcodes the prod recipient); staging bootstrap support is tracked in
#59.

### Editing a secret

```bash
sops infra/k8s/secrets/secrets.enc.yaml                       # prod
sops infra/k8s/overlays/staging/secrets/secrets.enc.yaml      # staging
```

This decrypts into your `$EDITOR`, you edit plaintext, and on save SOPS
re-encrypts to every recipient. Then apply and roll the backend:

```bash
sops --decrypt infra/k8s/secrets/secrets.enc.yaml | kubectl -n fmi-codes apply -f -
kubectl -n fmi-codes rollout restart deployment/backend
git add infra/k8s/secrets/secrets.enc.yaml && git commit -m "rotate app secrets"
```

`deploy-app.sh` does the decrypt-and-apply automatically: when `secrets.enc.yaml`
exists and your age key can decrypt it, the script makes SOPS the source of truth
(`sops --decrypt … | kubectl apply`). On a fresh clone with **no** age key, it
falls back to generating a throwaway `fmi-codes-app` in-cluster so a quick
spin-up still works — but that fallback has an empty `ADMIN_PASSWORD_HASH`, so the
production backend stays in CrashLoop until you set one (the same guard as
Phase 3). With the SOPS file in play, the committed hash ships a working default.

### Rotating a secret — one command

```bash
# rotate to an explicit value:
bash infra/k8s/scripts/rotate-secret.sh MAIL_PASSWORD 'new-smtp-app-password'

# rotate to a freshly generated strong random value (SECRET_KEY / JWT_SECRET_KEY):
bash infra/k8s/scripts/rotate-secret.sh JWT_SECRET_KEY

# rotate the admin password (generate the bcrypt hash first):
HASH=$(python3 -c "import bcrypt;print(bcrypt.hashpw(b'newpassword', bcrypt.gensalt(12)).decode())")
bash infra/k8s/scripts/rotate-secret.sh ADMIN_PASSWORD_HASH "$HASH"
```

The script re-encrypts just that one key in `secrets.enc.yaml`, re-applies the
secret, and `rollout restart`s the backend. Commit the updated file afterwards so
the change is the new source of truth. Pass `RESTART=false` to skip the rollout
(e.g. when batching several rotations).

> **The default `ADMIN_PASSWORD_HASH` is a bcrypt hash of `admin123`** — a
> bootstrap convenience so a fresh deploy comes up loginable. It is *encrypted* in
> git (not readable), but it's still a known-weak password. **Rotate it to a real
> value before any non-local use** with the command above.

### Adding or removing a team member

**Add** — the new dev generates their key (above) and sends you their **public**
recipient. Add it under the `age:` list in `.sops.yaml`, then re-encrypt the file
to the expanded recipient set:

```bash
sops updatekeys infra/k8s/secrets/secrets.enc.yaml
git add .sops.yaml infra/k8s/secrets/secrets.enc.yaml
git commit -m "add <dev> as a secrets recipient"
```

`updatekeys` only re-wraps the data key for the new recipient list — it does not
change the secret values, so no rollout is needed.

**Remove** — delete their recipient line from `.sops.yaml`, run `sops updatekeys`
again, **and then rotate every secret value.** Removing a recipient stops them
decrypting *future* versions, but they still have their private key and the *old*
ciphertext in git history — so anything they could already read must be considered
compromised and rotated:

```bash
# after editing .sops.yaml to drop the departing recipient:
sops updatekeys infra/k8s/secrets/secrets.enc.yaml
for k in SECRET_KEY JWT_SECRET_KEY; do bash infra/k8s/scripts/rotate-secret.sh "$k"; done
# rotate MAIL_PASSWORD / DISCORD_BUG_WEBHOOK_URL / ADMIN_PASSWORD_HASH to fresh values too
git add .sops.yaml infra/k8s/secrets/secrets.enc.yaml && git commit -m "offboard <dev>: drop recipient + rotate secrets"
```

### Verify the acceptance criteria (#31)

**No plaintext secrets in the repo** — every value in `secrets.enc.yaml` is
`ENC[AES256_GCM,…]`, and DB/Redis passwords aren't committed at all:

```bash
grep -E 'SECRET_KEY|JWT_SECRET_KEY|ADMIN_PASSWORD_HASH' infra/k8s/secrets/secrets.enc.yaml
# every hit is ENC[…]; no readable value
```

**Staging and prod keys are isolated (#54)** — each key decrypts only its own
environment's file:

```bash
sops -d infra/k8s/overlays/staging/secrets/secrets.enc.yaml   # only the staging key succeeds
sops -d infra/k8s/secrets/secrets.enc.yaml                    # only the prod key succeeds
```

With only the prod key in your keyring the first command fails; with only the staging
key the second fails. That mutual failure is the isolation guarantee.

**Backend starts reading config exclusively from ConfigMap/Secret** — the pod has
no `.env`, and the readiness probe proves it reached Postgres/Redis on env alone:

```bash
kubectl -n fmi-codes exec deploy/backend -- sh -c 'test ! -f /app/.env && echo "no .env in container"'
kubectl -n fmi-codes exec deploy/backend -- \
  python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/api/health/ready').read())"
```

**Rotating a secret is a documented one-command operation** — `rotate-secret.sh`
above. Confirm a rotation lands end-to-end:

```bash
bash infra/k8s/scripts/rotate-secret.sh JWT_SECRET_KEY
# → re-encrypts secrets.enc.yaml, re-applies the secret, restarts backend, waits for Ready
```

## Phase 6 — GitOps continuous deploy (#30)

Merging a backend/frontend change should redeploy the running pods with no manual
step **in staging**, while production stays behind a deliberate human gate. The
cluster lives on a local server (WSL2 or a Linux box) that GitHub's cloud runners
**cannot reach**, so a push-based CI deploy is impossible. Instead
[Flux](https://fluxcd.io/) runs *inside* the cluster and **pulls** — it watches
the registry for new images and git for manifest changes, and reconciles the
cluster to match. Nothing inbound is ever needed.

The model is **continuous-deploy-to-staging, manual-promote-to-prod**, off a single
`main` branch (no `staging` branch exists):

- Push to `main` → images build → Flux auto-bumps the **staging** overlay → staging
  redeploys. Every merge lands in staging automatically.
- A dev promotes to **prod** by running the `promote-to-prod` workflow once staging is
  vetted. It copies the tag currently live in staging into the prod overlay and opens a
  PR — merging that PR is the production gate.

| File | What it is |
| --- | --- |
| `flux/source.yaml` | `GitRepository` (this repo, `main`, over SSH) + four `Kustomization`s: `fmi-codes` / `fmi-codes-ingress` reconcile `overlays/prod/`, and `fmi-codes-staging` / `fmi-codes-staging-ingress` reconcile `overlays/staging/`. |
| `flux/image-automation.yaml` | `ImageRepository` ×2 (watch the two Docker Hub repos) + `ImagePolicy` ×2 (`*-staging`, pick the newest `<ts>-<sha>` tag) + `ImageUpdateAutomation` (commits tag bumps to `overlays/staging/` on the `flux-image-updates` branch). Prod has **no** ImagePolicy — its tag only ever changes via the promote workflow. |
| `overlays/staging/kustomization.yaml` | Kustomize `images:` override Flux edits (carries the `$imagepolicy` setter markers). |
| `overlays/prod/kustomization.yaml` | Kustomize `images:` override — **no** setter markers, so Flux never auto-edits it. The promote workflow writes the tag here. |
| `.github/workflows/promote-to-prod.yaml` | `workflow_dispatch` — reads the live staging tag (or an explicit input), writes it into the prod overlay, opens a PR to `main`. Does **not** auto-merge. |
| `scripts/flux-bootstrap.sh` | Idempotent: `flux install`, create the git-auth Secret from your SSH deploy key, apply the `flux/` resources, reconcile. |

### The deploy loop

```
merge backend change to main
  → docker-cd.yaml builds & pushes fssfmi/fmi-codes-backend:<unix-ts>-<sha>
  → Flux ImagePolicy sees the newer tag (sorted numerically on the timestamp)
  → Flux commits the bump to overlays/staging/kustomization.yaml on branch flux-image-updates
  → that branch auto-merges into main (flux-auto-pr.yaml)
  → Flux reconciles main and rolls ONLY the backend Deployment in STAGING (frontend untouched)

when staging is vetted, promote to prod
  → run the "Promote to production" workflow (Actions tab → Run workflow)
  → it copies staging's current tag into overlays/prod/kustomization.yaml and opens a PR
  → you review & merge that PR into main
  → Flux reconciles main and rolls the prod Deployment(s) to the promoted tag
```

Image tags are immutable `<unix-ts>-<sha>` (not `:latest`) precisely so Flux can
order them and detect "backend changed" per service. Staging bumps auto-merge (fast
feedback); the prod promote PR is merged by a human (the gate) — `git revert` of a
promote commit is a prod rollback.

### Ownership: Flux owns the app Deployments

Once Flux is bootstrapped it is the **single owner of the backend/frontend
Deployments** in both namespaces. `deploy-app.sh` still owns the SOPS app secret and
first-time bootstrap, but it detects the Flux `Kustomization` (`FLUX_KUSTOMIZATION`:
`fmi-codes` for prod, `fmi-codes-staging` for staging) and **skips re-applying the
Deployments** when Flux is active — no tug-of-war over the image tag. The stateful
tier (Postgres/Redis via Helm) and ingress stay owned by their respective
`deploy-*.sh` scripts; Flux reconciles `overlays/prod/` and `overlays/staging/`
(backend + frontend, plus the ingress build each depends on), so `prune: true` can
never touch them.

### One-time setup — SSH deploy key

Flux's image automation commits back to the repo, so it needs a **write-capable**
credential. Use a repo deploy key (repo-scoped, not tied to your account):

```bash
# 1. Generate a keypair (no passphrase — Flux reads it non-interactively)
ssh-keygen -t ed25519 -f ~/.ssh/fmi-codes-flux -N ""

# 2. Add the PUBLIC key as a repo deploy key WITH write access:
#    GitHub → repo → Settings → Deploy keys → Add deploy key → paste
#    ~/.ssh/fmi-codes-flux.pub, tick "Allow write access".
cat ~/.ssh/fmi-codes-flux.pub

# 3. Bootstrap Flux (creates the in-cluster Secret from the PRIVATE key):
bash infra/k8s/scripts/flux-bootstrap.sh
```

The private key never leaves the machine and is never committed — `flux-bootstrap.sh`
loads it into the `flux-git-auth` Secret and that's it. Override the path with
`DEPLOY_KEY=/path/to/key bash …` if you keep it elsewhere.

`init-linux.sh` runs this as an optional step 6 — off by default (it needs the key
present), enabled with `--with-flux`:

```bash
bash infra/k8s/scripts/init-linux.sh --with-flux
```

### Verify the acceptance criteria (#30)

**Flux is healthy and watching:**

```bash
flux get sources git --namespace flux-system        # fmi-codes: Ready, latest revision
flux get kustomizations --namespace flux-system      # prod + staging: Ready, Applied revision
flux get images all --namespace flux-system          # both repos scanned, latest tag picked
```

**Auto-deploy to staging** — push a backend-only change, confirm only the backend
rolls in the staging namespace after the `flux-image-updates` bump auto-merges:

```bash
kubectl -n fmi-codes-staging get pods -l app.kubernetes.io/name=fmi-codes-backend -w
# backend pods roll to the new image; frontend pods keep their AGE (untouched)
kubectl -n fmi-codes-staging get deploy backend  -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
kubectl -n fmi-codes-staging get deploy frontend -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
```

**Manual promote to prod** — run the promote workflow, merge the PR it opens, confirm
prod moves to the same tag staging is running:

```bash
kubectl -n fmi-codes get deploy backend  -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
kubectl -n fmi-codes get deploy frontend -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
```

**Rollback** — revert the promote commit on main; Flux reconciles prod back to the
previous image automatically.

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
# Remove the Phase 6 GitOps layer first (so Flux stops re-applying the app tier):
kubectl -n flux-system delete -f flux/image-automation.yaml -f flux/source.yaml
flux uninstall --namespace flux-system --silent

# Remove the Phase 4 networking tier (Ingress, cert, issuer, headers ConfigMap,
# then the two controllers and their namespaces):
kubectl delete -k overlays/prod/ingress
helm -n ingress-nginx uninstall ingress-nginx
helm -n cert-manager uninstall cert-manager
kubectl delete namespace ingress-nginx cert-manager

# Remove the Phase 3 app tier (stateless — nothing to preserve). Delete the
# workloads by label rather than `-k overlays/prod`, since that overlay includes
# the namespace and would cascade-delete the Phase 2 stateful tier with it:
kubectl -n fmi-codes delete deployment,service -l app.kubernetes.io/name=fmi-codes-backend
kubectl -n fmi-codes delete deployment,service -l app.kubernetes.io/name=fmi-codes-frontend
kubectl -n fmi-codes delete configmap fmi-codes-backend-config
kubectl -n fmi-codes delete secret fmi-codes-app

# Remove just the Phase 2 stateful releases (keeps the cluster):
helm -n fmi-codes uninstall redis postgres
# Helm leaves PVCs behind on purpose so data isn't lost by accident — drop them
# explicitly to reclaim the storage and force a fresh schema init next deploy:
kubectl -n fmi-codes delete pvc -l app.kubernetes.io/instance=postgres
kubectl -n fmi-codes delete pvc -l app.kubernetes.io/instance=redis
# Delete the Secrets together with their PVCs — a Secret and the PVC whose DB was
# initialized with it are a matched pair (see "The PVC is the real source of truth"):
kubectl -n fmi-codes delete secret fmi-codes-db fmi-codes-redis

# Or nuke the whole cluster — k3s ships an uninstaller that removes the service
# and all cluster state:
/usr/local/bin/k3s-uninstall.sh
```

Manifests and Helm values for later phases land in this directory as each phase
is implemented.
