#!/usr/bin/env bash

set -euo pipefail

NAMESPACE="${NAMESPACE:-fmi-codes}"
FROM="${FROM:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '\n\033[1;36m### %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [--from N]

All-in-one bring-up of the whole stack on a Debian/Ubuntu Linux host, in order:

  1. install-tools.sh    CLIs (kubectl, helm, k9s, sops, age, flux)
  2. bootstrap-k3s.sh    k3s cluster + '$NAMESPACE' namespace
  3. deploy-stateful.sh  Postgres + Redis Sentinel (Helm)
  4. deploy-app.sh       backend + frontend + app secret (SOPS)
  5. deploy-ingress.sh   ingress-nginx + cert-manager + TLS

Every step is idempotent, so re-running from the top is safe. If a step fails,
fix the cause and resume without redoing earlier steps:

  --from N   start at step N (1-5). Default 1.

Steps 1-2 need interactive sudo (k3s install, /usr/local/bin writes), so run
this in a terminal, not a headless context.

Runs on native Debian/Ubuntu Linux and on WSL2 (Ubuntu). On WSL2, run
init-windows.sh instead — it runs this script, then prints the Windows-side
host-resolution steps the browser needs.
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  --from) FROM="${2:-}"; [ -n "$FROM" ] || die "--from needs a step number (1-5)" ;;
  "") : ;;
  *) die "unknown argument '$1' (see --help)" ;;
esac

case "$FROM" in
  1|2|3|4|5) : ;;
  *) die "--from must be 1-5, got '$FROM'" ;;
esac

run_step() {
  local n="$1" name="$2" script="$3"
  if [ "$n" -lt "$FROM" ]; then
    log "Step $n ($name) — skipped (--from $FROM)"
    return 0
  fi
  [ -f "$SCRIPT_DIR/$script" ] || die "step $n: missing $SCRIPT_DIR/$script"
  log "Step $n/5 — $name"
  bash "$SCRIPT_DIR/$script" \
    || die "step $n ($name) failed. Fix the cause above, then resume with: $(basename "$0") --from $n"
}

run_step 1 "install tooling"        install-tools.sh
run_step 2 "bootstrap k3s cluster"  bootstrap-k3s.sh
run_step 3 "stateful tier"          deploy-stateful.sh
run_step 4 "app tier"               deploy-app.sh
run_step 5 "networking + TLS"       deploy-ingress.sh

INGRESS_IP="$(kubectl -n ingress-nginx get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
[ -n "$INGRESS_IP" ] || INGRESS_IP="<ingress-external-ip>"

cat <<EOF

$(printf '\033[1;32m')All five steps complete. The stack is up in namespace '$NAMESPACE'.$(printf '\033[0m')

Point the host name at the ingress so clients can reach it. On this host:
  echo "$INGRESS_IP fmi-codes.local" | sudo tee -a /etc/hosts

For a real server, add an A record fmi-codes.local -> $INGRESS_IP in your DNS
instead. Then browse to https://fmi-codes.local (self-signed cert — accept the
warning, or swap in a real cert per README 'Phase 4').

Verify the stack:
  kubectl -n $NAMESPACE get pods
  curl -k https://fmi-codes.local/api/health
EOF
