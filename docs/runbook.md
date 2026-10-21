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
                 deploy-stateful, deploy-app, deploy-ingress, install-forward-services,
                 deploy-observability, apply-config, rotate-secret
  base/          environment-agnostic manifests
                   base/app/     namespace, backend, frontend
                   base/ingress/ security-headers, certificate, ingress
  overlays/      per-env overlays layered on base
                   overlays/prod/     namespace fmi-codes, host fmicodes.com, Let's Encrypt
                   overlays/staging/  namespace fmi-codes-staging, host staging.fmicodes.com, self-signed
  helm-values/   Bitnami postgresql + redis values (prod)
  secrets/       prod secrets.enc.yaml (SOPS); staging's lives in overlays/staging/secrets/
  flux/          Flux GitOps — source, image-automation, self
```

## Environments

|                    | prod                                                 | staging                                                                 |
| ------------------ | ---------------------------------------------------- | ----------------------------------------------------------------------- |
| namespace          | `fmi-codes`                                          | `fmi-codes-staging`                                                     |
| host / port        | `fmicodes.com` (443)                                 | `staging.fmicodes.com` (8443)                                           |
| DB / Redis FQDN    | `*.fmi-codes.svc`                                    | `*.fmi-codes-staging.svc`                                               |
| DB name            | `fmi_hackathon_2026`                                 | `fmi_hackathon_2026_staging`                                            |
| TLS                | Let's Encrypt `ClusterIssuer` (browser-trusted)      | self-signed `Issuer` (`curl -k`)                                        |
| ingress controller | release `ingress-nginx`, class `nginx`, ports 80/443 | release `ingress-nginx-staging`, class `nginx-staging`, ports 8080/8443 |
| SOPS secret        | `secrets/secrets.enc.yaml`                           | `overlays/staging/secrets/secrets.enc.yaml` (separate age key)          |
| deploy             | manual promote (human-merged PR)                     | auto on every push to `main`                                            |

Everything else — replicas, probes, resource limits, feature-flag defaults, `FLASK_ENV` —
is identical by design: staging mirrors prod so it catches problems before prod does. The
two ingress controllers are fully independent, so a staging deploy never touches prod's
routing or headers. Verify an overlay renders with `kubectl kustomize infra/k8s/overlays/<env>`.

## TL;DR

From the repo root: `./bootstrap.sh` (staging) or `./bootstrap.sh --env prod`. It runs a
pre-flight (asks for the age key + admin password), then installs tools → k3s →
Postgres/Redis → app → ingress. Idempotent and resumable (`--from N`, N = 1–7). Full
walkthrough below.

## Set up on a brand-new machine — step by step

End-to-end, bare server → running cluster. Do it for staging first, then repeat with
`--env prod` for production.

### 0. Prerequisites

- A **Debian/Ubuntu** box (or WSL2 Ubuntu) with `sudo`, `git`, and `curl`. Nothing else —
  `install-tools.sh` fetches kubectl/helm/sops/age/flux.
- **The environment's age private key.** SOPS decrypts the committed app secrets with it.
  Two cases:
  - **Deploying the existing project** (normal case): get the private key from a teammate.
    The easiest path is to store it as a GitHub Actions secret (`SOPS_AGE_KEY_STAGING` /
    `SOPS_AGE_KEY_PROD`) and export it before running bootstrap — the script picks it up
    automatically:
    ```bash
    export SOPS_AGE_KEY_STAGING="AGE-SECRET-KEY-1..."
    ./bootstrap.sh              # no paste prompt
    ```
    Without the env var, the script falls back to an interactive paste prompt.
  - **Forking to your own project:** you don't have the org's key, so mint your own and take
    over the recipient — see [Forking: use your own keys](#forking-use-your-own-keys) below,
    do that once, then come back here.
- **DNS for prod only:** `fmicodes.com` needs a public A-record → the server's IP, resolving
  _before_ you deploy (Let's Encrypt verifies it over HTTP-01, so port 80 must be reachable
  from the internet). Staging uses a self-signed cert — a hosts-file entry is enough.

### 1. Clone

```bash
git clone https://github.com/fss-fmi/fmi-codes-website-2026.git
cd fmi-codes-website-2026
```

### 2. Know what secrets exist and where they live

Nothing to create by hand — the passwords split three ways and every one is handled for you:

| Secret                            | Keys                                                                                              | How it's set                                                                                                                                                                           |
| --------------------------------- | ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fmi-codes-app` (SOPS, in git)    | `SECRET_KEY`, `JWT_SECRET_KEY`, `ADMIN_PASSWORD_HASH`, `MAIL_PASSWORD`, `DISCORD_BUG_WEBHOOK_URL` | committed encrypted; `deploy-app.sh` decrypts + applies with your age key. `SECRET_KEY`/`JWT_SECRET_KEY` already have strong committed values; `ADMIN_PASSWORD_HASH` you set in step 3 |
| `fmi-codes-db`, `fmi-codes-redis` | DB / Redis passwords                                                                              | **generated in-cluster** by `deploy-stateful.sh` on first run — you never touch these                                                                                                  |

So the only secret you actively decide on a fresh deploy is the **admin password** — and the
bootstrap pre-flight prompts you for it. `MAIL_PASSWORD` / `DISCORD_BUG_WEBHOOK_URL` are
optional; set them later with `rotate-secret.sh` (step 5) if you want password-reset mail or
bug-report webhooks.

### 3. Run the bootstrap

`./bootstrap.sh` is the front door. It runs a pre-flight, then installs tools → k3s →
Postgres/Redis → app → ingress in order.

```bash
./bootstrap.sh              # staging (default)
./bootstrap.sh --env prod   # production
```

The pre-flight handles exactly two things on a fresh machine:

1. **The age private key** — it checks `~/.config/sops/age/keys.txt`. If missing or wrong,
   it looks for `SOPS_AGE_KEY_STAGING` (or `SOPS_AGE_KEY_PROD`) in the environment and writes
   the key automatically; otherwise it falls back to an interactive paste prompt. Either way
   the key is written `chmod 600` and immediately verified against that env's `secrets.enc.yaml`
   (wrong key → it aborts). Store the key as a GitHub Actions secret and export it before
   running bootstrap to skip the prompt entirely.
2. **The admin password** — if `ADMIN_PASSWORD_HASH` is empty in the secrets file, it asks
   for a password, bcrypt-hashes it, and writes the hash back into `secrets.enc.yaml`. Commit
   and push that file afterward so other servers get the same hash. (Skip it and the backend
   CrashLoops until you set one — fix later with `rotate-secret.sh ADMIN_PASSWORD_HASH`.)

It's idempotent and resumable — if a step fails, fix the cause and re-run with `--from N`
(N = 1–6). Steps 1–2 need interactive sudo, so run it in a real terminal.

> **WSL2 dev box:** `./bootstrap.sh` works identically — after the Linux bring-up it detects
> WSL2 and prints the Windows hosts-file and forward-services steps automatically.

### 4. Point the host at the cluster

**Prod:** set the `fmicodes.com` A-record in public DNS → the server's IP (do this _before_
step 3 so the TLS cert issues). **Staging** (or prod local testing): add a hosts entry to the
controller's IP — the deploy script prints the exact line:

```bash
INGRESS_IP=$(kubectl -n ingress-nginx-staging get svc ingress-nginx-staging-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "$INGRESS_IP staging.fmicodes.com" | sudo tee -a /etc/hosts   # reach it at :8443
```

That line is for reaching the cluster from **inside WSL** (or a native Linux host). To reach it
from a **Windows browser** the node IP does not work — install the boot-persistent forward services
once (`install-forward-services.sh`) and use `127.0.0.1` hosts entries (see [Phase 4](#4--ingress--tls)).

### 5. (Optional) Set mail / webhook secrets

```bash
bash infra/k8s/scripts/rotate-secret.sh MAIL_PASSWORD 'gmail-app-password'
bash infra/k8s/scripts/rotate-secret.sh DISCORD_BUG_WEBHOOK_URL 'https://discord.com/api/webhooks/…'
```

Each re-encrypts the one key, re-applies the secret, and restarts the backend. `ENV=staging`
(default) or `ENV=prod`. Commit the `.enc.yaml` afterward.

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

### 7. Verify

```bash
kubectl -n fmi-codes-staging get pods                        # all Running/Ready
curl -k https://staging.fmicodes.com:8443/api/health/ready   # {"db":"ok","redis":"ok"}
```

### Forking: use your own keys

Only if you're standing up your _own_ project rather than deploying this one. The repo ships
two committed age recipients (staging + prod) in `.sops.yaml`; to take ownership, replace the
recipient for the env you control and re-encrypt:

```bash
# 1. Generate your key pair:
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt && chmod 600 ~/.config/sops/age/keys.txt
age-keygen -y ~/.config/sops/age/keys.txt      # prints your age1… public recipient

# 2. In .sops.yaml, swap the `age:` recipient for your env's rule to that age1… value.
# 3. Re-encrypt the existing secrets file to your key:
sops updatekeys infra/k8s/overlays/staging/secrets/secrets.enc.yaml   # (prod: infra/k8s/secrets/secrets.enc.yaml)
# 4. Commit .sops.yaml + the re-encrypted file. Now bootstrap accepts YOUR key.
```

You'll also want your own Docker Hub images and hostnames — see
[Forking to your own infra](#forking-to-your-own-infra).

## The phases (reference)

The bootstrap runs these for you; this is what each does if you need to run one alone. Each
script refuses to run until the previous phase's resources exist, so ordering is enforced.
`ENV=staging` (default) or `ENV=prod` selects the target.

Each script refuses to run until the previous phase's resources exist, so ordering is
enforced, not assumed. `ENV=staging` (default) or `ENV=prod` selects the target.

### 1 — Tools + cluster

```bash
bash infra/k8s/scripts/install-tools.sh    # kubectl, helm, k9s, sops, age, flux — pinned + checksum-verified
bash infra/k8s/scripts/bootstrap-k3s.sh    # k3s (Traefik disabled), wires kubeconfig, creates the namespace
```

Both are idempotent. Versions are pinned via `*_VERSION` env vars at the top of each script;
override to upgrade (e.g. `K3S_VERSION=v1.37.0+k3s1 bash …`). `install-tools.sh` downloads
each binary pinned and SHA256-verified — nothing is piped into a shell.

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

`helm upgrade --install`s Bitnami Postgres (single primary, PVC) and Redis (1 master + 3
replicas + sentinels, master set `mymaster`, quorum 2). On first run it generates two
in-cluster Secrets with random passwords — `fmi-codes-db` and `fmi-codes-redis` — and the
charts consume them via `existingSecret`. Re-runs leave them untouched. `schema.sql` is
loaded into the `postgres-initdb` ConfigMap and run once by Postgres `initdb`.

In-cluster addresses the app tier uses: `postgres.<ns>.svc.cluster.local:5432` and
`redis.<ns>.svc.cluster.local:26379`.

**The PVC is the real source of truth.** Two things bake into the Postgres PVC at first
boot and never change on a re-run: the schema and the DB password. So editing `schema.sql`
and re-running does _not_ migrate a running DB (drop the PVC for a clean re-init, or add a
real migration tool later), and **a Secret and its PVC are a matched pair** — delete one
without the other and you get `password authentication failed`. Always delete them together.

> Images pull from `docker.io/bitnamilegacy/*`, not `bitnami/*` — Bitnami archived the free
> tier in Aug 2025. Don't "correct" them back; the `bitnami/*` tags no longer resolve and
> pods `ErrImagePull`. `bitnamilegacy` is frozen (no patches) — migrating to maintained
> images is future work.

### 3 — App tier (backend + frontend)

```bash
bash infra/k8s/scripts/deploy-app.sh   # ENV=prod|staging
```

Two `Deployment`s (2 replicas each) behind `ClusterIP` Services: `backend`
(`fssfmi/fmi-codes-backend`, :5001) and `frontend` (`fssfmi/fmi-codes-frontend`, :80). The
backend Service is named `backend` because the frontend image's `nginx.conf` proxies
`/api/` and `/static/` to `http://backend:5001` — the same image works under compose (where
the `app` service carries a `backend` alias) and k8s with no rebuild.

Config split: non-secret env comes from the `fmi-codes-backend-config` ConfigMap via
`envFrom`; passwords via `secretKeyRef` (`DB_PASSWORD`, `REDIS_PASSWORD` from Phase 2, and
`SECRET_KEY`/`JWT_SECRET_KEY`/`ADMIN_PASSWORD_HASH`/`MAIL_PASSWORD`/`DISCORD_BUG_WEBHOOK_URL`
from `fmi-codes-app`). `DATABASE_URL` is intentionally unset — the backend composes it from
the `DB_*` pieces.

Health endpoints: `GET /api/health` (liveness, touches nothing) and `GET /api/health/ready`
(readiness — pooled `SELECT 1` + Redis ping; Postgres gates readiness, Redis is fail-open).

### 4 — Ingress + TLS

```bash
bash infra/k8s/scripts/deploy-ingress.sh   # ENV=prod|staging
```

`helm upgrade --install`s the env's ingress-nginx controller + cert-manager, applies the
Ingress, waits for the cert. Path routing: `/api` and `/static` → `backend:5001`, everything
else → `frontend:80`. Security headers live in the `security-headers` ConfigMap wired into
the controller via `add-headers`, so **every** response through the Ingress carries them
(the backend routes shipped naked before). Prod gets a Let's Encrypt cert via HTTP-01 and
auto-renews; HTTP → HTTPS redirect is automatic.

Resolve the host for local testing (the script prints the exact line):

```bash
INGRESS_IP=$(kubectl -n ingress-nginx get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "$INGRESS_IP fmicodes.com" | sudo tee -a /etc/hosts
# staging: ingress-nginx-staging controller, port 8443 → https://staging.fmicodes.com:8443
```

On the production server, set the `fmicodes.com` A-record in DNS instead.

**From a Windows browser (WSL2 dev box):** the node IP above does **not** work — k3s/klipper does
not expose the ingress LoadBalancer ports to the Windows host, so a hosts entry pointing at it
resolves the name but cannot open a connection. Install the boot-persistent forward services once,
then use `127.0.0.1` hosts entries:

```bash
wsl.exe -u root -- bash infra/k8s/scripts/install-forward-services.sh install
```

This writes three `systemd` services (`enabled`, `Restart=always`, so they come back on every boot
with no terminal to keep open):

- `fmi-forward-prod` — `kubectl port-forward` the prod ingress controller to `127.0.0.1:8443`.
- `fmi-tls-prod` — `socat` `127.0.0.1:443` → `:8443`. Because the prod ingress multiplexes by host,
  this **one** bridge serves both `fmicodes.com` **and** `grafana.fmicodes.com` on bare `:443`.
- `fmi-forward-staging` — `kubectl port-forward` the staging ingress controller to `127.0.0.1:9443`.

It also sets `net.ipv4.ip_unprivileged_port_start=443` (persisted) so the `socat` bridge can bind
`:443` as a non-root user. Add the hosts entries (elevated PowerShell, once):

```
127.0.0.1 fmicodes.com
127.0.0.1 grafana.fmicodes.com
127.0.0.1 staging.fmicodes.com
```

Then browse `https://fmicodes.com`, `https://grafana.fmicodes.com`, and
`https://staging.fmicodes.com:9443` — staging keeps a port suffix because `:443` has a single
listener already taken by prod. Remove everything with
`wsl.exe -u root -- bash infra/k8s/scripts/install-forward-services.sh uninstall`. Requires
`systemd=true` in `/etc/wsl.conf` (the default here) and `socat` installed.

### 5 — Secrets (SOPS + age)

App secrets have a git-committed, encrypted single source of truth. SOPS encrypts only the
_values_ (keys stay readable, so a diff shows _which_ secret changed), using [age](https://github.com/FiloSottile/age)
as the backend — each dev holds an age key pair, SOPS encrypts to every public recipient in
`.sops.yaml`. **Only the SOPS-encrypted file belongs in git** — a plain k8s Secret's `data:`
is base64, not encryption, and `base64 -d` reveals it instantly.

DB/Redis passwords are deliberately **not** in SOPS — they're PVC-coupled and generated
in-cluster (see Phase 2). SOPS owns only the five `fmi-codes-app` values.

Getting the age key onto a machine is covered in the setup guide (paste it when bootstrap
prompts) and [Forking: use your own keys](#forking-use-your-own-keys) (mint your own). Back
the key up — lose every recipient's key and the committed secrets are permanently
undecryptable. Staging and prod use **separate** age keys, so a leak of one never exposes the
other; `.sops.yaml` routes each file to its recipient by path (staging rule first, more
specific). An operator managing both keeps both private keys in `~/.config/sops/age/keys.txt`
(one per line). The deploy/rotate scripts assert the decrypted manifest's namespace matches
`ENV` and refuse to apply across environments.

**Edit / rotate:**

```bash
sops infra/k8s/secrets/secrets.enc.yaml                    # prod (staging: overlays/staging/secrets/…)
bash infra/k8s/scripts/rotate-secret.sh JWT_SECRET_KEY     # re-encrypt one key, re-apply, restart backend
bash infra/k8s/scripts/rotate-secret.sh MAIL_PASSWORD 'value'
```

`deploy-app.sh` decrypts-and-applies automatically when your key can read the file. On a
fresh clone with no age key it falls back to a throwaway in-cluster secret — but that has an
empty `ADMIN_PASSWORD_HASH`, so the prod backend CrashLoops until you set one. Commit the
`.enc.yaml` after any rotation.

> The default `ADMIN_PASSWORD_HASH` is a bcrypt hash of a known-weak bootstrap password
> (encrypted in git, but known). **Rotate it before any non-local use.**

**Add / remove a recipient:** edit the `age:` list in `.sops.yaml`, then
`sops updatekeys <file>` (re-wraps the data key, no value change, no rollout). On **removal**
also rotate every value — the departing dev still has the old ciphertext in git history.

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
itself GitOps-managed — edits to `source.yaml`/`image-automation.yaml` self-reconcile within
5m; editing `self.yaml` needs a `flux-bootstrap.sh` re-run.

> `docker-cd.yaml` ignores `infra/**` on purpose: a bump commit is a push to `main`, and
> without the guard it would re-fire the build, mint a newer tag, and loop forever. The
> constraint this creates: build inputs (Dockerfiles, build scripts) must stay OUT of
> `infra/`. Today they're in `./backend` and `./frontend` — keep them there.

### 7 — Observability (Prometheus + Grafana)

Answers "is the backend leaking memory?" with a memory-per-pod graph over **days**, instead
of a manual `kubectl top` marathon. **Fully self-hosted — no external accounts, no SaaS, no
cost, nothing phones home.** The `kube-prometheus-stack` Helm chart (Prometheus operator +
Grafana + node-exporter + kube-state-metrics) runs in its own `monitoring` namespace; a Flask
`/metrics` endpoint feeds app-level series alongside the cluster resource metrics.

**The observability stack is GitOps-managed by Flux.** The chart install, upgrades, and the
backend `ServiceMonitor` are all reconciled from `infra/k8s/` — a values change merged to
`main` rolls out automatically with no script run. The Flux wiring lives in `flux/source.yaml`
(`fmi-codes-observability` and `fmi-codes-observability-staging` Kustomizations); each pulls in
the backend `ServiceMonitor` from `base/observability/monitors` as part of its own overlay, so
the monitor reconciles with whichever env is live.

**One-time bootstrap — Grafana admin secret only.** The only manual step is decrypting and
applying the SOPS-encrypted Grafana secret before Flux's first reconcile (so the chart can
mount it):

```bash
ENV=staging bash infra/k8s/scripts/deploy-observability.sh   # ENV=prod for production creds
```

The script creates the `monitoring` namespace (if needed) and applies the Grafana admin secret.
Flux then installs the chart and applies the ServiceMonitor. If `flux-bootstrap.sh` has not been
run yet, apply the Flux objects manually once first:

```bash
kubectl apply -f infra/k8s/flux/source.yaml
```

One stack scrapes **both** app namespaces. The `ENV` flag only selects which SOPS-encrypted
Grafana secret to decrypt (staging and prod are encrypted with different age keys). Monitoring
is independent of the app tier, but the app must be running for the ServiceMonitor to have a
scrape target.

|                                    | value                                   | why                                                                                                                   |
| ---------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| namespace                          | `monitoring`                            | kube-prometheus-stack convention; single shared stack                                                                 |
| scrapes                            | `fmi-codes` **and** `fmi-codes-staging` | one ServiceMonitor, `namespaceSelector.matchNames` lists both                                                         |
| retention                          | `14d`                                   | the leak window is multi-day; 10d default is too short                                                                |
| Prometheus PVC                     | 5Gi (prod) / 3Gi (staging)              | TSDB survives `wsl --shutdown`; in-memory would reset and defeat the investigation                                    |
| Grafana PVC                        | 1Gi (both envs)                         | dashboards + admin session survive restarts; `local-path` StorageClass doesn't support resize so both envs must match |
| alertmanager                       | **off**                                 | no paging on a hobby cluster                                                                                          |
| node-exporter + kube-state-metrics | **on**                                  | they produce the node/pod resource series — the whole point                                                           |

Resource requests+limits are set on every component (see `base/observability/helmrelease.yaml`
`spec.values`, with per-env overrides in the overlay patches)
to bound the stack's footprint — it adds roughly 600–900Mi to the node, so the limits are the
guardrail on a single WSL2 box already running the app+stateful tiers.

**Access Grafana** — on a WSL2 dev box, Grafana is reachable at `https://grafana.fmicodes.com`
with **no extra setup** once the boot-persistent forward services are installed (see
[Phase 4](#4--ingress--tls)). `grafana.fmicodes.com` is an ingress rule on the same prod `nginx`
controller as `fmicodes.com`, so the single `fmi-tls-prod` `:443` bridge serves it too — the ingress
routes by host. Add the hosts entry (once):

```
127.0.0.1 grafana.fmicodes.com
```

Log in with the admin user/password from the SOPS secret (`sops --decrypt
infra/k8s/secrets/grafana-secret.enc.yaml`). Anonymous access and sign-up are **disabled** in
the chart values, so there is no `admin/admin` and no open registration.

Ad-hoc alternative (no services, no `:443`) — a one-off port-forward straight to the Grafana
service:

```bash
kubectl -n monitoring port-forward svc/kps-grafana 3000:80    # http://localhost:3000
```

**Why not the ingress host?** The chart provisions a Grafana ingress (prod: `grafana.fmicodes.com`,
staging: `grafana.staging.fmicodes.com`), and that works on a **native Linux host** with a real
LoadBalancer. But on **WSL2/k3s it does not reach a Windows browser**: k3s's built-in ServiceLB
(klipper) does not expose the ingress controller's LoadBalancer ports to the Windows host, so no
Windows hosts-file entry — node IP or `127.0.0.1` — can open a TCP connection to them. Pointing the
hosts file at the WSL node IP resolves the name but the port is dead. The port-forward above is what
actually bridges the cluster to Windows-visible localhost, the same way the app tier is reached in
local testing. On a native Linux host, add the host to `/etc/hosts` → the controller IP and browse
`http://<grafana-host>` directly (plain HTTP, no TLS — both hosts are local-only).

**Grafana CSP vs the shared app CSP.** The ingress controller injects the app's strict
`security-headers` Content-Security-Policy (`script-src 'self'`) on _every_ response via
`controller.config.add-headers` — including the Grafana vhost. Grafana boots from an inline
`<script>`, which `script-src 'self'` blocks, so the Grafana SPA dies on a blank `/login` unless
its CSP is handled. Rather than weaken the app CSP, Grafana emits its **own** nonce-based CSP
(`grafana.ini` `[security] content_security_policy = true`, which stamps a per-response `$NONCE`
on both the header and the inline boot script), and the Grafana ingress carries a
`configuration-snippet` that overwrites the injected app CSP with Grafana's upstream one
(`more_set_headers "Content-Security-Policy: $upstream_http_content_security_policy"`). The app's
own hosts keep the strict CSP untouched. This needs `allow-snippet-annotations=true` and
`annotations-risk-level=Critical` on the controller (both set by `deploy-ingress.sh`), because
ingress-nginx gates `configuration-snippet` behind them by default.

**App-only dashboards:** Grafana → Dashboards → **FMI Codes** folder → **FMI Production** or
**FMI Staging**. Each shows request rate, request duration (p50/p95/p99), and error rate for
its namespace, hardcoded so there is no shared dropdown or data mixing between envs. These
dashboards provision automatically on every `deploy-observability.sh` run — no manual import.

**The memory-per-pod leak graph:** Grafana → Dashboards → **"Kubernetes / Compute Resources /
Pod"**, filter `namespace=fmi-codes-staging`, `pod=~backend.*`, the memory panel, set the range
to 7d. A steadily climbing line that never plateaus is the leak signature.

**Check scrape targets** (confirm the backend is actually being scraped):

```bash
kubectl -n monitoring port-forward svc/kps-kube-prometheus-stack-prometheus 9090:9090
# http://localhost:9090 -> Status -> Targets -> the fmi-codes-backend target is UP
```

> **The app `/metrics` gotcha.** The exporter registers `/metrics` at the backend ROOT, but the
> ingress routes `/`→frontend and only `/api`+`/static`→backend. So `/metrics` through the
> **public ingress** hits the frontend, not the backend — and that's FINE. Prometheus scrapes
> **in-cluster** via the ServiceMonitor at `backend.<ns>.svc:5001/metrics`, never through the
> ingress. Do **not** "fix" this by adding an ingress route — it would expose app metrics
> publicly for zero benefit.

**Known limitation — multiprocess counters.** The backend runs multiple Gunicorn workers, and
plain `PrometheusMetrics(app)` gives **per-worker** app counters (each scrape hits one random
worker). This is accepted for the first pass: the PRIMARY deliverable — memory-per-pod — comes
from cAdvisor/kube-state-metrics and is 100% independent of app counters. To get aggregated
app counters later, switch to `GunicornPrometheusMetrics`, set `PROMETHEUS_MULTIPROC_DIR` to a
tmpfs volume, and add a `child_exit` hook in the Gunicorn config — real complexity for marginal
value on a hobby cluster.

**Rotate the Grafana admin password** (the generalized `rotate-secret.sh`):

```bash
ENV=staging NAMESPACE=monitoring \
  SECRETS_ENC=infra/k8s/overlays/staging/secrets/grafana-secret.enc.yaml \
  RESTART_TARGET=deployment/kps-grafana \
  bash infra/k8s/scripts/rotate-secret.sh admin-password 'newpass'
```

The Grafana deployment name is `kps-grafana` because the values set `fullnameOverride: kps` —
verify with `kubectl -n monitoring get deploy` if you change it.

**Recorded decisions** (restated so this section is self-contained): a single shared
`monitoring` stack scrapes both envs (separation by namespace selector, not separate stacks);
persistence is PVC-backed (the multi-day window is the entire point); on a WSL2 dev box Grafana is
reached at `https://grafana.fmicodes.com` because klipper does not expose the LoadBalancer ports to
the Windows host, so the boot-persistent `fmi-tls-prod` `socat` bridge on `:443` fronts the prod
ingress — and since `grafana.fmicodes.com` is a rule on that same prod `nginx` controller, it rides
the one bridge for free (no Grafana-specific forward). The chart's Grafana ingress
(`grafana.fmicodes.com` / `grafana.staging.fmicodes.com`, env's nginx class, TLS omitted since both
are local-only) stays in place and is the direct access path only on a native Linux host with a real
LoadBalancer. Two provisioned dashboards ("FMI Production", "FMI Staging") ship with every install
via `grafana.dashboards` in the Helm values — no manual import needed.

## Forking to your own infra

To deploy this under your own project — your Docker Hub, your domain, your keys — change:

- **age keys** — mint your own and re-encrypt, per [Forking: use your own keys](#forking-use-your-own-keys).
- **Image registry** — the `fssfmi/fmi-codes-{backend,frontend}` names in `base/app/*.yaml`,
  `overlays/*/kustomization.yaml`, `.github/workflows/docker-cd.yaml`, and
  `flux/image-automation.yaml`; set the `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` repo secrets.
- **Hostnames** — `fmicodes.com` / `staging.fmicodes.com` in `base/ingress/ingress.yaml`,
  `overlays/*/ingress/*`, and `FRONTEND_ORIGIN` in `base/app/backend.yaml` +
  `overlays/staging/backend-config-patch.yaml`.
- **Flux git URL / deploy key** — `flux-bootstrap.sh` defaults to
  `ssh://git@github.com/fss-fmi/fmi-codes-website-2026.git`; override with
  `GIT_URL=… bash …` and add your own deploy key (step 6).

## Change a config value

Non-secret backend setting (feature flags, `FRONTEND_ORIGIN`, DB/Redis coordinates):

```bash
bash infra/k8s/scripts/apply-config.sh REGISTRATION_OPEN true
bash infra/k8s/scripts/apply-config.sh          # re-apply the overlay from disk, then roll
```

It patches the `fmi-codes-backend-config` ConfigMap and restarts the backend. Secrets are
refused (use `rotate-secret.sh` / `deploy-stateful.sh`). A live patch drifts from git, so
also edit the source and commit: env-specific keys (`FRONTEND_ORIGIN`, `DB_HOST`,
`REDIS_SENTINELS`) live in `overlays/<env>/backend-config-patch.yaml`, the rest in
`base/app/backend.yaml`. Pass `RESTART=false` to batch, `ENV=staging` to target staging.

## Verify a running deployment

```bash
kubectl -n fmi-codes get pods                                  # 2 backend, 2 frontend, Postgres, Redis
curl https://fmicodes.com/api/health                           # backend 200
curl -k https://staging.fmicodes.com:8443/api/health/ready     # {"db":"ok","redis":"ok"}
flux get kustomizations -n flux-system                         # prod + staging Ready (if Flux is up)
```

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
# the automation objects don't cascade-delete, so remove them explicitly):
kubectl -n flux-system delete -f flux/self.yaml
kubectl -n flux-system delete -f flux/image-automation.yaml -f flux/source.yaml
flux uninstall --namespace flux-system --silent

# Phase 7 — observability (suspend the Flux kustomizations first so Flux stops
# reconciling, then let Helm uninstall clean up; deleting the ns cascades the PVCs):
flux suspend kustomization fmi-codes-observability -n flux-system
flux suspend kustomization fmi-codes-observability-staging -n flux-system
helm -n monitoring uninstall kps
kubectl delete namespace monitoring

# Phase 4 — networking:
kubectl delete -k overlays/prod/ingress; kubectl delete -k overlays/staging/ingress
helm -n ingress-nginx uninstall ingress-nginx
helm -n ingress-nginx-staging uninstall ingress-nginx-staging
helm -n cert-manager uninstall cert-manager
kubectl delete namespace ingress-nginx ingress-nginx-staging cert-manager

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

# Or nuke the whole cluster:
/usr/local/bin/k3s-uninstall.sh
```
