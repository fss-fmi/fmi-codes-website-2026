#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
GRAFANA=false
TAILSCALE=false
ALERTMANAGER=false
FLUX_RELAY=false
GENERATE=false
KEY=""

die() { echo "Error: $1" >&2; exit 1; }
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [--grafana|--tailscale|--alertmanager|--flux-relay] KEY [--generate]

Rotate a single key in a SOPS-encrypted secret, re-apply it to the cluster,
and restart the workload so pods pick up the new value.

  KEY         A stringData key in the env's secrets.enc.yaml
              (SECRET_KEY, JWT_SECRET_KEY, ADMIN_PASSWORD_HASH,
              MAIL_PASSWORD, DISCORD_BUG_WEBHOOK_URL,
              SLACK_BUG_WEBHOOK_URL, SLACK_MIGRATIONS_WEBHOOK_URL, and on
              staging FRONTEND_ORIGIN, its tailnet URL),
              with --grafana: admin-password,
              with --tailscale: client_id or client_secret,
              with --alertmanager: cluster_url or staging_url,
              with --flux-relay: bot_token, cluster_channel or staging_channel.
  --generate  Use a strong random value (SECRET_KEY, JWT_SECRET_KEY).
  --grafana   Rotate the env's grafana-secret.enc.yaml (namespace monitoring,
              restarts deployment/kps-grafana). For admin-password it also
              resets the password stored in Grafana's database, because
              Grafana only reads the secret on its very first start.
  --tailscale Rotate staging's tailscale-oauth.enc.yaml, the operator's OAuth
              client (namespace tailscale, restarts deployment/operator). Every
              cluster, prod's included, uses staging's client, so ENV is ignored.
  --alertmanager
              Set a cluster-alerts incoming webhook in the env's
              alertmanager-slack.enc.yaml (namespace monitoring) and copy it
              for Flux: cluster_url (this cluster's channel, shared alerts included)
              to flux-system/flux-slack, staging_url (the staging channel) to
              flux-system/flux-slack-staging. Nothing restarts: Alertmanager
              and Flux read them on every send.
  --flux-relay
              Set the Flux Relay's Slack bot token or a channel ID in the env's
              flux-relay-slack.enc.yaml (namespace flux-system). cluster_channel
              is the channel cluster_url posts to, staging_channel staging_url's.
              Nothing restarts: the relay rereads the Secret.

The Grafana, Tailscale, Alertmanager and Flux Relay Secrets are cluster-wide, so the
script refuses to overwrite one that holds the other env's credentials
(ALLOW_ENV_SWITCH=true switches on purpose). The Tailscale one must hold staging's,
whatever ENV is.

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
  $(basename "$0") --tailscale client_secret
  ENV=prod $(basename "$0") --alertmanager cluster_url
  ENV=prod $(basename "$0") --alertmanager staging_url
  ENV=prod $(basename "$0") --flux-relay bot_token
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --generate) GENERATE=true; shift ;;
    --grafana) GRAFANA=true; shift ;;
    --tailscale) TAILSCALE=true; shift ;;
    --alertmanager) ALERTMANAGER=true; shift ;;
    --flux-relay) FLUX_RELAY=true; shift ;;
    -*) die "unknown option '$1' (see --help)" ;;
    *)
      [ -z "$KEY" ] || die "unexpected argument after $KEY. Values are no longer accepted as arguments (they leak into shell history and ps); run without it to be prompted, or pipe it on stdin. See --help."
      KEY="$1"; shift ;;
  esac
done
[ -n "$KEY" ] || { usage; exit 1; }
TARGETS=0
for flag in "$GRAFANA" "$TAILSCALE" "$ALERTMANAGER" "$FLUX_RELAY"; do [ "$flag" = "false" ] || TARGETS=$((TARGETS + 1)); done
[ "$TARGETS" -le 1 ] || die "--grafana, --tailscale, --alertmanager and --flux-relay target different secrets; pick one."

case "$ENV" in
  prod)    DEFAULT_NAMESPACE="fmi-codes"; SECRETS_REL="secrets" ;;
  staging) DEFAULT_NAMESPACE="fmi-codes-staging"; SECRETS_REL="overlays/staging/secrets" ;;
  *)       die "ENV must be 'prod' or 'staging', got '$ENV'." ;;
esac
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# The env whose copy the Secret holds; only the Tailscale client differs from ENV.
SECRET_ENV="$ENV"
if [ "$GRAFANA" = "true" ]; then
  NAMESPACE="${NAMESPACE:-monitoring}"
  SECRETS_ENC="${SECRETS_ENC:-$K8S_DIR/$SECRETS_REL/grafana-secret.enc.yaml}"
  SECRET_NAME="${SECRET_NAME:-grafana-admin}"
  RESTART_TARGET="${RESTART_TARGET:-deployment/kps-grafana}"
elif [ "$TAILSCALE" = "true" ]; then
  # shellcheck source=lib/tailscale-client.sh
  . "$SCRIPT_DIR/lib/tailscale-client.sh"
  NAMESPACE="${NAMESPACE:-tailscale}"
  SECRETS_ENC="${SECRETS_ENC:-$K8S_DIR/$TS_CLIENT_REL}"
  SECRET_NAME="${SECRET_NAME:-operator-oauth}"
  RESTART_TARGET="${RESTART_TARGET:-deployment/operator}"
  SECRET_ENV=staging
  [ "$ENV" = "staging" ] || echo "Note: the Tailscale client is staging's on every cluster, so ENV=$ENV doesn't change which file is rotated." >&2
elif [ "$ALERTMANAGER" = "true" ]; then
  NAMESPACE="${NAMESPACE:-monitoring}"
  SECRETS_ENC="${SECRETS_ENC:-$K8S_DIR/$SECRETS_REL/alertmanager-slack.enc.yaml}"
  SECRET_NAME="${SECRET_NAME:-alertmanager-slack}"
  RESTART_TARGET="${RESTART_TARGET:-}"
  case "$KEY" in
    cluster_url|staging_url) ;;
    *) die "--alertmanager takes cluster_url or staging_url, got '$KEY'." ;;
  esac
  # shellcheck source=lib/slack-webhooks.sh
  . "$SCRIPT_DIR/lib/slack-webhooks.sh"
elif [ "$FLUX_RELAY" = "true" ]; then
  # shellcheck source=lib/flux-relay.sh
  . "$SCRIPT_DIR/lib/flux-relay.sh"
  NAMESPACE="${NAMESPACE:-flux-system}"
  SECRETS_ENC="${SECRETS_ENC:-$K8S_DIR/$SECRETS_REL/flux-relay-slack.enc.yaml}"
  SECRET_NAME="${SECRET_NAME:-$FLUX_RELAY_SLACK}"
  RESTART_TARGET="${RESTART_TARGET:-}"
  case " $FLUX_RELAY_KEYS " in
    *" $KEY "*) ;;
    *) die "--flux-relay takes bot_token, cluster_channel or staging_channel, got '$KEY'." ;;
  esac
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
  || die "cannot decrypt $SECRETS_ENC — is the $SECRET_ENV age key in ~/.config/sops/age/keys.txt?"

secret_ns="$(sops --decrypt "$SECRETS_ENC" | grep -E '^[[:space:]]+namespace:' | head -1 | awk '{print $2}' || true)"
[ "$secret_ns" = "$NAMESPACE" ] \
  || die "$SECRETS_ENC targets namespace '${secret_ns:-<none>}' but ENV=$ENV expects '$NAMESPACE' — refusing to rotate across environments."

sops --decrypt "$SECRETS_ENC" \
  | grep -qE "^[[:space:]]+$(printf '%s' "$KEY" | sed 's/[.[\*^$/]/\\&/g'):" \
  || die "key '$KEY' not found in $SECRETS_ENC stringData."

# Same label and rule as deploy-observability.sh.
ENV_LABEL="fmi-codes/secrets-env"
CLUSTER_WIDE=false
if [ "$GRAFANA" = "true" ] || [ "$TAILSCALE" = "true" ] || [ "$ALERTMANAGER" = "true" ] || [ "$FLUX_RELAY" = "true" ]; then
  CLUSTER_WIDE=true
  live_env="$(kubectl -n "$NAMESPACE" get secret "$SECRET_NAME" --ignore-not-found \
    -o go-template="{{index .metadata.labels \"$ENV_LABEL\"}}" 2>/dev/null || true)"
  live_env="${live_env#<no value>}"
  if [ -n "$live_env" ] && [ "$live_env" != "$SECRET_ENV" ] && [ "${ALLOW_ENV_SWITCH:-false}" != "true" ]; then
    [ "$TAILSCALE" != "true" ] \
      || die "$NAMESPACE/$SECRET_NAME is labelled $live_env, but it always comes from staging's file, whatever ENV is. Release it first (docs/runbook.md 'Move Grafana and staging to another cluster'), or set ALLOW_ENV_SWITCH=true to replace it in place."
    die "$NAMESPACE/$SECRET_NAME holds the $live_env credentials; refusing to replace them with $ENV's. Run with ENV=$live_env, or set ALLOW_ENV_SWITCH=true to switch on purpose."
  fi
fi

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
if [ "$ALERTMANAGER" = "true" ] && [[ "$VALUE" != https://hooks.slack.com/services/* ]]; then
  die "that is not a Slack incoming webhook URL (https://hooks.slack.com/services/...); nothing changed."
fi
if [ "$FLUX_RELAY" = "true" ]; then
  flux_relay_check_value "$KEY" "$VALUE" || die "nothing changed."
fi

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

# The OAuth client is a pair. Applying it half-filled would let the waiting operator pod start
# with credentials that can't authenticate.
if [ "$TAILSCALE" = "true" ] && sops --decrypt "$SECRETS_ENC" \
    | grep -E "^[[:space:]]+client_(id|secret):[[:space:]]*(\"\"|'')?[[:space:]]*\$" >/dev/null; then
  unset VALUE
  if [ "$KEY" = "client_id" ]; then OTHER_KEY="client_secret"; else OTHER_KEY="client_id"; fi
  log "Stored '$KEY' in $SECRETS_ENC. Not applied yet: '$OTHER_KEY' is still empty. Set it next:"
  echo "  bash $0 --tailscale $OTHER_KEY"
  exit 0
fi

log "Applying updated secret from $SECRETS_ENC"
sops --decrypt "$SECRETS_ENC" | kubectl apply -f -
if [ "$CLUSTER_WIDE" = "true" ]; then
  kubectl -n "$NAMESPACE" label secret "$SECRET_NAME" "$ENV_LABEL=$SECRET_ENV" --overwrite >/dev/null
fi

if [ "$ALERTMANAGER" = "true" ]; then
  copy_slack_webhooks_for_flux "$NAMESPACE" "$SECRET_NAME"
  if [ -n "$SLACK_EMPTY_KEYS" ]; then
    echo "Still empty: $SLACK_EMPTY_KEYS. Set it too: with one key empty, every send to that channel"
    echo "fails and AlertmanagerFailedToSendAlerts posts to the cluster's channel."
  fi
fi

if [ "$FLUX_RELAY" = "true" ]; then
  FLUX_RELAY_EMPTY="$(flux_relay_empty_keys "$SECRETS_ENC")"
  if [ -n "$FLUX_RELAY_EMPTY" ]; then
    echo "Still empty: $FLUX_RELAY_EMPTY. Until all three are set, errors get no \"recovered\" reply"
    echo "(no token: none at all; no channel ID: none in that channel)."
  fi
fi

if [ -z "$RESTART_TARGET" ] && [ "$FLUX_RELAY" = "true" ]; then
  echo "No restart needed: the relay rereads its mounted Secret, which the kubelet updates within"
  echo "a minute or two."
elif [ -z "$RESTART_TARGET" ]; then
  echo "No restart needed: Alertmanager and Flux read the webhook on every send. The kubelet"
  echo "updates the mounted Secret within a minute or two."
elif [ "$RESTART" = "true" ]; then
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
    echo "If the old password leaked, you MUST also run (logs everyone out):"
    echo "  ENV=$ENV bash $0 JWT_SECRET_KEY --generate" ;;
esac

log "Done. Commit the updated $SECRETS_ENC so the change is the new source of truth."
