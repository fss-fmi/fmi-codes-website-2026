#!/usr/bin/env bash

set -euo pipefail

HEADERS_CONFIGMAP="${HEADERS_CONFIGMAP:-security-headers}"

ENV="${ENV:-staging}"
case "$ENV" in
  prod)
    NAMESPACE="${NAMESPACE:-fmi-codes}"
    HOST="${HOST:-fmicodes.com}"
    INGRESS_NAMESPACE="${INGRESS_NAMESPACE:-ingress-nginx}"
    INGRESS_RELEASE="${INGRESS_RELEASE:-ingress-nginx}"
    HOST_URL="https://$HOST"
    TAILNET_OVERLAY=""
    POD_CIDR="${POD_CIDR:-10.42.0.0/16}"
    # Reached only through the Cloudflare Tunnel, so the controller binds no host ports. Only
    # cloudflared's pods reach it, so the visitor's address is read from CF-Connecting-IP when
    # the peer is in the pod CIDR. use-forwarded-headers stays off: it would also trust a
    # client's X-Forwarded-Proto and X-Forwarded-Host.
    # The CPU request keeps half a core reserved for proxying during the rush (#219).
    HELM_SET_ARGS=(
      --set "controller.config.add-headers=$NAMESPACE/$HEADERS_CONFIGMAP"
      --set "controller.config.allow-snippet-annotations=true"
      --set "controller.config.annotations-risk-level=Critical"
      --set "controller.config.enable-real-ip=true"
      --set "controller.config.forwarded-for-header=CF-Connecting-IP"
      --set "controller.config.proxy-real-ip-cidr=$POD_CIDR"
      --set "controller.service.type=ClusterIP"
      --set "controller.resources.requests.cpu=500m"
    )
    ;;
  staging)
    NAMESPACE="${NAMESPACE:-fmi-codes-staging}"
    INGRESS_NAMESPACE="${INGRESS_NAMESPACE:-ingress-nginx-staging}"
    INGRESS_RELEASE="${INGRESS_RELEASE:-ingress-nginx-staging}"
    # Reached only over the tailnet (overlays/staging/tailnet), so the controller binds no host
    # ports: the Tailscale proxy holds the certificate.
    TAILNET_OVERLAY="overlays/staging/tailnet"
    HELM_SET_ARGS=(
      --set "controller.config.add-headers=$NAMESPACE/$HEADERS_CONFIGMAP"
      --set "controller.config.allow-snippet-annotations=true"
      --set "controller.config.annotations-risk-level=Critical"
      --set "controller.ingressClassResource.name=nginx-staging"
      --set "controller.ingressClassResource.controllerValue=k8s.io/ingress-nginx-staging"
      --set "controller.ingressClass=nginx-staging"
      --set "controller.electionID=ingress-nginx-staging-leader"
      --set "controller.service.type=ClusterIP"
    )
    ;;
  *)
    echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac

INGRESS_NGINX_REPO="${INGRESS_NGINX_REPO:-https://kubernetes.github.io/ingress-nginx}"
INGRESS_NGINX_CHART_VERSION="${INGRESS_NGINX_CHART_VERSION:-4.15.1}"

READY_TIMEOUT="${READY_TIMEOUT:-600}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INGRESS_OVERLAY="$K8S_DIR/overlays/$ENV/ingress"
TUNNEL_SECRET_ENC="${TUNNEL_SECRET_ENC:-$K8S_DIR/secrets/cloudflared-tunnel.enc.yaml}"
TUNNEL_SECRET_NAME="cloudflared-tunnel"
# Every cluster holding the tunnel's credentials becomes a connector of the one prod tunnel, and
# Cloudflare splits visitors between them, so serving it is a deliberate opt-in.
SERVE_PROD_TUNNEL="${SERVE_PROD_TUNNEL:-false}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33mWarning: %s\033[0m\n' "$1" >&2; }
die() { echo "Error: $1" >&2; exit 1; }

case "$SERVE_PROD_TUNNEL" in
  true|false) : ;;
  *) die "SERVE_PROD_TUNNEL must be 'true' or 'false', got '$SERVE_PROD_TUNNEL'." ;;
esac

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
command -v helm    >/dev/null 2>&1 || die "helm not found — run install-tools.sh first."
[ -f "$INGRESS_OVERLAY/kustomization.yaml" ] || die "missing $INGRESS_OVERLAY/kustomization.yaml"
[ -z "$TAILNET_OVERLAY" ] || [ -f "$K8S_DIR/$TAILNET_OVERLAY/kustomization.yaml" ] \
  || die "missing $K8S_DIR/$TAILNET_OVERLAY/kustomization.yaml"
if [ "$ENV" = "prod" ] && [ "$SERVE_PROD_TUNNEL" = "true" ]; then
  command -v sops >/dev/null 2>&1 || die "sops not found — run install-tools.sh first."
  [ -f "$TUNNEL_SECRET_ENC" ] \
    || die "missing $TUNNEL_SECRET_ENC — create the tunnel first (docs/runbook/cloudflare.md 'Cloudflare Tunnel')."
fi

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 \
  || die "namespace '$NAMESPACE' not found — run deploy-stateful.sh first (Phase 2)."

kubectl -n "$NAMESPACE" get service backend >/dev/null 2>&1 \
  || die "service 'backend' not found — run deploy-app.sh first (Phase 3)."
kubectl -n "$NAMESPACE" get service frontend >/dev/null 2>&1 \
  || die "service 'frontend' not found — run deploy-app.sh first (Phase 3)."

HELM_DOCKER_CONFIG="$(mktemp -d)"
printf '{}' > "$HELM_DOCKER_CONFIG/config.json"
trap 'rm -rf "$HELM_DOCKER_CONFIG"' EXIT
export DOCKER_CONFIG="$HELM_DOCKER_CONFIG"

log "Adding/refreshing the ingress-nginx Helm repo"
helm repo add ingress-nginx "$INGRESS_NGINX_REPO" >/dev/null 2>&1 || true
helm repo update ingress-nginx >/dev/null

log "Deploying ingress-nginx (chart $INGRESS_NGINX_CHART_VERSION)"
helm upgrade --install "$INGRESS_RELEASE" ingress-nginx/ingress-nginx \
  --namespace "$INGRESS_NAMESPACE" --create-namespace \
  --version "$INGRESS_NGINX_CHART_VERSION" \
  "${HELM_SET_ARGS[@]}" \
  --wait --timeout "${READY_TIMEOUT}s"

if [ "$ENV" = "staging" ]; then
  log "Applying the security-headers ConfigMap and Ingress"
  kubectl apply -k "$INGRESS_OVERLAY"
  log "Applying staging's tailnet Ingress (the Tailscale operator serves it)"
  kubectl apply -k "$K8S_DIR/$TAILNET_OVERLAY"
else
  if [ "$SERVE_PROD_TUNNEL" = "true" ]; then
    log "Applying the Cloudflare Tunnel credentials"
    sops --decrypt "$TUNNEL_SECRET_ENC" >/dev/null 2>&1 \
      || die "could not decrypt $TUNNEL_SECRET_ENC — is your prod age key at ~/.config/sops/age/keys.txt? See docs/runbook/secrets.md 'SOPS and age'."
    secret_ns="$(sops --decrypt "$TUNNEL_SECRET_ENC" | grep -E '^[[:space:]]+namespace:' | head -1 | awk '{print $2}' || true)"
    [ "$secret_ns" = "$NAMESPACE" ] \
      || die "$TUNNEL_SECRET_ENC targets namespace '$secret_ns', expected '$NAMESPACE'."
    sops --decrypt "$TUNNEL_SECRET_ENC" | kubectl apply -f -
  fi

  log "Applying the security-headers ConfigMap, the Ingress and cloudflared"
  kubectl apply -k "$INGRESS_OVERLAY"

  # Pods that waited past the progress deadline for the Secret make 'rollout status' fail at
  # once, so wait on availability instead.
  if [ "$SERVE_PROD_TUNNEL" = "true" ]; then
    TUNNEL_SERVED=true
    log "Waiting for cloudflared to connect to Cloudflare"
    if ! kubectl -n "$NAMESPACE" wait --for=condition=Available deployment/cloudflared --timeout "${READY_TIMEOUT}s"; then
      echo "" >&2
      echo "cloudflared is not ready within ${READY_TIMEOUT}s — continuing anyway." >&2
      echo "A pod is ready only while it holds a connection to Cloudflare. Check:" >&2
      echo "  kubectl -n $NAMESPACE logs deploy/cloudflared --tail=20" >&2
      echo "'Failed to get tunnel' means the credentials don't match the tunnel ID in" >&2
      echo "overlays/prod/ingress/cloudflared-config.yaml." >&2
    fi
  elif ! held="$(kubectl -n "$NAMESPACE" get secret "$TUNNEL_SECRET_NAME" --ignore-not-found -o name)"; then
    die "could not check whether this cluster holds the tunnel's Secret ($NAMESPACE/$TUNNEL_SECRET_NAME)."
  elif [ -n "$held" ]; then
    TUNNEL_SERVED=true
    warn "SERVE_PROD_TUNNEL is not true, but this cluster already holds the tunnel's credentials
  from an earlier run, so it still serves $HOST. If another cluster serves prod, stop this one:
  docs/runbook/cloudflare.md 'Move prod to another cluster', step 1."
  else
    TUNNEL_SERVED=false
    log "Not serving the Cloudflare Tunnel (SERVE_PROD_TUNNEL is not true)"
    echo "cloudflared stays waiting for its credentials, so $HOST never reaches this cluster."
  fi
fi

log "Deployed. Current state:"
kubectl -n "$INGRESS_NAMESPACE" get svc "${INGRESS_RELEASE}-controller" -o wide
kubectl -n "$NAMESPACE" get ingress

if [ "$ENV" = "staging" ]; then
  kubectl -n "$INGRESS_NAMESPACE" get ingress staging
  TAILNET_HOST="$(kubectl -n "$INGRESS_NAMESPACE" get ingress staging \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
  [ -n "$TAILNET_HOST" ] || TAILNET_HOST="staging.<tailnet>.ts.net"
  cat <<EOF

Networking is up (Phase 4). Staging is reachable only over the tailnet:
  https://$TAILNET_HOST -> Tailscale proxy (TLS) -> ${INGRESS_RELEASE}-controller:80
    /api/    -> backend:5001
    /        -> frontend:80

The address appears once the Tailscale operator runs with its OAuth client (Flux installs it,
deploy-observability.sh applies the client). Until then, or without Tailscale:
  kubectl -n $INGRESS_NAMESPACE port-forward svc/${INGRESS_RELEASE}-controller 8080:80
  curl http://127.0.0.1:8080/api/health

Verify from a tailnet device (see docs/runbook/index.md 'Phase 4'):
  curl https://$TAILNET_HOST/api/health
  curl -I https://$TAILNET_HOST/api/health    # security headers present
EOF
  exit 0
fi

kubectl -n "$NAMESPACE" get deployment cloudflared

if [ "$TUNNEL_SERVED" != "true" ]; then
  cat <<EOF

Networking is up (Phase 4), but prod is not on the internet from this cluster: it doesn't hold
the tunnel's credentials. Reach it with a port-forward:
  kubectl -n $INGRESS_NAMESPACE port-forward svc/${INGRESS_RELEASE}-controller 8081:80
  curl -H 'Host: $HOST' http://127.0.0.1:8081/api/health

To make this the cluster that serves $HOST, stop the tunnel on any cluster that runs it now
(only one may), then (docs/runbook/cloudflare.md 'Move prod to another cluster'):
  SERVE_PROD_TUNNEL=true ENV=prod bash $SCRIPT_DIR/deploy-ingress.sh
EOF
  exit 0
fi

cat <<EOF

Networking is up (Phase 4). Prod is reachable only through the Cloudflare Tunnel:
  $HOST_URL -> Cloudflare (TLS) -> cloudflared -> ${INGRESS_RELEASE}-controller:80
    /api/    -> backend:5001
    /        -> frontend:80

The first time, point the hostname at the tunnel from a machine signed in with cloudflared
(docs/runbook/cloudflare.md 'Cloudflare Tunnel'). Only one cluster may run the prod tunnel at a time.

Verify against the issue's acceptance criteria (see docs/runbook/cloudflare.md 'Serving the tunnel'):

  The tunnel is connected (READY 2/2):
    kubectl -n $NAMESPACE get deployment cloudflared

  Routing (backend vs frontend):
    curl ${HOST_URL}/api/health
    curl ${HOST_URL}/

  Security headers present on every response:
    curl -I ${HOST_URL}/api/health

  HTTP redirects to HTTPS (Cloudflare's Always Use HTTPS):
    curl -I http://$HOST/
EOF
