#!/usr/bin/env bash
# Phase 1 (#26): bootstrap a local k3s cluster inside WSL2 Ubuntu.
#
# Usage (inside a WSL2 Ubuntu shell):
#   curl -fsSL https://raw.githubusercontent.com/fss-fmi/fmi-codes-website-2026/main/infra/k8s/bootstrap-wsl2-k3s.sh | bash
# or, if you already cloned the repo:
#   bash infra/k8s/bootstrap-wsl2-k3s.sh
#
# What this does:
#   1. Installs k3s (Traefik disabled — Phase 4 installs ingress-nginx instead)
#   2. Points kubectl at the new cluster via ~/.kube/config
#   3. Installs Helm (needed for Phase 2's Postgres/Redis charts)
#   4. Creates the app namespace
#
# Safe to re-run — every step is idempotent.

set -euo pipefail

NAMESPACE="${NAMESPACE:-fmi-codes}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }

if ! grep -qi microsoft /proc/version 2>/dev/null; then
  echo "Warning: this doesn't look like WSL2. Continuing anyway — Ctrl+C to abort." >&2
fi

log "Installing prerequisites"
sudo apt-get update -y
sudo apt-get install -y curl ca-certificates apt-transport-https gnupg

log "Installing k3s (Traefik disabled, Phase 4 brings its own ingress controller)"
curl -sfL https://get.k3s.io | sh -s - --disable traefik

log "Waiting for the node to become Ready"
sudo k3s kubectl wait --for=condition=Ready node --all --timeout=120s

log "Wiring up kubectl for your user (no sudo needed for future kubectl calls)"
mkdir -p "$HOME/.kube"
sudo cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
sudo chown "$(id -u)":"$(id -g)" "$HOME/.kube/config"
chmod 600 "$HOME/.kube/config"

if ! command -v kubectl >/dev/null 2>&1; then
  log "Installing standalone kubectl (k3s bundles its own, but this matches upstream tooling/docs)"
  curl -sfLO "https://dl.k8s.io/release/$(curl -sfL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  chmod +x kubectl
  sudo mv kubectl /usr/local/bin/kubectl
fi

if ! command -v helm >/dev/null 2>&1; then
  log "Installing Helm (needed for Phase 2's Postgres/Redis Sentinel charts)"
  curl -sfL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

log "Creating namespace '$NAMESPACE'"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

log "Done. Verifying cluster:"
kubectl get nodes -o wide
kubectl get namespace "$NAMESPACE"

cat <<EOF

Next steps:
  - kubectl config current-context   # confirm it points at the new cluster
  - kubectl get pods -A              # sanity check core k3s pods are Running
  - Move on to Phase 2 (#27): Postgres + Redis Sentinel via Helm, into the '$NAMESPACE' namespace
EOF
