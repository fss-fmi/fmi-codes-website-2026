#!/usr/bin/env bash

set -euo pipefail

NAMESPACE="${NAMESPACE:-fmi-codes}"
INGRESS_NAMESPACE="${INGRESS_NAMESPACE:-ingress-nginx}"
CERT_MANAGER_NAMESPACE="${CERT_MANAGER_NAMESPACE:-cert-manager}"

INGRESS_NGINX_REPO="${INGRESS_NGINX_REPO:-https://kubernetes.github.io/ingress-nginx}"
CERT_MANAGER_REPO="${CERT_MANAGER_REPO:-https://charts.jetstack.io}"
INGRESS_NGINX_CHART_VERSION="${INGRESS_NGINX_CHART_VERSION:-4.15.1}"
CERT_MANAGER_CHART_VERSION="${CERT_MANAGER_CHART_VERSION:-v1.21.0}"

HEADERS_CONFIGMAP="${HEADERS_CONFIGMAP:-security-headers}"
CERTIFICATE_NAME="${CERTIFICATE_NAME:-fmi-codes-tls}"

READY_TIMEOUT="${READY_TIMEOUT:-600}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INGRESS_MANIFEST="$K8S_DIR/manifests/ingress.yaml"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
command -v helm    >/dev/null 2>&1 || die "helm not found — run install-tools.sh first."
[ -f "$INGRESS_MANIFEST" ] || die "missing $INGRESS_MANIFEST"

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 \
  || die "namespace '$NAMESPACE' not found — run deploy-stateful.sh first (Phase 2)."

kubectl -n "$NAMESPACE" get service backend >/dev/null 2>&1 \
  || die "service 'backend' not found — run deploy-app.sh first (Phase 3)."
kubectl -n "$NAMESPACE" get service frontend >/dev/null 2>&1 \
  || die "service 'frontend' not found — run deploy-app.sh first (Phase 3)."

INGRESS_IP_PRE="$(kubectl -n "$INGRESS_NAMESPACE" get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
if [ -n "$INGRESS_IP_PRE" ]; then
  RESOLVED_IP=""
  if command -v dig >/dev/null 2>&1; then
    RESOLVED_IP="$(dig +short fmicodes.com A 2>/dev/null | tail -1 || true)"
  elif command -v nslookup >/dev/null 2>&1; then
    RESOLVED_IP="$(nslookup fmicodes.com 2>/dev/null | awk '/^Address: /{print $2}' | tail -1 || true)"
  fi
  if [ -n "$RESOLVED_IP" ] && [ "$RESOLVED_IP" != "$INGRESS_IP_PRE" ]; then
    echo "Warning: fmicodes.com resolves to '$RESOLVED_IP', expected '$INGRESS_IP_PRE'." >&2
    echo "Let's Encrypt HTTP-01 will fail until DNS points at $INGRESS_IP_PRE." >&2
    echo "The cert will be issued automatically once DNS propagates — no re-deploy needed." >&2
  fi
fi

HELM_DOCKER_CONFIG="$(mktemp -d)"
printf '{}' > "$HELM_DOCKER_CONFIG/config.json"
trap 'rm -rf "$HELM_DOCKER_CONFIG"' EXIT
export DOCKER_CONFIG="$HELM_DOCKER_CONFIG"

log "Adding/refreshing the ingress-nginx and cert-manager Helm repos"
helm repo add ingress-nginx "$INGRESS_NGINX_REPO" >/dev/null 2>&1 || true
helm repo add jetstack "$CERT_MANAGER_REPO" >/dev/null 2>&1 || true
helm repo update ingress-nginx jetstack >/dev/null

log "Deploying ingress-nginx (chart $INGRESS_NGINX_CHART_VERSION)"
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace "$INGRESS_NAMESPACE" --create-namespace \
  --version "$INGRESS_NGINX_CHART_VERSION" \
  --set "controller.config.add-headers=$NAMESPACE/$HEADERS_CONFIGMAP" \
  --wait --timeout "${READY_TIMEOUT}s"

log "Deploying cert-manager (chart $CERT_MANAGER_CHART_VERSION)"
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace "$CERT_MANAGER_NAMESPACE" --create-namespace \
  --version "$CERT_MANAGER_CHART_VERSION" \
  --set crds.enabled=true \
  --wait --timeout "${READY_TIMEOUT}s"

log "Applying the security-headers ConfigMap, issuer, certificate, and Ingress"
kubectl apply -f "$INGRESS_MANIFEST"

log "Waiting for the TLS certificate '$CERTIFICATE_NAME' to be issued (ACME — may take several minutes)"
if ! kubectl -n "$NAMESPACE" wait --for=condition=Ready \
    "certificate/$CERTIFICATE_NAME" --timeout "${READY_TIMEOUT}s"; then
  echo "" >&2
  echo "Certificate not ready within ${READY_TIMEOUT}s — continuing anyway." >&2
  echo "This is normal if DNS has not yet propagated to the server." >&2
  echo "The cert will be issued automatically once Let's Encrypt can reach the challenge endpoint." >&2
  echo "Check progress with:" >&2
  echo "  kubectl -n $NAMESPACE describe certificate $CERTIFICATE_NAME" >&2
  echo "  kubectl -n $NAMESPACE get certificaterequest,order,challenge" >&2
fi

log "Deployed. Current state:"
kubectl -n "$INGRESS_NAMESPACE" get svc ingress-nginx-controller -o wide
kubectl -n "$NAMESPACE" get ingress
kubectl -n "$NAMESPACE" get certificate

INGRESS_IP="$(kubectl -n "$INGRESS_NAMESPACE" get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
[ -n "$INGRESS_IP" ] || INGRESS_IP="<ingress-external-ip>"

cat <<EOF

Networking is up (Phase 4). The ingress terminates TLS and routes:
  /api/    -> backend:5001
  /static/ -> backend:5001
  /        -> frontend:80

For local testing, add the host to /etc/hosts:
  echo "$INGRESS_IP fmicodes.com" | sudo tee -a /etc/hosts

For production, ensure the fmicodes.com A record points at $INGRESS_IP in DNS.
Let's Encrypt will issue the cert automatically once DNS resolves.

Verify against the issue's acceptance criteria (see infra/k8s/README.md 'Phase 4'):

  Routing (backend vs frontend):
    curl https://fmicodes.com/api/health
    curl https://fmicodes.com/

  Security headers present on every response:
    curl -I https://fmicodes.com/api/health

  HTTP redirects to HTTPS:
    curl -I http://fmicodes.com/
EOF
