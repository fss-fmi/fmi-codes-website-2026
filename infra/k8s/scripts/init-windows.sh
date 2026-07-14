#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${NAMESPACE:-fmi-codes}"

log() { printf '\n\033[1;36m### %s\033[0m\n' "$1"; }

if ! grep -qi microsoft /proc/version 2>/dev/null; then
  echo "Note: this doesn't look like WSL2. On a native Linux host run init-linux.sh directly." >&2
fi

log "Running the Linux bring-up (init-linux.sh)"
bash "$SCRIPT_DIR/init-linux.sh" "$@"

INGRESS_IP="$(kubectl -n ingress-nginx get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
[ -n "$INGRESS_IP" ] || INGRESS_IP="<ingress-node-ip>"

cat <<EOF

$(printf '\033[1;36m### WSL2 -> Windows host resolution\033[0m')

The cluster runs inside WSL2. A Windows browser cannot resolve fmi-codes.local
unless the name is in the WINDOWS hosts file — editing WSL's /etc/hosts does not
help the Windows side. Open an elevated (Administrator) editor on Windows and add
this line to C:\\Windows\\System32\\drivers\\etc\\hosts:

  $INGRESS_IP fmi-codes.local

From PowerShell as Administrator you can append it in one line:
  Add-Content -Path \$env:WINDIR\\System32\\drivers\\etc\\hosts -Value "$INGRESS_IP fmi-codes.local"

Then browse to https://fmi-codes.local (self-signed cert — accept the warning).

Caveat: the WSL node IP above changes across 'wsl --shutdown' / reboot unless
mirrored networking is enabled. After a restart, re-check it and update the hosts
line:
  kubectl -n ingress-nginx get svc ingress-nginx-controller
EOF
