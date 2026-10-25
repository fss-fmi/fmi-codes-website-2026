#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
case "$ENV" in
  prod)    NAMESPACE="${NAMESPACE:-fmi-codes}" ;;
  staging) NAMESPACE="${NAMESPACE:-fmi-codes-staging}" ;;
  *)       echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac
CONFIGMAP="${CONFIGMAP:-fmi-codes-backend-config}"
RESTART="${RESTART:-true}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_OVERLAY="${APP_OVERLAY:-$K8S_DIR/overlays/$ENV}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

SECRET_KEYS="SECRET_KEY JWT_SECRET_KEY ADMIN_PASSWORD_HASH MAIL_PASSWORD DISCORD_BUG_WEBHOOK_URL DB_PASSWORD REDIS_PASSWORD"

usage() {
  cat <<EOF
Usage: $(basename "$0") [KEY VALUE]

Apply a non-secret backend config change and roll the backend so pods pick it up.

  With KEY VALUE : patch that one key in the '$CONFIGMAP' ConfigMap, then
                   restart the backend. Only non-secret keys are allowed.
  No arguments   : re-apply the overlay for ENV ($ENV) from disk (the git
                   source of truth) and restart the backend.

Secrets do NOT belong here. To rotate SECRET_KEY / JWT_SECRET_KEY /
ADMIN_PASSWORD_HASH / MAIL_PASSWORD / DISCORD_BUG_WEBHOOK_URL use:
    bash $SCRIPT_DIR/rotate-secret.sh <KEY>      (prompts; --generate for a random one)
DB / Redis passwords are PVC-coupled and managed by deploy-stateful.sh.

Env overrides: ENV (prod|staging — selects the overlay and namespace),
NAMESPACE ($NAMESPACE), CONFIGMAP ($CONFIGMAP),
RESTART (true|false — skip the rollout restart when false).

Examples:
  $(basename "$0") FRONTEND_ORIGIN https://fmicodes.com
  $(basename "$0") REGISTRATION_OPEN true
  $(basename "$0")                       # re-apply manifests from disk
EOF
}

case "${1:-}" in -h|--help) usage; exit 0 ;; esac

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 \
  || die "namespace '$NAMESPACE' not found — run deploy-stateful.sh first."

restart_backend() {
  if [ "$RESTART" = "true" ]; then
    log "Restarting backend so pods pick up the change"
    kubectl -n "$NAMESPACE" rollout restart deployment/backend
    kubectl -n "$NAMESPACE" rollout status deployment/backend --timeout=120s
  else
    echo "RESTART=false — skipping rollout restart. Restart manually to apply:"
    echo "  kubectl -n $NAMESPACE rollout restart deployment/backend"
  fi
}

if [ $# -eq 0 ]; then
  [ -f "$APP_OVERLAY/kustomization.yaml" ] || die "missing $APP_OVERLAY/kustomization.yaml"
  log "Re-applying manifests from disk (overlay: $ENV)"
  kubectl apply -k "$APP_OVERLAY"
  restart_backend
  log "Done. The manifests on disk are now applied to the cluster."
  exit 0
fi

[ $# -eq 2 ] || { usage; exit 1; }
KEY="$1"
VALUE="$2"

case "$KEY" in
  *[!A-Za-z0-9._-]*|"") die "invalid ConfigMap key '$KEY' — allowed characters are letters, digits, '.', '_', '-'." ;;
esac

for s in $SECRET_KEYS; do
  if [ "$KEY" = "$s" ]; then
    die "'$KEY' is a secret — it does not belong in the ConfigMap. Use rotate-secret.sh (app secrets) or deploy-stateful.sh (DB/Redis)."
  fi
done

command -v python3 >/dev/null 2>&1 || die "python3 not found — needed to safely JSON-encode the value."
VALUE_JSON="$(VALUE="$VALUE" python3 -c 'import json,os;print(json.dumps(os.environ["VALUE"]))')"

log "Patching $CONFIGMAP: $KEY"
kubectl -n "$NAMESPACE" patch configmap "$CONFIGMAP" \
  --type merge -p "{\"data\":{\"$KEY\":$VALUE_JSON}}"

restart_backend

log "Done. Live ConfigMap updated. Also edit the git source of truth so a re-apply"
echo "from disk won't revert this: env-specific keys (FRONTEND_ORIGIN, DB_HOST,"
echo "REDIS_SENTINELS) live in overlays/$ENV/backend-config-patch.yaml; all other keys"
echo "live in base/app/backend.yaml. Commit the edit."
