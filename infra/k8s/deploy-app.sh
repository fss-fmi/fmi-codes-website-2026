#!/usr/bin/env bash

set -euo pipefail

NAMESPACE="${NAMESPACE:-fmi-codes}"
APP_SECRET="${APP_SECRET:-fmi-codes-app}"
DB_SECRET="${DB_SECRET:-fmi-codes-db}"
REDIS_SECRET="${REDIS_SECRET:-fmi-codes-redis}"
READY_TIMEOUT="${READY_TIMEOUT:-300}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_MANIFEST="$SCRIPT_DIR/backend.yaml"
FRONTEND_MANIFEST="$SCRIPT_DIR/frontend.yaml"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools-wsl2.sh first."
[ -f "$BACKEND_MANIFEST" ]  || die "missing $BACKEND_MANIFEST"
[ -f "$FRONTEND_MANIFEST" ] || die "missing $FRONTEND_MANIFEST"

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-wsl2-k3s.sh first."

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 \
  || die "namespace '$NAMESPACE' not found — run deploy-stateful.sh first (Phase 2)."

kubectl -n "$NAMESPACE" get secret "$DB_SECRET" >/dev/null 2>&1 \
  || die "secret '$DB_SECRET' not found — run deploy-stateful.sh first (Phase 2)."
kubectl -n "$NAMESPACE" get secret "$REDIS_SECRET" >/dev/null 2>&1 \
  || die "secret '$REDIS_SECRET' not found — run deploy-stateful.sh first (Phase 2)."

gen_password() {
  head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32
}

log "Ensuring app secret '$APP_SECRET'"
if kubectl -n "$NAMESPACE" get secret "$APP_SECRET" >/dev/null 2>&1; then
  echo "Secret $APP_SECRET already exists — leaving its values untouched."
else
  secret_key="$(gen_password)"
  jwt_secret_key="$(gen_password)"
  kubectl -n "$NAMESPACE" create secret generic "$APP_SECRET" \
    --from-literal=SECRET_KEY="$secret_key" \
    --from-literal=JWT_SECRET_KEY="$jwt_secret_key" \
    --from-literal=ADMIN_PASSWORD_HASH="" \
    --from-literal=MAIL_PASSWORD="" \
    --from-literal=DISCORD_BUG_WEBHOOK_URL=""
  echo "Created $APP_SECRET with generated SECRET_KEY/JWT_SECRET_KEY and empty placeholders."
  echo "Set a real ADMIN_PASSWORD_HASH before the backend will start in production mode:"
  echo "  kubectl -n $NAMESPACE patch secret $APP_SECRET -p '{\"data\":{\"ADMIN_PASSWORD_HASH\":\"<base64-bcrypt-hash>\"}}'"
fi

log "Applying backend and frontend manifests"
kubectl apply -n "$NAMESPACE" -f "$BACKEND_MANIFEST" -f "$FRONTEND_MANIFEST"

log "Waiting for rollouts to become ready"
kubectl -n "$NAMESPACE" rollout status deployment/backend  --timeout "${READY_TIMEOUT}s"
kubectl -n "$NAMESPACE" rollout status deployment/frontend --timeout "${READY_TIMEOUT}s"

log "Deployed. Current state in '$NAMESPACE':"
kubectl -n "$NAMESPACE" get pods -o wide
kubectl -n "$NAMESPACE" get svc

cat <<EOF

App tier is up (Phase 3). Verify against the issue's acceptance criteria:

  Pods Running/Ready:
    kubectl -n $NAMESPACE get pods -l app.kubernetes.io/part-of=fmi-codes-website-2026

  Self-heal (kill a backend pod, watch it reschedule with no downtime):
    kubectl -n $NAMESPACE delete pod \$(kubectl -n $NAMESPACE get pod \\
      -l app.kubernetes.io/name=fmi-codes-backend -o jsonpath='{.items[0].metadata.name}')
    kubectl -n $NAMESPACE get pods -l app.kubernetes.io/name=fmi-codes-backend -w

  Postgres + Redis reachability (readiness probes the real dependencies):
    kubectl -n $NAMESPACE exec deploy/backend -- \\
      python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/api/health/ready').read())"

See infra/k8s/README.md 'Phase 3' for the full checklist.
EOF
