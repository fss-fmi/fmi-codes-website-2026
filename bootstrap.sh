#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INIT_SCRIPT="$SCRIPT_DIR/infra/k8s/scripts/init-linux.sh"
AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
AGE_PUBKEY="age1txhwhk6d5nph0sqf68e7yw5a0er572847jc4f60gmen5rfrx65xs0feuhh"

log()  { printf '\n\033[1;36m### %s\033[0m\n' "$1"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m⚠ %s\033[0m\n' "$1"; }
die()  { printf '\033[1;31mError: %s\033[0m\n' "$1" >&2; exit 1; }
ask()  { printf '\033[1;35m? %s\033[0m ' "$1"; }

[ -f "$INIT_SCRIPT" ] || die "expected infra/k8s/scripts/init-linux.sh — are you in the repo root?"

PASS_ARGS=()
while [ $# -gt 0 ]; do
  PASS_ARGS+=("$1")
  shift
done

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
    echo "  1) Replace with the correct key (paste the private key below)"
    echo "  2) Abort and copy the right key manually, then re-run"
    echo
    ask "Replace the key? (yes/no):"
    read -r REPLACE
    if [ "$REPLACE" = "yes" ]; then
      mkdir -p "$(dirname "$AGE_KEY_FILE")"
      ask "Paste the full contents of keys.txt (AGE-SECRET-KEY-... line), then press Enter:"
      read -r RAW_KEY
      printf '%s\n' "$RAW_KEY" > "$AGE_KEY_FILE"
      chmod 600 "$AGE_KEY_FILE"
      ok "key written to $AGE_KEY_FILE"
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
  echo "If you have it on another machine:"
  echo "  scp ~/.config/sops/age/keys.txt $(whoami)@$(hostname):/tmp/keys.txt"
  echo "  Then paste it below."
  echo
  ask "Paste the full contents of keys.txt (AGE-SECRET-KEY-... line), then press Enter:"
  read -r RAW_KEY
  [ -n "$RAW_KEY" ] || die "no key provided — cannot decrypt secrets"
  mkdir -p "$(dirname "$AGE_KEY_FILE")"
  printf '%s\n' "$RAW_KEY" > "$AGE_KEY_FILE"
  chmod 600 "$AGE_KEY_FILE"
  ok "key written to $AGE_KEY_FILE"
fi

log "Pre-flight: admin password"

ADMIN_HASH="${ADMIN_PASSWORD_HASH:-}"
if command -v sops >/dev/null 2>&1 && [ -f "$SCRIPT_DIR/infra/k8s/secrets/secrets.enc.yaml" ]; then
  EXISTING_HASH="$(SOPS_AGE_KEY_FILE="$AGE_KEY_FILE" sops -d \
    --extract '["stringData"]["ADMIN_PASSWORD_HASH"]' \
    "$SCRIPT_DIR/infra/k8s/secrets/secrets.enc.yaml" 2>/dev/null || true)"
  if [ -n "$EXISTING_HASH" ] && [ "$EXISTING_HASH" != '""' ]; then
    ok "ADMIN_PASSWORD_HASH already set in secrets — using existing value"
  else
    warn "ADMIN_PASSWORD_HASH is empty in secrets.enc.yaml"
    warn "The backend will CrashLoop until a valid bcrypt hash is set"
    echo
    echo "Set it now (recommended) or skip and set later with rotate-secret.sh."
    echo
    ask "Enter the admin password (will be hashed), or press Enter to skip:"
    read -rs ADMIN_PASS
    echo
    if [ -n "$ADMIN_PASS" ]; then
      if command -v python3 >/dev/null 2>&1 && python3 -c "import bcrypt" 2>/dev/null; then
        ADMIN_HASH="$(python3 -c "import bcrypt; print(bcrypt.hashpw('$ADMIN_PASS'.encode(), bcrypt.gensalt(12)).decode())")"
      else
        warn "python3-bcrypt not available — installing..."
        pip3 install --quiet bcrypt 2>/dev/null || sudo pip3 install --quiet bcrypt 2>/dev/null \
          || die "could not install bcrypt — run: pip3 install bcrypt, then re-run this script"
        ADMIN_HASH="$(python3 -c "import bcrypt; print(bcrypt.hashpw('$ADMIN_PASS'.encode(), bcrypt.gensalt(12)).decode())")"
      fi
      ok "hash generated — rotating secret..."
      bash "$SCRIPT_DIR/infra/k8s/scripts/rotate-secret.sh" ADMIN_PASSWORD_HASH "$ADMIN_HASH" 2>/dev/null || {
        warn "cluster not up yet — hash will be applied during deploy-app.sh via:"
        export ADMIN_PASSWORD_HASH="$ADMIN_HASH"
        ok "ADMIN_PASSWORD_HASH exported for this session"
      }
    else
      warn "Skipping — backend will CrashLoop. Fix later:"
      echo "  bash infra/k8s/scripts/rotate-secret.sh ADMIN_PASSWORD_HASH \"\$(python3 -c \\\"import bcrypt; print(bcrypt.hashpw(b'yourpass', bcrypt.gensalt(12)).decode())\\\")\""
    fi
  fi
else
  warn "sops not installed yet — admin password check will be handled by deploy-app.sh"
fi

log "Handing off to init-linux.sh"

exec bash "$INIT_SCRIPT" "${PASS_ARGS[@]+"${PASS_ARGS[@]}"}"
