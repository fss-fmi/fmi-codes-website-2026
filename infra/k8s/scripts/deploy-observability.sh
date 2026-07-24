#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
case "$ENV" in
  prod)    APP_NAMESPACE="${APP_NAMESPACE:-fmi-codes}"; GRAFANA_SECRET_REL="secrets/grafana-secret.enc.yaml" ;;
  staging) APP_NAMESPACE="${APP_NAMESPACE:-fmi-codes-staging}"; GRAFANA_SECRET_REL="overlays/staging/secrets/grafana-secret.enc.yaml" ;;
  *)       echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac
case "$ENV" in
  prod)    OBS_VALUES_REL="helm-values/observability-values.yaml" ;;
  staging) OBS_VALUES_REL="overlays/staging/observability-values.yaml" ;;
esac

MONITORING_NS="${MONITORING_NS:-monitoring}"
PROM_REPO="${PROM_REPO:-https://prometheus-community.github.io/helm-charts}"
KPS_CHART_VERSION="${KPS_CHART_VERSION:-87.19.0}"
GRAFANA_SECRET="${GRAFANA_SECRET:-grafana-admin}"
READY_TIMEOUT="${READY_TIMEOUT:-600}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$K8S_DIR/../.." && pwd)"
OBS_VALUES="${OBS_VALUES:-$K8S_DIR/$OBS_VALUES_REL}"
GRAFANA_SECRET_ENC="${GRAFANA_SECRET_ENC:-$K8S_DIR/$GRAFANA_SECRET_REL}"
SERVICEMONITOR="${SERVICEMONITOR:-$K8S_DIR/base/observability/backend-servicemonitor.yaml}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
command -v helm    >/dev/null 2>&1 || die "helm not found — run install-tools.sh first."
command -v sops    >/dev/null 2>&1 || die "sops not found — run install-tools.sh first."
[ -f "$OBS_VALUES" ]         || die "missing $OBS_VALUES"
[ -f "$GRAFANA_SECRET_ENC" ] || die "missing $GRAFANA_SECRET_ENC"
[ -f "$SERVICEMONITOR" ]     || die "missing $SERVICEMONITOR"

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

HELM_DOCKER_CONFIG="$(mktemp -d)"
printf '{}' > "$HELM_DOCKER_CONFIG/config.json"
trap 'rm -rf "$HELM_DOCKER_CONFIG"' EXIT
export DOCKER_CONFIG="$HELM_DOCKER_CONFIG"

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
  die "found $GRAFANA_SECRET_ENC but could not decrypt it — is your $ENV age key at ~/.config/sops/age/keys.txt? See infra/k8s/README.md 'Phase 7'."
fi

log "Adding/refreshing the prometheus-community Helm repo"
helm repo add prometheus-community "$PROM_REPO" 2>/dev/null || true
helm repo update prometheus-community \
  || die "failed to refresh the prometheus-community Helm repo ($PROM_REPO) — check network/DNS."

log "Deploying kube-prometheus-stack (chart $KPS_CHART_VERSION)"
helm upgrade --install kps prometheus-community/kube-prometheus-stack \
  --namespace "$MONITORING_NS" \
  --version "$KPS_CHART_VERSION" \
  --values "$OBS_VALUES" \
  --wait --timeout "${READY_TIMEOUT}s"

log "Applying the backend ServiceMonitor (scrapes fmi-codes + fmi-codes-staging)"
kubectl apply -f "$SERVICEMONITOR"

log "Deployed. Current state in '$MONITORING_NS':"
kubectl -n "$MONITORING_NS" get pods -o wide
kubectl -n "$MONITORING_NS" get svc

case "$ENV" in
  prod)    GRAFANA_HOST="grafana.fmicodes.com" ;;
  staging) GRAFANA_HOST="grafana.staging.fmicodes.com" ;;
esac

cat <<EOF

Observability stack ($ENV context, scraping namespace '$APP_NAMESPACE') is up.

Access Grafana via ingress (add host entry to Windows hosts file first — see infra/k8s/README.md 'Phase 7'):
  open http://$GRAFANA_HOST
  log in with the admin user/password from the SOPS secret '$GRAFANA_SECRET'
  (read them with: sops --decrypt $GRAFANA_SECRET_ENC)

Access Grafana via port-forward (no hosts entry needed):
  kubectl -n $MONITORING_NS port-forward svc/kps-grafana 3000:80
  open http://localhost:3000

Access Prometheus (check scrape targets):
  kubectl -n $MONITORING_NS port-forward svc/kps-kube-prometheus-stack-prometheus 9090:9090
  open http://localhost:9090 -> Status -> Targets -> confirm the backend target is UP

The memory-per-pod leak graph: Grafana -> Dashboards -> "Kubernetes / Compute
Resources / Pod", filter namespace=$APP_NAMESPACE pod=~backend.*, memory panel, range 7d.
See infra/k8s/README.md 'Phase 7' for the full checklist.
EOF
