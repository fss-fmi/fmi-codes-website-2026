#!/usr/bin/env bash
# Phase 1 (#26) helper: install the WSL2 dev tooling for working with the cluster.
#
# Think of it as the "npm install" for this repo's k8s workflow — one command to
# get every CLI you need inside WSL2 Ubuntu:
#   - kubectl : talk to the cluster
#   - helm    : install Phase 2's Postgres/Redis Sentinel charts
#   - k9s     : terminal UI for browsing pods, logs, exec, etc.
#
# Usage (inside a WSL2 Ubuntu shell):
#   bash infra/k8s/install-tools-wsl2.sh
#
# Safe to re-run — every tool is skipped if already present. This does NOT stand
# up the cluster; run bootstrap-wsl2-k3s.sh for that.
#
# Supply-chain note: each tool is pinned to a specific version and every download
# is checksum-verified against the vendor-published SHA256 before install. Bump
# the *_VERSION pins below to upgrade. Nothing here is piped straight into a shell.

set -euo pipefail

# Pinned tool versions. Bump these to upgrade — do not track "latest".
KUBECTL_VERSION="${KUBECTL_VERSION:-v1.36.2}"
HELM_VERSION="${HELM_VERSION:-v3.21.3}"   # v3 line — Phase 2 charts target Helm 3, not 4
K9S_VERSION="${K9S_VERSION:-v0.51.0}"

# Match each vendor's arch naming (amd64/arm64) to the machine.
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

# All downloads land in a scratch dir that's wiped on exit, so nothing is left in
# the caller's CWD and a partial failure never litters the working tree.
TMPDIR_DL="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_DL"' EXIT

# verify_sha256 <file> <expected_hex> — abort if the download doesn't match.
verify_sha256() {
  local file="$1" expected="$2" actual
  actual="$(sha256sum "$file" | awk '{print $1}')"
  [ "$actual" = "$expected" ] \
    || { echo "Checksum mismatch for $file: expected $expected, got $actual" >&2; exit 1; }
}

log "Installing prerequisites"
sudo apt-get update -y
sudo apt-get install -y curl ca-certificates apt-transport-https gnupg tar coreutils

if ! command -v kubectl >/dev/null 2>&1; then
  log "Installing kubectl $KUBECTL_VERSION"
  base="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${ARCH}"
  curl -sfL -o "$TMPDIR_DL/kubectl" "$base/kubectl"
  # kubectl publishes a per-binary .sha256 alongside each release artifact.
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
  # get.helm.sh serves a matching .sha256sum ("<hash>  <filename>") per artifact.
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
  # k9s publishes one checksums.sha256 covering all assets ("<hash>  <filename>").
  expected_k9s="$(curl -sfL "$rel/checksums.sha256" | grep " ${tarball}\$" | awk '{print $1}')"
  [ -n "$expected_k9s" ] \
    || { echo "Could not find checksum for $tarball in k9s checksums.sha256" >&2; exit 1; }
  verify_sha256 "$TMPDIR_DL/$tarball" "$expected_k9s"
  # Extract into the scratch dir rather than assuming the binary name at the root.
  tar -xzf "$TMPDIR_DL/$tarball" -C "$TMPDIR_DL"
  chmod +x "$TMPDIR_DL/k9s"
  sudo mv "$TMPDIR_DL/k9s" /usr/local/bin/k9s
else
  log "k9s already installed — skipping"
fi

log "Done. Installed tooling:"
# `... | head`/`--short` can close the pipe early and trip -o pipefail, so each
# summary line is guarded with `|| true` — a version print must never abort the run.
{ command -v kubectl >/dev/null 2>&1 && kubectl version --client 2>/dev/null | head -1; } || true
{ command -v helm    >/dev/null 2>&1 && helm version --short 2>/dev/null; } || true
{ command -v k9s     >/dev/null 2>&1 && k9s version --short 2>/dev/null; } || true

cat <<'EOF'

Next:
  bash infra/k8s/bootstrap-wsl2-k3s.sh   # stand up the cluster + namespace
  k9s -n fmi-codes                       # browse the cluster once it's up
EOF
