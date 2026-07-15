#!/usr/bin/env bash

set -euo pipefail

FLUX_NAMESPACE="${FLUX_NAMESPACE:-flux-system}"
GIT_URL="${GIT_URL:-ssh://git@github.com/fss-fmi/fmi-codes-website-2026.git}"
GIT_REF="${GIT_REF:-main}"
GIT_SECRET="${GIT_SECRET:-flux-git-auth}"
DEPLOY_KEY="${DEPLOY_KEY:-$HOME/.ssh/fmi-codes-flux}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FLUX_DIR="$K8S_DIR/flux"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
command -v flux    >/dev/null 2>&1 || die "flux not found — run install-tools.sh first."
[ -d "$FLUX_DIR" ] || die "missing $FLUX_DIR"

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

log "Installing Flux controllers into '$FLUX_NAMESPACE'"
flux install --namespace "$FLUX_NAMESPACE" \
  --components-extra=image-reflector-controller,image-automation-controller

if kubectl -n "$FLUX_NAMESPACE" get secret "$GIT_SECRET" >/dev/null 2>&1; then
  echo "Secret $GIT_SECRET already exists — leaving it untouched."
else
  [ -f "$DEPLOY_KEY" ] \
    || die "deploy key not found at $DEPLOY_KEY. Generate one with 'ssh-keygen -t ed25519 -f $DEPLOY_KEY -N \"\"', add the .pub as a repo deploy key WITH WRITE access, then re-run (override the path with DEPLOY_KEY=)."
  log "Creating git auth secret '$GIT_SECRET' from $DEPLOY_KEY"
  flux create secret git "$GIT_SECRET" \
    --namespace "$FLUX_NAMESPACE" \
    --url "$GIT_URL" \
    --private-key-file "$DEPLOY_KEY"
fi

log "Applying Flux source, kustomization, and image-automation resources"
kubectl apply -f "$FLUX_DIR/source.yaml"
kubectl apply -f "$FLUX_DIR/image-automation.yaml"

if [ "$GIT_REF" != "main" ]; then
  log "Overriding tracked branch to '$GIT_REF' (committed default is 'main')"
  kubectl -n "$FLUX_NAMESPACE" patch gitrepository fmi-codes \
    --type merge -p "{\"spec\":{\"ref\":{\"branch\":\"$GIT_REF\"}}}"
  kubectl -n "$FLUX_NAMESPACE" patch imageupdateautomation fmi-codes \
    --type merge -p "{\"spec\":{\"git\":{\"checkout\":{\"ref\":{\"branch\":\"$GIT_REF\"}},\"push\":{\"branch\":\"$GIT_REF\"}}}}"
fi

log "Waiting for the git source and kustomization to reconcile"
flux reconcile source git fmi-codes --namespace "$FLUX_NAMESPACE" || true
flux reconcile kustomization fmi-codes --namespace "$FLUX_NAMESPACE" --timeout 5m || true

log "Current Flux state:"
flux get sources git --namespace "$FLUX_NAMESPACE"
flux get kustomizations --namespace "$FLUX_NAMESPACE"
flux get images all --namespace "$FLUX_NAMESPACE"

cat <<EOF

GitOps is live. From now on, a merge to main that changes backend or frontend:
  1. docker-cd.yaml builds & pushes an immutable <unix-ts>-<sha> image tag.
  2. Flux detects the newer tag and opens a commit on the 'flux-image-updates'
     branch bumping the tag in infra/k8s/manifests/kustomization.yaml.
  3. You review/merge that branch into main.
  4. Flux reconciles main and rolls ONLY the changed Deployment.

Watch it:
  flux get images all --namespace $FLUX_NAMESPACE
  flux get kustomizations --namespace $FLUX_NAMESPACE
  kubectl -n fmi-codes get pods -w
EOF
