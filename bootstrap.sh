#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INIT_SCRIPT="$SCRIPT_DIR/infra/k8s/scripts/init-linux.sh"
INSTALL_TOOLS="$SCRIPT_DIR/infra/k8s/scripts/install-tools.sh"
# Same lookup sops itself does, exported so every later script reads the file this one writes.
AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt}"
export SOPS_AGE_KEY_FILE="$AGE_KEY_FILE"

ENV="${ENV:-staging}"
PASSTHROUGH=()
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) exec bash "$INIT_SCRIPT" --help ;;
    --staging) ENV=staging; shift ;;
    --prod) ENV=prod; shift ;;
    --env) ENV="${2:-}"; [ -n "$ENV" ] || { echo "Error: --env needs a value (staging|prod)" >&2; exit 1; }; shift 2 ;;
    *) PASSTHROUGH+=("$1"); shift ;;
  esac
done

case "$ENV" in
  prod)    SECRETS_DIR="$SCRIPT_DIR/infra/k8s/secrets"; ENV_KEY_VAR="SOPS_AGE_KEY_PROD" ;;
  staging) SECRETS_DIR="$SCRIPT_DIR/infra/k8s/overlays/staging/secrets"; ENV_KEY_VAR="SOPS_AGE_KEY_STAGING" ;;
  *)       echo "Error: --env must be 'staging' or 'prod', got '$ENV'" >&2; exit 1 ;;
esac
SECRETS_ENC="$SECRETS_DIR/secrets.enc.yaml"
ENC_FILES=()
for f in "$SECRETS_ENC" "$SECRETS_DIR/grafana-secret.enc.yaml" "$SECRETS_DIR/tailscale-oauth.enc.yaml"; do
  if [ -f "$f" ]; then ENC_FILES+=("$f"); fi
done

log()  { printf '\n\033[1;36m### %s\033[0m\n' "$1"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m⚠ %s\033[0m\n' "$1"; }
die()  { printf '\033[1;31mError: %s\033[0m\n' "$1" >&2; exit 1; }
ask()  { printf '\033[1;35m? %s\033[0m ' "$1"; }

[ -f "$INIT_SCRIPT" ] || die "expected infra/k8s/scripts/init-linux.sh — are you in the repo root?"

PREFLIGHT_TMP="$(mktemp -d)"
trap 'rm -rf "$PREFLIGHT_TMP"' EXIT
FAILED_FILE=""

# The check is "can this key file decrypt every file", not a comparison of comment lines,
# so key order, missing "# public key:" comments and forked recipients all just work.
# Only $1 (plus candidate keys in $2) may count: shell keys are unset, and the empty
# XDG_CONFIG_HOME stops sops also reading the default keys.txt when $1 is a custom path.
# Candidate keys go through the environment, never argv (visible in ps) or a temp file.
decrypts_all() {
  local f
  for f in "${ENC_FILES[@]}"; do
    if ! (
      unset SOPS_AGE_KEY SOPS_AGE_KEY_CMD
      export XDG_CONFIG_HOME="$PREFLIGHT_TMP/no-config" SOPS_AGE_KEY_FILE="$1"
      if [ -n "${2:-}" ]; then export SOPS_AGE_KEY="$2"; fi
      sops --decrypt "$f" >/dev/null 2>"$PREFLIGHT_TMP/sops.err"
    ); then
      FAILED_FILE="$f"
      return 1
    fi
  done
}

key_in_file() {
  local line
  [ -f "$AGE_KEY_FILE" ] || return 1
  while IFS= read -r line || [ -n "$line" ]; do
    [ "${line%$'\r'}" = "$1" ] && return 0
  done < "$AGE_KEY_FILE"
  return 1
}

recipients() {
  { grep -hoE 'recipient: age1[0-9a-z]+' "${ENC_FILES[@]}" || true; } | awk '{print $2}' | sort -u
}

# Verifies the new key(s) against the files before touching keys.txt, then appends.
# Never overwrites: the other environment's key may live in the same file.
import_age_keys() {
  local raw="$1" keys key pub
  keys="$(printf '%s\n' "$raw" | grep -oE 'AGE-SECRET-KEY-1[0-9A-Z]+' | sort -u || true)"
  [ -n "$keys" ] || die "input does not contain an age private key (expected AGE-SECRET-KEY-1...)"
  while IFS= read -r key; do
    printf '%s\n' "$key" | age-keygen -y >/dev/null 2>&1 \
      || die "input contains a malformed age private key (checksum failed); copy it again"
  done <<<"$keys"

  if ! decrypts_all "$AGE_KEY_FILE" "$keys"; then
    warn "the provided key cannot decrypt $FAILED_FILE"
    echo "  provided key(s) have public key:"
    while IFS= read -r key; do
      printf '    %s\n' "$(printf '%s\n' "$key" | age-keygen -y)"
    done <<<"$keys"
    echo "  the $ENV secrets are encrypted to:"
    recipients | sed 's/^/    /'
    echo "  sops said:"
    sed 's/^/    /' "$PREFLIGHT_TMP/sops.err"
    die "nothing was written to $AGE_KEY_FILE"
  fi

  # Lock the file down before any key lands in it: a fresh file would otherwise be created
  # with the caller's umask (often 644) and stay world-readable if the script dies mid-append.
  (umask 077 && mkdir -p "$(dirname "$AGE_KEY_FILE")" && : >> "$AGE_KEY_FILE")
  chmod 600 "$AGE_KEY_FILE"
  if [ -s "$AGE_KEY_FILE" ] && [ -n "$(tail -c1 "$AGE_KEY_FILE")" ]; then
    echo >> "$AGE_KEY_FILE"
  fi
  while IFS= read -r key; do
    key_in_file "$key" && continue
    pub="$(printf '%s\n' "$key" | age-keygen -y)"
    printf '# added by bootstrap.sh (%s) on %s\n# public key: %s\n%s\n' \
      "$ENV" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$pub" "$key" >> "$AGE_KEY_FILE"
    ok "added key $pub to $AGE_KEY_FILE"
  done <<<"$keys"
  decrypts_all "$AGE_KEY_FILE" \
    || die "$AGE_KEY_FILE still cannot decrypt $FAILED_FILE: $(cat "$PREFLIGHT_TMP/sops.err")"
  ok "verified: $AGE_KEY_FILE decrypts every $ENV secrets file"
}

log "Pre-flight: tools (sops, age)"

if command -v sops >/dev/null 2>&1 && command -v age-keygen >/dev/null 2>&1; then
  ok "sops and age already installed"
else
  [ -f "$INSTALL_TOOLS" ] || die "expected $INSTALL_TOOLS"
  bash "$INSTALL_TOOLS" || die "install-tools.sh failed; fix the cause above and re-run"
fi

log "Pre-flight: age key (SOPS decryption)"

if [ "${#ENC_FILES[@]}" -eq 0 ]; then
  warn "no SOPS files in $SECRETS_DIR; skipping (deploy-app.sh will generate an in-cluster app secret)"
else
  if [ -e "$AGE_KEY_FILE" ]; then
    { [ -r "$AGE_KEY_FILE" ] && [ -w "$AGE_KEY_FILE" ]; } \
      || die "$AGE_KEY_FILE is not readable and writable by $(id -un); fix its ownership and re-run"
    if [ -s "$AGE_KEY_FILE" ] && ! age-keygen -y "$AGE_KEY_FILE" >/dev/null 2>"$PREFLIGHT_TMP/age.err"; then
      die "$AGE_KEY_FILE contains a line age cannot parse, so no key in it works: $(cat "$PREFLIGHT_TMP/age.err")"
    fi
  fi

  if [ -s "$AGE_KEY_FILE" ] && decrypts_all "$AGE_KEY_FILE"; then
    ok "$AGE_KEY_FILE already decrypts every $ENV secrets file; nothing to do"
  else
    if [ -s "$AGE_KEY_FILE" ]; then
      warn "no key in $AGE_KEY_FILE can decrypt $FAILED_FILE"
      warn "existing keys are kept; the $ENV key is added alongside them"
    else
      echo "No age key found at $AGE_KEY_FILE."
    fi
    echo
    echo "The $ENV secrets are encrypted to:"
    recipients | sed 's/^/  /'
    echo
    ENV_VAL="${!ENV_KEY_VAR:-}"
    if [ -n "$ENV_VAL" ]; then
      ok "using the key from \$$ENV_KEY_VAR"
      import_age_keys "$ENV_VAL"
    else
      [ -t 0 ] || die "no terminal to prompt on; export $ENV_KEY_VAR=AGE-SECRET-KEY-1... and re-run"
      echo "Tip: export $ENV_KEY_VAR=AGE-SECRET-KEY-1... to skip this prompt."
      echo
      echo "If you have the key on another machine, copy its AGE-SECRET-KEY-1... line from"
      echo "that machine's ~/.config/sops/age/keys.txt."
      echo
      ask "Paste the AGE-SECRET-KEY-1... line (input is hidden), then press Enter:"
      RAW_KEY=""
      read -rs RAW_KEY || true
      echo
      [ -n "$RAW_KEY" ] || die "no key provided; cannot decrypt secrets"
      import_age_keys "$RAW_KEY"
    fi
  fi
fi
# The key is on disk now; installers, helm and kubectl run below never need it in their env.
unset SOPS_AGE_KEY_STAGING SOPS_AGE_KEY_PROD ENV_VAL RAW_KEY

log "Pre-flight: admin password"

if [ -f "$SECRETS_ENC" ]; then
  EXISTING_HASH="$(sops -d \
    --extract '["stringData"]["ADMIN_PASSWORD_HASH"]' \
    "$SECRETS_ENC" 2>/dev/null | tr -d '"' || true)"
  if [ "${#EXISTING_HASH}" -gt 0 ]; then
    ok "ADMIN_PASSWORD_HASH already set in secrets — deploy-app.sh will apply it"
  else
    warn "ADMIN_PASSWORD_HASH is empty in secrets.enc.yaml"
    warn "The backend will CrashLoop until a valid bcrypt hash is written into the secrets file"
    echo
    ask "Enter the admin password (min 12 chars) to hash and write into secrets.enc.yaml, or press Enter to skip:"
    ADMIN_PASS=""
    read -rs ADMIN_PASS || true
    echo
    if [ -n "$ADMIN_PASS" ]; then
      [ "${#ADMIN_PASS}" -ge 12 ] || die "admin password must be at least 12 characters; nothing written"
      ask "Repeat it:"
      ADMIN_PASS_CONFIRM=""
      read -rs ADMIN_PASS_CONFIRM || true
      echo
      [ "$ADMIN_PASS" = "$ADMIN_PASS_CONFIRM" ] || die "the two entries differ; nothing written"
      unset ADMIN_PASS_CONFIRM
      [[ "$(sops set --help 2>&1 || true)" == *--value-stdin* ]] \
        || die "this sops has no 'set --value-stdin'; replace it with the version install-tools.sh pins (sudo rm \"$(command -v sops)\" && bash $INSTALL_TOOLS)"
      if ! command -v python3 >/dev/null 2>&1; then
        die "python3 not found — install it first: sudo apt-get install -y python3"
      fi
      if ! python3 -c "import bcrypt" 2>/dev/null; then
        warn "python3-bcrypt not available — installing via apt..."
        sudo apt-get install -y python3-bcrypt \
          || die "could not install python3-bcrypt — run: sudo apt-get install -y python3-bcrypt, then re-run"
      fi
      ADMIN_HASH="$(ADMIN_PASS="$ADMIN_PASS" python3 -c \
        "import bcrypt, os; print(bcrypt.hashpw(os.environ['ADMIN_PASS'].encode(), bcrypt.gensalt(12)).decode())")"
      unset ADMIN_PASS
      # Through stdin: an argument would show the hash to every local user via ps.
      printf '"%s"' "$ADMIN_HASH" | sops set --value-stdin "$SECRETS_ENC" '["stringData"]["ADMIN_PASSWORD_HASH"]'
      unset ADMIN_HASH
      ok "hash written into secrets.enc.yaml — commit and push this file before deploying to other servers"
    else
      warn "Skipping — backend will CrashLoop. Fix later with:"
      echo "  ENV=$ENV bash infra/k8s/scripts/rotate-secret.sh ADMIN_PASSWORD_HASH"
    fi
  fi
else
  warn "no $SECRETS_ENC; deploy-app.sh generates the app secret and prints how to set ADMIN_PASSWORD_HASH"
fi

log "Pre-flight: Tailscale OAuth client (Grafana and staging access)"

# Mirrors init-linux.sh: observability (step 7) runs whenever Flux does, unless opted out.
WILL_OBSERVE="${WITH_FLUX:-false}"
PREV_ARG=""
for a in ${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}; do
  case "$a" in
    --with-flux|--with-observability) WILL_OBSERVE=true ;;
  esac
  if [ "$PREV_ARG" = "--from" ] && { [ "$a" = 6 ] || [ "$a" = 7 ]; }; then WILL_OBSERVE=true; fi
  PREV_ARG="$a"
done
for a in ${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}; do
  if [ "$a" = "--without-observability" ]; then WILL_OBSERVE=false; fi
done
[ "${WITH_OBSERVABILITY:-auto}" != "false" ] || WILL_OBSERVE=false

TS_FILE="$SECRETS_DIR/tailscale-oauth.enc.yaml"
TS_SCRIPT="$SCRIPT_DIR/infra/k8s/scripts/tailscale-oauth.sh"
TS_EMPTY_RE="^[[:space:]]+client_(id|secret):[[:space:]]*(\"\"|'')?[[:space:]]*\$"
NEW_CLIENT_STEPS="Create an OAuth client for THIS cluster in the Tailscale admin console
(Settings -> OAuth clients, or Trust credentials):
  scopes: General -> Services, Devices -> Core, Keys -> Auth Keys (read + write each)
  tag:    tag:k8s-operator
Save the client ID and secret in the password manager; you paste them below.
First time on this tailnet? Do docs/runbook.md 'Tailscale setup' (steps 1 to 4) first."

# set_ts_client: run 'tailscale-oauth.sh set', offering another try after a typo.
set_ts_client() {
  until ENV="$ENV" TAILSCALE_SECRET_ENC="$TS_FILE" bash "$TS_SCRIPT" set; do
    ask "Try again? [Y/n]"
    local again=""
    # EOF (terminal gone) counts as no, or this would ask forever.
    read -r again || again=n
    case "$again" in
      n|N) warn "skipped; set it later with: ENV=$ENV bash infra/k8s/scripts/tailscale-oauth.sh set"; return 0 ;;
    esac
  done
  ok "OAuth client stored; commit $TS_FILE before deploying this env anywhere else"
}

if [ "$WILL_OBSERVE" != "true" ]; then
  ok "skipped: the Tailscale client (step 7) only runs with --with-flux"
  if [ "$ENV" = "staging" ]; then
    warn "staging is reached only over the tailnet, so without it use a port-forward:
  kubectl -n ingress-nginx-staging port-forward svc/ingress-nginx-staging-controller 8080:80"
  fi
elif [ ! -f "$TS_FILE" ]; then
  warn "no $TS_FILE; Grafana and staging will not join the tailnet"
# Not grep -q: exiting at the first match could SIGPIPE sops, and pipefail would invert the result.
elif ! sops --decrypt "$TS_FILE" | grep -E "$TS_EMPTY_RE" >/dev/null; then
  ok "$TS_FILE already holds an OAuth client"
  if [ -t 0 ]; then
    ask "Is this cluster taking over Grafana and staging from another cluster (for example a new server)? [y/N]"
    TAKEOVER=""
    read -r TAKEOVER || true
    case "$TAKEOVER" in
      y|Y)
        cat <<EOF

Only one cluster may hold the 'grafana' and 'staging' tailnet names. Before this one takes over
(details: docs/runbook.md 'Move Grafana and staging to another cluster'):
  1. On the old cluster, if it still runs:
       ENV=<its env> bash infra/k8s/scripts/tailscale-oauth.sh release
     and commit the emptied file it names.
  2. Tailscale admin console: revoke the old cluster's OAuth client, and on the Machines page
     delete its 'grafana', 'staging' and 'fmi-codes-operator' devices.
  3. $NEW_CLIENT_STEPS

EOF
        ask "Press Enter once steps 1 to 3 are done (Ctrl+C to stop here):"
        read -r _ || true
        set_ts_client
        ;;
    esac
  fi
else
  if [ -t 0 ]; then
    cat <<EOF
Grafana and staging are reached over Tailscale, and this cluster has no OAuth client yet.
$NEW_CLIENT_STEPS

EOF
    ask "Set the OAuth client now? [Y/n]"
    SET_NOW=""
    read -r SET_NOW || true
    case "$SET_NOW" in
      n|N) warn "skipped; Grafana and staging stay off the tailnet. Later: ENV=$ENV bash infra/k8s/scripts/tailscale-oauth.sh set, then ENV=$ENV bash infra/k8s/scripts/deploy-observability.sh" ;;
      *) set_ts_client ;;
    esac
  else
    warn "no terminal to prompt on; Grafana and staging stay off the tailnet until: ENV=$ENV bash infra/k8s/scripts/tailscale-oauth.sh set"
  fi
fi

log "Handing off to init-linux.sh"

export ENV
bash "$INIT_SCRIPT" --env "$ENV" ${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}

if grep -qi microsoft /proc/version 2>/dev/null; then
  # Run for staging too: it removes the fmi-forward-staging unit older setups installed.
  log "Installing boot-persistent forward services (prod only; staging is on the tailnet)"
  INSTALL_SVC_SCRIPT="$SCRIPT_DIR/infra/k8s/scripts/install-forward-services.sh"
  # A bare wsl.exe targets the Windows default distro (docker-desktop when Docker Desktop is installed), not this one.
  if [ -n "${WSL_DISTRO_NAME:-}" ] \
    && wsl.exe -d "$WSL_DISTRO_NAME" -u root -- bash -c "bash '${INSTALL_SVC_SCRIPT}' install"; then
    FWD_STATUS="The forward services are now installed (auto-start on every boot, no terminal needed).
One manual step remains — map"
  else
    warn "forward services install failed — run manually: wsl.exe -d \"\$WSL_DISTRO_NAME\" -u root -- bash infra/k8s/scripts/install-forward-services.sh install"
    FWD_STATUS="The forward services did NOT install: run the command from the warning above first.
Then map"
  fi

  if [ "$ENV" = "prod" ]; then
    cat <<EOF

$(printf '\033[1;36m### WSL2 -> Windows host resolution\033[0m')

${FWD_STATUS} the hostnames to loopback in the WINDOWS hosts file
(C:\\Windows\\System32\\drivers\\etc\\hosts). Editing WSL's /etc/hosts does not help
the Windows browser. From an elevated PowerShell:
  Add-Content -Path \$env:WINDIR\\System32\\drivers\\etc\\hosts -Value "127.0.0.1 fmicodes.com"

Then browse to https://fmicodes.com

Note: adding fmicodes.com to your hosts file overrides public DNS on this machine.
Remove this line when you want your browser to reach the production server instead.
EOF
  else
    cat <<EOF

Staging needs no Windows hosts entry: open its tailnet address from any tailnet device
(kubectl -n ingress-nginx-staging get ingress staging). If an older setup added
"127.0.0.1 staging.fmicodes.com" to the Windows hosts file, delete that line.

$(printf '\033[1;33m### Next step: bootstrap prod\033[0m')

Staging is up. To bring up prod, run:
  ENV=prod bash bootstrap.sh
EOF
  fi
fi

cat <<EOF

Grafana and staging (with --with-flux) need no hosts entry: they are reachable only over
Tailscale, at the addresses \`kubectl -n monitoring get ingress grafana\` and
\`kubectl -n ingress-nginx-staging get ingress staging\` show.
Setup and handover: docs/runbook.md 'Phase 7'.
EOF
