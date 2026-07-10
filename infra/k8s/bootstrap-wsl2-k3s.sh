#!/usr/bin/env bash
# Phase 1 (#26): bootstrap a local k3s cluster inside WSL2 Ubuntu.
#
# Usage (inside a WSL2 Ubuntu shell):
#   bash infra/k8s/bootstrap-wsl2-k3s.sh
#
# What this does:
#   1. Installs k3s, pinned to $K3S_VERSION (Traefik disabled — Phase 4 installs
#      ingress-nginx instead), with a private (600) kubeconfig.
#   2. Points kubectl at the new cluster via ~/.kube/config
#   3. Installs Helm (needed for Phase 2's Postgres/Redis charts)
#   4. Creates the app namespace (from namespace.yaml when run from a checkout)
#
# Safe to re-run — every step is idempotent.
#
# Supply-chain note: step 1 runs the official k3s installer from get.k3s.io. That
# installer executes with sudo (it registers a system service and drops binaries
# under /usr/local/bin) and GPG-verifies the k3s binary it fetches. We pin the
# version so re-runs are reproducible. If you prefer not to run a remote installer
# as root, install k3s from a downloaded release binary out of band instead.

set -euo pipefail

NAMESPACE="${NAMESPACE:-fmi-codes}"
# Pinned versions — bump to upgrade rather than tracking "latest".
K3S_VERSION="${K3S_VERSION:-v1.36.2+k3s1}"
HELM_VERSION="${HELM_VERSION:-v3.21.3}"   # v3 line — Phase 2 charts target Helm 3, not 4

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

command -v apt-get >/dev/null 2>&1 \
  || { echo "This script requires an apt-based distro (Ubuntu/Debian)." >&2; exit 1; }

log "Installing prerequisites"
sudo apt-get update -y
sudo apt-get install -y curl ca-certificates apt-transport-https gnupg tar coreutils

log "Installing k3s $K3S_VERSION (Traefik disabled, Phase 4 brings its own ingress controller)"
# --write-kubeconfig-mode 600 keeps the cluster-admin kubeconfig private at its
# source (/etc/rancher/k3s/k3s.yaml) — not just the copy we make below.
curl -sfL https://get.k3s.io \
  | INSTALL_K3S_VERSION="$K3S_VERSION" sh -s - --disable traefik --write-kubeconfig-mode 600

log "Waiting for the node to become Ready"
if ! sudo k3s kubectl wait --for=condition=Ready node --all --timeout=180s; then
  echo "Node not Ready within 180s. k3s is already installed as a service — just" >&2
  echo "re-run this script (it's idempotent) once the machine has settled." >&2
  exit 1
fi

log "Wiring up kubectl for your user (no sudo needed for future kubectl calls)"
mkdir -p "$HOME/.kube"
sudo cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
sudo chown "$(id -u)":"$(id -g)" "$HOME/.kube/config"
chmod 600 "$HOME/.kube/config"

# Downloads land in a scratch dir wiped on exit — nothing left in the caller's CWD.
TMPDIR_DL="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_DL"' EXIT

if ! command -v kubectl >/dev/null 2>&1; then
  log "Installing standalone kubectl (k3s bundles its own, but this matches upstream tooling/docs)"
  base="https://dl.k8s.io/release/$(curl -sfL https://dl.k8s.io/release/stable.txt)/bin/linux/${ARCH}"
  curl -sfL -o "$TMPDIR_DL/kubectl" "$base/kubectl"
  curl -sfL -o "$TMPDIR_DL/kubectl.sha256" "$base/kubectl.sha256"
  actual="$(sha256sum "$TMPDIR_DL/kubectl" | awk '{print $1}')"
  [ "$actual" = "$(cat "$TMPDIR_DL/kubectl.sha256")" ] \
    || { echo "kubectl checksum mismatch" >&2; exit 1; }
  chmod +x "$TMPDIR_DL/kubectl"
  sudo mv "$TMPDIR_DL/kubectl" /usr/local/bin/kubectl
fi

if ! command -v helm >/dev/null 2>&1; then
  log "Installing Helm $HELM_VERSION (needed for Phase 2's Postgres/Redis Sentinel charts)"
  tarball="helm-${HELM_VERSION}-linux-${ARCH}.tar.gz"
  curl -sfL -o "$TMPDIR_DL/$tarball" "https://get.helm.sh/$tarball"
  expected_helm="$(curl -sfL "https://get.helm.sh/${tarball}.sha256sum" | awk '{print $1}')"
  actual="$(sha256sum "$TMPDIR_DL/$tarball" | awk '{print $1}')"
  [ "$actual" = "$expected_helm" ] \
    || { echo "helm checksum mismatch" >&2; exit 1; }
  tar -xzf "$TMPDIR_DL/$tarball" -C "$TMPDIR_DL"
  sudo mv "$TMPDIR_DL/linux-${ARCH}/helm" /usr/local/bin/helm
fi

log "Creating namespace '$NAMESPACE'"
# Prefer the declarative manifest that ships next to this script (reviewable,
# version-controlled). When run via `curl | bash` there's no local checkout, so
# fall back to generating an equivalently-labeled namespace on the fly.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
NAMESPACE_MANIFEST="${SCRIPT_DIR:-}/namespace.yaml"
if [ "$NAMESPACE" = "fmi-codes" ] && [ -f "$NAMESPACE_MANIFEST" ]; then
  kubectl apply -f "$NAMESPACE_MANIFEST"
else
  # Custom NAMESPACE override, or no checkout (piped from curl). Apply the same
  # app.kubernetes.io/* labels the manifest carries so both paths agree.
  kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml \
    | kubectl label --local -f - \
        "app.kubernetes.io/name=${NAMESPACE}" \
        app.kubernetes.io/part-of=fmi-codes-website-2026 \
        app.kubernetes.io/managed-by=kubectl \
        -o yaml \
    | kubectl apply -f -
fi

log "Done. Verifying cluster:"
kubectl get nodes -o wide
kubectl get namespace "$NAMESPACE"

cat <<EOF

Next steps:
  - kubectl config current-context   # confirm it points at the new cluster
  - kubectl get pods -A              # sanity check core k3s pods are Running
  - Move on to Phase 2 (#27): Postgres + Redis Sentinel via Helm, into the '$NAMESPACE' namespace
EOF
