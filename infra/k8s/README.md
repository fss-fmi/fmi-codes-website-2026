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

The script generates strong random `SECRET_KEY` / `JWT_SECRET_KEY` on first
create and leaves `ADMIN_PASSWORD_HASH`, `MAIL_PASSWORD`,
`DISCORD_BUG_WEBHOOK_URL` empty. The backend runs `production` config, which
hard-fails at startup unless `ADMIN_PASSWORD_HASH` is set, so patch a real bcrypt
hash in before expecting the pods to go Ready:

```bash
HASH=$(python -c "import bcrypt;print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt(12)).decode())")
kubectl -n fmi-codes patch secret fmi-codes-app \
  -p "{\"data\":{\"ADMIN_PASSWORD_HASH\":\"$(printf '%s' "$HASH" | base64 -w0)\"}}"
kubectl -n fmi-codes rollout restart deployment/backend
```

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
| `ingress.yaml` | The `Ingress` (host `fmi-codes.local`, path rules below), its `tls:` block, the `security-headers` ConfigMap, and the cert-manager self-signed `ClusterIssuer` + `Certificate`. |
| `deploy-ingress.sh` | Idempotent deploy: `helm upgrade --install`s `ingress-nginx` and `cert-manager`, applies `ingress.yaml`, waits for the cert to be issued. |

```bash
# Cluster + stateful + app tiers must already be up (Phases 1–3). Then:
bash infra/k8s/deploy-ingress.sh
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

### TLS: self-signed via cert-manager

This is a LAN-only local cluster with no public DNS name, so there is no Let's
Encrypt/ACME. Instead `cert-manager` issues a **self-signed** cert: a
`ClusterIssuer` (`selfSigned: {}`) mints the `fmi-codes-tls` `Certificate` into a
`kubernetes.io/tls` Secret the Ingress references, and cert-manager auto-renews it
(`renewBefore: 720h`). Swapping to a real cert later is a one-issuer change — point
the `Certificate`'s `issuerRef` at an ACME `ClusterIssuer` and nothing else moves.

Because the cert is self-signed, clients must either trust the CA or skip
verification (`curl -k`). Browsers will show the usual self-signed warning.

### HTTP → HTTPS redirect

ingress-nginx's `ssl-redirect` defaults to `true` and fires automatically once an
Ingress rule has a TLS cert, so HTTP requests get a `308` to HTTPS with no extra
config. The Ingress sets `nginx.ingress.kubernetes.io/ssl-redirect: "true"`
explicitly for clarity.

### Resolve the host

The Ingress matches on `Host: fmi-codes.local`. Point that name at the ingress
controller's external address (the deploy script prints the exact line):

```bash
INGRESS_IP=$(kubectl -n ingress-nginx get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "$INGRESS_IP fmi-codes.local" | sudo tee -a /etc/hosts
```

### Verify the acceptance criteria (#29)

**Routing** — `/api/...` hits the backend, everything else the frontend:

```bash
curl -k https://fmi-codes.local/api/health   # backend JSON, HTTP 200
curl -k https://fmi-codes.local/             # the SPA's index.html
```

**Security headers present** on every response, including the backend routes that
shipped naked before:

```bash
curl -k -I https://fmi-codes.local/api/health
# expect: X-Frame-Options, X-Content-Type-Options, Content-Security-Policy,
#         Strict-Transport-Security, Referrer-Policy, Permissions-Policy
```

**HTTPS works and HTTP redirects to it:**

```bash
curl -I http://fmi-codes.local/              # HTTP/1.1 308, Location: https://fmi-codes.local/
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
# Remove the Phase 4 networking tier (Ingress, cert, issuer, headers ConfigMap,
# then the two controllers and their namespaces):
kubectl -n fmi-codes delete -f ingress.yaml
helm -n ingress-nginx uninstall ingress-nginx
helm -n cert-manager uninstall cert-manager
kubectl delete namespace ingress-nginx cert-manager

# Remove the Phase 3 app tier (stateless — nothing to preserve):
kubectl -n fmi-codes delete -f frontend.yaml -f backend.yaml
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
