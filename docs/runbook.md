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

| Secret                            | Keys                                                                                                                                                       | How it's set                                                                                                                                                                           |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fmi-codes-app` (SOPS, in git)    | `SECRET_KEY`, `JWT_SECRET_KEY`, `ADMIN_PASSWORD_HASH`, `MAIL_PASSWORD`, `DISCORD_BUG_WEBHOOK_URL`, `SLACK_BUG_WEBHOOK_URL`, `SLACK_MIGRATIONS_WEBHOOK_URL` | committed encrypted; `deploy-app.sh` decrypts + applies with your age key. `SECRET_KEY`/`JWT_SECRET_KEY` already have strong committed values; `ADMIN_PASSWORD_HASH` you set in step 3 |
| `fmi-codes-db`, `fmi-codes-redis` | DB / Redis passwords                                                                                                                                       | **generated in-cluster** by `deploy-stateful.sh` on first run; rotate with `rotate-datastore-password.sh`, never by hand                                                               |

So the only secret you actively decide on a fresh deploy is the **admin password** — and the
bootstrap pre-flight prompts you for it. `MAIL_PASSWORD` / `DISCORD_BUG_WEBHOOK_URL` /
`SLACK_BUG_WEBHOOK_URL` / `SLACK_MIGRATIONS_WEBHOOK_URL` are optional; set them later with
`rotate-secret.sh` (step 5) if you want password-reset mail, bug reports in Discord or Slack,
or migration results in Slack.

### 3. Run the bootstrap

`./bootstrap.sh` is the front door. It runs a pre-flight, then installs tools → k3s →
Postgres/Redis → app → ingress in order.

```bash
./bootstrap.sh              # staging (default)
./bootstrap.sh --env prod   # production
```

The pre-flight first installs `sops` and `age` if they're missing (so it can verify keys on a
bare box), then handles two things:

1. **The age private key**: it test-decrypts every SOPS file of that env (`secrets.enc.yaml`
   and `grafana-secret.enc.yaml`) with `~/.config/sops/age/keys.txt` (or `$SOPS_AGE_KEY_FILE`
   if set). If that works it does nothing, whatever else is in the file and in whatever order.
   Otherwise it takes the key from `SOPS_AGE_KEY_STAGING` (or `SOPS_AGE_KEY_PROD`), falling
   back to a hidden paste prompt, verifies the key decrypts those files **before** writing
   anything, then **appends** it to `keys.txt` with a `# public key:` comment (`chmod 600`).
   Existing keys are never replaced or removed. A wrong key aborts with its public key next
   to the one the files are encrypted to, and leaves `keys.txt` untouched. To skip the prompt,
   export the key first as shown in [step 0](#0-prerequisites).
2. **The admin password** — if `ADMIN_PASSWORD_HASH` is empty in the secrets file, it asks
   for a password (hidden, typed twice, at least 12 characters), bcrypt-hashes it, and writes
   the hash back into `secrets.enc.yaml` through stdin, so neither shows up in `ps`. Commit
   and push that file afterward so other servers get the same hash. (Skip it and the backend
   CrashLoops until you set one — fix later with `rotate-secret.sh ADMIN_PASSWORD_HASH`.)

It's idempotent and resumable — if a step fails, fix the cause and re-run with `--from N`
(N = 1–7). Steps 1–2 need interactive sudo, so run it in a real terminal.

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

That line is for reaching the cluster from **inside WSL** (or a native Linux host). A **Windows
browser** can reach the node IP too, but WSL2's NAT address can change after `wsl --shutdown` or a
reboot, so a Windows hosts entry pointing at it goes stale. Install the boot-persistent forward
services once (`install-forward-services.sh`) and use `127.0.0.1` hosts entries instead (see
[Phase 4](#4--ingress--tls)).

### 5. (Optional) Set mail / webhook secrets

```bash
bash infra/k8s/scripts/rotate-secret.sh MAIL_PASSWORD             # prompts (hidden, twice)
bash infra/k8s/scripts/rotate-secret.sh DISCORD_BUG_WEBHOOK_URL
bash infra/k8s/scripts/rotate-secret.sh SLACK_BUG_WEBHOOK_URL
bash infra/k8s/scripts/rotate-secret.sh SLACK_MIGRATIONS_WEBHOOK_URL
```

Each prompts for the value, re-encrypts the one key, re-applies the secret, and restarts the
backend. `ENV=staging` (default) or `ENV=prod`. Commit the `.enc.yaml` afterward. Every secret
and how to rotate it: [Rotate a secret](#rotate-a-secret).

The script only changes keys already in the file. If `SLACK_BUG_WEBHOOK_URL` or
`SLACK_MIGRATIONS_WEBHOOK_URL` is missing (files encrypted before they were added), add it once
with `sops <file>` first.

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

#### GitHub bot app for automated PRs

The bump, migrate and promote workflows open their PRs as a GitHub App (`fmi-codes-bot`)
instead of the built-in `GITHUB_TOKEN`. GitHub holds CI on a PR opened with `GITHUB_TOKEN`
until someone clicks **Approve workflows to run**, and that token can't enable auto-merge,
so without the app every staging bump stalls. One-time setup, by an org admin:

1. **Create it:** org **Settings → Developer settings → GitHub Apps → New GitHub App**. Name it,
   set the homepage to the repo URL, untick **Webhook → Active**. Repository permissions:
   **Contents: Read and write** and **Pull requests: Read and write** (Metadata read-only is
   added automatically), nothing else. No events. Installable **only on this account**.
2. **Credentials:** copy the **Client ID** from the app page, then **Generate a private key**
   (a `.pem` downloads).
3. **Install it:** **Install App → Only select repositories →** this repo.
4. **Store them in the repo** (the key goes in through stdin, never as an argument):

   ```bash
   gh variable set BOT_APP_CLIENT_ID --repo fss-fmi/fmi-codes-website-2026 --body "Iv23li..."
   gh secret set BOT_APP_PRIVATE_KEY --repo fss-fmi/fmi-codes-website-2026 < ~/Downloads/<app>.<date>.private-key.pem
   ```

   Keep the `.pem` in a password manager and delete the download. To rotate, generate a new
   key on the app page, set the secret again and delete the old key there.

Also turn on **Settings → General → Allow auto-merge**. The repo's required checks (Lint, Unit
& E2E tests) still gate every merge; the app gets no bypass.

### 7. Verify

```bash
kubectl -n fmi-codes-staging get pods                        # all Running/Ready
curl -k https://staging.fmicodes.com:8443/api/health/ready   # {"db":"ok","redis":"ok"}
```

### Forking: use your own keys

Only if you're standing up your _own_ project rather than deploying this one. The repo ships
two committed age recipients (staging + prod) in `.sops.yaml`. Without the org's private keys
you can't decrypt the committed files, so `sops updatekeys` won't work for you: mint your own
key, point `.sops.yaml` at it and replace that env's encrypted files with your own values.

```bash
# 1. Generate a key pair. Appends, so an existing keys.txt is kept (age-keygen -o refuses
#    to write to an existing file). Prints "Public key: age1…" on stderr.
mkdir -p ~/.config/sops/age
(umask 077 && age-keygen >> ~/.config/sops/age/keys.txt)

# 2. In .sops.yaml, set the `age:` recipient of BOTH rules for your env (secrets.enc.yaml and
#    grafana-secret.enc.yaml) to that age1… value.

# 3. Overwrite each of that env's .enc.yaml files with a plaintext Secret holding your values
#    (same metadata and stringData keys as the committed file; those stay readable), then
#    encrypt it in place. .sops.yaml picks the recipient by path:
sops --encrypt --in-place infra/k8s/overlays/staging/secrets/secrets.enc.yaml
sops --encrypt --in-place infra/k8s/overlays/staging/secrets/grafana-secret.enc.yaml
# (prod: infra/k8s/secrets/secrets.enc.yaml and infra/k8s/secrets/grafana-secret.enc.yaml)

# 4. Commit .sops.yaml + the encrypted files. Bootstrap checks keys by decrypting the files,
#    so it accepts YOUR key with no script changes.
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
and re-running does _not_ migrate a running DB (schema changes reach it through the migration
runner, see [Database migrations](deployment.md#database-migrations)), and **a Secret and its PVC are a matched pair** — delete one
without the other and you get `password authentication failed`. Always delete them together.
To change a password without wiping data, use
[`rotate-datastore-password.sh`](#db-and-redis-passwords).

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
and, optionally, `SLACK_BUG_WEBHOOK_URL` from `fmi-codes-app`; the `migrate` initContainer
reads `SLACK_MIGRATIONS_WEBHOOK_URL` from it, optionally). `DATABASE_URL` is intentionally
unset — the backend composes it from the `DB_*` pieces.

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

**From a Windows browser (WSL2 dev box):** Windows can reach the node IP above, but WSL2 gives the
VM a NAT address that can change after `wsl --shutdown` or a Windows reboot, so a hosts entry
pointing at it breaks without warning. Install the boot-persistent forward services once, then use
`127.0.0.1` hosts entries, which never change. From the repo root inside WSL:

```bash
wsl.exe -d "$WSL_DISTRO_NAME" -u root -- bash infra/k8s/scripts/install-forward-services.sh install
```

Keep the `-d "$WSL_DISTRO_NAME"`: a bare `wsl.exe` runs in the Windows default distro, which is
`docker-desktop` when Docker Desktop is installed, and fails there with `bash: not found`.
`sudo bash infra/k8s/scripts/install-forward-services.sh install` works too.

The script only installs the services for an env whose ingress controller Service exists, so a
port-forward never crash-loops against a missing controller. Re-run it after bootstrapping the other
env to add that env's services. It writes up to three `systemd` services (`enabled`,
`Restart=always`, so they come back on every boot with no terminal to keep open):

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
`wsl.exe -d "$WSL_DISTRO_NAME" -u root -- bash infra/k8s/scripts/install-forward-services.sh uninstall`. Requires
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
(one per line, any order): sops tries every key in the file, and `bootstrap.sh` only ever
appends a missing key, so nothing needs commenting out when switching environments. The
deploy/rotate scripts assert the decrypted manifest's namespace matches `ENV` and refuse to
apply across environments.

**Edit / rotate:** use `rotate-secret.sh`, covered per secret in
[Rotate a secret](#rotate-a-secret). A manual `sops infra/k8s/secrets/secrets.enc.yaml` edit
(staging: `overlays/staging/secrets/…`) only changes git; apply it with
`sops -d <file> | kubectl apply -f -` and restart the backend yourself.

`deploy-app.sh` decrypts-and-applies automatically when your key can read the file. On a
fresh clone with no age key it falls back to a throwaway in-cluster secret — but that has an
empty `ADMIN_PASSWORD_HASH`, so the prod backend CrashLoops until you set one. Commit the
`.enc.yaml` after any rotation.

> The default `ADMIN_PASSWORD_HASH` is a bcrypt hash of a known-weak bootstrap password
> (encrypted in git, but known). **Rotate it before any non-local use.**

**Add / remove a recipient:** edit the `age:` list in `.sops.yaml`, then
`sops updatekeys -y <file>` for each of the env's files (re-wraps the data key, no value
change, no rollout). On **removal** also rotate every value — the departing dev still has the
old ciphertext in git history. Replacing a key end to end:
[Rotate an age key](#rotate-an-age-key).

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
LoadBalancer. On **WSL2/k3s a Windows hosts entry to it is fragile**: the ingress controller's
LoadBalancer ports are reachable at the WSL node IP, but that NAT address can change after
`wsl --shutdown` or a reboot, so the entry silently goes stale. The `127.0.0.1` bridge above stays
put, the same way the app tier is reached in local testing. On a native Linux host, add the host to
`/etc/hosts` → the controller IP and browse `http://<grafana-host>` directly (plain HTTP, no TLS — both hosts are local-only).

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

**Rotate the Grafana admin password:** `bash infra/k8s/scripts/rotate-secret.sh --grafana
admin-password` (details and why it also resets Grafana's database in
[Grafana admin password](#grafana-admin-password)).

The Grafana deployment name is `kps-grafana` because the values set `fullnameOverride: kps` —
verify with `kubectl -n monitoring get deploy` if you change it (then pass
`RESTART_TARGET=deployment/<name>` to `rotate-secret.sh --grafana`).

**Recorded decisions** (restated so this section is self-contained): a single shared
`monitoring` stack scrapes both envs (separation by namespace selector, not separate stacks);
persistence is PVC-backed (the multi-day window is the entire point); on a WSL2 dev box Grafana is
reached at `https://grafana.fmicodes.com` because the WSL node IP is not stable across restarts, so
the boot-persistent `fmi-tls-prod` `socat` bridge on `:443` fronts the prod
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
- **Bot app** — create your own and set `BOT_APP_CLIENT_ID` / `BOT_APP_PRIVATE_KEY`, per
  [GitHub bot app for automated PRs](#github-bot-app-for-automated-prs).

## Rotate a secret

`infra/k8s/scripts/rotate-secret.sh` rotates one key of an env's SOPS file: it re-encrypts the
value in git, applies the Secret to the cluster and restarts the workload that reads it. Run
it once per environment (`ENV=staging` is the default, `ENV=prod` for production) and commit
the changed `.enc.yaml` afterward. Use a different value per environment.

The value is **never** a command-line argument, because arguments land in shell history and
are readable by every local user through `ps`. It comes from one of:

```bash
bash infra/k8s/scripts/rotate-secret.sh JWT_SECRET_KEY --generate           # strong random value
ENV=prod bash infra/k8s/scripts/rotate-secret.sh MAIL_PASSWORD             # hidden prompt, typed twice
bash infra/k8s/scripts/rotate-secret.sh DISCORD_BUG_WEBHOOK_URL < hook.txt  # piped (one trailing newline is dropped)
```

Passing the value as a second argument is refused with an explanation. Under the hood the
script hands the value to `sops set --value-stdin`; a `sops` too old for that flag is refused
with the fix (reinstall the version `install-tools.sh` pins).

| Secret                         | Rotate with                                                                                 | What users notice                                                                                                                        | Rotate when                                                                                                                                                                    |
| ------------------------------ | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `SECRET_KEY`                   | `rotate-secret.sh SECRET_KEY --generate`                                                    | Nothing. Flask's key; nothing in the app signs with it today (reset and verification links are random tokens stored as hashes).          | It may have leaked                                                                                                                                                             |
| `JWT_SECRET_KEY`               | `rotate-secret.sh JWT_SECRET_KEY --generate`                                                | **Everyone is logged out**: participants, mentors and the admin.                                                                         | It may have leaked; after an admin password leak (see next row)                                                                                                                |
| `ADMIN_PASSWORD_HASH`          | `rotate-secret.sh ADMIN_PASSWORD_HASH`                                                      | The admin logs in with the new password. Admin sessions already open **stay valid** until they expire (`JWT_EXPIRY_DAYS`, 3 by default). | Before first real use (the committed default is known-weak); when an organizer with the password leaves; on a leak, **together with `JWT_SECRET_KEY`** (see the warning below) |
| `MAIL_PASSWORD`                | `rotate-secret.sh MAIL_PASSWORD`                                                            | Nothing; mail keeps working after the restart.                                                                                           | Google revoked it or it leaked                                                                                                                                                 |
| `DISCORD_BUG_WEBHOOK_URL`      | `rotate-secret.sh DISCORD_BUG_WEBHOOK_URL`                                                  | Nothing.                                                                                                                                 | It leaked (anyone with the URL can post to the channel)                                                                                                                        |
| `SLACK_BUG_WEBHOOK_URL`        | `rotate-secret.sh SLACK_BUG_WEBHOOK_URL`                                                    | Nothing.                                                                                                                                 | It leaked (anyone with the URL can post to the channel)                                                                                                                        |
| `SLACK_MIGRATIONS_WEBHOOK_URL` | `rotate-secret.sh SLACK_MIGRATIONS_WEBHOOK_URL`                                             | Nothing.                                                                                                                                 | It leaked (anyone with the URL can post to the channel)                                                                                                                        |
| Grafana `admin-password`       | `rotate-secret.sh --grafana admin-password`                                                 | The Grafana admin logs in with the new password.                                                                                         | It leaked; someone with access leaves                                                                                                                                          |
| age private keys               | [manual, below](#rotate-an-age-key)                                                         | Nothing.                                                                                                                                 | A key leaked, or someone holding it leaves                                                                                                                                     |
| DB / Redis passwords           | `rotate-datastore-password.sh` `db`, `db-admin`, `redis` ([below](#db-and-redis-passwords)) |                                                                                                                                          |                                                                                                                                                                                |

!!! warning "If the admin password leaks, rotate `JWT_SECRET_KEY` too"

    Changing `ADMIN_PASSWORD_HASH` alone does **not** lock out whoever has the old password.
    The admin has no database row, so there is no per-user revocation like participants and
    mentors have: any admin session opened with the leaked password stays valid until it
    expires (`JWT_EXPIRY_DAYS`, 3 days by default). The only way to end those sessions is to
    rotate `JWT_SECRET_KEY`, which invalidates **every** login token, so **everyone is logged
    out**: all participants, all mentors and the admin. Do both, in this order, per environment:

    ```bash
    ENV=prod bash infra/k8s/scripts/rotate-secret.sh ADMIN_PASSWORD_HASH
    ENV=prod bash infra/k8s/scripts/rotate-secret.sh JWT_SECRET_KEY --generate
    ```

    During the event, warn participants and mentors first; they only need to log in again.
    Nothing else is lost (teams, applications and preferences live in the database).

Notes per secret:

- **`ADMIN_PASSWORD_HASH`**: give the script the **password**, not a hash. It needs at least
  12 characters (the app's own minimum), is bcrypt-hashed locally (cost 12, needs
  `python3-bcrypt`) and only the hash is stored. Piped input that already is a bcrypt hash is
  stored as-is. On a leak, also rotate `JWT_SECRET_KEY` (warning above); the script reminds you.
- **`MAIL_PASSWORD`** is a Gmail app password of the account in `MAIL_USERNAME`. Create the new
  app password in that Google account, rotate, check that a password-reset mail arrives, then
  revoke the old app password.
- **`DISCORD_BUG_WEBHOOK_URL`**: create a new webhook in the Discord channel settings, rotate,
  send a test bug report, then delete the old webhook.
- **`SLACK_BUG_WEBHOOK_URL`** and **`SLACK_MIGRATIONS_WEBHOOK_URL`**: add a new webhook for
  the same channel under the Slack app's Incoming Webhooks, rotate, then remove the old one
  there. A test bug report (or the next migration run) confirms it.
- `--generate` is refused for `ADMIN_PASSWORD_HASH` (nobody would know the password), and an
  empty value is always refused. To clear an optional secret, edit the file with `sops`.

Other options: `RESTART=false` skips the restart (restart yourself later), and `NAMESPACE`,
`SECRETS_ENC`, `SECRET_NAME`, `RESTART_TARGET` override the defaults. The script still
refuses to write a file whose manifest namespace doesn't match `ENV`.

### Grafana admin password

```bash
ENV=prod bash infra/k8s/scripts/rotate-secret.sh --grafana admin-password
```

`--grafana` targets the env's `grafana-secret.enc.yaml` (namespace `monitoring`, restarts
`deployment/kps-grafana`). Updating the Secret alone is **not enough**: Grafana reads
`GF_SECURITY_ADMIN_PASSWORD` only on its very first start, when it creates its database on
the PVC, and ignores it after that. (Verified against `grafana/grafana:12.0.0`: after an env
change and restart the new password is rejected and the old one still works.) So the script
also runs `grafana cli admin reset-admin-password --password-from-stdin` in the pod, which
changes the password stored in the database. Log in with the new password to confirm. If
that last step fails, the Secret is already rotated but the old password still works: re-run
the same command.

`admin-user` has the same first-start-only behaviour and the CLI can't rename the account, so
rotating it only changes the Secret; rename the account in Grafana's UI to match.

### Rotate an age key

Each environment's SOPS files are encrypted to one age key (`.sops.yaml`). Replace it when the
private key may have leaked or when someone who holds it leaves. Example for staging; for
prod use the `infra/k8s/secrets/` files and `SOPS_AGE_KEY_PROD`.

```bash
# 1. New key pair, appended next to the old one (keep the old one until step 5).
(umask 077 && age-keygen >> ~/.config/sops/age/keys.txt)   # prints "Public key: age1…"

# 2. In .sops.yaml, replace the old age1… recipient in BOTH staging rules
#    (secrets.enc.yaml and grafana-secret.enc.yaml) with the new one.

# 3. Re-wrap both files to the new key (needs the old key, still in keys.txt):
sops updatekeys -y infra/k8s/overlays/staging/secrets/secrets.enc.yaml
sops updatekeys -y infra/k8s/overlays/staging/secrets/grafana-secret.enc.yaml
grep recipient infra/k8s/overlays/staging/secrets/*.enc.yaml   # only the new age1… is listed

# 4. Commit and push .sops.yaml and both files.

# 5. Hand out the new private key and retire the old one:
#    Replace the old AGE-SECRET-KEY-1… line in the password manager with the new one. On every
#    machine that deploys staging, add the new line to keys.txt (bootstrap.sh does it from its
#    prompt or SOPS_AGE_KEY_STAGING) and delete the old key's lines.
```

`updatekeys` changes who can decrypt, not the values. Anyone holding the **old** key can still
decrypt every old version of these files from git history, so if the old key leaked, also
rotate every secret of that environment from the table above, including Grafana's.

### DB and Redis passwords

These live only in the cluster (Secrets `fmi-codes-db` and `fmi-codes-redis`, generated by
`deploy-stateful.sh`), never in git. Rotate them without losing data:

```bash
ENV=prod bash infra/k8s/scripts/rotate-datastore-password.sh db         # Postgres app role (fmi_app)
ENV=prod bash infra/k8s/scripts/rotate-datastore-password.sh db-admin   # Postgres superuser
ENV=prod bash infra/k8s/scripts/rotate-datastore-password.sh redis      # Redis + Sentinel
```

The script generates the new password itself; nobody sees it, it never appears in an argument
or the output, and there is nothing to commit. **Never** delete the Secret together with its
PVC to "rotate" (the reset in [Phase 2](#2--stateful-tier-postgres--redis-sentinel)): that
wipes the data.

| Target     | What the script does                                                                                                                                                                                                                                                                                                                 | What users notice                                                                                                                                                                                                                                        |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `db`       | Parks the new password in the Secret as `password-next`, runs `ALTER ROLE` as the superuser with a SCRAM hash computed locally (the plaintext never reaches Postgres or its logs), checks that the new password logs in and the old one is rejected, makes it live, restarts the backend.                                            | Nothing. For a few seconds old backend pods can't open _new_ connections; their pooled ones keep working. The migration initContainer and the manual migrate Job read the Secret when they start.                                                        |
| `db-admin` | The same for the `postgres` superuser (`postgres-password`). Nothing in the app uses it, so nothing restarts.                                                                                                                                                                                                                        | Nothing.                                                                                                                                                                                                                                                 |
| `redis`    | Scales the StatefulSet to 0 and deletes its pods, waits until **none** is left, updates the Secret, scales back to `replica.replicaCount` from the Helm values, checks that every node takes only the new password, there is exactly one master, the replicas are linked and every Sentinel names that master, restarts the backend. | **Redis is unavailable for about 25 to 30 s** (the run takes about 100 s). The app keeps working without it ([ADR-003](adr/003-redis-optional-fail-open.md)): rate limits fall back to per-process, the logout blocklist is not checked and caches miss. |

Why the Postgres password needs `ALTER ROLE`: it is stored in the database on the volume, so
changing only the Secret breaks every new connection. Why Redis is stopped completely instead
of restarted pod by pod: every Redis and Sentinel process has to switch at the same moment. If a
new pod starts while an old one is still running or terminating, the new Sentinel asks the old
one for the master, gets `WRONGPASS`, records a master literally named `NOAUTH`, and the
StatefulSet deadlocks in `CrashLoopBackOff`. That happened in testing, which is why the script
waits for zero pods before touching the Secret. Redis data survives on its volume (AOF); after
the restart `redis-node-0` is the master, so writes that had not reached it before the stop
(caches, rate-limit counters, recent logouts) can be lost.

**If a run dies halfway, run the same command again.** `db` and `db-admin` resume with the
password parked in `<key>-next` (including when the `ALTER ROLE` already happened); `redis`
reads the replica count from the values file, so it also repairs a Redis left at 0 replicas
or stuck in `CrashLoopBackOff`.

When to rotate: someone with cluster access leaves, a kubeconfig or machine is lost, or a
password was exposed (pasted while debugging, in a screenshot). During the event prefer a quiet
moment for `redis` because of the short degraded window; `db` and `db-admin` have no visible
effect. Verified on a local k3s `v1.36.2` with the repo's chart versions and staging values:
repeated rotations; resume before and after `ALTER ROLE`, from Redis at 0 replicas and from
Redis in `CrashLoopBackOff`; a frozen unhealthy replica; failover afterward; data intact
throughout.

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
`kubectl -n $NS exec postgres-0 -- psql -U fmi_app -d <db> -c '\dt'` (the Owner column).

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
