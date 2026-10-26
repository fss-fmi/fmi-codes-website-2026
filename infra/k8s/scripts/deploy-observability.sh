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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GRAFANA_SECRET_ENC="${GRAFANA_SECRET_ENC:-$K8S_DIR/$SECRETS_REL/grafana-secret.enc.yaml}"
TAILSCALE_SECRET_ENC="${TAILSCALE_SECRET_ENC:-$K8S_DIR/$SECRETS_REL/tailscale-oauth.enc.yaml}"
# Both Secrets are cluster-wide (one monitoring stack, one operator) but each env has its own
# encrypted copy. The label records which env's copy is live so a second run with the other
# ENV can't silently swap the credentials underneath the running stack.
ENV_LABEL="fmi-codes/secrets-env"

log()  { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33mWarning: %s\033[0m\n' "$1" >&2; }
die()  { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
command -v sops    >/dev/null 2>&1 || die "sops not found — run install-tools.sh first."
[ -f "$GRAFANA_SECRET_ENC" ]   || die "missing $GRAFANA_SECRET_ENC"
[ -f "$TAILSCALE_SECRET_ENC" ] || die "missing $TAILSCALE_SECRET_ENC"

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

ensure_namespace() {
  kubectl get namespace "$1" >/dev/null 2>&1 || kubectl create namespace "$1"
}

# apply_secret FILE NAMESPACE: decrypt, check the target, refuse an env switch, apply, label.
apply_secret() {
  local file="$1" ns="$2" manifest name live_env
  manifest="$(sops --decrypt "$file" 2>/dev/null)" \
    || die "could not decrypt $file — is your $ENV age key at ~/.config/sops/age/keys.txt? See docs/runbook.md 'Phase 7'."
  # printf is a builtin: the plaintext goes through a pipe, never argv or a here-string temp file.
  [ "$(printf '%s\n' "$manifest" | grep -E '^[[:space:]]+namespace:' | head -1 | awk '{print $2}')" = "$ns" ] \
    || die "$file does not target namespace '$ns' — refusing to apply a secret across targets."
  name="$(printf '%s\n' "$manifest" | grep -E '^[[:space:]]+name:' | head -1 | awk '{print $2}')"

  live_env="$(kubectl -n "$ns" get secret "$name" --ignore-not-found \
    -o go-template="{{index .metadata.labels \"$ENV_LABEL\"}}" 2>/dev/null || true)"
  live_env="${live_env#<no value>}"
  if [ -n "$live_env" ] && [ "$live_env" != "$ENV" ] && [ "${ALLOW_ENV_SWITCH:-false}" != "true" ]; then
    die "$ns/$name holds the $live_env credentials; refusing to replace them with $ENV's. Run with ENV=$live_env, or set ALLOW_ENV_SWITCH=true to switch on purpose."
  fi

  log "Applying $ns/$name from $file ($ENV)"
  printf '%s\n' "$manifest" | kubectl apply -f -
  kubectl -n "$ns" label secret "$name" "$ENV_LABEL=$ENV" --overwrite >/dev/null
}

log "Ensuring namespaces '$MONITORING_NS' and '$TAILSCALE_NS' exist"
ensure_namespace "$MONITORING_NS"
ensure_namespace "$TAILSCALE_NS"

apply_secret "$GRAFANA_SECRET_ENC" "$MONITORING_NS"

TAILSCALE_STATUS="applied"
if sops --decrypt "$TAILSCALE_SECRET_ENC" 2>/dev/null \
    | grep -E "^[[:space:]]+client_(id|secret):[[:space:]]*(\"\"|'')?[[:space:]]*\$" >/dev/null; then
  TAILSCALE_STATUS="skipped"
  warn "$TAILSCALE_SECRET_ENC has no Tailscale OAuth client yet; the operator stays idle and Grafana and staging have no tailnet address.
  Create the OAuth client (docs/runbook.md 'Phase 7'), then:
    ENV=$ENV bash $SCRIPT_DIR/tailscale-oauth.sh set
    ENV=$ENV bash $SCRIPT_DIR/deploy-observability.sh"
else
  apply_secret "$TAILSCALE_SECRET_ENC" "$TAILSCALE_NS"
fi

cat <<EOF

Grafana admin secret applied; Tailscale OAuth secret $TAILSCALE_STATUS.

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
  ENV="$ENV" MONITORING_NS="$MONITORING_NS" TAILSCALE_NS="$TAILSCALE_NS" \
    bash "$SCRIPT_DIR/tailscale-oauth.sh" check || true
fi
