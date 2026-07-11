#!/usr/bin/env bash

set -euo pipefail

KUBECTL_VERSION="${KUBECTL_VERSION:-v1.36.2}"
HELM_VERSION="${HELM_VERSION:-v3.21.3}"
K9S_VERSION="${K9S_VERSION:-v0.51.0}"

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

TMPDIR_DL="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_DL"' EXIT

verify_sha256() {
  local file="$1" expected="$2" actual
  actual="$(sha256sum "$file" | awk '{print $1}')"
  [ "$actual" = "$expected" ] \
    || { echo "Checksum mismatch for $file: expected $expected, got $actual" >&2; exit 1; }
}

log "Checking prerequisites"
missing_pkgs=()
command -v curl      >/dev/null 2>&1 || missing_pkgs+=(curl)
command -v tar       >/dev/null 2>&1 || missing_pkgs+=(tar)
command -v sha256sum >/dev/null 2>&1 || missing_pkgs+=(coreutils)
[ -d /etc/ssl/certs ]                || missing_pkgs+=(ca-certificates)

if [ "${#missing_pkgs[@]}" -eq 0 ]; then
  log "All prerequisites already present — skipping apt"
else
  log "Installing missing prerequisites: ${missing_pkgs[*]}"
  sudo apt-get update -y \
    || echo "Warning: 'apt-get update' reported errors (likely an unrelated broken/expired third-party apt repo already on this machine, not this repo). Continuing." >&2
  sudo apt-get install -y "${missing_pkgs[@]}"
fi

if ! command -v kubectl >/dev/null 2>&1; then
  log "Installing kubectl $KUBECTL_VERSION"
  base="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${ARCH}"
  curl -sfL -o "$TMPDIR_DL/kubectl" "$base/kubectl"
  curl -sfL -o "$TMPDIR_DL/kubectl.sha256" "$base/kubectl.sha256"
  verify_sha256 "$TMPDIR_DL/kubectl" "$(cat "$TMPDIR_DL/kubectl.sha256")"
  chmod +x "$TMPDIR_DL/kubectl"
  sudo mv "$TMPDIR_DL/kubectl" /usr/local/bin/kubectl
else
  log "kubectl already installed — skipping"
fi

if ! command -v helm >/dev/null 2>&1; then
  log "Installing Helm $HELM_VERSION"
  tarball="helm-${HELM_VERSION}-linux-${ARCH}.tar.gz"
  curl -sfL -o "$TMPDIR_DL/$tarball" "https://get.helm.sh/$tarball"
  expected_helm="$(curl -sfL "https://get.helm.sh/${tarball}.sha256sum" | awk '{print $1}')"
  verify_sha256 "$TMPDIR_DL/$tarball" "$expected_helm"
  tar -xzf "$TMPDIR_DL/$tarball" -C "$TMPDIR_DL"
  sudo mv "$TMPDIR_DL/linux-${ARCH}/helm" /usr/local/bin/helm
else
  log "helm already installed — skipping"
fi

if ! command -v k9s >/dev/null 2>&1; then
  log "Installing k9s $K9S_VERSION"
  tarball="k9s_Linux_${ARCH}.tar.gz"
  rel="https://github.com/derailed/k9s/releases/download/${K9S_VERSION}"
  curl -sfL -o "$TMPDIR_DL/$tarball" "$rel/$tarball"
  expected_k9s="$(curl -sfL "$rel/checksums.sha256" | grep " ${tarball}\$" | awk '{print $1}')"
  [ -n "$expected_k9s" ] \
    || { echo "Could not find checksum for $tarball in k9s checksums.sha256" >&2; exit 1; }
  verify_sha256 "$TMPDIR_DL/$tarball" "$expected_k9s"
  tar -xzf "$TMPDIR_DL/$tarball" -C "$TMPDIR_DL"
  chmod +x "$TMPDIR_DL/k9s"
  sudo mv "$TMPDIR_DL/k9s" /usr/local/bin/k9s
else
  log "k9s already installed — skipping"
fi

log "Done. Installed tooling:"
{ command -v kubectl >/dev/null 2>&1 && kubectl version --client 2>/dev/null | head -1; } || true
{ command -v helm    >/dev/null 2>&1 && helm version --short 2>/dev/null; } || true
{ command -v k9s     >/dev/null 2>&1 && k9s version --short 2>/dev/null; } || true

cat <<'EOF'

Next:
  bash infra/k8s/bootstrap-wsl2-k3s.sh   # stand up the cluster + namespace
  k9s -n fmi-codes                       # browse the cluster once it's up
EOF
