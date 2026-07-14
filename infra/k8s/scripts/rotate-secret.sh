#!/usr/bin/env bash

set -euo pipefail

NAMESPACE="${NAMESPACE:-fmi-codes}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRETS_ENC="${SECRETS_ENC:-$K8S_DIR/secrets/secrets.enc.yaml}"
RESTART="${RESTART:-true}"

die() { echo "Error: $1" >&2; exit 1; }
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }

usage() {
  cat <<EOF
Usage: $(basename "$0") KEY [VALUE]

Rotate a single key in the SOPS-encrypted app secret, re-apply it to the
cluster, and restart the backend so pods pick up the new value.

  KEY     One of the stringData keys in secrets.enc.yaml
          (SECRET_KEY, JWT_SECRET_KEY, ADMIN_PASSWORD_HASH,
           MAIL_PASSWORD, DISCORD_BUG_WEBHOOK_URL).
  VALUE   The new value. If omitted, a strong random 64-char value is
          generated (use for SECRET_KEY / JWT_SECRET_KEY).

Env overrides: NAMESPACE ($NAMESPACE), SECRETS_ENC ($SECRETS_ENC),
RESTART (true|false — skip the rollout restart when false).

Examples:
  $(basename "$0") JWT_SECRET_KEY
  $(basename "$0") MAIL_PASSWORD 'my-smtp-app-password'
  ADMIN_PASSWORD_HASH rotation (generate the bcrypt hash first):
    HASH=\$(python3 -c "import bcrypt;print(bcrypt.hashpw(b'newpass', bcrypt.gensalt(12)).decode())")
    $(basename "$0") ADMIN_PASSWORD_HASH "\$HASH"
EOF
}

[ $# -ge 1 ] || { usage; exit 1; }
case "$1" in -h|--help) usage; exit 0 ;; esac

KEY="$1"
shift || true

command -v sops    >/dev/null 2>&1 || die "sops not found — run install-tools-wsl2.sh first."
command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools-wsl2.sh first."
[ -f "$SECRETS_ENC" ] || die "missing $SECRETS_ENC"

sops --decrypt "$SECRETS_ENC" >/dev/null 2>&1 \
  || die "cannot decrypt $SECRETS_ENC — is your age key at ~/.config/sops/age/keys.txt?"

sops --decrypt "$SECRETS_ENC" \
  | grep -qE "^[[:space:]]+$(printf '%s' "$KEY" | sed 's/[.[\*^$/]/\\&/g'):" \
  || die "key '$KEY' not found in $SECRETS_ENC stringData."

if [ $# -ge 1 ]; then
  VALUE="$1"
else
  command -v python3 >/dev/null 2>&1 \
    || die "no VALUE given and python3 not available to generate one."
  VALUE="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
  log "No value supplied — generated a strong random value for $KEY."
fi

VALUE_JSON="$(VALUE="$VALUE" python3 -c 'import json,os;print(json.dumps(os.environ["VALUE"]))')"

log "Rotating '$KEY' in $SECRETS_ENC"
sops set "$SECRETS_ENC" "[\"stringData\"][\"$KEY\"]" "$VALUE_JSON"

log "Applying updated secret from $SECRETS_ENC"
sops --decrypt "$SECRETS_ENC" | kubectl apply -f -

if [ "$RESTART" = "true" ]; then
  log "Restarting backend so pods pick up the rotated value"
  kubectl -n "$NAMESPACE" rollout restart deployment/backend
  kubectl -n "$NAMESPACE" rollout status deployment/backend --timeout=120s
else
  echo "RESTART=false — skipping rollout restart. Restart manually to apply:"
  echo "  kubectl -n $NAMESPACE rollout restart deployment/backend"
fi

log "Done. Commit the updated $SECRETS_ENC so the change is the new source of truth."
