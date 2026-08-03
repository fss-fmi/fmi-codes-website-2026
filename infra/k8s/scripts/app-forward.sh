#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
case "$ENV" in
  prod)
    HOST="${HOST:-fmicodes.com}"
    INGRESS_NS="${INGRESS_NS:-ingress-nginx}"
    INGRESS_SVC="${INGRESS_SVC:-ingress-nginx-controller}"
    SVC_HTTPS_PORT="${SVC_HTTPS_PORT:-443}"
    LOCAL_PORT="${LOCAL_PORT:-8443}"
    BROWSE_PORT="${BROWSE_PORT:-443}"
    CERT_NOTE="(Let's Encrypt cert — trusted when reached as $HOST)"
    ;;
  staging)
    HOST="${HOST:-staging.fmicodes.com}"
    INGRESS_NS="${INGRESS_NS:-ingress-nginx-staging}"
    INGRESS_SVC="${INGRESS_SVC:-ingress-nginx-staging-controller}"
    SVC_HTTPS_PORT="${SVC_HTTPS_PORT:-8443}"
    LOCAL_PORT="${LOCAL_PORT:-8443}"
    BROWSE_PORT="${BROWSE_PORT:-8443}"
    CERT_NOTE="(self-signed cert — the browser warning is expected)"
    ;;
  *)
    echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac

ADDRESS="${ADDRESS:-127.0.0.1}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

kubectl -n "$INGRESS_NS" get svc "$INGRESS_SVC" >/dev/null 2>&1 \
  || die "service '$INGRESS_SVC' not found in namespace '$INGRESS_NS' — deploy ingress first with deploy-ingress.sh (see infra/k8s/README.md 'Phase 4')."

SOCAT_PID=""
cleanup() { [ -n "$SOCAT_PID" ] && kill "$SOCAT_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

if [ "$BROWSE_PORT" != "$LOCAL_PORT" ]; then
  if command -v socat >/dev/null 2>&1; then
    log "Bridging $ADDRESS:$BROWSE_PORT -> $ADDRESS:$LOCAL_PORT (socat)"
    socat "TCP4-LISTEN:${BROWSE_PORT},bind=${ADDRESS},fork,reuseaddr" "TCP4:${ADDRESS}:${LOCAL_PORT}" &
    SOCAT_PID=$!
    BROWSE_URL="https://$HOST"
  else
    echo "Note: socat not found — cannot bridge :$BROWSE_PORT, browse the forwarded port directly." >&2
    BROWSE_URL="https://$HOST:$LOCAL_PORT"
  fi
else
  BROWSE_URL="https://$HOST:$BROWSE_PORT"
fi

cat <<EOF

Forwarding the $ENV ingress ($INGRESS_SVC) to $ADDRESS:$LOCAL_PORT

  add to the Windows hosts file (C:\\Windows\\System32\\drivers\\etc\\hosts):
    127.0.0.1 $HOST
  then browse: $BROWSE_URL
  $CERT_NOTE

This is how the app is reached from a Windows browser on a WSL2 dev box: k3s/klipper
does not expose the ingress LoadBalancer ports to the Windows host, so 127.0.0.1 plus
this forward is what actually connects — a hosts entry pointing at the WSL node IP does not.

Press Ctrl-C to stop.
EOF

log "Starting port-forward ($ADDRESS:$LOCAL_PORT -> $INGRESS_SVC:$SVC_HTTPS_PORT)"
if [ -n "$SOCAT_PID" ]; then
  kubectl -n "$INGRESS_NS" port-forward --address "$ADDRESS" "svc/$INGRESS_SVC" "${LOCAL_PORT}:${SVC_HTTPS_PORT}"
else
  exec kubectl -n "$INGRESS_NS" port-forward --address "$ADDRESS" "svc/$INGRESS_SVC" "${LOCAL_PORT}:${SVC_HTTPS_PORT}"
fi
