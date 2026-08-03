#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
case "$ENV" in
  prod)    GRAFANA_SECRET_REL="secrets/grafana-secret.enc.yaml"; GRAFANA_HOST="grafana.fmicodes.com" ;;
  staging) GRAFANA_SECRET_REL="overlays/staging/secrets/grafana-secret.enc.yaml"; GRAFANA_HOST="grafana.staging.fmicodes.com" ;;
  *)       echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac

MONITORING_NS="${MONITORING_NS:-monitoring}"
GRAFANA_SVC="${GRAFANA_SVC:-kps-grafana}"
PORT="${PORT:-3000}"
ADDRESS="${ADDRESS:-127.0.0.1}"
DETACH="${DETACH:-1}"
LOG_FILE="${LOG_FILE:-/tmp/grafana-forward-${PORT}.log}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GRAFANA_SECRET_ENC="$K8S_DIR/$GRAFANA_SECRET_REL"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

kubectl -n "$MONITORING_NS" get svc "$GRAFANA_SVC" >/dev/null 2>&1 \
  || die "service '$GRAFANA_SVC' not found in namespace '$MONITORING_NS' — deploy the stack first with deploy-observability.sh (see infra/k8s/README.md 'Phase 7')."

PF_MATCH="port-forward --address $ADDRESS svc/$GRAFANA_SVC ${PORT}:80\$"

print_access() {
  cat <<EOF

Grafana ($ENV creds) is forwarded to $ADDRESS:${PORT}.

  browse: http://localhost:${PORT}
  or add these to the Windows hosts file (C:\\Windows\\System32\\drivers\\etc\\hosts)
  and browse http://grafana.fmicodes.com:${PORT} / http://grafana.staging.fmicodes.com:${PORT}:
    127.0.0.1 grafana.fmicodes.com
    127.0.0.1 grafana.staging.fmicodes.com

  log in with the admin user/password from the SOPS secret:
    sops --decrypt $GRAFANA_SECRET_ENC

  set ADDRESS=0.0.0.0 if 127.0.0.1 is not reachable from Windows on your setup.
  stop it with: pkill -f "$PF_MATCH"
EOF
}

if [ "$DETACH" = "1" ]; then
  if pgrep -f "$PF_MATCH" >/dev/null 2>&1; then
    log "A Grafana forward on port $PORT is already running — leaving it as is"
    print_access
    exit 0
  fi
  log "Starting detached port-forward ($ADDRESS:$PORT -> $GRAFANA_SVC:80)"
  setsid kubectl -n "$MONITORING_NS" port-forward --address "$ADDRESS" "svc/$GRAFANA_SVC" "${PORT}:80" \
    </dev/null >"$LOG_FILE" 2>&1 &
  pf_pid=$!
  sleep 1
  kill -0 "$pf_pid" 2>/dev/null \
    || die "port-forward exited immediately — is $ADDRESS:$PORT already in use? check $LOG_FILE"
  print_access
  echo "  logs: $LOG_FILE"
  exit 0
fi

print_access
log "Starting port-forward in the foreground — press Ctrl-C to stop"
exec kubectl -n "$MONITORING_NS" port-forward --address "$ADDRESS" "svc/$GRAFANA_SVC" "${PORT}:80"
