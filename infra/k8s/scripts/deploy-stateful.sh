#!/usr/bin/env bash

set -euo pipefail

NAMESPACE="${NAMESPACE:-fmi-codes}"
BITNAMI_REPO="${BITNAMI_REPO:-https://charts.bitnami.com/bitnami}"
POSTGRES_CHART_VERSION="${POSTGRES_CHART_VERSION:-15.5.38}"
REDIS_CHART_VERSION="${REDIS_CHART_VERSION:-20.13.4}"

DB_SECRET="${DB_SECRET:-fmi-codes-db}"
REDIS_SECRET="${REDIS_SECRET:-fmi-codes-redis}"
INITDB_CONFIGMAP="${INITDB_CONFIGMAP:-postgres-initdb}"

READY_TIMEOUT="${READY_TIMEOUT:-300}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$K8S_DIR/../.." && pwd)"
SCHEMA_SQL="${SCHEMA_SQL:-$REPO_ROOT/backend/database/schema.sql}"
POSTGRES_VALUES="$K8S_DIR/helm-values/postgresql-values.yaml"
REDIS_VALUES="$K8S_DIR/helm-values/redis-values.yaml"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools-wsl2.sh first."
command -v helm    >/dev/null 2>&1 || die "helm not found — run install-tools-wsl2.sh first."
[ -f "$SCHEMA_SQL" ]     || die "schema not found at $SCHEMA_SQL"
[ -f "$POSTGRES_VALUES" ] || die "missing $POSTGRES_VALUES"
[ -f "$REDIS_VALUES" ]    || die "missing $REDIS_VALUES"

kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-wsl2-k3s.sh first."

HELM_DOCKER_CONFIG="$(mktemp -d)"
printf '{}' > "$HELM_DOCKER_CONFIG/config.json"
trap 'rm -rf "$HELM_DOCKER_CONFIG"' EXIT
export DOCKER_CONFIG="$HELM_DOCKER_CONFIG"

gen_password() {
  head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32
}

log "Ensuring namespace '$NAMESPACE' exists"
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 \
  || kubectl create namespace "$NAMESPACE"

log "Ensuring Postgres secret '$DB_SECRET'"
if kubectl -n "$NAMESPACE" get secret "$DB_SECRET" >/dev/null 2>&1; then
  echo "Secret $DB_SECRET already exists — leaving its passwords untouched."
else
  db_password="$(gen_password)"
  admin_password="$(gen_password)"
  kubectl -n "$NAMESPACE" create secret generic "$DB_SECRET" \
    --from-literal=password="$db_password" \
    --from-literal=postgres-password="$admin_password"
  echo "Created $DB_SECRET with freshly generated passwords."
fi

log "Ensuring Redis secret '$REDIS_SECRET'"
if kubectl -n "$NAMESPACE" get secret "$REDIS_SECRET" >/dev/null 2>&1; then
  echo "Secret $REDIS_SECRET already exists — leaving its password untouched."
else
  redis_password="$(gen_password)"
  kubectl -n "$NAMESPACE" create secret generic "$REDIS_SECRET" \
    --from-literal=redis-password="$redis_password"
  echo "Created $REDIS_SECRET with a freshly generated password."
fi

log "Syncing schema ConfigMap '$INITDB_CONFIGMAP' from $SCHEMA_SQL"
kubectl -n "$NAMESPACE" create configmap "$INITDB_CONFIGMAP" \
  --from-file=01_schema.sql="$SCHEMA_SQL" \
  --dry-run=client -o yaml \
  | kubectl apply -f -

log "Adding/refreshing the Bitnami Helm repo"
helm repo add bitnami "$BITNAMI_REPO" 2>/dev/null || helm repo list 2>/dev/null | grep -q "^bitnami" \
  || die "failed to add the Bitnami Helm repo ($BITNAMI_REPO) — check network/DNS."
helm repo update bitnami >/dev/null

log "Deploying Postgres (chart $POSTGRES_CHART_VERSION)"
helm upgrade --install postgres bitnami/postgresql \
  --namespace "$NAMESPACE" \
  --version "$POSTGRES_CHART_VERSION" \
  --values "$POSTGRES_VALUES" \
  --wait --timeout "${READY_TIMEOUT}s"

log "Deploying Redis Sentinel (chart $REDIS_CHART_VERSION)"
helm upgrade --install redis bitnami/redis \
  --namespace "$NAMESPACE" \
  --version "$REDIS_CHART_VERSION" \
  --values "$REDIS_VALUES" \
  --wait --timeout "${READY_TIMEOUT}s"

log "Deployed. Current state in '$NAMESPACE':"
kubectl -n "$NAMESPACE" get pods -o wide
kubectl -n "$NAMESPACE" get svc

cat <<EOF

Stateful tier is up. Connection coordinates for the app tier (Phase 3):
  Postgres : postgres.$NAMESPACE.svc.cluster.local:5432
             DB=fmi_hackathon_2026 USER=fmi_app
             password  -> secret/$DB_SECRET key 'password'
  Redis    : sentinel  redis.$NAMESPACE.svc.cluster.local:26379  (master set 'mymaster')
             password  -> secret/$REDIS_SECRET key 'redis-password'
             app env: REDIS_SENTINELS=redis.$NAMESPACE.svc.cluster.local:26379
                      REDIS_MASTER_NAME=mymaster

Verify (see infra/k8s/README.md 'Phase 2' for the full checklist):
  kubectl -n $NAMESPACE get pods
  kubectl -n $NAMESPACE exec -it redis-node-0 -c sentinel -- \\
    redis-cli -p 26379 sentinel master mymaster
EOF
