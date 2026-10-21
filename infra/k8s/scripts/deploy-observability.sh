#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
case "$ENV" in
  prod)    GRAFANA_SECRET_REL="secrets/grafana-secret.enc.yaml" ;;
  staging) GRAFANA_SECRET_REL="overlays/staging/secrets/grafana-secret.enc.yaml" ;;
  *)       echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac

MONITORING_NS="${MONITORING_NS:-monitoring}"
GRAFANA_SECRET="${GRAFANA_SECRET:-grafana-admin}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GRAFANA_SECRET_ENC="${GRAFANA_SECRET_ENC:-$K8S_DIR/$GRAFANA_SECRET_REL}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
command -v sops    >/dev/null 2>&1 || die "sops not found — run install-tools.sh first."
[ -f "$GRAFANA_SECRET_ENC" ] || die "missing $GRAFANA_SECRET_ENC"

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

log "Ensuring namespace '$MONITORING_NS' exists"
kubectl get namespace "$MONITORING_NS" >/dev/null 2>&1 \
  || kubectl create namespace "$MONITORING_NS"

if sops --decrypt "$GRAFANA_SECRET_ENC" >/dev/null 2>&1; then
  secret_ns="$(sops --decrypt "$GRAFANA_SECRET_ENC" | grep -E '^[[:space:]]+namespace:' | head -1 | awk '{print $2}' || true)"
  [ "$secret_ns" = "$MONITORING_NS" ] \
    || die "$GRAFANA_SECRET_ENC targets namespace '${secret_ns:-<none>}' but expected '$MONITORING_NS' — refusing to apply a secret across targets."
  log "Applying Grafana admin secret '$GRAFANA_SECRET' from $GRAFANA_SECRET_ENC (SOPS-managed)"
  sops --decrypt "$GRAFANA_SECRET_ENC" | kubectl apply -f -
else
  die "found $GRAFANA_SECRET_ENC but could not decrypt it — is your $ENV age key at ~/.config/sops/age/keys.txt? See docs/runbook.md 'Phase 7'."
fi

cat <<EOF

Grafana admin secret applied to namespace '$MONITORING_NS'.

Flux will install kube-prometheus-stack and reconcile the ServiceMonitor automatically
once the GitOps pipeline reconciles. Watch progress:
  flux get helmreleases -n flux-system
  flux get kustomizations -n flux-system
  kubectl -n $MONITORING_NS get pods -w
EOF
