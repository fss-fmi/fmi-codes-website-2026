#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INIT_SCRIPT="$SCRIPT_DIR/infra/k8s/scripts/init-linux.sh"
AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"

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
  prod)    AGE_PUBKEY="age1txhwhk6d5nph0sqf68e7yw5a0er572847jc4f60gmen5rfrx65xs0feuhh"; SECRETS_ENC="$SCRIPT_DIR/infra/k8s/secrets/secrets.enc.yaml" ;;
  staging) AGE_PUBKEY="age15zg0ymdvkt87hdvsj4xg582h0zsdgdrnkkk6msc76xtcrcyxyvcsljz0w5"; SECRETS_ENC="$SCRIPT_DIR/infra/k8s/overlays/staging/secrets/secrets.enc.yaml" ;;
  *)       echo "Error: --env must be 'staging' or 'prod', got '$ENV'" >&2; exit 1 ;;
esac

log()  { printf '\n\033[1;36m### %s\033[0m\n' "$1"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m⚠ %s\033[0m\n' "$1"; }
die()  { printf '\033[1;31mError: %s\033[0m\n' "$1" >&2; exit 1; }
ask()  { printf '\033[1;35m? %s\033[0m ' "$1"; }

[ -f "$INIT_SCRIPT" ] || die "expected infra/k8s/scripts/init-linux.sh — are you in the repo root?"

write_age_key() {
  local raw_key="$1"
  echo "$raw_key" | grep -qE '^AGE-SECRET-KEY-1[A-Z0-9]+$' \
    || die "input does not look like a valid age private key (expected AGE-SECRET-KEY-1...)"
  local tmp
  tmp="$(mktemp)"
  printf '%s\n' "$raw_key" > "$tmp"
  chmod 600 "$tmp"
  mkdir -p "$(dirname "$AGE_KEY_FILE")"
  mv "$tmp" "$AGE_KEY_FILE"
  ok "key written to $AGE_KEY_FILE"
  if [ -f "$SECRETS_ENC" ] && command -v sops >/dev/null 2>&1; then
    SOPS_AGE_KEY_FILE="$AGE_KEY_FILE" sops -d "$SECRETS_ENC" >/dev/null 2>&1 \
      || die "key was written but cannot decrypt $SECRETS_ENC — wrong key?"
    ok "key verified: successfully decrypts secrets.enc.yaml"
  fi
}

log "Pre-flight: age key (SOPS decryption)"

if [ -f "$AGE_KEY_FILE" ]; then
  EXISTING_PUB="$(grep -m1 '^# public key:' "$AGE_KEY_FILE" | awk '{print $NF}' || true)"
  if [ "$EXISTING_PUB" = "$AGE_PUBKEY" ]; then
    ok "age key already in place and matches the repo recipient — nothing to do"
  else
    warn "age key exists but public key does not match the repo recipient"
    warn "  found:    ${EXISTING_PUB:-<could not read>}"
    warn "  expected: $AGE_PUBKEY"
    echo
    echo "Options:"
    echo "  1) Replace with the correct key (paste the AGE-SECRET-KEY-1... line below)"
    echo "  2) Abort and copy the right key manually, then re-run"
    echo
    ask "Replace the key? (yes/no):"
    read -r REPLACE
    if [ "$REPLACE" = "yes" ]; then
      ask "Paste the AGE-SECRET-KEY-1... line, then press Enter:"
      read -r RAW_KEY
      write_age_key "$RAW_KEY"
    else
      die "aborted — copy the correct age private key to $AGE_KEY_FILE and re-run"
    fi
  fi
else
  echo "No age key found at $AGE_KEY_FILE."
  echo
  echo "You need the private key that corresponds to:"
  echo "  $AGE_PUBKEY"
  echo
  echo "If you have it on another machine, copy the AGE-SECRET-KEY-1... line from"
  echo "  ~/.config/sops/age/keys.txt"
  echo "and paste it below (paste only that one line, not the comment lines)."
  echo
  ask "Paste the AGE-SECRET-KEY-1... line, then press Enter:"
  read -r RAW_KEY
  [ -n "$RAW_KEY" ] || die "no key provided — cannot decrypt secrets"
  write_age_key "$RAW_KEY"
fi

log "Pre-flight: admin password"

if command -v sops >/dev/null 2>&1 && [ -f "$SECRETS_ENC" ]; then
  EXISTING_HASH="$(SOPS_AGE_KEY_FILE="$AGE_KEY_FILE" sops -d \
    --extract '["stringData"]["ADMIN_PASSWORD_HASH"]' \
    "$SECRETS_ENC" 2>/dev/null | tr -d '"' || true)"
  if [ "${#EXISTING_HASH}" -gt 0 ]; then
    ok "ADMIN_PASSWORD_HASH already set in secrets — deploy-app.sh will apply it"
  else
    warn "ADMIN_PASSWORD_HASH is empty in secrets.enc.yaml"
    warn "The backend will CrashLoop until a valid bcrypt hash is written into the secrets file"
    echo
    ask "Enter the admin password to hash and write into secrets.enc.yaml, or press Enter to skip:"
    read -rs ADMIN_PASS
    echo
    if [ -n "$ADMIN_PASS" ]; then
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
      SOPS_AGE_KEY_FILE="$AGE_KEY_FILE" sops set "$SECRETS_ENC" \
        '["stringData"]["ADMIN_PASSWORD_HASH"]' "\"$ADMIN_HASH\""
      ok "hash written into secrets.enc.yaml — commit and push this file before deploying to other servers"
    else
      warn "Skipping — backend will CrashLoop. Fix later with:"
      echo "  bash infra/k8s/scripts/rotate-secret.sh ADMIN_PASSWORD_HASH"
    fi
  fi
else
  warn "sops not installed yet — admin password check will be handled by deploy-app.sh"
fi

log "Handing off to init-linux.sh"

export ENV
bash "$INIT_SCRIPT" --env "$ENV" ${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}

if grep -qi microsoft /proc/version 2>/dev/null; then
  case "$ENV" in
    prod)    HOST="fmicodes.com";         HOST_URL="https://$HOST" ;;
    staging) HOST="staging.fmicodes.com"; HOST_URL="https://$HOST:9443" ;;
  esac

  if [ "$ENV" = "prod" ]; then
    DNS_NOTE="Note: adding $HOST to your hosts file overrides public DNS on this machine.
Remove this line when you want your browser to reach the production server instead."
  else
    DNS_NOTE="Note: this maps $HOST only on this machine, for reaching the staging
cluster in WSL2. Remove the line when you no longer need it."
  fi

  log "Installing boot-persistent forward services (prod + staging bridges)"
  INSTALL_SVC_SCRIPT="$SCRIPT_DIR/infra/k8s/scripts/install-forward-services.sh"
  wsl.exe -u root -- bash -c "bash '${INSTALL_SVC_SCRIPT}' install" \
    || warn "forward services install failed — run manually: wsl.exe -u root -- bash infra/k8s/scripts/install-forward-services.sh install"

  cat <<EOF

$(printf '\033[1;36m### WSL2 -> Windows host resolution\033[0m')

The forward services are now installed (auto-start on every boot, no terminal needed).
One manual step remains — map the hostnames to loopback in the WINDOWS hosts file
(C:\\Windows\\System32\\drivers\\etc\\hosts). Editing WSL's /etc/hosts does not help
the Windows browser. From an elevated PowerShell:
  Add-Content -Path \$env:WINDIR\\System32\\drivers\\etc\\hosts -Value "127.0.0.1 $HOST"
EOF

  if [ "$ENV" = "prod" ]; then
    cat <<EOF
  Add-Content -Path \$env:WINDIR\\System32\\drivers\\etc\\hosts -Value "127.0.0.1 grafana.fmicodes.com"
EOF
  fi

  cat <<EOF

Then browse to ${HOST_URL}

$DNS_NOTE
EOF

  if [ "$ENV" = "staging" ]; then
    cat <<EOF

$(printf '\033[1;33m### Next step: bootstrap prod\033[0m')

Staging is up. To bring up prod (app + Grafana), run:
  ENV=prod bash bootstrap.sh

Grafana (grafana.fmicodes.com) only becomes reachable once prod is bootstrapped —
it rides the prod ingress bridge. When you do, also add to the Windows hosts file:
  Add-Content -Path \$env:WINDIR\\System32\\drivers\\etc\\hosts -Value "127.0.0.1 grafana.fmicodes.com"
EOF
  fi
fi
