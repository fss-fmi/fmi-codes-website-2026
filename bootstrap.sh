#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INIT_SCRIPT="$SCRIPT_DIR/infra/k8s/scripts/init-linux.sh"
AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
AGE_PUBKEY="age1txhwhk6d5nph0sqf68e7yw5a0er572847jc4f60gmen5rfrx65xs0feuhh"
SECRETS_ENC="$SCRIPT_DIR/infra/k8s/secrets/secrets.enc.yaml"

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

exec bash "$INIT_SCRIPT" "$@"
