#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV="${ENV:-staging}"
case "$ENV" in
  prod)
    HOST="${HOST:-fmicodes.com}"
    HOST_URL="https://$HOST"
    ;;
  staging)
    HOST="${HOST:-staging.fmicodes.com}"
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

if [ "$ENV" = "prod" ]; then
  DNS_NOTE="Note: adding $HOST to your hosts file overrides public DNS on this machine.
Remove this line when you want your browser to reach the production server instead."
else
  DNS_NOTE="Note: this maps $HOST only on this machine, for reaching the staging
cluster in WSL2. Remove the line when you no longer need it."
fi

cat <<EOF

$(printf '\033[1;36m### WSL2 -> Windows host resolution\033[0m')

The cluster runs inside WSL2. Two things are needed for a Windows browser to reach
$HOST, and the WSL node IP is NOT one of them: k3s/klipper does not expose the
ingress LoadBalancer ports to the Windows host, so a hosts entry pointing at the
node IP resolves the name but cannot open a connection.

1) Map the host to loopback in the WINDOWS hosts file
   (C:\\Windows\\System32\\drivers\\etc\\hosts) — editing WSL's /etc/hosts does not
   help the Windows side. From an elevated PowerShell:
     Add-Content -Path \$env:WINDIR\\System32\\drivers\\etc\\hosts -Value "127.0.0.1 $HOST"

2) Run the forward that bridges the ingress to loopback (leave it running):
     ENV=$ENV bash infra/k8s/scripts/app-forward.sh

Then browse to ${HOST_URL}

$DNS_NOTE
EOF
