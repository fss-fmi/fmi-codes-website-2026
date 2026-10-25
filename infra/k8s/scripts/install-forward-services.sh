#!/usr/bin/env bash

set -euo pipefail

ACTION="${1:-install}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }
need_root() { [ "$(id -u)" -eq 0 ] || die "run as root: wsl.exe -d \"\$WSL_DISTRO_NAME\" -u root -- bash infra/k8s/scripts/install-forward-services.sh $ACTION"; }

# /run/systemd/private is a socket, so -d on it is always false; this directory is sd_booted()'s marker.
check_systemd() {
  [ -d /run/systemd/system ] \
    || die "systemd is not running — enable it in WSL2 first:
  1. Add to /etc/wsl.conf (inside WSL):
       [boot]
       systemd=true
  2. From PowerShell: wsl --shutdown
  3. Reopen WSL, then re-run."
}

detect_user() {
  if [ -n "${SVC_USER:-}" ]; then echo "$SVC_USER"; return; fi
  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then echo "$SUDO_USER"; return; fi
  local u
  u="$(getent passwd 1000 | cut -d: -f1)"
  if [ -n "$u" ]; then echo "$u"; return; fi
  echo "root"
}

SVC_USER="$(detect_user)"
if [ "$SVC_USER" = "root" ] && [ "$ACTION" = "install" ]; then
  die "could not detect a non-root WSL user — set SVC_USER explicitly:
  wsl.exe -d \"\$WSL_DISTRO_NAME\" -u root -- env SVC_USER=<youruser> bash infra/k8s/scripts/install-forward-services.sh install"
fi
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

PROD_UNITS="fmi-forward-prod.service fmi-tls-prod.service"
STAGING_UNITS="fmi-forward-staging.service"
UNITS="$PROD_UNITS $STAGING_UNITS"

remove_units() {
  for u in "$@"; do
    systemctl disable --now "$u" 2>/dev/null || true
    rm -f "$UNIT_DIR/$u"
  done
}

kctl() { KUBECONFIG="$KUBECONFIG_PATH" "$KUBECTL_BIN" --request-timeout=10s "$@"; }

if [ "$ACTION" = "uninstall" ]; then
  need_root
  check_systemd
  log "Removing FMI forward services"
  remove_units $UNITS
  systemctl daemon-reload
  systemctl reset-failed $UNITS 2>/dev/null || true
  rm -f /etc/sysctl.d/99-unpriv443.conf
  sysctl -w net.ipv4.ip_unprivileged_port_start=1024 >/dev/null 2>&1 || true
  echo "Removed: $UNITS"
  exit 0
fi

[ "$ACTION" = "install" ] || die "unknown action '$ACTION' — use 'install' or 'uninstall'."
need_root
check_systemd

[ -x "$KUBECTL_BIN" ] || die "kubectl not found at '$KUBECTL_BIN' — run install-tools.sh first."
[ -x "$SOCAT_BIN" ]   || die "socat not found at '$SOCAT_BIN' — install it (apt-get install -y socat)."
[ -f "$KUBECONFIG_PATH" ] || die "kubeconfig not found at '$KUBECONFIG_PATH' — set KUBECONFIG_PATH."
id "$SVC_USER" >/dev/null 2>&1 || die "user '$SVC_USER' does not exist — set SVC_USER."

# Without this, an API outage would look like "no env bootstrapped" and remove working units below.
kctl get --raw /readyz >/dev/null 2>&1 \
  || die "cluster API unreachable with '$KUBECONFIG_PATH' — start k3s (bootstrap-k3s.sh) and re-run."

# An env that isn't bootstrapped has no controller Service, and its port-forward would restart every 3s forever.
WITH_PROD=0
WITH_STAGING=0
kctl -n "$PROD_NS" get svc "$PROD_SVC" >/dev/null 2>&1 && WITH_PROD=1
kctl -n "$STAGING_NS" get svc "$STAGING_SVC" >/dev/null 2>&1 && WITH_STAGING=1
[ "$WITH_PROD" = 1 ] || [ "$WITH_STAGING" = 1 ] \
  || die "no ingress controller Service in '$PROD_NS' or '$STAGING_NS' — bootstrap an env first."

ENABLE_UNITS=""

if [ "$WITH_PROD" = 1 ]; then
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
Description=socat 127.0.0.1:443 to prod forward ${PROD_LOCAL} (serves fmicodes.com)
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
  ENABLE_UNITS="$ENABLE_UNITS $PROD_UNITS"
else
  log "Skipping prod: no $PROD_NS/$PROD_SVC Service (re-run after bootstrapping prod)"
  remove_units $PROD_UNITS
fi

if [ "$WITH_STAGING" = 1 ]; then
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
  ENABLE_UNITS="$ENABLE_UNITS $STAGING_UNITS"
else
  log "Skipping staging: no $STAGING_NS/$STAGING_SVC Service (re-run after bootstrapping staging)"
  remove_units $STAGING_UNITS
fi

log "Enabling + starting services"
systemctl daemon-reload
systemctl enable --now $ENABLE_UNITS

HOSTS_LINES=""
BROWSE_LINES=""
if [ "$WITH_PROD" = 1 ]; then
  HOSTS_LINES="${HOSTS_LINES}  127.0.0.1 fmicodes.com
"
  BROWSE_LINES="${BROWSE_LINES}  https://fmicodes.com           prod app
"
fi
if [ "$WITH_STAGING" = 1 ]; then
  HOSTS_LINES="${HOSTS_LINES}  127.0.0.1 staging.fmicodes.com
"
  BROWSE_LINES="${BROWSE_LINES}  https://staging.fmicodes.com:${STAGING_LOCAL}   staging app (self-signed cert)
"
fi

cat <<EOF

FMI forward services installed and enabled (auto-start on every boot):${ENABLE_UNITS}

Add to the Windows hosts file (C:\\Windows\\System32\\drivers\\etc\\hosts):
${HOSTS_LINES}
Then browse (no terminal needed, survives reboot):
${BROWSE_LINES}
Manage:
  systemctl status${ENABLE_UNITS}
  wsl.exe -d "\$WSL_DISTRO_NAME" -u root -- bash infra/k8s/scripts/install-forward-services.sh uninstall
EOF
