#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
case "$ENV" in
  prod)    NAMESPACE="${NAMESPACE:-fmi-codes}" ;;
  staging) NAMESPACE="${NAMESPACE:-fmi-codes-staging}" ;;
  *)       echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac
K3S_VERSION="${K3S_VERSION:-v1.36.2+k3s1}"
HELM_VERSION="${HELM_VERSION:-v3.21.3}"
IMAGE_MAX_GC_AGE="${IMAGE_MAX_GC_AGE:-168h}"

API_TIMEOUT="${API_TIMEOUT:-300}"
NODE_TIMEOUT="${NODE_TIMEOUT:-180}"
CRASH_LOOP_MAX_RESTARTS="${CRASH_LOOP_MAX_RESTARTS:-3}"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)  ARCH=amd64 ;;
  aarch64) ARCH=arm64 ;;
  *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
esac

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }

dump_k3s_diagnostics() {
  echo >&2
  echo "----- systemctl status k3s -----" >&2
  sudo systemctl status k3s --no-pager --full 2>&1 | sed -n '1,15p' >&2 || true
  echo >&2
  echo "----- journalctl -u k3s (last 60 lines) -----" >&2
  sudo journalctl -u k3s --no-pager --lines=60 >&2 || true
  echo >&2
}

k3s_restart_count() {
  sudo systemctl show k3s -p NRestarts --value 2>/dev/null | grep -E '^[0-9]+$' || echo 0
}

if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "Detected WSL2. (Native Debian/Ubuntu Linux works the same way.)" >&2
fi

command -v apt-get >/dev/null 2>&1 \
  || { echo "This script requires an apt-based distro (Ubuntu/Debian)." >&2; exit 1; }

log "Installing prerequisites"
sudo apt-get update -y
sudo apt-get install -y curl ca-certificates apt-transport-https gnupg tar coreutils

# Size-based image GC only starts at 85% disk; on WSL2's 1 TB virtual disk the Windows drive fills
# first, so every deployed version piles up. Modes match what k3s creates.
log "Removing images unused for $IMAGE_MAX_GC_AGE (kubelet drop-in)"
KUBELET_DROPIN_DIR=/var/lib/rancher/k3s/agent/etc/kubelet.conf.d
KUBELET_DROPIN="$KUBELET_DROPIN_DIR/50-image-gc.conf"
KUBELET_DROPIN_CONTENT="apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
imageMaximumGCAge: ${IMAGE_MAX_GC_AGE}"
# The installer skips its restart when k3s itself is unchanged, so a changed drop-in has to force it.
K3S_FORCE_RESTART=false
sudo install -d -m 755 /var/lib/rancher/k3s
sudo install -d -m 700 /var/lib/rancher/k3s/agent /var/lib/rancher/k3s/agent/etc "$KUBELET_DROPIN_DIR"
if [ "$(sudo cat "$KUBELET_DROPIN" 2>/dev/null)" != "$KUBELET_DROPIN_CONTENT" ]; then
  # Not `install /dev/stdin`: uutils install (Ubuntu 26.04) fails reading stdin onto an existing file.
  printf '%s\n' "$KUBELET_DROPIN_CONTENT" | sudo tee "$KUBELET_DROPIN" >/dev/null
  sudo chmod 600 "$KUBELET_DROPIN"
  K3S_FORCE_RESTART=true
fi

log "Installing k3s $K3S_VERSION (Traefik disabled, Phase 4 brings its own ingress controller)"
curl -sfL https://get.k3s.io \
  | INSTALL_K3S_VERSION="$K3S_VERSION" INSTALL_K3S_FORCE_RESTART="$K3S_FORCE_RESTART" \
    sh -s - --disable traefik --write-kubeconfig-mode 600

log "Waiting for the k3s API server to accept connections (up to ${API_TIMEOUT}s)"
api_ready=false
restarts_baseline="$(k3s_restart_count)"
deadline=$(( $(date +%s) + API_TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if sudo k3s kubectl get --raw='/readyz' >/dev/null 2>&1; then
    api_ready=true
    break
  fi
  restarts_now="$(k3s_restart_count)"
  if [ "$(( restarts_now - restarts_baseline ))" -ge "$CRASH_LOOP_MAX_RESTARTS" ]; then
    echo "k3s has restarted $(( restarts_now - restarts_baseline )) times while waiting — it's crash-looping, not just slow to start." >&2
    dump_k3s_diagnostics
    echo "The journal above shows why k3s keeps exiting. Common WSL2 causes:" >&2
    echo "  - missing iptables tools (install with: sudo apt-get install -y iptables)" >&2
    echo "  - a stale cluster from a prior boot (reset with: sudo k3s-killall.sh; sudo rm -rf /var/lib/rancher/k3s)" >&2
    echo "  - too little memory given to WSL2 (raise the limit in %USERPROFILE%\\.wslconfig)" >&2
    exit 1
  fi
  sleep 3
done
if ! $api_ready; then
  echo "k3s API server did not come up within ${API_TIMEOUT}s." >&2
  dump_k3s_diagnostics
  echo "Fix the cause shown above, then re-run this script (it's idempotent)." >&2
  exit 1
fi

log "Waiting for the node to become Ready (up to ${NODE_TIMEOUT}s)"
if ! sudo k3s kubectl wait --for=condition=Ready node --all --timeout="${NODE_TIMEOUT}s"; then
  echo "Node not Ready within ${NODE_TIMEOUT}s." >&2
  dump_k3s_diagnostics
  echo "Fix the cause shown above, then re-run this script (it's idempotent)." >&2
  exit 1
fi

log "Wiring up kubectl for your user (no sudo needed for future kubectl calls)"
mkdir -p "$HOME/.kube"
sudo cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
sudo chown "$(id -u)":"$(id -g)" "$HOME/.kube/config"
chmod 600 "$HOME/.kube/config"

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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
NAMESPACE_MANIFEST="${SCRIPT_DIR:+$SCRIPT_DIR/../base/app}/namespace.yaml"
if [ "$NAMESPACE" = "fmi-codes" ] && [ -f "$NAMESPACE_MANIFEST" ]; then
  kubectl apply -f "$NAMESPACE_MANIFEST"
else
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
