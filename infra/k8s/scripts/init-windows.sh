#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV="${ENV:-staging}"
case "$ENV" in
  prod)
    HOST="${HOST:-fmicodes.com}"
    INGRESS_NAMESPACE="ingress-nginx"
    INGRESS_RELEASE="ingress-nginx"
    HOST_URL="https://$HOST"
    ;;
  staging)
    HOST="${HOST:-staging.fmicodes.com}"
    INGRESS_NAMESPACE="ingress-nginx-staging"
    INGRESS_RELEASE="ingress-nginx-staging"
    HOST_URL="https://$HOST:8443"
    ;;
  *)
    echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac

log() { printf '\n\033[1;36m### %s\033[0m\n' "$1"; }

case "${1:-}" in -h|--help) exec bash "$SCRIPT_DIR/init-linux.sh" --help ;; esac

if ! grep -qi microsoft /proc/version 2>/dev/null; then
  echo "Note: this doesn't look like WSL2. On a native Linux host run init-linux.sh directly." >&2
fi

log "Running the Linux bring-up (init-linux.sh)"
bash "$SCRIPT_DIR/init-linux.sh" "$@"

INGRESS_IP="$(kubectl -n "$INGRESS_NAMESPACE" get svc "${INGRESS_RELEASE}-controller" \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
[ -n "$INGRESS_IP" ] || INGRESS_IP="<ingress-node-ip>"

if [ "$ENV" = "prod" ]; then
  DNS_NOTE="Note: adding $HOST to your hosts file overrides public DNS on this machine.
Remove this line when you want your browser to reach the production server instead."
else
  DNS_NOTE="Note: this maps $HOST only on this machine, for reaching the staging
cluster in WSL2. Remove the line when you no longer need it."
fi

cat <<EOF

$(printf '\033[1;36m### WSL2 -> Windows host resolution\033[0m')

The cluster runs inside WSL2. A Windows browser cannot resolve $HOST
unless the name is in the WINDOWS hosts file — editing WSL's /etc/hosts does not
help the Windows side. Open an elevated (Administrator) editor on Windows and add
this line to C:\\Windows\\System32\\drivers\\etc\\hosts:

  $INGRESS_IP $HOST

From PowerShell as Administrator you can append it in one line:
  Add-Content -Path \$env:WINDIR\\System32\\drivers\\etc\\hosts -Value "$INGRESS_IP $HOST"

Then browse to ${HOST_URL}

$DNS_NOTE

Caveat: the WSL node IP above changes across 'wsl --shutdown' / reboot unless
mirrored networking is enabled. After a restart, re-check it and update the hosts
line:
  kubectl -n $INGRESS_NAMESPACE get svc ${INGRESS_RELEASE}-controller
EOF
