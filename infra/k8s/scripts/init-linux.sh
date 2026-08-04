#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
FROM="${FROM:-1}"
WITH_FLUX="${WITH_FLUX:-false}"
WITH_OBSERVABILITY="${WITH_OBSERVABILITY:-false}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '\n\033[1;36m### %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [--env staging|prod] [--from N] [--with-flux] [--with-observability]

All-in-one bring-up of the whole stack on a Debian/Ubuntu Linux host, in order:

  1. install-tools.sh    CLIs (kubectl, helm, k9s, sops, age, flux)
  2. bootstrap-k3s.sh    k3s cluster + target namespace
  3. deploy-stateful.sh  Postgres + Redis Sentinel (Helm)
  4. deploy-app.sh       backend + frontend + app secret (SOPS)
  5. deploy-ingress.sh   ingress-nginx + cert-manager + TLS
  6. flux-bootstrap.sh   GitOps CD (only with --with-flux)
  7. deploy-observability.sh  Grafana admin secret (Flux installs kube-prometheus-stack; only with --with-observability)

Every step is idempotent, so re-running from the top is safe. If a step fails,
fix the cause and resume without redoing earlier steps:

  --env E                 target environment: staging (default) or prod. Prod is normally
                          promoted via the workflow action, not hand-bootstrapped.
  --from N                start at step N (1-7). Default 1.
  --with-flux             also run step 6 (Flux GitOps). Off by default because it needs an
                          SSH deploy key present — see README 'Phase 6' before enabling.
  --with-observability    also run step 7 (Grafana admin secret; Flux then reconciles the
                          kube-prometheus-stack chart automatically). Requires --with-flux
                          and the env's age key at ~/.config/sops/age/keys.txt — see
                          README 'Phase 7' before enabling.

Steps 1-2 need interactive sudo (k3s install, /usr/local/bin writes), so run
this in a terminal, not a headless context.

Runs on native Debian/Ubuntu Linux and on WSL2 (Ubuntu). On WSL2, run
bootstrap.sh from the repo root instead — it handles the age key pre-flight,
runs this script, and auto-installs the boot-persistent port-forward services.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --env) ENV="${2:-}"; [ -n "$ENV" ] || die "--env needs a value (staging|prod)"; shift 2 ;;
    --from) FROM="${2:-}"; [ -n "$FROM" ] || die "--from needs a step number (1-7)"; shift 2 ;;
    --with-flux) WITH_FLUX=true; shift ;;
    --with-observability) WITH_OBSERVABILITY=true; shift ;;
    *) die "unknown argument '$1' (see --help)" ;;
  esac
done

case "$ENV" in
  prod)
    NAMESPACE="${NAMESPACE:-fmi-codes}"
    HOST="${HOST:-fmicodes.com}"
    INGRESS_NAMESPACE="ingress-nginx"
    INGRESS_RELEASE="ingress-nginx"
    HOST_URL="https://$HOST"
    ;;
  staging)
    NAMESPACE="${NAMESPACE:-fmi-codes-staging}"
    HOST="${HOST:-staging.fmicodes.com}"
    INGRESS_NAMESPACE="ingress-nginx-staging"
    INGRESS_RELEASE="ingress-nginx-staging"
    HOST_URL="https://$HOST:9443"
    ;;
  *)       die "--env must be 'staging' or 'prod', got '$ENV'" ;;
esac

case "$FROM" in
  1|2|3|4|5|6|7) : ;;
  *) die "--from must be 1-7, got '$FROM'" ;;
esac

if [ "$FROM" = "6" ]; then
  WITH_FLUX=true
fi

if [ "$FROM" = "7" ]; then
  WITH_FLUX=true
  WITH_OBSERVABILITY=true
fi

run_step() {
  local n="$1" name="$2" script="$3"
  if [ "$n" -lt "$FROM" ]; then
    log "Step $n ($name) — skipped (--from $FROM)"
    return 0
  fi
  [ -f "$SCRIPT_DIR/$script" ] || die "step $n: missing $SCRIPT_DIR/$script"
  log "Step $n/7 — $name"
  ENV="$ENV" bash "$SCRIPT_DIR/$script" \
    || die "step $n ($name) failed. Fix the cause above, then resume with: $(basename "$0") --from $n"
}

run_step 1 "install tooling"        install-tools.sh
run_step 2 "bootstrap k3s cluster"  bootstrap-k3s.sh
run_step 3 "stateful tier"          deploy-stateful.sh
run_step 4 "app tier"               deploy-app.sh
run_step 5 "networking + TLS"       deploy-ingress.sh

if [ "$WITH_FLUX" = "true" ]; then
  run_step 6 "GitOps CD (Flux)"     flux-bootstrap.sh
else
  log "Step 6 (GitOps CD) — skipped (pass --with-flux to enable; see README 'Phase 6')"
fi

if [ "$WITH_OBSERVABILITY" = "true" ]; then
  run_step 7 "observability (Prometheus + Grafana)"  deploy-observability.sh
else
  log "Step 7 (observability) — skipped (pass --with-observability to enable; see README 'Phase 7')"
fi

INGRESS_IP="$(kubectl -n "$INGRESS_NAMESPACE" get svc "${INGRESS_RELEASE}-controller" \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
[ -n "$INGRESS_IP" ] || INGRESS_IP="<ingress-external-ip>"

if [ "$ENV" = "prod" ]; then
  TLS_NOTE="For production, point the $HOST A record at $INGRESS_IP in DNS.
Let's Encrypt issues the cert automatically once DNS resolves."
else
  TLS_NOTE="For staging, the /etc/hosts entry above is enough — TLS is a self-signed
certificate from a namespaced Issuer, so expect a browser warning."
fi

cat <<EOF

$(printf '\033[1;32m')Bring-up complete. The stack is up in namespace '$NAMESPACE'.$(printf '\033[0m')

Point the host name at the ingress so clients can reach it. On this host:
  echo "$INGRESS_IP $HOST" | sudo tee -a /etc/hosts

$TLS_NOTE

Verify the stack:
  kubectl -n $NAMESPACE get pods
  curl ${HOST_URL}/api/health
EOF
