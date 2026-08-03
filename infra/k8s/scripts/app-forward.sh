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
DETACH="${DETACH:-1}"
LOG_FILE="${LOG_FILE:-/tmp/app-forward-${ENV}-${LOCAL_PORT}.log}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

kubectl -n "$INGRESS_NS" get svc "$INGRESS_SVC" >/dev/null 2>&1 \
  || die "service '$INGRESS_SVC' not found in namespace '$INGRESS_NS' — deploy ingress first with deploy-ingress.sh (see infra/k8s/README.md 'Phase 4')."

PF_MATCH="port-forward --address $ADDRESS svc/$INGRESS_SVC ${LOCAL_PORT}:${SVC_HTTPS_PORT}\$"
SOCAT_MATCH="socat TCP4-LISTEN:${BROWSE_PORT},bind=${ADDRESS}"

NEED_SOCAT=0
if [ "$BROWSE_PORT" != "$LOCAL_PORT" ]; then
  if command -v socat >/dev/null 2>&1; then
    NEED_SOCAT=1
    BROWSE_URL="https://$HOST"
  else
    echo "Note: socat not found — cannot bridge :$BROWSE_PORT, browse the forwarded port directly." >&2
    BROWSE_URL="https://$HOST:$LOCAL_PORT"
  fi
else
  BROWSE_URL="https://$HOST:$BROWSE_PORT"
fi

STOP_HINT="pkill -f \"$PF_MATCH\""
[ "$NEED_SOCAT" = "1" ] && STOP_HINT="$STOP_HINT; pkill -f \"$SOCAT_MATCH\""

print_access() {
  cat <<EOF

The $ENV app ($INGRESS_SVC) is forwarded to $ADDRESS:$LOCAL_PORT.

  add to the Windows hosts file (C:\\Windows\\System32\\drivers\\etc\\hosts):
    127.0.0.1 $HOST
  then browse: $BROWSE_URL
  $CERT_NOTE

  stop it with: $STOP_HINT
EOF
}

start_socat() {
  setsid socat "TCP4-LISTEN:${BROWSE_PORT},bind=${ADDRESS},fork,reuseaddr" "TCP4:${ADDRESS}:${LOCAL_PORT}" \
    </dev/null >>"$LOG_FILE" 2>&1 &
}

if [ "$DETACH" = "1" ]; then
  if pgrep -f "$PF_MATCH" >/dev/null 2>&1; then
    log "An app forward for $ENV on port $LOCAL_PORT is already running — leaving it as is"
    print_access
    exit 0
  fi
  : > "$LOG_FILE"
  [ "$NEED_SOCAT" = "1" ] && { log "Bridging $ADDRESS:$BROWSE_PORT -> $ADDRESS:$LOCAL_PORT (socat, detached)"; start_socat; }
  log "Starting detached port-forward ($ADDRESS:$LOCAL_PORT -> $INGRESS_SVC:$SVC_HTTPS_PORT)"
  setsid kubectl -n "$INGRESS_NS" port-forward --address "$ADDRESS" "svc/$INGRESS_SVC" "${LOCAL_PORT}:${SVC_HTTPS_PORT}" \
    </dev/null >>"$LOG_FILE" 2>&1 &
  pf_pid=$!
  sleep 1
  if ! kill -0 "$pf_pid" 2>/dev/null; then
    [ "$NEED_SOCAT" = "1" ] && pkill -f "$SOCAT_MATCH" 2>/dev/null || true
    die "port-forward exited immediately — is $ADDRESS:$LOCAL_PORT already in use? check $LOG_FILE"
  fi
  print_access
  echo "  logs: $LOG_FILE"
  exit 0
fi

SOCAT_PID=""
cleanup() { [ -n "$SOCAT_PID" ] && kill "$SOCAT_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

if [ "$NEED_SOCAT" = "1" ]; then
  log "Bridging $ADDRESS:$BROWSE_PORT -> $ADDRESS:$LOCAL_PORT (socat)"
  socat "TCP4-LISTEN:${BROWSE_PORT},bind=${ADDRESS},fork,reuseaddr" "TCP4:${ADDRESS}:${LOCAL_PORT}" &
  SOCAT_PID=$!
fi

print_access
log "Starting port-forward in the foreground — press Ctrl-C to stop"
if [ -n "$SOCAT_PID" ]; then
  kubectl -n "$INGRESS_NS" port-forward --address "$ADDRESS" "svc/$INGRESS_SVC" "${LOCAL_PORT}:${SVC_HTTPS_PORT}"
else
  exec kubectl -n "$INGRESS_NS" port-forward --address "$ADDRESS" "svc/$INGRESS_SVC" "${LOCAL_PORT}:${SVC_HTTPS_PORT}"
fi
