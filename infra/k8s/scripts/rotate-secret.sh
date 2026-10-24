#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
GRAFANA=false
GENERATE=false
KEY=""

die() { echo "Error: $1" >&2; exit 1; }
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [--grafana] KEY [--generate]

Rotate a single key in a SOPS-encrypted secret, re-apply it to the cluster,
and restart the workload so pods pick up the new value.

  KEY         A stringData key in the env's secrets.enc.yaml
              (SECRET_KEY, JWT_SECRET_KEY, ADMIN_PASSWORD_HASH,
              MAIL_PASSWORD, DISCORD_BUG_WEBHOOK_URL),
              or with --grafana: admin-password.
  --generate  Use a strong random value (SECRET_KEY, JWT_SECRET_KEY).
  --grafana   Rotate the env's grafana-secret.enc.yaml (namespace monitoring,
              restarts deployment/kps-grafana). For admin-password it also
              resets the password stored in Grafana's database, because
              Grafana only reads the secret on its very first start.

The value is never taken as an argument (that leaks it into shell history and
ps). Without --generate it is read from:
  - a hidden prompt, typed twice, when run in a terminal
  - stdin when piped, e.g.  pass show fmi/mail | $(basename "$0") MAIL_PASSWORD
    (one trailing newline is stripped)

ADMIN_PASSWORD_HASH takes the admin PASSWORD (min 12 chars) and stores its
bcrypt hash. Input that already is a bcrypt hash is stored as-is.

Env overrides: ENV (prod|staging, default staging), NAMESPACE, SECRETS_ENC,
SECRET_NAME, RESTART_TARGET, RESTART (true|false).

Examples:
  $(basename "$0") JWT_SECRET_KEY --generate
  ENV=prod $(basename "$0") ADMIN_PASSWORD_HASH
  $(basename "$0") DISCORD_BUG_WEBHOOK_URL < webhook.txt
  ENV=prod $(basename "$0") --grafana admin-password
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --generate) GENERATE=true; shift ;;
    --grafana) GRAFANA=true; shift ;;
    -*) die "unknown option '$1' (see --help)" ;;
    *)
      [ -z "$KEY" ] || die "unexpected argument after $KEY. Values are no longer accepted as arguments (they leak into shell history and ps); run without it to be prompted, or pipe it on stdin. See --help."
      KEY="$1"; shift ;;
  esac
done
[ -n "$KEY" ] || { usage; exit 1; }

case "$ENV" in
  prod)    DEFAULT_NAMESPACE="fmi-codes"; SECRETS_REL="secrets" ;;
  staging) DEFAULT_NAMESPACE="fmi-codes-staging"; SECRETS_REL="overlays/staging/secrets" ;;
  *)       die "ENV must be 'prod' or 'staging', got '$ENV'." ;;
esac
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ "$GRAFANA" = "true" ]; then
  NAMESPACE="${NAMESPACE:-monitoring}"
  SECRETS_ENC="${SECRETS_ENC:-$K8S_DIR/$SECRETS_REL/grafana-secret.enc.yaml}"
  SECRET_NAME="${SECRET_NAME:-grafana-admin}"
  RESTART_TARGET="${RESTART_TARGET:-deployment/kps-grafana}"
else
  NAMESPACE="${NAMESPACE:-$DEFAULT_NAMESPACE}"
  SECRETS_ENC="${SECRETS_ENC:-$K8S_DIR/$SECRETS_REL/secrets.enc.yaml}"
  SECRET_NAME="${SECRET_NAME:-fmi-codes-app}"
  RESTART_TARGET="${RESTART_TARGET:-deployment/backend}"
fi
RESTART="${RESTART:-true}"

command -v sops    >/dev/null 2>&1 || die "sops not found — run install-tools.sh first."
command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
command -v python3 >/dev/null 2>&1 || die "python3 not found — sudo apt-get install -y python3"
[[ "$(sops set --help 2>&1 || true)" == *--value-stdin* ]] \
  || die "this sops has no 'set --value-stdin'; replace it with the version install-tools.sh pins (sudo rm \"$(command -v sops)\" && bash $SCRIPT_DIR/install-tools.sh)."
[ -f "$SECRETS_ENC" ] || die "missing $SECRETS_ENC"

sops --decrypt "$SECRETS_ENC" >/dev/null 2>&1 \
  || die "cannot decrypt $SECRETS_ENC — is your age key at ~/.config/sops/age/keys.txt?"

secret_ns="$(sops --decrypt "$SECRETS_ENC" | grep -E '^[[:space:]]+namespace:' | head -1 | awk '{print $2}' || true)"
[ "$secret_ns" = "$NAMESPACE" ] \
  || die "$SECRETS_ENC targets namespace '${secret_ns:-<none>}' but ENV=$ENV expects '$NAMESPACE' — refusing to rotate across environments."

sops --decrypt "$SECRETS_ENC" \
  | grep -qE "^[[:space:]]+$(printf '%s' "$KEY" | sed 's/[.[\*^$/]/\\&/g'):" \
  || die "key '$KEY' not found in $SECRETS_ENC stringData."

if [ "$GENERATE" = "true" ]; then
  [ "$KEY" != "ADMIN_PASSWORD_HASH" ] || die "--generate makes no sense for ADMIN_PASSWORD_HASH; you need to know the password."
  VALUE="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
  log "Generated a strong random value for $KEY."
elif [ -t 0 ]; then
  printf 'New value for %s (input hidden): ' "$KEY"
  VALUE=""; read -rs VALUE || true; echo
  printf 'Repeat it: '
  CONFIRM=""; read -rs CONFIRM || true; echo
  [ "$VALUE" = "$CONFIRM" ] || die "the two entries differ; nothing changed."
  unset CONFIRM
else
  VALUE="$(cat)"
  VALUE="${VALUE%$'\r'}"
fi
[ -n "$VALUE" ] || die "empty value; nothing changed. Use --generate for a random one, or edit with: sops $SECRETS_ENC"

if [ "$KEY" = "ADMIN_PASSWORD_HASH" ] && ! [[ "$VALUE" =~ ^\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{53}$ ]]; then
  [ "${#VALUE}" -ge 12 ] || die "admin password must be at least 12 characters (the app's own minimum)."
  python3 -c 'import bcrypt' 2>/dev/null || die "python3-bcrypt missing — sudo apt-get install -y python3-bcrypt"
  ADMIN_PASSWORD="$VALUE"
  VALUE="$(ADMIN_PASSWORD="$ADMIN_PASSWORD" python3 -c \
    'import bcrypt,os;print(bcrypt.hashpw(os.environ["ADMIN_PASSWORD"].encode(),bcrypt.gensalt(12)).decode())')"
  unset ADMIN_PASSWORD
fi

log "Rotating '$KEY' in $SECRETS_ENC"
VALUE="$VALUE" python3 -c 'import json,os;print(json.dumps(os.environ["VALUE"]))' \
  | sops set --value-stdin "$SECRETS_ENC" "[\"stringData\"][\"$KEY\"]"

log "Applying updated secret from $SECRETS_ENC"
sops --decrypt "$SECRETS_ENC" | kubectl apply -f -

if [ "$RESTART" = "true" ]; then
  log "Restarting $RESTART_TARGET so pods pick up the rotated value"
  kubectl -n "$NAMESPACE" rollout restart "$RESTART_TARGET"
  kubectl -n "$NAMESPACE" rollout status "$RESTART_TARGET" --timeout=120s
else
  echo "RESTART=false — skipping rollout restart. Restart manually to apply:"
  echo "  kubectl -n $NAMESPACE rollout restart $RESTART_TARGET"
fi

if [ "$GRAFANA" = "true" ] && [ "$KEY" = "admin-password" ]; then
  log "Resetting the password stored in Grafana's database"
  printf '%s' "$VALUE" | kubectl -n "$NAMESPACE" exec -i "$RESTART_TARGET" -c grafana -- \
    grafana cli admin reset-admin-password --password-from-stdin \
    || die "secret rotated, but resetting Grafana's stored password failed; the old password still logs in. Re-run this command."
elif [ "$GRAFANA" = "true" ] && [ "$KEY" = "admin-user" ]; then
  echo "Note: Grafana only reads admin-user on its first start; rename the account in Grafana's UI to match."
fi
unset VALUE

case "$KEY" in
  JWT_SECRET_KEY)
    echo "Every login token is now invalid: all participants, mentors and the admin must log in again." ;;
  ADMIN_PASSWORD_HASH)
    echo "Admin sessions issued before this stay valid until they expire (JWT_EXPIRY_DAYS)."
    echo "If the old password may have leaked, also run: ENV=$ENV $(basename "$0") JWT_SECRET_KEY --generate" ;;
esac

log "Done. Commit the updated $SECRETS_ENC so the change is the new source of truth."
