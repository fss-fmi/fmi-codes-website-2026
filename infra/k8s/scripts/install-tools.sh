#!/usr/bin/env bash

set -euo pipefail

KUBECTL_VERSION="${KUBECTL_VERSION:-v1.36.2}"
HELM_VERSION="${HELM_VERSION:-v3.21.3}"
K9S_VERSION="${K9S_VERSION:-v0.51.0}"
SOPS_VERSION="${SOPS_VERSION:-v3.13.2}"
AGE_VERSION="${AGE_VERSION:-v1.3.1}"
FLUX_VERSION="${FLUX_VERSION:-v2.9.2}"

AGE_SHA256_amd64="bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377"
AGE_SHA256_arm64="c6878a324421b69e3e20b00ba17c04bc5c6dab0030cfe55bf8f68fa8d9e9093a"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)  ARCH=amd64 ;;
  aarch64) ARCH=arm64 ;;
  *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
esac

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }

if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "Detected WSL2. (Native Debian/Ubuntu Linux works the same way.)" >&2
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

if ! command -v sops >/dev/null 2>&1; then
  log "Installing sops $SOPS_VERSION"
  rel="https://github.com/getsops/sops/releases/download/${SOPS_VERSION}"
  asset="sops-${SOPS_VERSION}.linux.${ARCH}"
  curl -sfL -o "$TMPDIR_DL/sops" "$rel/$asset"
  expected_sops="$(curl -sfL "$rel/sops-${SOPS_VERSION}.checksums.txt" | grep " ${asset}\$" | awk '{print $1}')"
  [ -n "$expected_sops" ] \
    || { echo "Could not find checksum for $asset in sops checksums.txt" >&2; exit 1; }
  verify_sha256 "$TMPDIR_DL/sops" "$expected_sops"
  chmod +x "$TMPDIR_DL/sops"
  sudo mv "$TMPDIR_DL/sops" /usr/local/bin/sops
else
  log "sops already installed — skipping"
fi

if ! command -v age >/dev/null 2>&1 || ! command -v age-keygen >/dev/null 2>&1; then
  log "Installing age $AGE_VERSION"
  tarball="age-${AGE_VERSION}-linux-${ARCH}.tar.gz"
  rel="https://github.com/FiloSottile/age/releases/download/${AGE_VERSION}"
  curl -sfL -o "$TMPDIR_DL/$tarball" "$rel/$tarball"
  eval "expected_age=\"\${AGE_SHA256_${ARCH}}\""
  [ -n "$expected_age" ] \
    || { echo "No pinned age checksum for arch $ARCH" >&2; exit 1; }
  verify_sha256 "$TMPDIR_DL/$tarball" "$expected_age"
  tar -xzf "$TMPDIR_DL/$tarball" -C "$TMPDIR_DL"
  sudo mv "$TMPDIR_DL/age/age" /usr/local/bin/age
  sudo mv "$TMPDIR_DL/age/age-keygen" /usr/local/bin/age-keygen
else
  log "age already installed — skipping"
fi

if ! command -v flux >/dev/null 2>&1; then
  log "Installing flux $FLUX_VERSION"
  ver="${FLUX_VERSION#v}"
  tarball="flux_${ver}_linux_${ARCH}.tar.gz"
  rel="https://github.com/fluxcd/flux2/releases/download/${FLUX_VERSION}"
  curl -sfL -o "$TMPDIR_DL/$tarball" "$rel/$tarball"
  expected_flux="$(curl -sfL "$rel/flux_${ver}_checksums.txt" | grep " ${tarball}\$" | awk '{print $1}')"
  [ -n "$expected_flux" ] \
    || { echo "Could not find checksum for $tarball in flux checksums.txt" >&2; exit 1; }
  verify_sha256 "$TMPDIR_DL/$tarball" "$expected_flux"
  tar -xzf "$TMPDIR_DL/$tarball" -C "$TMPDIR_DL"
  chmod +x "$TMPDIR_DL/flux"
  sudo mv "$TMPDIR_DL/flux" /usr/local/bin/flux
else
  log "flux already installed — skipping"
fi

log "Done. Installed tooling:"
{ command -v kubectl >/dev/null 2>&1 && kubectl version --client 2>/dev/null | head -1; } || true
{ command -v helm    >/dev/null 2>&1 && helm version --short 2>/dev/null; } || true
{ command -v k9s     >/dev/null 2>&1 && k9s version --short 2>/dev/null; } || true
{ command -v sops    >/dev/null 2>&1 && sops --version 2>/dev/null | head -1; } || true
{ command -v age     >/dev/null 2>&1 && age --version 2>/dev/null; } || true
{ command -v flux    >/dev/null 2>&1 && flux --version 2>/dev/null; } || true

cat <<'EOF'

Next:
  bash infra/k8s/scripts/init-linux.sh         # bring up the whole stack in order
  k9s -n fmi-codes                       # browse the cluster once it's up
EOF
