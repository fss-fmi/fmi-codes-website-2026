#!/usr/bin/env bash

set -euo pipefail

ACTION="${1:-install}"

detect_user() {
  if [ -n "${SVC_USER:-}" ]; then echo "$SVC_USER"; return; fi
  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then echo "$SUDO_USER"; return; fi
  local u
  u="$(getent passwd 1000 | cut -d: -f1)"
  [ -n "$u" ] && { echo "$u"; return; }
  id -un
}

SVC_USER="$(detect_user)"
SVC_GROUP="${SVC_GROUP:-$(id -gn "$SVC_USER")}"
SVC_HOME="$(getent passwd "$SVC_USER" | cut -d: -f6)"
KUBECONFIG_PATH="${KUBECONFIG_PATH:-$SVC_HOME/.kube/config}"
KUBECTL_BIN="${KUBECTL_BIN:-$(command -v kubectl || echo /usr/local/bin/kubectl)}"
SOCAT_BIN="${SOCAT_BIN:-$(command -v socat || echo /usr/bin/socat)}"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"

PROD_SVC="ingress-nginx-controller"
PROD_NS="ingress-nginx"
PROD_LOCAL="8443"
STAGING_SVC="ingress-nginx-staging-controller"
STAGING_NS="ingress-nginx-staging"
STAGING_LOCAL="9443"
STAGING_SVC_PORT="8443"

UNITS="fmi-forward-prod.service fmi-tls-prod.service fmi-forward-staging.service"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }
need_root() { [ "$(id -u)" -eq 0 ] || die "run as root: wsl.exe -u root -- bash infra/k8s/scripts/install-forward-services.sh $ACTION"; }

if [ "$ACTION" = "uninstall" ]; then
  need_root
  log "Removing FMI forward services"
  for u in $UNITS; do
    systemctl disable --now "$u" 2>/dev/null || true
    rm -f "$UNIT_DIR/$u"
  done
  systemctl daemon-reload
  systemctl reset-failed $UNITS 2>/dev/null || true
  rm -f /etc/sysctl.d/99-unpriv443.conf
  sysctl -w net.ipv4.ip_unprivileged_port_start=1024 >/dev/null 2>&1 || true
  echo "Removed: $UNITS"
  exit 0
fi

[ "$ACTION" = "install" ] || die "unknown action '$ACTION' — use 'install' or 'uninstall'."
need_root

[ "$SVC_USER" != "root" ] || die "refusing to install services as root — set SVC_USER to your normal WSL user."
[ -x "$KUBECTL_BIN" ] || die "kubectl not found at '$KUBECTL_BIN' — run install-tools.sh first."
[ -x "$SOCAT_BIN" ]   || die "socat not found at '$SOCAT_BIN' — install it (apt-get install -y socat)."
[ -f "$KUBECONFIG_PATH" ] || die "kubeconfig not found at '$KUBECONFIG_PATH' — set KUBECONFIG_PATH."
id "$SVC_USER" >/dev/null 2>&1 || die "user '$SVC_USER' does not exist — set SVC_USER."

log "Allowing non-root to bind port 443 (persisted)"
sysctl -w net.ipv4.ip_unprivileged_port_start=443 >/dev/null
echo "net.ipv4.ip_unprivileged_port_start=443" > /etc/sysctl.d/99-unpriv443.conf

log "Writing $UNIT_DIR/fmi-forward-prod.service"
cat > "$UNIT_DIR/fmi-forward-prod.service" <<EOF
[Unit]
Description=Port-forward prod ingress-nginx to 127.0.0.1:${PROD_LOCAL} for Windows browser access
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${SVC_USER}
Group=${SVC_GROUP}
Environment=KUBECONFIG=${KUBECONFIG_PATH}
ExecStart=${KUBECTL_BIN} -n ${PROD_NS} port-forward svc/${PROD_SVC} ${PROD_LOCAL}:443 --address 127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

log "Writing $UNIT_DIR/fmi-tls-prod.service"
cat > "$UNIT_DIR/fmi-tls-prod.service" <<EOF
[Unit]
Description=socat 127.0.0.1:443 to prod forward ${PROD_LOCAL} (serves fmicodes.com + grafana.fmicodes.com)
After=network-online.target fmi-forward-prod.service
Wants=network-online.target
Requires=fmi-forward-prod.service
StartLimitIntervalSec=0

[Service]
Type=simple
User=${SVC_USER}
Group=${SVC_GROUP}
ExecStart=${SOCAT_BIN} TCP4-LISTEN:443,bind=127.0.0.1,fork,reuseaddr TCP4:127.0.0.1:${PROD_LOCAL}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

log "Writing $UNIT_DIR/fmi-forward-staging.service"
cat > "$UNIT_DIR/fmi-forward-staging.service" <<EOF
[Unit]
Description=Port-forward staging ingress-nginx to 127.0.0.1:${STAGING_LOCAL} for Windows browser access
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${SVC_USER}
Group=${SVC_GROUP}
Environment=KUBECONFIG=${KUBECONFIG_PATH}
ExecStart=${KUBECTL_BIN} -n ${STAGING_NS} port-forward svc/${STAGING_SVC} ${STAGING_LOCAL}:${STAGING_SVC_PORT} --address 127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

log "Enabling + starting services"
systemctl daemon-reload
systemctl enable --now $UNITS

cat <<EOF

FMI forward services installed and enabled (auto-start on every boot).

Add to the Windows hosts file (C:\\Windows\\System32\\drivers\\etc\\hosts):
  127.0.0.1 fmicodes.com
  127.0.0.1 grafana.fmicodes.com
  127.0.0.1 staging.fmicodes.com

Then browse (no terminal needed, survives reboot):
  https://fmicodes.com           prod app
  https://grafana.fmicodes.com   Grafana (rides the prod ingress bridge)
  https://staging.fmicodes.com:${STAGING_LOCAL}   staging app (self-signed cert)

Manage:
  systemctl status $UNITS
  wsl.exe -u root -- bash infra/k8s/scripts/install-forward-services.sh uninstall
EOF
