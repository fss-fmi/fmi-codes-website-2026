#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
case "$ENV" in
  prod)    NAMESPACE="${NAMESPACE:-fmi-codes}"; FLUX_KUSTOMIZATION="${FLUX_KUSTOMIZATION:-fmi-codes}"; SECRETS_REL="secrets/secrets.enc.yaml" ;;
  staging) NAMESPACE="${NAMESPACE:-fmi-codes-staging}"; FLUX_KUSTOMIZATION="${FLUX_KUSTOMIZATION:-fmi-codes-staging}"; SECRETS_REL="overlays/staging/secrets/secrets.enc.yaml" ;;
  *)       echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac
APP_SECRET="${APP_SECRET:-fmi-codes-app}"
DB_SECRET="${DB_SECRET:-fmi-codes-db}"
REDIS_SECRET="${REDIS_SECRET:-fmi-codes-redis}"
READY_TIMEOUT="${READY_TIMEOUT:-300}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_OVERLAY="$K8S_DIR/overlays/$ENV"
SECRETS_ENC="${SECRETS_ENC:-$K8S_DIR/$SECRETS_REL}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
[ -f "$APP_OVERLAY/kustomization.yaml" ] || die "missing $APP_OVERLAY/kustomization.yaml"

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 \
  || die "namespace '$NAMESPACE' not found — run deploy-stateful.sh first (Phase 2)."

kubectl -n "$NAMESPACE" get secret "$DB_SECRET" >/dev/null 2>&1 \
  || die "secret '$DB_SECRET' not found — run deploy-stateful.sh first (Phase 2)."
kubectl -n "$NAMESPACE" get secret "$REDIS_SECRET" >/dev/null 2>&1 \
  || die "secret '$REDIS_SECRET' not found — run deploy-stateful.sh first (Phase 2)."

gen_password() {
  head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32
}

sops_can_decrypt() {
  command -v sops >/dev/null 2>&1 || return 1
  [ -f "$SECRETS_ENC" ] || return 1
  sops --decrypt "$SECRETS_ENC" >/dev/null 2>&1
}

if sops_can_decrypt; then
  secret_ns="$(sops --decrypt "$SECRETS_ENC" | grep -E '^[[:space:]]+namespace:' | head -1 | awk '{print $2}' || true)"
  [ "$secret_ns" = "$NAMESPACE" ] \
    || die "$SECRETS_ENC targets namespace '${secret_ns:-<none>}' but ENV=$ENV expects '$NAMESPACE' — refusing to apply a secret across environments."
  log "Applying app secret '$APP_SECRET' from $SECRETS_ENC (SOPS-managed)"
  sops --decrypt "$SECRETS_ENC" | kubectl apply -f -
elif [ -f "$SECRETS_ENC" ]; then
  if command -v sops >/dev/null 2>&1; then
    die "found $SECRETS_ENC but could not decrypt it — is your age key at ~/.config/sops/age/keys.txt? See docs/runbook.md 'Phase 5'."
  else
    die "found $SECRETS_ENC but sops is not installed — run install-tools.sh, then ensure your age key is at ~/.config/sops/age/keys.txt. See docs/runbook.md 'Phase 5'."
  fi
else
  log "Ensuring app secret '$APP_SECRET' (generated in-cluster; no SOPS file present)"
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
      --from-literal=DISCORD_BUG_WEBHOOK_URL="" \
      --from-literal=SLACK_MIGRATIONS_WEBHOOK_URL=""
    echo "Created $APP_SECRET with generated SECRET_KEY/JWT_SECRET_KEY and empty placeholders."
    echo "Set a real ADMIN_PASSWORD_HASH before the backend will start in production mode:"
    echo "  kubectl -n $NAMESPACE patch secret $APP_SECRET -p '{\"data\":{\"ADMIN_PASSWORD_HASH\":\"<base64-bcrypt-hash>\"}}'"
  fi
fi

flux_owns_app() {
  kubectl get kustomizations.kustomize.toolkit.fluxcd.io "$FLUX_KUSTOMIZATION" -n flux-system >/dev/null 2>&1
}

admin_hash="$(kubectl -n "$NAMESPACE" get secret "$APP_SECRET" \
  -o jsonpath='{.data.ADMIN_PASSWORD_HASH}' 2>/dev/null || true)"
if [ -z "$admin_hash" ]; then
  log "ADMIN_PASSWORD_HASH is empty — the backend will CrashLoop until it is set"
  echo "The backend runs production config, which refuses to start without a real"
  echo "admin password hash. Set one before expecting the backend to go Ready:"
  echo "  HASH=\$(python -c \"import bcrypt;print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt(12)).decode())\")"
  echo "  bash $SCRIPT_DIR/rotate-secret.sh ADMIN_PASSWORD_HASH \"\$HASH\""
fi

if flux_owns_app; then
  log "Flux is active — it owns the backend/frontend Deployments"
  echo "Applied the app secret only. Flux reconciles the Deployments from git; it"
  echo "will pick up the secret change on its next reconcile, or force it now with:"
  echo "  flux reconcile kustomization $FLUX_KUSTOMIZATION -n flux-system"
  echo "  kubectl -n $NAMESPACE rollout restart deployment/backend"
  exit 0
fi

log "Applying backend and frontend manifests"
kubectl apply -k "$APP_OVERLAY"

if [ -z "$admin_hash" ]; then
  log "Waiting for the frontend rollout only"
  kubectl -n "$NAMESPACE" rollout status deployment/frontend --timeout "${READY_TIMEOUT}s"
  kubectl -n "$NAMESPACE" get pods -o wide
  kubectl -n "$NAMESPACE" get svc
  exit 0
fi

log "Restarting backend so pods pick up any ConfigMap/Secret changes"
kubectl -n "$NAMESPACE" rollout restart deployment/backend

log "Waiting for rollouts to become ready"
kubectl -n "$NAMESPACE" rollout status deployment/backend  --timeout "${READY_TIMEOUT}s"
kubectl -n "$NAMESPACE" rollout status deployment/frontend --timeout "${READY_TIMEOUT}s"

log "Deployed. Current state in '$NAMESPACE':"
kubectl -n "$NAMESPACE" get pods -o wide
kubectl -n "$NAMESPACE" get svc

cat <<EOF

App tier is up. Verify against the issue's acceptance criteria:

  Pods Running/Ready:
    kubectl -n $NAMESPACE get pods -l app.kubernetes.io/part-of=fmi-codes-website-2026

  Self-heal (kill a backend pod, watch it reschedule with no downtime):
    kubectl -n $NAMESPACE delete pod \$(kubectl -n $NAMESPACE get pod \\
      -l app.kubernetes.io/name=fmi-codes-backend -o jsonpath='{.items[0].metadata.name}')
    kubectl -n $NAMESPACE get pods -l app.kubernetes.io/name=fmi-codes-backend -w

  Postgres + Redis reachability (readiness probes the real dependencies):
    kubectl -n $NAMESPACE exec deploy/backend -- \\
      python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/api/health/ready').read())"

To rotate a secret (SECRET_KEY, JWT_SECRET_KEY, ADMIN_PASSWORD_HASH, MAIL_PASSWORD,
DISCORD_BUG_WEBHOOK_URL, SLACK_MIGRATIONS_WEBHOOK_URL) in one command:
    bash infra/k8s/scripts/rotate-secret.sh <KEY> [VALUE]

See docs/runbook.md 'Phase 3' and 'Phase 5' for the full checklists.
EOF
