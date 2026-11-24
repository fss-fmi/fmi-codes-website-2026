# Secrets

Every secret the cluster uses, where it lives and how to rotate it. Which secrets exist and how
a fresh bootstrap sets them: [Know what secrets exist](index.md#2-know-what-secrets-exist-and-where-they-live).

## SOPS and age

App secrets have a git-committed, encrypted single source of truth. SOPS encrypts only the
_values_ (keys stay readable, so a diff shows _which_ secret changed), using [age](https://github.com/FiloSottile/age)
as the backend — each dev holds an age key pair, SOPS encrypts to every public recipient in
`.sops.yaml`. **Only the SOPS-encrypted file belongs in git** — a plain k8s Secret's `data:`
is base64, not encryption, and `base64 -d` reveals it instantly.

DB/Redis passwords are deliberately **not** in SOPS — they're PVC-coupled and generated
in-cluster ([Phase 2](index.md#2--stateful-tier-postgres--redis-sentinel)). SOPS owns the
`fmi-codes-app` values, the cluster-wide Grafana admin, Tailscale OAuth, Alertmanager webhook
and Flux Relay secrets ([Phase 7](index.md#7--observability-prometheus--grafana)), prod's
Cloudflare Tunnel credentials ([Set up the tunnel](cloudflare.md#set-up-the-tunnel)) and each
env's mentor seed ([Mentor seed](#mentor-seed)).

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

**Add / remove a recipient:** edit the `age:` list in `.sops.yaml`, then
`sops updatekeys -y <file>` for each of the env's files (re-wraps the data key, no value
change, no rollout). On **removal** also rotate every value — the departing dev still has the
old ciphertext in git history. Replacing a key end to end:
[Rotate an age key](#rotate-an-age-key).

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

| Secret                         | Rotate with                                                                                       | What users notice                                                                                                                        | Rotate when                                                                                                       |
| ------------------------------ | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `SECRET_KEY`                   | `rotate-secret.sh SECRET_KEY --generate`                                                          | Nothing. Flask's key; nothing in the app signs with it today (reset and verification links are random tokens stored as hashes).          | It may have leaked                                                                                                |
| `JWT_SECRET_KEY`               | `rotate-secret.sh JWT_SECRET_KEY --generate`                                                      | **Everyone is logged out**: participants, mentors and the admin.                                                                         | It may have leaked; after an admin password leak (see next row)                                                   |
| `ADMIN_PASSWORD_HASH`          | `rotate-secret.sh ADMIN_PASSWORD_HASH`                                                            | The admin logs in with the new password. Admin sessions already open **stay valid** until they expire (`JWT_EXPIRY_DAYS`, 3 by default). | When an organizer with the password leaves; on a leak, **together with `JWT_SECRET_KEY`** (see the warning below) |
| `MAIL_PASSWORD`                | `rotate-secret.sh MAIL_PASSWORD`                                                                  | Nothing; mail keeps working after the restart.                                                                                           | Google revoked it or it leaked                                                                                    |
| `DISCORD_BUG_WEBHOOK_URL`      | `rotate-secret.sh DISCORD_BUG_WEBHOOK_URL`                                                        | Nothing.                                                                                                                                 | It leaked (anyone with the URL can post to the channel)                                                           |
| `SLACK_BUG_WEBHOOK_URL`        | `rotate-secret.sh SLACK_BUG_WEBHOOK_URL`                                                          | Nothing.                                                                                                                                 | It leaked (anyone with the URL can post to the channel)                                                           |
| `SLACK_MIGRATIONS_WEBHOOK_URL` | `rotate-secret.sh SLACK_MIGRATIONS_WEBHOOK_URL`                                                   | Nothing.                                                                                                                                 | It leaked (anyone with the URL can post to the channel)                                                           |
| `SLACK_EVENTS_WEBHOOK_URL`     | `rotate-secret.sh SLACK_EVENTS_WEBHOOK_URL`                                                       | Nothing.                                                                                                                                 | It leaked (anyone with the URL can post to the channel)                                                           |
| Grafana `admin-password`       | `rotate-secret.sh --grafana admin-password`                                                       | The Grafana admin logs in with the new password.                                                                                         | It leaked; someone with access leaves                                                                             |
| Tailscale OAuth client         | `rotate-secret.sh --tailscale client_id`, then `client_secret` ([below](#tailscale-oauth-client)) | Nothing; the operator restarts and Grafana and staging keep their tailnet addresses.                                                     | It leaked; someone with cluster or admin-console access leaves                                                    |
| Cluster alerts webhooks        | `rotate-secret.sh --alertmanager cluster_url` / `staging_url`                                     | Nothing; no restart.                                                                                                                     | It leaked (anyone with the URL can post to the channel)                                                           |
| Flux Relay bot token           | `rotate-secret.sh --flux-relay bot_token`                                                         | Nothing; no restart.                                                                                                                     | It leaked (it can read and post in both alert channels)                                                           |
| `FRONTEND_ORIGIN` (staging)    | `ENV=staging rotate-secret.sh FRONTEND_ORIGIN`                                                    | New reset and verification emails link to the new address.                                                                               | Staging's tailnet address changed (new tailnet, or it joined as `staging-1`)                                      |
| age private keys               | [manual, below](#rotate-an-age-key)                                                               | Nothing.                                                                                                                                 | A key leaked, or someone holding it leaves                                                                        |
| Cloudflare Tunnel credentials  | a new tunnel, [Cloudflare Tunnel credentials](cloudflare.md#cloudflare-tunnel-credentials)        | Nothing: a temporary second `cloudflared` serves the new tunnel while DNS moves.                                                         | They leaked (anyone with them can serve `fmicodes.com`)                                                           |
| DB / Redis passwords           | `rotate-datastore-password.sh` `db`, `db-admin`, `redis` ([below](#db-and-redis-passwords))       |                                                                                                                                          |                                                                                                                   |

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
- **`SLACK_BUG_WEBHOOK_URL`**, **`SLACK_MIGRATIONS_WEBHOOK_URL`** and
  **`SLACK_EVENTS_WEBHOOK_URL`**: add a new webhook for the same channel under the Slack app's
  Incoming Webhooks, rotate, then remove the old one there. A test bug report, the next
  migration run or a flag switched off and on again on staging confirms it.
- **Cluster alerts webhooks** (`--alertmanager cluster_url` or `staging_url`): same steps for that
  channel. The staging webhook sits in both envs' files, so rotate `staging_url` in each. The
  script also updates Flux's copy (`flux-system/flux-slack` or `flux-slack-staging`). The test in
  [Cluster alerts](alerts.md#cluster-alerts) confirms it.
- **Flux Relay bot token** (`--flux-relay bot_token`): on the Flux Relay app's **OAuth &
  Permissions** page, revoke the token (**Revoke All OAuth Tokens**) and reinstall the app to
  get a new one, then rotate it in both envs' files. If the bot left the alert channels,
  `/invite @Flux Relay` again. The test in [Recovery replies](alerts.md#recovery-replies) confirms it.
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

### Tailscale OAuth client

```bash
RESTART=false bash infra/k8s/scripts/rotate-secret.sh --tailscale client_id
bash infra/k8s/scripts/rotate-secret.sh --tailscale client_secret
```

An OAuth client's ID and secret come as a pair, so a rotation always replaces both: create a
new client in the admin console with the same scopes and tag as the old one
([Tailscale setup](tailscale.md#tailscale-setup-once-per-tailnet), step 5), run the two commands back to back
(the first skips the restart so the running operator isn't restarted onto a half-updated
pair), confirm
`kubectl -n tailscale get pods` shows the operator Running again, then revoke the old client.
`--tailscale` targets staging's `tailscale-oauth.enc.yaml` on every cluster, prod's included
(namespace `tailscale`, restarts `deployment/operator`); an `ENV=prod` is ignored with a note
([One Tailscale client for every cluster](tailscale.md#one-tailscale-client-for-every-cluster)). It refuses
to overwrite a Secret that isn't labelled `staging`.

### Mentor seed

The mentor roster (names, emails, phones and any starting passwords) is personal data, so it
lives only in the SOPS-encrypted Secret `fmi-codes-mentors-seed`, key `mentors.json`, a JSON list
in the format the loader reads: `infra/k8s/overlays/staging/secrets/mentors-seed.enc.yaml`
(staging's 20 mentors) and `infra/k8s/secrets/mentors-seed.enc.yaml`
(prod, `[]` until the 2027 roster). The backend mounts it at `/etc/fmi-codes/mentors/` and seeds
from it on every start. Production config has no other seed, so an unset, missing or broken
file logs a warning or an error and seeds nobody, without blocking the rollout.

An entry with no `password` gets no password at all: that mentor can't log in until they set
one through forgot password, which needs `MAIL_PASSWORD` in that env. Seed the 2027 roster that
way, never with a shared password.

To change it (`rotate-secret.sh` doesn't handle this one):

```bash
sops infra/k8s/overlays/staging/secrets/mentors-seed.enc.yaml   # opens the decrypted Secret in $EDITOR
ENV=staging bash infra/k8s/scripts/deploy-app.sh                 # applies it (Flux on or off)
#   or: sops -d <file> | kubectl apply -f -
kubectl -n fmi-codes-staging rollout restart deployment/backend --field-manager=fmi-codes-scripts
```

Commit the `.enc.yaml` afterwards. Seeding only inserts mentors who aren't there yet (matched
by email, or by name and company), so an edit never changes or removes a mentor that already
exists: change those in the database. Without Flux, `deploy-app.sh` restarts the backend
itself. The image never carries the real seed: `backend/database/seeds/mentors.json` is
gitignored and excluded by `backend/.dockerignore`.

### Rotate an age key

Each environment's SOPS files are encrypted to one age key (`.sops.yaml`). Replace it when the
private key may have leaked or when someone who holds it leaves. The example is for staging,
which has six files. Prod has six too (`cloudflared-tunnel.enc.yaml` in place of
`tailscale-oauth.enc.yaml`): use its six rules, the six `infra/k8s/secrets/` files and
`SOPS_AGE_KEY_PROD`.

```bash
# 1. New key pair, appended next to the old one (keep the old one until step 5).
(umask 077 && age-keygen >> ~/.config/sops/age/keys.txt)   # prints "Public key: age1…"

# 2. In .sops.yaml, replace the old age1… recipient in the six staging rules
#    (secrets.enc.yaml, grafana-secret.enc.yaml, tailscale-oauth.enc.yaml,
#    alertmanager-slack.enc.yaml, flux-relay-slack.enc.yaml, mentors-seed.enc.yaml) with the
#    new one.

# 3. Re-wrap the six files to the new key (needs the old key, still in keys.txt):
sops updatekeys -y infra/k8s/overlays/staging/secrets/secrets.enc.yaml
sops updatekeys -y infra/k8s/overlays/staging/secrets/grafana-secret.enc.yaml
sops updatekeys -y infra/k8s/overlays/staging/secrets/tailscale-oauth.enc.yaml
sops updatekeys -y infra/k8s/overlays/staging/secrets/alertmanager-slack.enc.yaml
sops updatekeys -y infra/k8s/overlays/staging/secrets/flux-relay-slack.enc.yaml
sops updatekeys -y infra/k8s/overlays/staging/secrets/mentors-seed.enc.yaml
grep recipient infra/k8s/overlays/staging/secrets/*.enc.yaml   # only the new age1… is listed

# 4. Commit and push .sops.yaml and the six files.

# 5. Hand out the new private key and retire the old one:
#    Replace the old AGE-SECRET-KEY-1… line in the password manager with the new one. On every
#    machine that deploys staging, and every prod machine (it reads staging's Tailscale file),
#    add the new line to keys.txt (bootstrap.sh does it from its prompt or
#    SOPS_AGE_KEY_STAGING) and delete the old key's lines.
```

`updatekeys` changes who can decrypt, not the values. Anyone holding the **old** key can still
decrypt every old version of these files from git history, so if the old key leaked, also
rotate every secret of that environment from the table above, including Grafana's, the Flux
Relay bot token and, for the staging key, the Tailscale OAuth client.

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
PVC to "rotate" (the reset in [Phase 2](index.md#2--stateful-tier-postgres--redis-sentinel)): that
wipes the data.

| Target     | What the script does                                                                                                                                                                                                                                                                                                                 | What users notice                                                                                                                                                                                                                                           |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `db`       | Parks the new password in the Secret as `password-next`, runs `ALTER ROLE` as the superuser with a SCRAM hash computed locally (the plaintext never reaches Postgres or its logs), checks that the new password logs in and the old one is rejected, makes it live, restarts the backend.                                            | Nothing. For a few seconds old backend pods can't open _new_ connections; their pooled ones keep working. The migration initContainer and the manual migrate Job read the Secret when they start.                                                           |
| `db-admin` | The same for the `postgres` superuser (`postgres-password`). Nothing in the app uses it, so nothing restarts.                                                                                                                                                                                                                        | Nothing.                                                                                                                                                                                                                                                    |
| `redis`    | Scales the StatefulSet to 0 and deletes its pods, waits until **none** is left, updates the Secret, scales back to `replica.replicaCount` from the Helm values, checks that every node takes only the new password, there is exactly one master, the replicas are linked and every Sentinel names that master, restarts the backend. | **Redis is unavailable for about 25 to 30 s** (the run takes about 100 s). The app keeps working without it ([ADR-003](../adr/003-redis-optional-fail-open.md)): rate limits fall back to per-process, the logout blocklist is not checked and caches miss. |

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

## Forking: use your own keys

Only if you're standing up your _own_ project rather than deploying this one. The repo ships
two committed age recipients (staging + prod) in `.sops.yaml`. Without the org's private keys
you can't decrypt the committed files, so `sops updatekeys` won't work for you: mint your own
key, point `.sops.yaml` at it and replace that env's encrypted files with your own values.

```bash
# 1. Generate a key pair. Appends, so an existing keys.txt is kept (age-keygen -o refuses
#    to write to an existing file). Prints "Public key: age1…" on stderr.
mkdir -p ~/.config/sops/age
(umask 077 && age-keygen >> ~/.config/sops/age/keys.txt)

# 2. In .sops.yaml, set the `age:` recipient of every rule for your env to that age1… value:
#    secrets.enc.yaml, grafana-secret.enc.yaml, alertmanager-slack.enc.yaml,
#    flux-relay-slack.enc.yaml and mentors-seed.enc.yaml, plus tailscale-oauth.enc.yaml for
#    staging (and cloudflared-tunnel.enc.yaml for prod). tailscale-oauth has no
#    prod copy: every cluster reads staging's, so a prod-only fork still has to replace it and
#    use its staging key on prod.

# 3. Overwrite each of that env's .enc.yaml files with a plaintext Secret holding your values
#    (same metadata and stringData keys as the committed file; those stay readable), then
#    encrypt it in place. .sops.yaml picks the recipient by path:
sops --encrypt --in-place infra/k8s/overlays/staging/secrets/secrets.enc.yaml
sops --encrypt --in-place infra/k8s/overlays/staging/secrets/grafana-secret.enc.yaml
sops --encrypt --in-place infra/k8s/overlays/staging/secrets/tailscale-oauth.enc.yaml
sops --encrypt --in-place infra/k8s/overlays/staging/secrets/alertmanager-slack.enc.yaml
sops --encrypt --in-place infra/k8s/overlays/staging/secrets/flux-relay-slack.enc.yaml
sops --encrypt --in-place infra/k8s/overlays/staging/secrets/mentors-seed.enc.yaml
# mentors-seed holds your own roster as mentors.json, or "[]" (quoted) for none yet.
# (prod: the same files under infra/k8s/secrets/, minus tailscale-oauth; prod's
# cloudflared-tunnel.enc.yaml comes from your own tunnel, see cloudflare.md 'Set up the tunnel').
# tailscale-oauth can stay empty until your tailnet exists (tailscale.md 'Tailscale setup'),
# alertmanager-slack until you have a Slack webhook (alerts.md 'Setup'), flux-relay-slack until
# you have the Flux Relay app (alerts.md 'Set up the Flux Relay').
# Staging's secrets.enc.yaml also needs a FRONTEND_ORIGIN key: your
# https://staging.<tailnet>.ts.net, or "" until you know it.

# 4. Commit .sops.yaml + the encrypted files. Bootstrap checks keys by decrypting the files,
#    so it accepts YOUR key with no script changes.
```

You'll also want your own Docker Hub images and hostnames — see
[Forking to your own infra](index.md#forking-to-your-own-infra).
