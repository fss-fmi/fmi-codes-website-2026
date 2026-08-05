#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
case "$ENV" in
  prod)    APP_NAMESPACE="fmi-codes"; FLUX_RESOURCE="fmi-codes" ;;
  staging) APP_NAMESPACE="fmi-codes-staging"; FLUX_RESOURCE="fmi-codes-staging" ;;
  *)       echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac
FLUX_NAMESPACE="${FLUX_NAMESPACE:-flux-system}"
GIT_URL="${GIT_URL:-ssh://git@github.com/fss-fmi/fmi-codes-website-2026.git}"
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
  log "Verifying deploy key can authenticate to GitHub"
  if ! ssh -i "$DEPLOY_KEY" -o StrictHostKeyChecking=accept-new -o BatchMode=yes \
       -o ConnectTimeout=10 git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo ""
    echo "Warning: the deploy key at $DEPLOY_KEY could not authenticate to GitHub."
    echo "Flux will fail to pull from the repo until the public key is registered."
    echo ""
    echo "Add this public key to the repo with write access:"
    echo "  GitHub → repo → Settings → Deploy keys → Add deploy key → tick 'Allow write access'"
    echo ""
    cat "${DEPLOY_KEY}.pub" 2>/dev/null || echo "(public key file not found at ${DEPLOY_KEY}.pub)"
    echo ""
    echo "Continuing — the secret will be written, but Flux reconciliation will fail until the key is registered."
  else
    echo "Deploy key authenticated successfully."
  fi
  log "Creating git auth secret '$GIT_SECRET' from $DEPLOY_KEY"
  flux create secret git "$GIT_SECRET" \
    --namespace "$FLUX_NAMESPACE" \
    --url "$GIT_URL" \
    --private-key-file "$DEPLOY_KEY"
fi

log "Applying Flux source, image-automation, and self-managing resources"
kubectl apply -f "$FLUX_DIR/source.yaml"
kubectl apply -f "$FLUX_DIR/image-automation.yaml"
kubectl apply -f "$FLUX_DIR/self.yaml"

log "Waiting for the git source and kustomization to reconcile"
flux reconcile source git fmi-codes --namespace "$FLUX_NAMESPACE" || true
flux reconcile kustomization "$FLUX_RESOURCE" --namespace "$FLUX_NAMESPACE" --timeout 5m || true
flux reconcile kustomization flux-system-config --namespace "$FLUX_NAMESPACE" --timeout 5m || true

log "Current Flux state:"
flux get sources git --namespace "$FLUX_NAMESPACE"
flux get kustomizations --namespace "$FLUX_NAMESPACE"
flux get images all --namespace "$FLUX_NAMESPACE"

cat <<EOF

GitOps is live. From now on, a merge to main that changes backend or frontend:
  1. docker-cd.yaml builds & pushes an immutable <unix-ts>-<sha> image tag.
  2. Flux detects the newer tag and opens a commit on the 'flux-image-updates'
     branch bumping the tag in infra/k8s/overlays/$ENV/kustomization.yaml.
  3. You review/merge that branch into main.
  4. Flux reconciles main and rolls ONLY the changed Deployment.

Watch it:
  flux get images all --namespace $FLUX_NAMESPACE
  flux get kustomizations --namespace $FLUX_NAMESPACE
  kubectl -n $APP_NAMESPACE get pods -w
EOF
