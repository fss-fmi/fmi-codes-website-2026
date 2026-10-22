#!/usr/bin/env bash
# Render the db-migrate Job into an overlay and register it as a resource.
# Used by .github/workflows/migrate-database.yaml and by CI to validate the result.
#
# Usage: render-migrate-job.sh <staging|prod> <run-id> <backend-image-tag> [k8s-dir]

set -euo pipefail

ENV="${1:-}"
RUN_ID="${2:-}"
TAG="${3:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="${4:-$(cd "$SCRIPT_DIR/.." && pwd)}"

die() { echo "Error: $1" >&2; exit 1; }

case "$ENV" in
  staging|prod) ;;
  *) die "environment must be 'staging' or 'prod', got '$ENV'" ;;
esac
case "$RUN_ID" in
  ''|*[!0-9]*) die "run id must be numeric, got '$RUN_ID'" ;;
esac
case "$TAG" in
  [0-9]*-*[0-9a-f]) ;;
  *) die "image tag '$TAG' must match the <unix-ts>-<short-sha> scheme" ;;
esac

overlay="$K8S_DIR/overlays/$ENV"
sed -e "s/__RUN_ID__/$RUN_ID/g" -e "s/__IMAGE_TAG__/$TAG/g" \
  "$K8S_DIR/templates/db-migrate-job.yaml" > "$overlay/db-migrate-job.yaml"

# Not `kustomize edit add resource`: it rewrites the file and drops the staging
# overlay's `# {"$imagepolicy": ...}` markers, which silently stops Flux's
# staging image automation.
kustomization="$overlay/kustomization.yaml"
if ! grep -q 'db-migrate-job.yaml' "$kustomization"; then
  sed -i -E 's#^([[:space:]]*)- \.\./\.\./base/app$#&\n\1- db-migrate-job.yaml#' "$kustomization"
  grep -q 'db-migrate-job.yaml' "$kustomization" \
    || die "could not add db-migrate-job.yaml to $kustomization resources"
fi

echo "Rendered db-migrate-$RUN_ID ($TAG) into $overlay"
