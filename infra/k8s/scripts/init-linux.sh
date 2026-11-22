#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
FROM="${FROM:-1}"
WITH_FLUX="${WITH_FLUX:-false}"
# auto = on whenever Flux is on (the stack is Flux-managed, so it needs Flux either way).
WITH_OBSERVABILITY="${WITH_OBSERVABILITY:-auto}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '\n\033[1;36m### %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [--env staging|prod] [--from N] [--with-flux] [--without-observability]

All-in-one bring-up of the whole stack on a Debian/Ubuntu Linux host, in order:

  1. install-tools.sh    CLIs (kubectl, helm, k9s, sops, age, flux)
  2. bootstrap-k3s.sh    k3s cluster + target namespace
  3. deploy-stateful.sh  Postgres + Redis Sentinel (Helm)
  4. deploy-app.sh       backend + frontend + app secret (SOPS)
  5. deploy-ingress.sh   ingress-nginx (+ prod's cloudflared; staging's tailnet Ingress)
  6. flux-bootstrap.sh   GitOps CD (only with --with-flux)
  7. deploy-observability.sh  Grafana admin + Tailscale OAuth secrets (Flux installs kube-prometheus-stack
                              and the Tailscale operator; runs whenever step 6 does). Staging is
                              reached only over the tailnet, so it needs steps 6 and 7.

Every step is idempotent, so re-running from the top is safe. If a step fails,
fix the cause and resume without redoing earlier steps:

  --env E                 target environment: staging (default) or prod. Prod is normally
                          promoted via the workflow action, not hand-bootstrapped.
  --from N                start at step N (1-7). Default 1.
  --with-flux             also run step 6 (Flux GitOps). Off by default because it needs an
                          SSH deploy key present — see docs/runbook/index.md 'Phase 6' before enabling.
  --without-observability skip step 7 even with Flux (Grafana admin + Tailscale OAuth secrets;
                          Flux reconciles kube-prometheus-stack and the Tailscale operator
                          either way). Without the OAuth secret staging gets no tailnet
                          address. --with-observability is still accepted and is the
                          default with --with-flux. See docs/runbook/index.md 'Phase 7'.

  SERVE_PROD_TUNNEL=true  prod only: step 5 applies the Cloudflare Tunnel's credentials, so this
                          cluster serves fmicodes.com. Only one cluster may (docs/runbook/cloudflare.md
                          'Move prod to another cluster'); without it prod stays off the internet.

Steps 1-2 need interactive sudo (k3s install, /usr/local/bin writes), so run
this in a terminal, not a headless context.

Runs on native Debian/Ubuntu Linux and on WSL2 (Ubuntu). On WSL2, run
bootstrap.sh from the repo root instead — it handles the age key pre-flight,
runs this script, and removes the port-forward services older setups installed.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --env) ENV="${2:-}"; [ -n "$ENV" ] || die "--env needs a value (staging|prod)"; shift 2 ;;
    --from) FROM="${2:-}"; [ -n "$FROM" ] || die "--from needs a step number (1-7)"; shift 2 ;;
    --with-flux) WITH_FLUX=true; shift ;;
    --with-observability) WITH_OBSERVABILITY=true; shift ;;
    --without-observability) WITH_OBSERVABILITY=false; shift ;;
    *) die "unknown argument '$1' (see --help)" ;;
  esac
done

case "$ENV" in
  prod)
    NAMESPACE="${NAMESPACE:-fmi-codes}"
    HOST="${HOST:-fmicodes.com}"
    HOST_URL="https://$HOST"
    ;;
  staging)
    NAMESPACE="${NAMESPACE:-fmi-codes-staging}"
    INGRESS_NAMESPACE="ingress-nginx-staging"
    ;;
  *)       die "--env must be 'staging' or 'prod', got '$ENV'" ;;
esac

case "$FROM" in
  1|2|3|4|5|6|7) : ;;
  *) die "--from must be 1-7, got '$FROM'" ;;
esac

# Checked here too, so a typo stops the run before k3s is installed, not at step 5.
case "${SERVE_PROD_TUNNEL:-false}" in
  true|false) : ;;
  *) die "SERVE_PROD_TUNNEL must be 'true' or 'false', got '$SERVE_PROD_TUNNEL'" ;;
esac
if [ "$ENV" = "staging" ] && [ "${SERVE_PROD_TUNNEL:-false}" = "true" ]; then
  echo "Note: SERVE_PROD_TUNNEL only applies to prod; ignored for staging." >&2
fi

if [ "$FROM" = "6" ]; then
  WITH_FLUX=true
fi

if [ "$FROM" = "7" ]; then
  WITH_FLUX=true
  WITH_OBSERVABILITY=true
fi

if [ "$WITH_OBSERVABILITY" = "auto" ]; then
  WITH_OBSERVABILITY="$WITH_FLUX"
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
run_step 5 "networking"             deploy-ingress.sh

if [ "$WITH_FLUX" = "true" ]; then
  run_step 6 "GitOps CD (Flux)"     flux-bootstrap.sh
else
  log "Step 6 (GitOps CD) — skipped (pass --with-flux to enable; see docs/runbook/index.md 'Phase 6')"
fi

if [ "$WITH_OBSERVABILITY" = "true" ]; then
  run_step 7 "observability (Prometheus + Grafana)"  deploy-observability.sh
else
  log "Step 7 (observability) — skipped (it runs with --with-flux unless --without-observability; see docs/runbook/index.md 'Phase 7')"
fi

if [ "$ENV" = "staging" ]; then
  TAILNET_HOST="$(kubectl -n "$INGRESS_NAMESPACE" get ingress staging \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
  if [ -n "$TAILNET_HOST" ]; then
    ACCESS_NOTE="Open https://$TAILNET_HOST from a device on the tailnet (no hosts entry)."
  else
    ACCESS_NOTE="Staging has no tailnet address yet. It gets one once Flux runs the Tailscale
operator and step 7 applies its OAuth client (docs/runbook/tailscale.md 'Tailscale setup'); then:
  kubectl -n $INGRESS_NAMESPACE get ingress staging    # ADDRESS = staging's URL"
  fi
  cat <<EOF

$(printf '\033[1;32m')Bring-up complete. The stack is up in namespace '$NAMESPACE'.$(printf '\033[0m')

Staging is reachable only over the tailnet. $ACCESS_NOTE

Verify the stack:
  kubectl -n $NAMESPACE get pods
  curl https://${TAILNET_HOST:-staging.<tailnet>.ts.net}/api/health
EOF
  exit 0
fi

if ! TUNNEL_HELD="$(kubectl -n "$NAMESPACE" get secret cloudflared-tunnel --ignore-not-found -o name)"; then
  die "could not check whether this cluster holds the tunnel's Secret ($NAMESPACE/cloudflared-tunnel)."
fi
if [ -z "$TUNNEL_HELD" ]; then
  cat <<EOF

$(printf '\033[1;32m')Bring-up complete. The stack is up in namespace '$NAMESPACE'.$(printf '\033[0m')

Prod is not on the internet from this cluster: it doesn't hold the Cloudflare Tunnel's
credentials (SERVE_PROD_TUNNEL=true applies them; only one cluster may, see docs/runbook/cloudflare.md
'Move prod to another cluster').

Verify the stack:
  kubectl -n $NAMESPACE get pods
  kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8081:80
  curl -H 'Host: $HOST' http://127.0.0.1:8081/api/health
EOF
  exit 0
fi

cat <<EOF

$(printf '\033[1;32m')Bring-up complete. The stack is up in namespace '$NAMESPACE'.$(printf '\033[0m')

Prod is reachable only through the Cloudflare Tunnel, at $HOST_URL from anywhere (no hosts
entry, no DNS record to set here). The first time, point $HOST at the tunnel
(docs/runbook/cloudflare.md 'Cloudflare Tunnel'). Only one cluster may run the prod tunnel at a time.

Verify the stack:
  kubectl -n $NAMESPACE get pods
  kubectl -n $NAMESPACE get deployment cloudflared    # READY 2/2 = connected
  curl ${HOST_URL}/api/health
EOF
