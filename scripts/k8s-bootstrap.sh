#!/usr/bin/env bash
#
# k8s-bootstrap.sh — Phase 1 of the k8s migration (issue #26).
#
# Stands up a local single-node k3s cluster as the foundation for later phases,
# then creates the `fmi-codes` namespace the rest of the deployment lives in.
#
# What it does:
#   1. Installs k3s as a systemd service (survives host reboots) if not present.
#   2. Confirms kubectl works against the cluster.
#   3. Applies k8s/namespace.yaml.
#   4. Verifies the acceptance criteria from #26.
#
# Idempotent: safe to re-run. If k3s is already installed it is left as-is,
# and applying the namespace again is a no-op.
#
# Usage:
#   ./scripts/k8s-bootstrap.sh
#
# Requires: Linux with systemd, curl, and sudo. k3s is Linux-only — on macOS or
# Windows run this inside a Linux VM (or use kind instead; see k8s/README.md).

set -euo pipefail

# Resolve the repo root from this script's location so it works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
NAMESPACE_MANIFEST="${REPO_ROOT}/k8s/namespace.yaml"
NAMESPACE="fmi-codes"

# Pin the k3s channel for reproducible bring-ups instead of tracking "latest".
K3S_CHANNEL="${K3S_CHANNEL:-stable}"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m warn:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

require_linux_systemd() {
  [ "$(uname -s)" = "Linux" ] || die "k3s is Linux-only. Run inside a Linux VM, or use kind (see k8s/README.md)."
  command -v systemctl >/dev/null 2>&1 || die "systemd (systemctl) not found — required to install k3s as a persistent service."
  command -v curl >/dev/null 2>&1 || die "curl not found — required to fetch the k3s installer."
}

install_k3s() {
  if command -v k3s >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q '^k3s\.service'; then
    log "k3s already installed as a systemd service — skipping install."
    return
  fi

  log "Installing k3s (channel: ${K3S_CHANNEL}) as a systemd service…"
  # --write-kubeconfig-mode 644 lets a non-root user read the kubeconfig.
  # The official installer registers and enables the k3s systemd unit, so the
  # cluster comes back automatically after a reboot.
  curl -sfL https://get.k3s.io | \
    INSTALL_K3S_CHANNEL="${K3S_CHANNEL}" \
    INSTALL_K3S_EXEC="--write-kubeconfig-mode 644" \
    sh -

  systemctl is-enabled --quiet k3s \
    || warn "k3s.service is not enabled — it may not survive a reboot. Enable with: sudo systemctl enable k3s"
}

setup_kubeconfig() {
  # Prefer an existing kubeconfig the user already points at; otherwise fall
  # back to the one k3s writes. Exported so the kubectl calls below see it.
  if [ -n "${KUBECONFIG:-}" ] && [ -f "${KUBECONFIG}" ]; then
    log "Using KUBECONFIG from environment: ${KUBECONFIG}"
  elif [ -f "${HOME}/.kube/config" ]; then
    log "Using kubeconfig at ~/.kube/config"
  elif [ -f /etc/rancher/k3s/k3s.yaml ]; then
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
    log "Using k3s kubeconfig at /etc/rancher/k3s/k3s.yaml"
  else
    die "No kubeconfig found. Expected /etc/rancher/k3s/k3s.yaml after k3s install."
  fi
}

# k3s bundles its own kubectl; prefer a standalone one if the user has it.
kubectl_cmd() {
  if command -v kubectl >/dev/null 2>&1; then
    kubectl "$@"
  else
    k3s kubectl "$@"
  fi
}

wait_for_node_ready() {
  log "Waiting for a node to become Ready (up to 120s)…"
  # `kubectl wait` returns non-zero on timeout, which -e would turn into an
  # exit; capture it so we can print a clearer diagnostic first.
  if ! kubectl_cmd wait --for=condition=Ready nodes --all --timeout=120s >/dev/null 2>&1; then
    kubectl_cmd get nodes || true
    die "No node reached Ready within 120s. Check 'sudo systemctl status k3s' and 'sudo journalctl -u k3s'."
  fi
}

apply_namespace() {
  [ -f "${NAMESPACE_MANIFEST}" ] || die "Namespace manifest not found at ${NAMESPACE_MANIFEST}"
  log "Applying namespace manifest…"
  kubectl_cmd apply -f "${NAMESPACE_MANIFEST}"
}

verify() {
  log "Verifying acceptance criteria (#26)…"
  echo
  echo "  kubectl get nodes:"
  kubectl_cmd get nodes | sed 's/^/    /'
  echo
  echo "  kubectl get namespace ${NAMESPACE}:"
  kubectl_cmd get namespace "${NAMESPACE}" | sed 's/^/    /'
  echo

  if systemctl is-enabled --quiet k3s 2>/dev/null; then
    log "k3s.service is enabled — cluster will survive a host reboot. ✅"
  else
    warn "k3s.service is NOT enabled — cluster may not survive a reboot."
  fi
}

main() {
  require_linux_systemd
  install_k3s
  setup_kubeconfig
  wait_for_node_ready
  apply_namespace
  verify
  log "Phase 1 complete. Cluster is up and the '${NAMESPACE}' namespace exists."
}

main "$@"
