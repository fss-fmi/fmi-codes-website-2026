#!/usr/bin/env bash
# Phase 1 (#26) helper: install the WSL2 dev tooling for working with the cluster.
#
# Think of it as the "npm install" for this repo's k8s workflow — one command to
# get every CLI you need inside WSL2 Ubuntu:
#   - kubectl : talk to the cluster
#   - helm    : install Phase 2's Postgres/Redis Sentinel charts
#   - k9s     : terminal UI for browsing/among pods, logs, exec, etc.
#
# Usage (inside a WSL2 Ubuntu shell):
#   bash infra/k8s/install-tools-wsl2.sh
#
# Safe to re-run — every tool is skipped if already present. This does NOT stand
# up the cluster; run bootstrap-wsl2-k3s.sh for that.

set -euo pipefail

# Match kubectl's arch naming (amd64/arm64) to the machine.
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)  ARCH=amd64 ;;
  aarch64) ARCH=arm64 ;;
  *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
esac

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }

if ! grep -qi microsoft /proc/version 2>/dev/null; then
  echo "Warning: this doesn't look like WSL2. Continuing anyway — Ctrl+C to abort." >&2
fi

log "Installing prerequisites"
sudo apt-get update -y
sudo apt-get install -y curl ca-certificates apt-transport-https gnupg tar

if ! command -v kubectl >/dev/null 2>&1; then
  log "Installing kubectl"
  curl -sfLO "https://dl.k8s.io/release/$(curl -sfL https://dl.k8s.io/release/stable.txt)/bin/linux/${ARCH}/kubectl"
  chmod +x kubectl
  sudo mv kubectl /usr/local/bin/kubectl
else
  log "kubectl already installed — skipping ($(kubectl version --client -o yaml 2>/dev/null | grep -m1 gitVersion || true))"
fi

if ! command -v helm >/dev/null 2>&1; then
  log "Installing Helm"
  curl -sfL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
else
  log "helm already installed — skipping"
fi

if ! command -v k9s >/dev/null 2>&1; then
  log "Installing k9s"
  # k9s ships prebuilt tarballs on GitHub releases; grab the latest for this arch.
  K9S_VERSION="$(curl -sfL https://api.github.com/repos/derailed/k9s/releases/latest | grep -m1 '"tag_name"' | cut -d'"' -f4)"
  curl -sfLO "https://github.com/derailed/k9s/releases/download/${K9S_VERSION}/k9s_Linux_${ARCH}.tar.gz"
  tar -xzf "k9s_Linux_${ARCH}.tar.gz" k9s
  chmod +x k9s
  sudo mv k9s /usr/local/bin/k9s
  rm -f "k9s_Linux_${ARCH}.tar.gz"
else
  log "k9s already installed — skipping"
fi

log "Done. Installed tooling:"
command -v kubectl >/dev/null 2>&1 && kubectl version --client 2>/dev/null | head -1
command -v helm    >/dev/null 2>&1 && helm version --short 2>/dev/null
command -v k9s     >/dev/null 2>&1 && k9s version --short 2>/dev/null

cat <<'EOF'

Next:
  bash infra/k8s/bootstrap-wsl2-k3s.sh   # stand up the cluster + namespace
  k9s -n fmi-codes                       # browse the cluster once it's up
EOF
