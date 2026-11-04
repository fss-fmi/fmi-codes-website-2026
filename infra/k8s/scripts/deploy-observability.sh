#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
case "$ENV" in
  prod)    SECRETS_REL="secrets" ;;
  staging) SECRETS_REL="overlays/staging/secrets" ;;
  *)       echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac

MONITORING_NS="${MONITORING_NS:-monitoring}"
TAILSCALE_NS="${TAILSCALE_NS:-tailscale}"
PROD_NS="${PROD_NS:-fmi-codes}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/slack-webhooks.sh
. "$SCRIPT_DIR/lib/slack-webhooks.sh"
# shellcheck source=lib/tailscale-client.sh
. "$SCRIPT_DIR/lib/tailscale-client.sh"
# shellcheck source=lib/flux-relay.sh
. "$SCRIPT_DIR/lib/flux-relay.sh"
GRAFANA_SECRET_ENC="${GRAFANA_SECRET_ENC:-$K8S_DIR/$SECRETS_REL/grafana-secret.enc.yaml}"
TAILSCALE_SECRET_ENC="${TAILSCALE_SECRET_ENC:-$K8S_DIR/$TS_CLIENT_REL}"
ALERTMANAGER_SECRET_ENC="${ALERTMANAGER_SECRET_ENC:-$K8S_DIR/$SECRETS_REL/alertmanager-slack.enc.yaml}"
FLUX_RELAY_SECRET_ENC="${FLUX_RELAY_SECRET_ENC:-$K8S_DIR/$SECRETS_REL/flux-relay-slack.enc.yaml}"
# These Secrets are cluster-wide (one monitoring stack, one operator, one Flux). Grafana's, the
# Slack webhooks and the Flux Relay's have a copy per env; the label records which env's copy is
# live so a second run with the other ENV can't silently swap the credentials underneath the
# running stack.
ENV_LABEL="fmi-codes/secrets-env"

log()  { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33mWarning: %s\033[0m\n' "$1" >&2; }
die()  { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
command -v sops    >/dev/null 2>&1 || die "sops not found — run install-tools.sh first."
[ -f "$GRAFANA_SECRET_ENC" ]   || die "missing $GRAFANA_SECRET_ENC"
[ -f "$TAILSCALE_SECRET_ENC" ] || die "missing $TAILSCALE_SECRET_ENC"
[ -f "$ALERTMANAGER_SECRET_ENC" ] || die "missing $ALERTMANAGER_SECRET_ENC"
[ -f "$FLUX_RELAY_SECRET_ENC" ] || die "missing $FLUX_RELAY_SECRET_ENC"

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

ensure_namespace() {
  kubectl get namespace "$1" >/dev/null 2>&1 || kubectl create namespace "$1"
}

# decrypt_secret FILE NAMESPACE ENV: print FILE decrypted, after checking it targets NAMESPACE.
decrypt_secret() {
  local file="$1" ns="$2" env="$3" manifest
  manifest="$(sops --decrypt "$file" 2>/dev/null)" \
    || die "could not decrypt $file — is your $env age key at ~/.config/sops/age/keys.txt? See docs/runbook.md 'Phase 7'."
  # printf is a builtin: the plaintext goes through a pipe, never argv or a here-string temp file.
  [ "$(printf '%s\n' "$manifest" | grep -E '^[[:space:]]+namespace:' | head -1 | awk '{print $2}')" = "$ns" ] \
    || die "$file does not target namespace '$ns' — refusing to apply a secret across targets."
  printf '%s\n' "$manifest"
}

# check_secret FILE NAMESPACE [ENV]: refuse to replace a live Secret that holds another env's
# copy. ENV is the env whose copy FILE is: $ENV, or fixed for the Tailscale client. Run for every
# Secret before any is applied, so a refusal leaves the cluster as it was.
check_secret() {
  local file="$1" ns="$2" env="${3:-$ENV}" name live_env
  name="$(decrypt_secret "$file" "$ns" "$env" | grep -E '^[[:space:]]+name:' | head -1 | awk '{print $2}')"
  live_env="$(kubectl -n "$ns" get secret "$name" --ignore-not-found \
    -o go-template="{{index .metadata.labels \"$ENV_LABEL\"}}" 2>/dev/null || true)"
  live_env="${live_env#<no value>}"
  [ -n "$live_env" ] && [ "$live_env" != "$env" ] && [ "${ALLOW_ENV_SWITCH:-false}" != "true" ] || return 0
  if [ -n "${3:-}" ]; then
    die "$ns/$name is labelled $live_env, but it always comes from $env's file ($file), whatever ENV is. Release it first (docs/runbook.md 'Move Grafana and staging to another cluster'), or set ALLOW_ENV_SWITCH=true to replace it in place."
  fi
  local hint=""
  [ "$env" = "prod" ] && hint=" A staging-only box that now runs prod too should switch: docs/runbook.md 'Adding prod to a staging-only box'."
  die "$ns/$name holds the $live_env credentials; refusing to replace them with $env's. Run with ENV=$live_env, or set ALLOW_ENV_SWITCH=true to switch on purpose.$hint"
}

# apply_secret FILE NAMESPACE [ENV]: apply FILE and label it with ENV (as for check_secret).
apply_secret() {
  local file="$1" ns="$2" env="${3:-$ENV}" manifest name
  manifest="$(decrypt_secret "$file" "$ns" "$env")" || exit 1
  name="$(printf '%s\n' "$manifest" | grep -E '^[[:space:]]+name:' | head -1 | awk '{print $2}')"
  log "Applying $ns/$name from $file ($env)"
  printf '%s\n' "$manifest" | kubectl apply -f -
  kubectl -n "$ns" label secret "$name" "$ENV_LABEL=$env" --overwrite >/dev/null
  APPLIED_SECRET_NAME="$name"
}

TAILSCALE_STATUS="applied"
if ! sops --decrypt "$TAILSCALE_SECRET_ENC" >/dev/null 2>&1; then
  TAILSCALE_STATUS="skipped (no staging age key)"
  warn "cannot decrypt $TAILSCALE_SECRET_ENC. The Tailscale client is staging's on every cluster, so
  this machine needs the staging age key too (docs/runbook.md 'One Tailscale client for every
  cluster'). The live tailscale/operator-oauth, if any, is left as it is. Add the key, then re-run:
    ENV=$ENV bash $SCRIPT_DIR/deploy-observability.sh"
# Not grep -q: exiting at the first match could SIGPIPE sops, and pipefail would invert the result.
elif sops --decrypt "$TAILSCALE_SECRET_ENC" \
    | grep -E "^[[:space:]]+client_(id|secret):[[:space:]]*(\"\"|'')?[[:space:]]*\$" >/dev/null; then
  TAILSCALE_STATUS="skipped"
  warn "$TAILSCALE_SECRET_ENC has no Tailscale OAuth client yet; the operator stays idle and Grafana and staging have no tailnet address.
  Create the OAuth client (docs/runbook.md 'Phase 7'), then:
    bash $SCRIPT_DIR/tailscale-oauth.sh set
    ENV=$ENV bash $SCRIPT_DIR/deploy-observability.sh"
fi

# The relay runs in Flux's namespace; without Flux there is nothing to apply it to.
FLUX_RELAY_STATUS="applied"
if ! kubectl get namespace "$FLUX_NS" >/dev/null 2>&1; then
  FLUX_RELAY_STATUS="skipped (Flux not installed)"
fi

check_secret "$GRAFANA_SECRET_ENC" "$MONITORING_NS"
check_secret "$ALERTMANAGER_SECRET_ENC" "$MONITORING_NS"
if [ "$FLUX_RELAY_STATUS" = "applied" ]; then
  check_secret "$FLUX_RELAY_SECRET_ENC" "$FLUX_NS"
fi
if [ "$TAILSCALE_STATUS" = "applied" ]; then
  check_secret "$TAILSCALE_SECRET_ENC" "$TAILSCALE_NS" staging
fi

log "Ensuring namespaces '$MONITORING_NS' and '$TAILSCALE_NS' exist"
ensure_namespace "$MONITORING_NS"
ensure_namespace "$TAILSCALE_NS"

apply_secret "$GRAFANA_SECRET_ENC" "$MONITORING_NS"

# Applied even while the webhooks are empty: the Alertmanager pod mounts it and can't start
# without it, and nothing would report that (the kps release itself still looks fine).
apply_secret "$ALERTMANAGER_SECRET_ENC" "$MONITORING_NS"

copy_slack_webhooks_for_flux "$MONITORING_NS" "$APPLIED_SECRET_NAME"
SLACK_STATUS="set"
if [ -n "$SLACK_EMPTY_KEYS" ]; then
  SLACK_STATUS="missing: $SLACK_EMPTY_KEYS"
  warn "$ALERTMANAGER_SECRET_ENC has no webhook for: $SLACK_EMPTY_KEYS. Set both keys: with only one,
  every send to the other fails and AlertmanagerFailedToSendAlerts posts to the cluster's channel.
  Create the webhooks (docs/runbook.md 'Cluster alerts'), then for each key:
    ENV=$ENV bash $SCRIPT_DIR/rotate-secret.sh --alertmanager <cluster_url|staging_url>"
fi

if [ "$FLUX_RELAY_STATUS" = "applied" ]; then
  # Applied even while empty: the relay mounts it optionally and idles until the token is set.
  apply_secret "$FLUX_RELAY_SECRET_ENC" "$FLUX_NS"
  FLUX_RELAY_EMPTY="$(flux_relay_empty_keys "$FLUX_RELAY_SECRET_ENC")"
  if [ -n "$FLUX_RELAY_EMPTY" ]; then
    FLUX_RELAY_STATUS="applied, missing: $FLUX_RELAY_EMPTY"
    warn "$FLUX_RELAY_SECRET_ENC has no value for: $FLUX_RELAY_EMPTY. Flux errors still post, but
  get no \"recovered\" reply. Set up the Flux Relay app (docs/runbook.md 'Cluster alerts'), then for each key:
    ENV=$ENV bash $SCRIPT_DIR/rotate-secret.sh --flux-relay <bot_token|cluster_channel|staging_channel>"
  fi
else
  warn "Flux isn't installed, so $FLUX_NS/$FLUX_RELAY_SLACK isn't applied. Once it is, re-run:
    ENV=$ENV bash $SCRIPT_DIR/deploy-observability.sh"
fi

if [ "$TAILSCALE_STATUS" = "applied" ]; then
  apply_secret "$TAILSCALE_SECRET_ENC" "$TAILSCALE_NS" staging
fi

cat <<EOF

Grafana admin and Alertmanager secrets applied (Slack webhooks $SLACK_STATUS);
Flux Relay secret $FLUX_RELAY_STATUS;
Tailscale OAuth secret $TAILSCALE_STATUS.

Flux installs kube-prometheus-stack and the Tailscale operator and reconciles the
ServiceMonitor and the tailnet Ingresses of Grafana and staging. Watch progress:
  flux get helmreleases -n flux-system
  flux get kustomizations -n flux-system
  kubectl -n $MONITORING_NS get ingress grafana              # ADDRESS = Grafana's tailnet URL
  kubectl -n ingress-nginx-staging get ingress staging  # ADDRESS = staging's tailnet URL
EOF

# A missing address or a name clash is reported, not fatal: everything else is deployed and
# the fix happens in the Tailscale admin console.
if [ "$TAILSCALE_STATUS" = "applied" ] && [ "${SKIP_TAILSCALE_CHECK:-false}" != "true" ]; then
  MONITORING_NS="$MONITORING_NS" TAILSCALE_NS="$TAILSCALE_NS" \
    bash "$SCRIPT_DIR/tailscale-oauth.sh" check || true
fi

# cluster_url is the channel of the env that owns the cluster, so staging's copies on a box
# that runs prod send prod's alerts to the staging channel, and nothing else would say so.
if [ "$ENV" = "staging" ] && kubectl get namespace "$PROD_NS" >/dev/null 2>&1; then
  warn "this cluster also runs prod (namespace $PROD_NS) but now holds staging's cluster-wide
  Secrets, so prod's alerts post to the staging Slack channel. Switch them to prod:
    ALLOW_ENV_SWITCH=true ENV=prod bash $SCRIPT_DIR/deploy-observability.sh
  Details: docs/runbook.md 'Adding prod to a staging-only box'."
fi
