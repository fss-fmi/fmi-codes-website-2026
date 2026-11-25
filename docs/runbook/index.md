# Kubernetes deployment (k3s)

The app runs on a self-hosted single-node **k3s** cluster. Staging and prod share the
node, isolated by namespace, built from one shared `base/` via Kustomize overlays.
Postgres and Redis come from Bitnami Helm charts; app secrets are SOPS-encrypted in git;
Flux does GitOps continuous deploy (auto to staging, manual promote to prod).

**Platform:** Debian/Ubuntu Linux, or WSL2 Ubuntu on a Windows dev box. Not macOS, not
native Windows (the scripts are apt + bash, k3s is Linux-native).

## Layout

```
infra/k8s/
  scripts/       init-linux, init-windows, install-tools, bootstrap-k3s,
                 deploy-stateful, deploy-app, deploy-ingress, deploy-observability,
                 flux-bootstrap, tailscale-oauth, apply-config, rotate-secret,
                 rotate-datastore-password, render-migrate-job, test-prometheus-rules
                 scripts/lib/ shared helpers the scripts source (slack-webhooks, flux-relay,
                 tailscale-client, sops-keys, rollout)
  base/          environment-agnostic manifests
                   base/app/     namespace, backend, frontend
                   base/ingress/ security-headers, ingress
                   base/observability/ kube-prometheus-stack, Grafana tailnet Ingress, ServiceMonitor (shared)
                   base/tailscale/     Tailscale operator (shared)
                   base/flux-relay/    replies "recovered" under Flux's Slack errors (shared, in flux-system)
  overlays/      per-env overlays layered on base
                   overlays/prod/     namespace fmi-codes, host fmicodes.com
                   overlays/prod/ingress/ prod's edge plus cloudflared, the Cloudflare Tunnel
                   overlays/staging/  namespace fmi-codes-staging, any host, no TLS (Tailscale holds it)
                   overlays/staging/tailnet/ staging's Tailscale Ingress (namespace ingress-nginx-staging)
  helm-values/   Bitnami postgresql + redis values (prod)
  secrets/       prod secrets, grafana-secret, alertmanager-slack, flux-relay-slack, cloudflared-tunnel,
                 mentors-seed .enc.yaml (SOPS);
                 staging's live in overlays/staging/secrets/, with the only tailscale-oauth
  flux/          Flux GitOps — source, image-automation, notifications, self
```

## Environments

|                    | prod                                                 | staging                                                                             |
| ------------------ | ---------------------------------------------------- | ----------------------------------------------------------------------------------- |
| namespace          | `fmi-codes`                                          | `fmi-codes-staging`                                                                 |
| URL                | `https://fmicodes.com` (public)                      | `https://staging.<tailnet>.ts.net` (tailnet only)                                   |
| DB / Redis FQDN    | `*.fmi-codes.svc`                                    | `*.fmi-codes-staging.svc`                                                           |
| DB name            | `fmi_hackathon_2026`                                 | `fmi_hackathon_2026_staging`                                                        |
| way in             | the Cloudflare Tunnel (`cloudflared` in `fmi-codes`) | the Tailscale proxy                                                                 |
| TLS                | Cloudflare's edge certificate (browser-trusted)      | the Tailscale proxy's certificate (browser-trusted)                                 |
| ingress controller | release `ingress-nginx`, class `nginx`, `ClusterIP`  | release `ingress-nginx-staging`, class `nginx-staging`, `ClusterIP` (no host ports) |
| `FRONTEND_ORIGIN`  | ConfigMap (`base/app/backend.yaml`)                  | SOPS app secret, so the tailnet name stays out of the repo                          |
| SOPS secret        | `secrets/secrets.enc.yaml`                           | `overlays/staging/secrets/secrets.enc.yaml` (separate age key)                      |
| deploy             | manual promote (human-merged PR)                     | auto on every push to `main`                                                        |

Everything else (probes, the frontend, feature-flag defaults, `FLASK_ENV`) is identical by
design: staging mirrors prod so it catches problems before prod does. The exceptions are
deliberate. Prod is sized for the registration rush: its backend runs 4 pods at 1 CPU
requested and up to 3 (`overlays/prod/backend-capacity-patch.yaml`; staging 2 pods at 100m
and 1, whole cores on both so staging gets prod's hash slots per core), its Postgres allows
250 connections (staging 150) and its ingress controller requests 500m CPU. Staging
multiplies every rate limit by 10 (`RATELIMIT_MULTIPLIER`). The two ingress controllers are
fully independent, so a staging deploy never touches prod's routing or headers. Staging's
Tailscale proxy forwards to the staging controller, not to the app, so staging still
exercises prod's `security-headers` and `/api` routing
([ADR-009](../adr/009-staging-over-tailscale.md)). Verify an overlay renders with
`kubectl kustomize infra/k8s/overlays/<env>`.

## TL;DR

From the repo root: `./bootstrap.sh` (staging) or `./bootstrap.sh --env prod`. It runs a
pre-flight (asks for the age key, the admin password and, with `--with-flux`, the Tailscale
OAuth client for Grafana and staging), then installs tools → k3s → Postgres/Redis → app → ingress, plus
Flux and the monitoring stack with `--with-flux`. Idempotent and resumable (`--from N`,
N = 1–7). Prod serves `fmicodes.com` only with `SERVE_PROD_TUNNEL=true`, which only the one
cluster that runs prod sets ([Move prod to another cluster](cloudflare.md#move-prod-to-another-cluster)).
Full walkthrough below.

## Set up on a brand-new machine — step by step

End-to-end, bare server → running cluster. Do it for staging first, then repeat with
`--env prod` for production (`SERVE_PROD_TUNNEL=true ./bootstrap.sh --env prod` on the server
that serves `fmicodes.com`).

### 0. Prerequisites

- A **Debian/Ubuntu** box (or WSL2 Ubuntu) with `sudo`, `git`, and `curl`. Nothing else —
  `install-tools.sh` fetches kubectl/helm/sops/age/flux.
- **The environment's age private key.** SOPS decrypts the committed app secrets with it.
  Two cases:
  - **Deploying the existing project** (normal case): get the private key from a teammate
    through a password manager, never chat or email. `./bootstrap.sh` asks for it at a hidden
    paste prompt. To skip the prompt, export `SOPS_AGE_KEY_STAGING` / `SOPS_AGE_KEY_PROD`
    first, without typing the key on the command line, so it stays out of shell history:
    ```bash
    read -rs SOPS_AGE_KEY_STAGING && export SOPS_AGE_KEY_STAGING   # paste the key, press Enter
    ./bootstrap.sh              # no paste prompt
    ```
    Don't keep the key in GitHub Actions secrets: no workflow reads it, and GitHub never
    shows a secret's value again, so it only adds a place for the key to leak from.
    If you run both environments from one machine, both keys live in the same `keys.txt`, in
    any order; there is nothing to comment out when switching.
  - **Forking to your own project:** you don't have the org's key, so mint your own and take
    over the recipient — see [Forking: use your own keys](secrets.md#forking-use-your-own-keys),
    do that once, then come back here.
- **A prod machine also needs the staging age key** when it runs with `--with-flux`: the
  Tailscale client is staging's on every cluster
  ([One Tailscale client for every cluster](tailscale.md#one-tailscale-client-for-every-cluster)).
- **Prod needs outbound internet only.** No public address, no open port, no router setup and
  no DNS change per server: prod is reached through the Cloudflare Tunnel that `cloudflared` in
  the cluster dials out to. The tunnel and its DNS record are made once, not per server
  ([Set up the tunnel](cloudflare.md#set-up-the-tunnel)). Staging needs no DNS or hosts entry: it is reached
  over the tailnet.
- **For staging, the `fss-fmi` tailnet** ([Tailscale setup](tailscale.md#tailscale-setup-once-per-tailnet))
  and `--with-flux`: Flux installs the Tailscale operator that serves staging. Without them
  staging is reachable only by `kubectl port-forward`.

### 1. Clone

```bash
git clone https://github.com/fss-fmi/fmi-codes-website-2026.git
cd fmi-codes-website-2026
```

### 2. Know what secrets exist and where they live

Nothing to create by hand — the passwords split three ways and every one is handled for you:

| Secret                                  | Keys                                                                                                                                                                                                                   | How it's set                                                                                                                                                                                                                                                                                                   |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fmi-codes-app` (SOPS, in git)          | `SECRET_KEY`, `JWT_SECRET_KEY`, `ADMIN_PASSWORD_HASH`, `MAIL_PASSWORD`, `DISCORD_BUG_WEBHOOK_URL`, `SLACK_BUG_WEBHOOK_URL`, `SLACK_MIGRATIONS_WEBHOOK_URL`, `SLACK_EVENTS_WEBHOOK_URL`; staging also `FRONTEND_ORIGIN` | committed encrypted; `deploy-app.sh` decrypts + applies with your age key. `SECRET_KEY`/`JWT_SECRET_KEY` already have strong committed values; `ADMIN_PASSWORD_HASH` you set in step 3. Staging's `FRONTEND_ORIGIN` is its tailnet URL ([Access Grafana and staging](tailscale.md#access-grafana-and-staging)) |
| `fmi-codes-db`, `fmi-codes-redis`       | DB / Redis passwords                                                                                                                                                                                                   | **generated in-cluster** by `deploy-stateful.sh` on first run; rotate with `rotate-datastore-password.sh`, never by hand                                                                                                                                                                                       |
| `grafana-admin` (SOPS, in git)          | `admin-user`, `admin-password`                                                                                                                                                                                         | committed encrypted; applied by `deploy-observability.sh` ([Phase 7](#7--observability-prometheus--grafana))                                                                                                                                                                                                   |
| `operator-oauth` (SOPS, in git)         | `client_id`, `client_secret` (Tailscale OAuth client)                                                                                                                                                                  | **staging's file only**, used by every cluster ([why](tailscale.md#one-tailscale-client-for-every-cluster)); the bootstrap pre-flight asks for it once the tailnet exists ([Tailscale setup](tailscale.md#tailscale-setup-once-per-tailnet)), then `deploy-observability.sh` applies it                        |
| `alertmanager-slack` (SOPS, in git)     | `cluster_url`, `staging_url` (the cluster-alerts incoming webhooks)                                                                                                                                                    | committed **empty**; `deploy-observability.sh` applies it anyway (Alertmanager can't start without it). Set them with `rotate-secret.sh --alertmanager cluster_url` / `staging_url` ([Cluster alerts](alerts.md#cluster-alerts))                                                                               |
| `flux-relay-slack` (SOPS, in git)       | `bot_token`, `cluster_channel`, `staging_channel` (the Flux Relay Slack app's token and the two channel IDs)                                                                                                           | committed **empty**; `deploy-observability.sh` applies it to `flux-system`. Until it's filled the relay idles and Flux errors get no "recovered" reply. Set them with `rotate-secret.sh --flux-relay <key>` ([Recovery replies](alerts.md#recovery-replies))                                                   |
| `cloudflared-tunnel` (SOPS, in git)     | `credentials.json` (the prod tunnel's credentials file)                                                                                                                                                                | **prod only**, committed encrypted; `deploy-ingress.sh` applies it only with `SERVE_PROD_TUNNEL=true`, on the one cluster that serves prod. Made once per tunnel ([Set up the tunnel](cloudflare.md#set-up-the-tunnel))                                                                                        |
| `fmi-codes-mentors-seed` (SOPS, in git) | `mentors.json` (the mentor roster: names, emails, phones, any starting passwords)                                                                                                                                      | committed encrypted, staging's with its 20 mentors and prod's as `[]` until the 2027 roster; `deploy-app.sh` applies it (even with Flux on) and the backend mounts it, seeding on start. Optional: without it the backend seeds no mentors ([Mentor seed](secrets.md#mentor-seed))                             |

So the only secret you actively decide on a fresh deploy is the **admin password** — and the
bootstrap pre-flight prompts you for it. `MAIL_PASSWORD` / `DISCORD_BUG_WEBHOOK_URL` /
`SLACK_BUG_WEBHOOK_URL` / `SLACK_MIGRATIONS_WEBHOOK_URL` / `SLACK_EVENTS_WEBHOOK_URL` are
optional; set them later with `rotate-secret.sh` (step 5) if you want password-reset mail, bug
reports in Discord or Slack, migration results in Slack, or the event feed (feature flag
changes, ranking submissions and matching) in Slack.

### 3. Run the bootstrap

`./bootstrap.sh` is the front door. It runs a pre-flight, then installs tools → k3s →
Postgres/Redis → app → ingress in order.

```bash
./bootstrap.sh                                     # staging (default)
./bootstrap.sh --env prod                          # production, off the internet
SERVE_PROD_TUNNEL=true ./bootstrap.sh --env prod   # production that serves fmicodes.com
```

The pre-flight first installs `sops` and `age` if they're missing (so it can verify keys on a
bare box), then handles three things:

1. **The age private key**: it test-decrypts every SOPS file of that env (`secrets.enc.yaml`,
   `grafana-secret.enc.yaml`, `alertmanager-slack.enc.yaml`, `flux-relay-slack.enc.yaml` and
   `mentors-seed.enc.yaml`, plus `tailscale-oauth.enc.yaml` on staging and `cloudflared-tunnel.enc.yaml` on prod) with `~/.config/sops/age/keys.txt` (or
   `$SOPS_AGE_KEY_FILE` if set). If that works it does nothing, whatever else is in the file
   and in whatever order. Otherwise it takes the key from `SOPS_AGE_KEY_STAGING` (or
   `SOPS_AGE_KEY_PROD`), falling back to a hidden paste prompt, verifies the key decrypts those
   files **before** writing anything, then **appends** it to `keys.txt` with a `# public key:`
   comment (`chmod 600`).
   Existing keys are never replaced or removed. A wrong key aborts with its public key next
   to the one the files are encrypted to, and leaves `keys.txt` untouched. To skip the prompt,
   export the key first as shown in [step 0](#0-prerequisites). A prod run with `--with-flux`
   then checks the **staging** key the same way (`SOPS_AGE_KEY_STAGING` or the prompt), because
   the Tailscale client is staging's on every cluster
   ([One Tailscale client for every cluster](tailscale.md#one-tailscale-client-for-every-cluster)).
2. **The admin password** — if `ADMIN_PASSWORD_HASH` is empty in the secrets file, it asks
   for a password (hidden, typed twice, at least 12 characters), bcrypt-hashes it, and writes
   the hash back into `secrets.enc.yaml` through stdin, so neither shows up in `ps`. Commit
   and push that file afterward so other servers get the same hash. (Skip it and the backend
   CrashLoops until you set one — fix later with `rotate-secret.sh ADMIN_PASSWORD_HASH`.)
3. **The Tailscale OAuth client** (only with `--with-flux`, which also deploys Grafana and the
   operator that serves staging): if staging's `tailscale-oauth.enc.yaml` is empty, it lists
   the admin-console steps for a new client and asks for its ID and secret (hidden, typed
   twice, checked for a swapped ID and secret). If the file already holds a client it asks
   whether this cluster is **taking over** from another one; answer yes on a new server and it
   walks you through the [handover](tailscale.md#move-grafana-and-staging-to-another-cluster) first. Enter
   skips it; Grafana and staging then stay off the tailnet until `tailscale-oauth.sh set`.

It's idempotent and resumable — if a step fails, fix the cause and re-run with `--from N`
(N = 1–7). Steps 1–2 need interactive sudo, so run it in a real terminal.

### 4. Point the host at the cluster

**Prod:** nothing per server. `fmicodes.com` points at the tunnel, not at a machine, so once its
DNS record exists ([Set up the tunnel](cloudflare.md#set-up-the-tunnel), step 4) whichever cluster runs the
tunnel serves it. Only one cluster may run it at a time
([Move prod to another cluster](cloudflare.md#move-prod-to-another-cluster)).

**Staging:** nothing to point. Once the operator runs, staging's Tailscale Ingress gets its
address, and every tailnet device can open it ([Access Grafana and staging](tailscale.md#access-grafana-and-staging)):

```bash
kubectl -n ingress-nginx-staging get ingress staging   # ADDRESS = https://staging.<tailnet>.ts.net
```

The first time, store that URL as staging's `FRONTEND_ORIGIN` so emailed links point at it
(`deploy-observability.sh` warns while it differs):

```bash
ENV=staging bash infra/k8s/scripts/rotate-secret.sh FRONTEND_ORIGIN   # paste https://staging.<tailnet>.ts.net
```

### 5. (Optional) Set mail / webhook secrets

```bash
bash infra/k8s/scripts/rotate-secret.sh MAIL_PASSWORD             # prompts (hidden, twice)
bash infra/k8s/scripts/rotate-secret.sh DISCORD_BUG_WEBHOOK_URL
bash infra/k8s/scripts/rotate-secret.sh SLACK_BUG_WEBHOOK_URL
bash infra/k8s/scripts/rotate-secret.sh SLACK_MIGRATIONS_WEBHOOK_URL
bash infra/k8s/scripts/rotate-secret.sh SLACK_EVENTS_WEBHOOK_URL   # #event-feed-staging / #event-feed-prod
```

Each prompts for the value, re-encrypts the one key, re-applies the secret, and restarts the
backend. `ENV=staging` (default) or `ENV=prod`. Commit the `.enc.yaml` afterward. Every secret
and how to rotate it: [Rotate a secret](secrets.md#rotate-a-secret).

The script only changes keys already in the file. If `SLACK_BUG_WEBHOOK_URL`,
`SLACK_MIGRATIONS_WEBHOOK_URL` or `SLACK_EVENTS_WEBHOOK_URL` is missing (files encrypted before
they were added), add it once with `sops <file>` first. Each environment's
`SLACK_EVENTS_WEBHOOK_URL` is a webhook for its own channel, so staging's test flips never land
in prod's feed.

### 6. (Optional) Enable GitOps auto-deploy — the Flux deploy key

Skip this for a one-shot deploy; do it if you want pushes to `main` to auto-deploy staging.
Flux commits image-tag bumps back to the repo, so it needs a **write-capable** SSH key. Use a
repo **deploy key** (repo-scoped, not tied to a personal account):

```bash
# a) Generate a keypair on the server (no passphrase — Flux reads it non-interactively):
ssh-keygen -t ed25519 -f ~/.ssh/fmi-codes-flux -N ""

# b) Add the PUBLIC key to the repo WITH write access:
#    GitHub → repo → Settings → Deploy keys → Add deploy key → paste the line below,
#    tick "Allow write access", save.
cat ~/.ssh/fmi-codes-flux.pub

# c) Bootstrap Flux (loads the PRIVATE key into the in-cluster flux-git-auth secret):
bash infra/k8s/scripts/flux-bootstrap.sh
```

The private key never leaves the server and is never committed. Override the path with
`DEPLOY_KEY=/path/to/key` if you keep it elsewhere. `init-linux.sh --with-flux` runs this as
step 6 automatically once the key file exists.

The staging bump PRs that Flux's commits turn into are opened by a GitHub App, which needs a
one-time setup: [GitHub bot app for automated PRs](../github-automation.md#github-bot-app-for-automated-prs).

### 7. Verify

```bash
kubectl -n fmi-codes-staging get pods                            # all Running/Ready
curl https://staging.<tailnet>.ts.net/api/health/ready           # from a tailnet device: {"db":"ok","redis":"ok"}
```

## The phases (reference)

The bootstrap runs these for you; this is what each does if you need to run one alone. Each
script refuses to run until the previous phase's resources exist, so ordering is enforced.
`ENV=staging` (default) or `ENV=prod` selects the target.

### 1 — Tools + cluster

```bash
bash infra/k8s/scripts/install-tools.sh    # kubectl, helm, k9s, sops, age, flux — pinned + checksum-verified
bash infra/k8s/scripts/bootstrap-k3s.sh    # k3s (Traefik disabled), wires kubeconfig, creates the namespace
```

Both are idempotent. Versions are pinned via `*_VERSION` env vars at the top of each script;
override to upgrade (e.g. `K3S_VERSION=v1.37.0+k3s1 bash …`). `install-tools.sh` downloads
each binary pinned and SHA256-verified — nothing is piped into a shell.

**Old images are removed after 7 days unused.** The kubelet's default image cleanup only starts
at 85% disk. On WSL2 that is 85% of a 1 TB virtual disk, so the Windows drive fills first and every
deployed version piles up. `bootstrap-k3s.sh` therefore writes a kubelet drop-in,
`/var/lib/rancher/k3s/agent/etc/kubelet.conf.d/50-image-gc.conf`, with
`imageMaximumGCAge: 168h` (override with `IMAGE_MAX_GC_AGE`). On an existing node a re-run
restarts k3s only when that file changed; pods keep running through it. Images used in the last
7 days stay on the node, so a rollback within that window starts without a pull; older ones are
pulled from Docker Hub again, which keeps every tag. The running image is never removed, and the
85% backstop stays in place. A k3s restart resets the 7-day count, so a node that restarts more
often than weekly never removes anything this way (tested on WSL2, which stops the distro whenever
no session is open). On such a node, prune by hand while the pods are up:
`sudo k3s crictl --timeout 60s rmi --prune`. Check what the kubelet loaded:

```bash
NODE=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
kubectl get --raw "/api/v1/nodes/$NODE/proxy/configz" | grep -o '"imageMaximumGCAge":"[^"]*"'
```

**WSL2: eth0 is held at MTU 1500.** In its default NAT networking mode,
WSL2 gives `eth0` the lowest MTU of any Windows network adapter, so once Tailscale (or another
VPN) is installed on Windows `eth0` boots at 1280. Flannel sizes every pod's network from `eth0`
when k3s starts (1280 − 50 = 1230). That is too small for the WireGuard packets of the Tailscale
proxy pods, so anything served over the tailnet (Grafana, staging) resolves and connects but hangs in the
TLS handshake. The signature: TCP connects (`Test-NetConnection <100.x address> -Port 443`
succeeds on Windows), `curl -v https://grafana.<tailnet>.ts.net` stalls in the TLS handshake,
and the proxy pod logs `TLS handshake error … EOF`. On WSL2, `bootstrap-k3s.sh` therefore writes a systemd drop-in,
`/etc/systemd/system/k3s.service.d/wsl-mtu.conf`, that sets `eth0` to 1500 on every k3s start
(override with `WSL_ETH0_MTU`). 1500 is right because WSL2's traffic leaves through the real
network card, not the Tailscale adapter. Native Linux (where `eth0` is already 1500) and WSL2 in
mirrored networking mode are left alone. Check it:

```bash
cat /sys/class/net/eth0/mtu                 # 1500 = fixed, 1280 = affected
cat /sys/class/net/cni0/mtu                 # 1450 = fixed, 1230 = pods still on the old MTU
grep MTU /run/flannel/subnet.env            # FLANNEL_MTU=1450 = fixed, 1230 = affected
```

A k3s restart keeps the pod network it already built, so a cluster that first started at 1280
stays at 1230 until that network is rebuilt; the script ends with a warning when it finds one. The
fix stops every pod, so the apps are down until they come back; data on the PVCs is kept:

```bash
sudo /usr/local/bin/k3s-killall.sh && sudo systemctl start k3s
```

`eth0` can also drop back to 1280 while the VM keeps running, which hangs tailnet TLS the same way
with `cni0` still at 1450. k3s doesn't restart then, so the drop-in doesn't rerun. `bootstrap-k3s.sh`
therefore also installs a `wsl-eth0-mtu` systemd service that starts just before k3s, stops with it,
checks `eth0` every 5 seconds, raises it if it is below 1500 and logs the old value. An existing
cluster gets the service by re-running the script, which doesn't restart k3s for it. Re-running in
mirrored mode removes it. With `cni0` at 1450 no pod network rebuild is needed:

```bash
systemctl is-active wsl-eth0-mtu             # active = watching; activating = it can't raise eth0, read the journal
journalctl -u wsl-eth0-mtu -n 20 --no-pager  # "eth0 MTU was … at service start" is a normal boot, "… while running" is a reset
```

**k3s installs as a systemd service, so it survives reboot** — on a real Linux host. Default
WSL2 has systemd off, so either enable it once (`/etc/wsl.conf` → `[boot]\nsystemd=true`,
then `wsl --shutdown`) or just re-run `bootstrap-k3s.sh` after each WSL relaunch (idempotent,
seconds). If bootstrap reports the API "did not come up", check `sudo journalctl -u k3s -e`:
a resetting uptime means k3s is crash-looping — common WSL2 causes are missing iptables
(`sudo apt-get install -y iptables`), stale state (`sudo /usr/local/bin/k3s-killall.sh &&
sudo rm -rf /var/lib/rancher/k3s`), or too little memory (raise it in `.wslconfig`).

### 2 — Stateful tier (Postgres + Redis Sentinel)

```bash
bash infra/k8s/scripts/deploy-stateful.sh   # ENV=prod|staging
```

`helm upgrade --install`s Bitnami Postgres (single primary, PVC) and Redis (3 nodes, 1 master
and 2 replicas, each with a Sentinel; master set `mymaster`, quorum 2). On first run it generates two
in-cluster Secrets with random passwords — `fmi-codes-db` and `fmi-codes-redis` — and the
charts consume them via `existingSecret`. Re-runs leave them untouched. `schema.sql` is
loaded into the `postgres-initdb` ConfigMap and run once by Postgres `initdb`.

Prod's Postgres runs with `max_connections = 250`, a 1-CPU request, no CPU limit and a 2Gi
memory limit (`helm-values/postgresql-values.yaml`); staging's with 150 and 1Gi. The
backend's pools have to fit: each Gunicorn worker keeps up to `DB_POOL_MAX` connections (8,
one per thread, in the backend ConfigMap), 4 workers a pod, and a rollout runs its surge pod
(`maxSurge: 1`) on top of the old ones while one old pod is still draining (its 10 s
`preStop` sleep, then up to 30 s of Gunicorn drain), plus the migrate initContainer, backups
and an operator. That is 202 on prod and 138 on staging, and
`tests/test_capacity_budget.py` fails when the pods outgrow `max_connections` or the pool
drops below the thread count. Under heavy load more old pods can drain at once (three is 266
on prod), so don't roll out prod during the registration rush
([Rollouts](../deployment.md#rollouts)). A change to these values reaches a running database
only by re-running this script, which restarts the Postgres pod for a few seconds, so do it
well before registration opens. The backend needs no restart after it: each checkout pings its
pooled connection and replaces the ones the restart killed (#277).

Both values files also set Postgres's TCP keepalives (30 s idle, 10 s probes, 3 probes) and
`tcp_user_timeout = 10000`, the same values the backend's connections use
(`CONNECT_OPTIONS` in `backend/app/database.py`, checked by `tests/test_connection_timeouts.py`).
Without them Postgres keeps a silently vanished client's session, and its locks, for about 2 h
(the OS default keepalive), so one backend pod lost mid-transaction would freeze every team
change. Like `max_connections`, they reach a running database only through this script. Check
the live values over TCP, `psql -h 127.0.0.1` as in
[Restore a migration backup](#restore-a-migration-backup): a Unix-socket session reads 0 for
all four whether the file is applied or not.
`SELECT name, setting FROM pg_settings WHERE name LIKE 'tcp_%' ORDER BY name` then returns
`tcp_keepalives_count` 3, `tcp_keepalives_idle` 30, `tcp_keepalives_interval` 10 and
`tcp_user_timeout` 10000; an unapplied file shows 9, 7200, 75 and 0. The server's
`tcp_user_timeout` also ends a session whose client stops reading for more than 10 s, so any
client that can stall that long sets `PGOPTIONS=-c tcp_user_timeout=0`: the migrate Job's
`pg_dump` does (gzip's writes to the volume can fall behind), and a `pg_dump`, `\copy` or big
`SELECT` you run by hand over TCP, a `kubectl port-forward` included, needs the same.

In-cluster addresses the app tier uses: `postgres.<ns>.svc.cluster.local:5432` and
`redis.<ns>.svc.cluster.local:26379`.

**The PVC is the real source of truth.** Two things bake into the Postgres PVC at first
boot and never change on a re-run: the schema and the DB password. So editing `schema.sql`
and re-running does _not_ migrate a running DB (schema changes reach it through the migration
runner, see [Database migrations](../deployment.md#database-migrations)), and **a Secret and its PVC are a matched pair** — delete one
without the other and you get `password authentication failed`. Always delete them together.
To change a password without wiping data, use
[`rotate-datastore-password.sh`](secrets.md#db-and-redis-passwords).

> Images pull from `docker.io/bitnamilegacy/*`, not `bitnami/*` — Bitnami archived the free
> tier in Aug 2025. Don't "correct" them back; the `bitnami/*` tags no longer resolve and
> pods `ErrImagePull`. `bitnamilegacy` is frozen (no patches) — migrating to maintained
> images is future work.

### 3 — App tier (backend + frontend)

```bash
bash infra/k8s/scripts/deploy-app.sh   # ENV=prod|staging
```

Two `Deployment`s behind `ClusterIP` Services (the frontend runs 2 replicas, the backend 2 on
staging and 4 on prod): `backend`
(`fssfmi/fmi-codes-backend`, :5001) and `frontend` (`fssfmi/fmi-codes-frontend`, :80). The
backend Service is named `backend` because the frontend image's `nginx.conf` proxies
`/api/` to `http://backend:5001` — the same image works under compose (where
the `app` service carries a `backend` alias) and k8s with no rebuild.

Config split: non-secret env comes from the `fmi-codes-backend-config` ConfigMap via
`envFrom`; passwords via `secretKeyRef` (`DB_PASSWORD`, `REDIS_PASSWORD` from Phase 2, and
`SECRET_KEY`/`JWT_SECRET_KEY`/`ADMIN_PASSWORD_HASH`/`MAIL_PASSWORD`/`DISCORD_BUG_WEBHOOK_URL`
and, optionally, `SLACK_BUG_WEBHOOK_URL` and `SLACK_EVENTS_WEBHOOK_URL` from `fmi-codes-app`; the `migrate` initContainer
reads `SLACK_MIGRATIONS_WEBHOOK_URL` from it, optionally). On staging, `FRONTEND_ORIGIN` comes
from `fmi-codes-app` too (`overlays/staging/backend-origin-patch.yaml`, optional, so a secret
without it never blocks a rollout; the backend then falls back to `http://localhost:5173` and
`deploy-app.sh` warns). `DATABASE_URL` is intentionally unset — the backend composes it from the
`DB_*` pieces. The mentor seed is a file, not env: the `fmi-codes-mentors-seed` Secret is
mounted read-only at `/etc/fmi-codes/mentors/` (optional, so a cluster without it still rolls
out and seeds no mentors) and `MENTORS_SEED_FILE` points at its `mentors.json`. Only the
backend container gets it, never the `migrate` initContainer. `deploy-app.sh` applies it right
after the app secret ([Mentor seed](secrets.md#mentor-seed)).

Health endpoints: `GET /api/health` (liveness, touches nothing) and `GET /api/health/ready`
(readiness — pooled `SELECT 1` + Redis ping; Postgres gates readiness, Redis is fail-open).
Both probes give a request 10 s, since under load a probe waits for a thread like any request.
Overload reaches every pod at once, so readiness drops a pod from the Service only after 12
misses (2 min) and liveness restarts it after 30 (5 min); Gunicorn's own 120 s worker timeout
replaces a single hung worker inside a pod
([ADR-016](../adr/016-shed-password-hashes.md)).

Password hashes are capped per pod: `HASH_SLOTS` comes from the container's CPU limit through
the downward API, one slot per core, so keep the limit whole cores (`test_capacity_budget.py`
fails otherwise). Past the cap a hash waits up to 2 s or gets a 429 `The server is busy`, and
`password_hash_shed_total{reason}` counts each one in Prometheus. Sheds mean the pods are out
of hashing CPU: during the rush they are expected at the peak, and a steady rate means the
backend needs more CPU (raise the limit and with it the slots, or add pods within the
connection budget above).

### 4 — Ingress

```bash
bash infra/k8s/scripts/deploy-ingress.sh   # ENV=prod|staging
```

`helm upgrade --install`s the env's ingress-nginx controller and applies the Ingress. Path
routing: `/api` → `backend:5001`, everything else → `frontend:80`. Security
headers live in the `security-headers` ConfigMap wired into the controller via `add-headers`,
so **every** response through the Ingress carries them.

Neither env's controller binds a host port: both are `ClusterIP` Services, and each env has
exactly one way in.

**Prod** is reached only through the Cloudflare Tunnel
([ADR-017](../adr/017-prod-through-cloudflare-tunnel.md)):

```
visitor → Cloudflare (TLS, https://fmicodes.com) → cloudflared (fmi-codes, 2 pods) → ingress-nginx-controller:80 (HTTP) → app
```

The script also applies `overlays/prod/ingress`, which holds `cloudflared`'s Deployment and its
routing config; Flux reconciles the same overlay as `fmi-codes-ingress`. Prod's controller
requests 500m CPU, so proxying keeps its share during the registration rush.

Serving `fmicodes.com` is opt-in (`SERVE_PROD_TUNNEL=true`, on the one cluster that runs
prod). What the flag does, the real-address checks after a deploy and how to reach prod
without the tunnel: [Serving the tunnel](cloudflare.md#serving-the-tunnel).

**Staging** has no certificate and no host ports either. Its controller is a
`ClusterIP` Service, and the script also applies `overlays/staging/tailnet`, a Tailscale Ingress
in `ingress-nginx-staging` whose backend is that controller on port 80:

```
device → Tailscale proxy (TLS, https://staging.<tailnet>.ts.net) → ingress-nginx-staging-controller:80 (HTTP) → app
```

The proxy terminates TLS and forwards plain HTTP with the `ts.net` Host header kept, so the
staging nginx Ingress matches any host, has no TLS block and turns `ssl-redirect` off (a
host-less rule sits in nginx's catch-all server, which has the default certificate, so the
redirect would loop). The controller sets `X-Forwarded-For` to its TCP peer, which on staging is
the Tailscale proxy, so every anonymous staging visitor shares one address bucket. That is why
staging sets `RATELIMIT_MULTIPLIER: "10"` in `overlays/staging/backend-config-patch.yaml`: every
limit is 10 times prod's (150 login attempts per account a minute, anonymous default 30000/min).
To test prod's exact limits, set it to `"1"` there and merge it (Flux reverts a live patch, so
`apply-config.sh` refuses one), then put it back. A staging rate-limit test still says nothing
about how prod buckets real clients. Flux reconciles the
tailnet Ingress as `fmi-codes-staging-tailnet`. The address appears once the operator runs
([Phase 7](#7--observability-prometheus--grafana)); until then, or without Tailscale:

```bash
kubectl -n ingress-nginx-staging port-forward svc/ingress-nginx-staging-controller 8080:80
curl http://127.0.0.1:8080/api/health
```

### 5 — Secrets (SOPS + age)

App secrets are SOPS-encrypted in git with one age key per environment; DB and Redis passwords
are generated in-cluster (Phase 2) and never touch git. `deploy-app.sh` decrypts and applies
`fmi-codes-app` when your key can read the file. How SOPS is set up here, every rotation and
forking with your own keys: [Secrets](secrets.md).

### 6 — GitOps continuous deploy (Flux, opt-in)

The cluster lives on a server GitHub's runners can't reach, so deploy is **pull-based**: Flux
runs inside the cluster, watches the registry and git, and reconciles. Push to `main` →
`docker-cd.yaml` builds `fssfmi/fmi-codes-{backend,frontend}:<ts>-<sha>` → Flux auto-bumps
the **staging** overlay → staging redeploys. **Prod** has no ImagePolicy — its tag only moves
when the `promote-to-prod` workflow opens a PR and a human merges it. That human merge is the
production gate; a `git revert` of a promote commit is a rollback.

One-time setup is the SSH deploy key (Flux commits tag bumps back, so it needs write access)
plus `flux-bootstrap.sh` — see [step 6 of the setup guide](#6-optional-enable-gitops-auto-deploy--the-flux-deploy-key).
Once bootstrapped, Flux owns the app Deployments in both namespaces; `deploy-app.sh` detects
this and skips re-applying them (no tug-of-war over the image tag). The `flux/` directory is
itself GitOps-managed: edits to `source.yaml`, `image-automation.yaml` and
`notifications.yaml` self-reconcile within 5m; editing `self.yaml` needs a `flux-bootstrap.sh`
re-run (or `kubectl apply -f infra/k8s/flux/self.yaml`).

Between commits Flux only asks GitHub whether `main` moved; each new commit costs a full
depth-1 clone, for the source and again for image automation. `source.yaml` gives both 5
minutes. If they still fail with `unable to clone ... context deadline exceeded`, the link is
slower than that clone, and raising `timeout` in git alone won't fix it: Flux has to clone the
commit that raises the timeout using the old one. Merge the new `timeout` in `source.yaml`
first, then get that commit through by hand:

```bash
kubectl -n flux-system patch gitrepository fmi-codes --type merge -p '{"spec":{"timeout":"<new value>"}}'
flux reconcile source git fmi-codes
```

`flux-system-config` then applies `source.yaml` from that commit, so the git value takes over
within 5 minutes and stays. A patch made before the merge doesn't last: `flux-system-config`
puts the old value back, and the merge commit is a new clone that times out again, so patch
once more after it lands.

Each new tag is also an image pull on the node. A new pod still pulling after 10 minutes (the
Deployment's default `progressDeadlineSeconds`) marks the Deployment
`ProgressDeadlineExceeded`, and the env's Kustomization fails its health check with
`stalled resources: [Deployment/<namespace>/<name> status: 'Failed']`. The old pods keep
serving; once the pull finishes the rollout completes and the Kustomization turns Ready on its
next retry. The pull time shows which case it is:

```bash
kubectl -n fmi-codes-staging get events --sort-by=.lastTimestamp | grep -E 'Pulling|Pulled'
```

A deploy should pull only the layer holding the changed app files. Both Dockerfiles copy with
`COPY --chown`, because a `chown -R` after a `COPY` stores every file a second time, and each
image has its own build cache scope, because a shared one makes the builds overwrite each
other's cache and the backend reinstalls its dependencies into a new layer every time.
`tests/test_docker_images.py` checks both.

> `docker-cd.yaml` ignores `infra/**` on purpose: a bump commit is a push to `main`, and
> without the guard it would re-fire the build, mint a newer tag, and loop forever. The
> constraint this creates: build inputs (Dockerfiles, build scripts) must stay OUT of
> `infra/`. Today they're in `./backend` and `./frontend` — keep them there.

**A release reaches staging whole or not at all.** `docker-cd.yaml` pushes the backend image
about a minute before the frontend, both with the same tag, and Flux scans each image
repository every 5 minutes on its own timer. A scan in that gap commits a bump of the backend
alone to `flux-image-updates`. `flux-auto-pr.yaml` therefore runs a gate
(`.github/scripts/flux_bump_gate.py`) that reads the live branch and compares every
`$imagepolicy` tag in the staging overlay:

| Branch tags | What the gate does                                                                                                                  |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| differ      | Opens nothing, turns auto-merge off on an open bump PR, logs a notice that it is waiting for the other image. The run still passes. |
| all match   | Opens the PR (or reuses the open one), titles it `deploy: bump <old> -> <new>` from the tags, enables auto-merge.                   |
| match main  | Nothing to bump; opens nothing.                                                                                                     |

The next scan bumps the second image, and that push's run opens or re-arms the PR. Runs share
a concurrency group that never cancels a run in progress; each reads the live branch rather
than the commit that started it, so the last run decides and an older one can't undo it. The
gate only touches a PR from this repo's own `flux-image-updates` branch: `gh pr list --head`
matches the branch name alone, so a fork's PR from a branch of the same name is skipped.

**Known gap (accepted 2026-11-09): a failed gate run can let a half bump merge.** The gate
protects `main` only when it runs. It takes three things at once: a bump PR is already open
with auto-merge on (the previous release's CI hasn't finished), Flux pushes a half bump of the
next release onto it, and that push's **Open PR for Flux image bump** run fails (a GitHub or
bot token outage). Auto-merge then stays on, and the half bump merges once CI passes. Staging
runs a mixed pair until the next scan bumps the second image a few minutes later, and a
promote in that window would send the mixed pair to prod. When the CI alert reports a failed
gate run, check the open bump PR's tags; if they differ, turn auto-merge off by hand until the
next scan completes the release:
`gh pr merge <number> --repo fss-fmi/fmi-codes-website-2026 --disable-auto`. Not closed in
code on purpose: a required CI check that fails mismatched bump PRs would block it, but would
also post a CI failure alert on every split release, which happens far more often than this.

If no bump PR opens within about 10 minutes of a merge that builds images (anything outside
`infra/**` and the docs) and the last **Open PR for Flux image bump** run logged
`holds part of a release`, the second image of that release was
never pushed, almost always a failed frontend build in **Build and Push Docker Image** (the
CI alert names it). That release does not deploy. Fix the build or run it again (**Actions →
Build and Push Docker Image → Run workflow**): every run builds both images under a new tag,
which Flux picks up as one whole release.

### 7 — Observability (Prometheus + Grafana)

Metrics, dashboards and alerts for both environments, fully self-hosted: the
`kube-prometheus-stack` Helm chart (Prometheus operator, Grafana, Alertmanager, node-exporter,
kube-state-metrics) runs in its own `monitoring` namespace, and the backend's `/metrics` endpoint
feeds request, latency, 5xx, 429, hash-shedding and mail series alongside the cluster resource
metrics.
Alertmanager posts cluster failures to Slack
([Cluster alerts](alerts.md#cluster-alerts)). The one outside service besides Slack is
[Tailscale](https://tailscale.com), which is how people reach Grafana and staging (see
[Access Grafana and staging](tailscale.md#access-grafana-and-staging)).
The reasoning is in [ADR-008](../adr/008-grafana-over-tailscale.md),
[ADR-009](../adr/009-staging-over-tailscale.md) and [ADR-010](../adr/010-cluster-alerts-to-slack.md).

**GitOps-managed by Flux, independent of the app envs.** Three Kustomizations in
`flux/source.yaml`, none of which depends on an app env, so a cluster with only staging
bootstrapped gets the whole stack:

| Kustomization             | Path                          | What it installs                                           |
| ------------------------- | ----------------------------- | ---------------------------------------------------------- |
| `fmi-codes-observability` | `base/observability`          | the `kps` HelmRelease and Grafana's tailnet Ingress        |
| `fmi-codes-monitors`      | `base/observability/monitors` | the backend ServiceMonitor (waits for the chart's CRDs)    |
| `fmi-codes-tailscale`     | `base/tailscale`              | the Tailscale operator HelmRelease (namespace `tailscale`) |

A values change merged to `main` rolls out with no script run. Staging's tailnet Ingress has
its own Kustomization, `fmi-codes-staging-tailnet` ([Phase 4](#4--ingress)); it uses the
same operator.

**One-time bootstrap: the secrets.** Flux never decrypts SOPS, so one script applies the
Grafana admin secret, the Alertmanager webhook secret, the Flux Relay's Slack secret (to
`flux-system`, skipped with a warning while Flux isn't installed) and the Tailscale OAuth
secret, and copies the webhooks to `flux-system` for Flux. `bootstrap.sh --with-flux` runs it as
step 7 (opt out with `--without-observability`, which also leaves staging without a tailnet
address, since the operator never gets its client); by hand:

```bash
ENV=staging bash infra/k8s/scripts/deploy-observability.sh   # ENV=prod on a cluster that runs prod
```

After applying the OAuth secret it waits up to 10 minutes (`TS_WAIT_SECONDS`) for the tailnet
addresses of Grafana and, on a cluster that runs staging, of staging. It warns if one has none
yet, or if an address starts with `grafana-1` or `staging-1`: that means another cluster still
holds the name, and the [handover](tailscale.md#move-grafana-and-staging-to-another-cluster) was skipped.
It also warns when staging's `FRONTEND_ORIGIN` (in the live app secret) is not staging's
address, and prints the `rotate-secret.sh` command that fixes it. None of this stops the script.

These Secrets are cluster-wide (one monitoring stack, one operator, one Flux). Grafana's, the
Slack webhooks and the Flux Relay's have an encrypted copy per env (`grafana-secret.enc.yaml`,
`alertmanager-slack.enc.yaml`, `flux-relay-slack.enc.yaml`) under its age key. Pick
the env the cluster belongs to: `prod` on the server, `staging` on a staging-only dev box. The
script labels each Secret with that env and refuses to overwrite it with the other env's copy
later (`ALLOW_ENV_SWITCH=true` switches on purpose, as when a staging-only box gets prod too:
[Adding prod to a staging-only box](alerts.md#adding-prod-to-a-staging-only-box)). The Tailscale client is the exception:
there is only staging's `tailscale-oauth.enc.yaml`, applied with the `staging` label whatever
`ENV` is ([One Tailscale client for every cluster](tailscale.md#one-tailscale-client-for-every-cluster)).
While it still holds empty values the script skips it with a warning and the operator sits
idle; fill it in once the tailnet exists ([Tailscale setup](tailscale.md#tailscale-setup-once-per-tailnet),
step 6). An
empty `alertmanager-slack.enc.yaml` is still applied, because the Alertmanager pod mounts it
and can't start without it; only the copy for Flux is skipped, with a warning. An empty
`flux-relay-slack.enc.yaml` is applied too, with a warning naming the empty keys. If
`flux-bootstrap.sh` has not been run yet, apply the Flux objects once first:
`kubectl apply -f infra/k8s/flux/source.yaml`.

One stack scrapes **both** app namespaces. Monitoring is independent of the app tier, but an
app must be running for the ServiceMonitor to have a scrape target.

|                                    | value                                   | why                                                                          |
| ---------------------------------- | --------------------------------------- | ---------------------------------------------------------------------------- |
| namespace                          | `monitoring`                            | kube-prometheus-stack convention; single shared stack                        |
| scrapes                            | `fmi-codes` **and** `fmi-codes-staging` | one ServiceMonitor, `namespaceSelector.matchNames` lists both                |
| retention                          | `14d`                                   | two weeks of history, enough to see a slow trend like a leak                 |
| Prometheus PVC                     | 5Gi                                     | the TSDB survives restarts and `wsl --shutdown`                              |
| Grafana PVC                        | 1Gi                                     | dashboards, users and sessions survive restarts                              |
| alertmanager                       | **on**                                  | posts cluster failures to Slack ([Cluster alerts](alerts.md#cluster-alerts)) |
| node-exporter + kube-state-metrics | **on**                                  | they produce the node/pod resource series — the whole point                  |

Resource requests+limits are set on every component (see `base/observability/helmrelease.yaml`
`spec.values`) to bound the stack's footprint — it adds roughly 600–900Mi to the node, so the
limits are the guardrail on a single box already running the app+stateful tiers.

What posts to Slack, the routing per channel, silences and the tests: [Cluster alerts](alerts.md).
Reaching Grafana and staging, the tailnet setup and moving them to another cluster:
[Tailscale](tailscale.md).

#### Dashboards and checks

**App-only dashboards:** Grafana → Dashboards → **FMI Codes** folder → **FMI Production** or
**FMI Staging**. Each shows, for its namespace: request rate, request duration (p50/p95/p99),
the share of requests answered with a 5xx (what `BackendHighErrorRate` alerts on, plus a
2-minute line), 429s by route, register and login p95, password hash sheds, backend CPU per
pod against its limit and how throttled it is, backend pods ready and restarted, emails by
kind and result plus the node's CPU. The namespace is hardcoded, so there is no shared
dropdown or data mixing between envs. They are the screen for the registration rush
([Event day](event-day.md#during)). They are provisioned
from `grafana.dashboards` in the Helm values on every chart reconcile, so there is nothing to
import. On a staging-only cluster **FMI Production** is simply empty.

**The memory-per-pod leak graph:** Grafana → Dashboards → **"Kubernetes / Compute Resources /
Pod"**, filter `namespace=fmi-codes-staging`, `pod=~backend.*`, the memory panel, set the range
to 7d. A steadily climbing line that never plateaus is the leak signature.

**Check scrape targets** (confirm the backend is actually being scraped):

```bash
kubectl -n monitoring port-forward svc/kps-prometheus 9090:9090
# http://localhost:9090 -> Status -> Targets -> the fmi-codes-backend target is UP
```

> **The app `/metrics` gotcha.** The exporter registers `/metrics` at the backend ROOT, but the
> ingress routes `/`→frontend and only `/api`→backend. So `/metrics` through the
> **public ingress** hits the frontend, not the backend — and that's FINE. Prometheus scrapes
> **in-cluster** via the ServiceMonitor at `backend.<ns>.svc:5001/metrics`, never through the
> ingress. Do **not** "fix" this by adding an ingress route — it would expose app metrics
> publicly for zero benefit.

**Counters are per pod, not per worker.** Gunicorn's 4 workers write their metrics to shared
files in `PROMETHEUS_MULTIPROC_DIR` (set by `backend/gunicorn.conf.py`, an in-memory `emptyDir`
in `base/app/backend.yaml`), and whichever worker answers a scrape sums them all. So each pod
has one series per label set, and a counter only goes down when the pod or its container
restarts (the folder is emptied when Gunicorn starts). A worker that dies keeps its counts in
the total. Three consequences:

- The Python process series (`process_*`, `python_*`) are not exported. Memory per pod comes
  from cAdvisor, which doesn't need them.
- `/api/health` and `/api/health/ready` are not counted, so the kubelet's probes don't swamp
  the request rate or dilute the 5xx share.
- The latency histogram is labelled by Flask route (`url_rule`, like
  `/api/teams/<int:team_id>`), not the raw path, and every unknown URL shares
  `url_rule="None"`. The shared files never drop a series, so raw paths from a scanner would
  grow them until the 64Mi volume filled and the pod was evicted.

To check it: `resets(flask_http_request_total[30m])` in Prometheus is 0 for every backend pod
that wasn't restarted in that window.

**Rotate the Grafana admin password:** `bash infra/k8s/scripts/rotate-secret.sh --grafana
admin-password` (details and why it also resets Grafana's database in
[Grafana admin password](secrets.md#grafana-admin-password)). The Tailscale OAuth client:
[Tailscale OAuth client](secrets.md#tailscale-oauth-client).

Object names start with `kps`: `fullnameOverride: kps` names the chart's own objects
(`kps-operator`, `kps-prometheus`), and the HelmRelease's `releaseName: kps` names the
subcharts' (`kps-grafana`, `kps-kube-state-metrics`). Without `releaseName`, Flux would call the
release `monitoring-kps` and Grafana would become `monitoring-kps-grafana`. If you change
either, check `kubectl -n monitoring get deploy,svc`, then pass
`RESTART_TARGET=deployment/<name>` to `rotate-secret.sh --grafana` and update the Service name in
`base/observability/grafana-ingress.yaml`.

`install.remediation.retries: -1` keeps Flux retrying a failed first install. On a fresh cluster
Flux usually installs the chart before `deploy-observability.sh` has applied `grafana-admin`, so
the first attempt times out waiting for Grafana; it succeeds on a later retry once the Secret
exists.

## Forking to your own infra

To deploy this under your own project (your Docker Hub, your domain, your keys), change:

- **age keys**: mint your own and re-encrypt, per [Forking: use your own keys](secrets.md#forking-use-your-own-keys).
- **Mentors**: the committed seeds hold this project's mentors under its keys, so write your
  own roster into both `mentors-seed.enc.yaml` files ([Mentor seed](secrets.md#mentor-seed)).
- **Image registry**: the `fssfmi/fmi-codes-{backend,frontend}` names in `base/app/*.yaml`,
  `overlays/*/kustomization.yaml`, `.github/workflows/docker-cd.yaml`, and
  `flux/image-automation.yaml`; set the `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` repo secrets.
- **Hostnames**: `fmicodes.com` in `base/ingress/ingress.yaml`,
  `overlays/prod/ingress/cloudflared-config.yaml` and `FRONTEND_ORIGIN` in
  `base/app/backend.yaml`. Staging takes its name from your tailnet: set `FRONTEND_ORIGIN` in
  staging's `secrets.enc.yaml` to your `https://staging.<tailnet>.ts.net`.
- **Cloudflare Tunnel**: your own zone and tunnel, with its ID in `cloudflared-config.yaml`
  and its credentials in `secrets/cloudflared-tunnel.enc.yaml`, per
  [Set up the tunnel](cloudflare.md#set-up-the-tunnel).
- **Flux git URL / deploy key**: `flux-bootstrap.sh` defaults to
  `ssh://git@github.com/fss-fmi/fmi-codes-website-2026.git`; override with
  `GIT_URL=… bash …` and add your own deploy key (step 6).
- **Bot app**: create your own and set `BOT_APP_CLIENT_ID` / `BOT_APP_PRIVATE_KEY`, per
  [GitHub bot app for automated PRs](../github-automation.md#github-bot-app-for-automated-prs).
- **Slack PR feed and CI alerts**: set `SLACK_BOT_TOKEN`, `SLACK_PR_CHANNEL_ID` and
  `SLACK_ACTIONS_CHANNEL_ID` for your own workspace, per [Slack PR feed](../github-automation.md#slack-pr-feed) and
  [Slack CI alerts](../github-automation.md#slack-ci-alerts), or leave them unset and both workflows skip.
- **Cluster alerts**: your own prod and staging channel webhooks in both envs' files, per
  [Cluster alerts](alerts.md#cluster-alerts). With both keys left empty, alerts are evaluated but
  nothing is posted; don't set only one.

## Change a config value

Non-secret backend setting (`REQUIRE_EMAIL_VERIFICATION`, `FRONTEND_ORIGIN`, DB/Redis
coordinates) in the `fmi-codes-backend-config` ConfigMap. The value lives in git. Prod's
values are `infra/k8s/base/app/backend.yaml`, and staging inherits each of them unless
`infra/k8s/overlays/staging/backend-config-patch.yaml` sets the key. So:

- **Staging only:** set the key in staging's patch (add it if it isn't there).
- **Prod only:** set it in the base. If staging's patch doesn't set that key, add staging's
  current value there too, or staging changes with prod.

Staging's `FRONTEND_ORIGIN` is in its SOPS app secret, so the script refuses it for staging
(use `rotate-secret.sh FRONTEND_ORIGIN`).

**With Flux** (both envs once `--with-flux` ran), Flux applies git every 5 minutes and puts
back any live change, so a change goes through git:

1. Edit the YAML, open a PR and merge it.
2. Apply `main` now and restart the backend, which reads the ConfigMap only at startup (if
   `main` also changed the backend's pod template, an image bump for example, Flux is rolling
   it already and the script only waits):

   ```bash
   ENV=prod bash infra/k8s/scripts/apply-config.sh
   ```

`apply-config.sh <KEY> <VALUE>` refuses on a Flux cluster and names the file to edit. For a
change that can't wait for the merge (SMTP breaks and `REQUIRE_EMAIL_VERIFICATION` has to go
off now), suspend Flux for that env first; then the patch holds:

```bash
flux suspend kustomization fmi-codes -n flux-system     # fmi-codes-staging for staging
ENV=prod bash infra/k8s/scripts/apply-config.sh REQUIRE_EMAIL_VERIFICATION false
# merge the same change to main, then:
flux resume kustomization fmi-codes -n flux-system
```

While suspended, Flux deploys nothing to that env, image bumps included. Resuming applies
`main`, so resume only after the merge: before it, the ConfigMap goes back to the old value,
and the backend's next restart, whatever causes it, quietly picks that up.

**Without Flux**, `apply-config.sh <KEY> <VALUE>` patches the live ConfigMap and restarts
the backend; commit the same change to the YAML afterwards. With no arguments it re-applies
the overlay from disk and restarts.

Registration, preference submission, rankings and the mentor roster are not config: the admin switches or schedules
them in Mission Control (**SITE** tab), and the script refuses `REGISTRATION_OPEN`,
`RANKINGS_LIVE` and `MENTORS_STAY_TUNED` ([Deployment](../deployment.md#feature-flags-during-the-event)).
Secrets are refused too (use `rotate-secret.sh` / `rotate-datastore-password.sh`). Staging is
the default; pass `ENV=prod` for prod and `RESTART=false` to batch several changes into one
restart.

**Restarting by hand.** On every apply Flux drops whatever a `kubectl*` field manager owns,
so a plain `kubectl rollout restart` of a Flux-applied Deployment loses its restart annotation
within 5 minutes and rolls a second time. The scripts restart under their own field manager,
which Flux leaves alone; do the same:

```bash
kubectl -n fmi-codes rollout restart deployment/backend --field-manager=fmi-codes-scripts
```

## Restore a migration backup

The manual **Migrate database** Job writes `pg_dump` files to the `db-migration-backups` PVC
in the target namespace (last 5 kept, named `<namespace>-<UTC time>-run<N>.sql.gz`). To
list them and restore one, mount the PVC in a throwaway pod:

```bash
NS=fmi-codes   # or fmi-codes-staging
kubectl -n $NS run restore --rm -it --image=postgres:16.4 \
  --overrides='{"spec":{"volumes":[{"name":"b","persistentVolumeClaim":{"claimName":"db-migration-backups"}}],"containers":[{"name":"restore","image":"postgres:16.4","stdin":true,"tty":true,"command":["bash"],"volumeMounts":[{"name":"b","mountPath":"/backups"}]}]}}'
# inside the pod:
ls -l /backups
```

A dump is plain SQL for the whole database, so restore into an empty database: scale the
backend to 0, drop and recreate the database (or restore into a new one and repoint
`DB_NAME`), then `zcat /backups/<file>.sql.gz | psql -h postgres -U fmi_app -d <db>`.
Rehearse on staging first.

The runner and the Job connect as `fmi_app`, which works because `fmi_app` owns the tables.
Confirm that on a live database with
`{ kubectl -n $NS get secret fmi-codes-db -o jsonpath='{.data.password}' | base64 -d; echo; } | kubectl -n $NS exec -i postgres-0 -- sh -c 'IFS= read -r PGPASSWORD; export PGPASSWORD; exec psql -h 127.0.0.1 -U fmi_app -d <db> -c "\dt"'`
(the Owner column). psql gets no password unless it is passed one (`fe_sendauth: no password supplied`),
and the pod's `POSTGRES_PASSWORD` goes stale after `rotate-datastore-password.sh db`, so the current
one comes from the Secret as the first line of stdin.

## Verify a running deployment

```bash
kubectl -n fmi-codes get pods                                  # 4 backend, 2 frontend, 2 cloudflared, Postgres, Redis
kubectl -n fmi-codes get deployment cloudflared                # READY 2/2: the tunnel is connected
curl https://fmicodes.com/api/health                           # backend 200, through Cloudflare
curl https://staging.<tailnet>.ts.net/api/health/ready         # from a tailnet device: {"db":"ok","redis":"ok"}
flux get kustomizations -n flux-system                         # prod + staging Ready (if Flux is up)
```

Staging's edge should match prod's: the response headers of
`curl -sI https://staging.<tailnet>.ts.net/api/health` and `curl -sI https://fmicodes.com/api/health`
carry the same `security-headers` set (CSP, HSTS, `X-Frame-Options` and the rest).

Two invariants are the whole reason the staging/prod split exists — check both after any
change:

- **The gate holds** — a push to `main` moves staging but **never** prod. Record prod's
  backend image tag, push, and confirm prod's tag is unchanged. It holds structurally: the
  prod overlay has no `$imagepolicy` markers, so Flux has nothing to write into.
- **The DBs are isolated** — a row written to the staging DB is absent from prod. They're
  separate StatefulSets, PVCs, and secrets in separate namespaces.

Read a datastore password back with:

```bash
kubectl -n fmi-codes get secret fmi-codes-db -o jsonpath='{.data.password}' | base64 -d; echo
```

## k9s

[k9s](https://k9scli.io/) is a terminal UI for the cluster (reads the same `~/.kube/config`):

```bash
k9s -n fmi-codes
```

`:pods` / `:svc` / `:ns` switch views, `l` tails logs, `s` shells in, `d` describes, `:q` quits.

## Tear down

Run from `infra/k8s/` (the `-f` and `-k` paths below are relative to it):

```bash
# Phase 6 — GitOps (delete self.yaml first so it stops reconciling flux/; prune:false means
# the automation objects don't cascade-delete, so remove them explicitly). The Slack alerts
# go first, so the teardown doesn't post its own errors. Deleting source.yaml prunes the Flux
# Relay (its Kustomization has prune: true); `flux uninstall` removes the flux-slack and
# flux-relay-slack Secrets and the relay's state ConfigMap with the namespace:
kubectl -n flux-system delete -f flux/notifications.yaml
kubectl -n flux-system delete -f flux/self.yaml
kubectl -n flux-system delete -f flux/image-automation.yaml -f flux/source.yaml
flux uninstall --namespace flux-system --silent

# Phase 7 — observability (suspend the Flux kustomizations first so Flux stops
# reconciling, then let Helm uninstall clean up; deleting the ns cascades the PVCs).
# Delete the tailnet Ingresses while the operator still runs, so it removes the proxies'
# tailnet devices; anything left over goes from the admin console's Machines page.
flux suspend kustomization fmi-codes-monitors -n flux-system
flux suspend kustomization fmi-codes-observability -n flux-system
flux suspend kustomization fmi-codes-staging-tailnet -n flux-system
flux suspend kustomization fmi-codes-tailscale -n flux-system
kubectl -n monitoring delete ingress grafana --wait
kubectl -n ingress-nginx-staging delete ingress staging --wait --ignore-not-found
helm -n monitoring uninstall kps
helm -n tailscale uninstall tailscale-operator
kubectl delete namespace monitoring tailscale

# Phase 4 — networking (prod's overlay includes cloudflared; its Secret goes with it, so this
# cluster stops serving the tunnel):
kubectl delete -k overlays/prod/ingress; kubectl delete -k overlays/staging/ingress
kubectl -n fmi-codes delete secret cloudflared-tunnel --ignore-not-found
helm -n ingress-nginx uninstall ingress-nginx
helm -n ingress-nginx-staging uninstall ingress-nginx-staging
kubectl delete namespace ingress-nginx ingress-nginx-staging
# Clusters bootstrapped before the tunnel also have cert-manager:
helm -n cert-manager uninstall cert-manager && kubectl delete namespace cert-manager

# Phase 3 — app tier (delete by label, NOT -k overlays/prod — that includes the namespace
# and would cascade into the stateful tier):
kubectl -n fmi-codes delete deployment,service -l app.kubernetes.io/name=fmi-codes-backend
kubectl -n fmi-codes delete deployment,service -l app.kubernetes.io/name=fmi-codes-frontend
kubectl -n fmi-codes delete configmap fmi-codes-backend-config
kubectl -n fmi-codes delete secret fmi-codes-app

# Phase 2 — stateful (delete each Secret together with its PVC — matched pair):
helm -n fmi-codes uninstall redis postgres
kubectl -n fmi-codes delete pvc -l app.kubernetes.io/instance=postgres
kubectl -n fmi-codes delete pvc -l app.kubernetes.io/instance=redis
kubectl -n fmi-codes delete secret fmi-codes-db fmi-codes-redis

# Or nuke the whole cluster (on WSL2 also remove the eth0 MTU drop-in and watcher, which the
# uninstaller leaves behind):
/usr/local/bin/k3s-uninstall.sh
sudo systemctl disable --now wsl-eth0-mtu 2>/dev/null || true
sudo rm -f /etc/systemd/system/k3s.service.d/wsl-mtu.conf /etc/systemd/system/wsl-eth0-mtu.service /usr/local/sbin/wsl-eth0-mtu
sudo systemctl daemon-reload
```
