#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
TAILSCALE_NS="${TAILSCALE_NS:-tailscale}"
MONITORING_NS="${MONITORING_NS:-monitoring}"
TS_WAIT_SECONDS="${TS_WAIT_SECONDS:-600}"
ENV_LABEL="fmi-codes/secrets-env"
# Matched with grep -E >/dev/null, never -q: an early grep exit can SIGPIPE sops under pipefail.
EMPTY_RE="^[[:space:]]+client_(id|secret):[[:space:]]*(\"\"|'')?[[:space:]]*\$"

die()  { echo "Error: $1" >&2; exit 1; }
log()  { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33mWarning: %s\033[0m\n' "$1" >&2; }

usage() {
  cat <<EOF
Usage: $(basename "$0") set|release|check

Manages the cluster's Tailscale OAuth client, which lets the operator put Grafana on the
tailnet. Only one cluster may hold it at a time (docs/runbook.md 'Move Grafana to another
cluster').

  set      Ask for the OAuth client ID and secret (hidden, typed twice) and write them into
           the env's tailscale-oauth.enc.yaml. Touches no cluster, so it works before
           bootstrap. Piped input is read as two lines: ID, then secret.
  release  Run on the cluster that is giving Grafana up: removes the operator's credentials,
           its proxies and their tailnet state, empties the env's tailscale-oauth.enc.yaml,
           then lists the admin-console steps that finish the handover.
  check    Wait (up to TS_WAIT_SECONDS, default 600) for Grafana's tailnet address and fail
           if another cluster still holds the name 'grafana'. Exit 0 ok, 3 name clash,
           4 no address yet.

Env overrides: ENV (prod|staging, default staging), TAILSCALE_SECRET_ENC, TAILSCALE_NS,
MONITORING_NS, TS_WAIT_SECONDS.
EOF
}

CMD="${1:-}"
case "$CMD" in
  -h|--help) usage; exit 0 ;;
  set|release|check) ;;
  *) usage; exit 1 ;;
esac

case "$ENV" in
  prod)    SECRETS_REL="secrets" ;;
  staging) SECRETS_REL="overlays/staging/secrets" ;;
  *)       die "ENV must be 'prod' or 'staging', got '$ENV'." ;;
esac
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TS_FILE="${TAILSCALE_SECRET_ENC:-$K8S_DIR/$SECRETS_REL/tailscale-oauth.enc.yaml}"
RUNBOOK="docs/runbook.md 'Move Grafana to another cluster'"

need_sops_file() {
  command -v sops >/dev/null 2>&1 || die "sops not found — run install-tools.sh first."
  [ -f "$TS_FILE" ] || die "missing $TS_FILE"
  sops --decrypt "$TS_FILE" >/dev/null 2>&1 \
    || die "cannot decrypt $TS_FILE — is your $ENV age key at ~/.config/sops/age/keys.txt?"
}

# The value never reaches argv: python3 JSON-encodes it from the environment for sops' stdin.
store() {
  VALUE="$2" python3 -c 'import json,os;print(json.dumps(os.environ["VALUE"]))' \
    | sops set --value-stdin "$TS_FILE" "[\"stringData\"][\"$1\"]"
}

# read_value VAR LABEL: hidden and typed twice on a terminal, one line from stdin otherwise.
read_value() {
  local var="$1" label="$2" first="" second=""
  if [ -t 0 ]; then
    printf '%s (input hidden): ' "$label" >&2
    read -rs first || true; echo >&2
    printf 'Repeat it: ' >&2
    read -rs second || true; echo >&2
    [ "$first" = "$second" ] || die "the two entries differ; nothing written."
  else
    IFS= read -r first || true
    first="${first%$'\r'}"
  fi
  [ -n "$first" ] || die "empty $label; nothing written."
  printf -v "$var" '%s' "$first"
}

print_console_release_steps() {
  cat <<EOF

Finish the handover in the Tailscale admin console (a tailnet admin):
  1. Settings -> OAuth clients (or Trust credentials): revoke the client this cluster used.
  2. Machines: delete this cluster's 'grafana' and 'fmi-codes-operator' devices
     (they may carry a -N suffix). That frees the name 'grafana' for the next cluster.
Then commit the emptied $TS_FILE.
EOF
}

cmd_set() {
  need_sops_file
  [[ "$(sops set --help 2>&1 || true)" == *--value-stdin* ]] \
    || die "this sops has no 'set --value-stdin'; reinstall the version install-tools.sh pins."
  command -v python3 >/dev/null 2>&1 || die "python3 not found — sudo apt-get install -y python3"

  local id="" secret=""
  read_value id "Tailscale OAuth client ID"
  read_value secret "Tailscale OAuth client secret"
  [[ "$id" != tskey-* ]] \
    || die "the client ID looks like a secret (tskey-...); the ID is the short value shown next to it. Nothing written."
  [[ "$secret" == tskey-client-* ]] \
    || die "the client secret should start with 'tskey-client-'; check you copied the secret, not the ID. Nothing written."

  log "Writing the OAuth client into $TS_FILE"
  store client_id "$id"
  store client_secret "$secret"
  unset id secret
  if sops --decrypt "$TS_FILE" | grep -E "$EMPTY_RE" >/dev/null; then
    die "a value is still empty in $TS_FILE after writing; edit it with: sops $TS_FILE"
  fi
  echo "Stored. Commit $TS_FILE (it is encrypted), then deploy-observability.sh applies it."
}

cmd_release() {
  need_sops_file
  command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
  kubectl cluster-info >/dev/null 2>&1 || die "no reachable cluster; run this on the cluster that is giving Grafana up."

  local live_env
  live_env="$(kubectl -n "$TAILSCALE_NS" get secret operator-oauth --ignore-not-found \
    -o go-template="{{index .metadata.labels \"$ENV_LABEL\"}}" 2>/dev/null || true)"
  live_env="${live_env#<no value>}"
  if [ -n "$live_env" ] && [ "$live_env" != "$ENV" ]; then
    die "this cluster runs the $live_env OAuth client; re-run with ENV=$live_env so the right file is emptied."
  fi

  log "Removing the operator's credentials, proxies and tailnet state from this cluster"
  # Stopped first so it can't recreate the proxies it owns. A rollout restart would not do: the
  # old pod keeps running until a new one is Ready, and without operator-oauth none ever is.
  local has_operator=false
  if kubectl -n "$TAILSCALE_NS" get deployment operator >/dev/null 2>&1; then
    has_operator=true
    kubectl -n "$TAILSCALE_NS" scale deployment/operator --replicas=0
    kubectl -n "$TAILSCALE_NS" wait --for=delete pod -l app=operator --timeout=60s 2>/dev/null || true
  fi
  kubectl -n "$TAILSCALE_NS" delete secret operator-oauth --ignore-not-found
  kubectl -n "$TAILSCALE_NS" delete statefulset -l tailscale.com/managed=true --ignore-not-found
  kubectl -n "$TAILSCALE_NS" delete secret -l tailscale.com/managed=true --ignore-not-found
  kubectl -n "$TAILSCALE_NS" delete secret operator --ignore-not-found
  # Back to the replica count Flux expects; the pod waits for operator-oauth, so it stays idle.
  if [ "$has_operator" = "true" ]; then
    kubectl -n "$TAILSCALE_NS" scale deployment/operator --replicas=1
  fi

  log "Emptying $TS_FILE"
  printf '""' | sops set --value-stdin "$TS_FILE" '["stringData"]["client_id"]'
  printf '""' | sops set --value-stdin "$TS_FILE" '["stringData"]["client_secret"]'
  print_console_release_steps
}

cmd_check() {
  command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
  local deadline host="" next_note
  deadline=$(( $(date +%s) + TS_WAIT_SECONDS ))
  next_note=$(( $(date +%s) + 30 ))
  log "Waiting up to ${TS_WAIT_SECONDS}s for Grafana's tailnet address"
  while :; do
    host="$(kubectl -n "$MONITORING_NS" get ingress grafana \
      -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
    [ -z "$host" ] || break
    [ "$(date +%s)" -lt "$deadline" ] || break
    if [ "$(date +%s)" -ge "$next_note" ]; then
      echo "  still waiting (Flux installs the chart and operator first; kubectl -n $TAILSCALE_NS get pods)"
      next_note=$(( $(date +%s) + 30 ))
    fi
    sleep 5
  done

  if [ -z "$host" ]; then
    warn "Grafana has no tailnet address yet. Check: kubectl -n $TAILSCALE_NS get pods,statefulsets
  and kubectl -n $MONITORING_NS describe ingress grafana. See docs/runbook.md 'Access Grafana'."
    return 4
  fi
  if [ "${host%%.*}" != "grafana" ]; then
    warn "Grafana joined the tailnet as ${host%%.*}, not 'grafana': another cluster still holds the name.
  Hand over first ($RUNBOOK): on the old cluster run 'tailscale-oauth.sh release', and in the
  admin console revoke its OAuth client and delete its devices. Then make this cluster re-register:
    kubectl -n $TAILSCALE_NS delete statefulset,secret -l tailscale.com/managed=true
  and delete this cluster's stale '${host%%.*}' device in the admin console."
    return 3
  fi
  echo "Grafana is on the tailnet: https://$host"
}

case "$CMD" in
  set) cmd_set ;;
  release) cmd_release ;;
  check) cmd_check ;;
esac
