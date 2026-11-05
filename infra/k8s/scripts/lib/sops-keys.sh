# Sourced by the other libs and scripts, not run on its own.

# sops_empty_keys FILE KEY...: print, space-separated, the KEYs whose stringData value in the
# SOPS file FILE is empty. Fails, printing nothing, if FILE doesn't decrypt.
sops_empty_keys() {
  local file="$1" decrypted key empty=""
  shift
  decrypted="$(sops --decrypt "$file" 2>/dev/null)" || return 1
  for key in "$@"; do
    # Not grep -q: exiting at the first match could SIGPIPE printf, and pipefail would invert it.
    if printf '%s\n' "$decrypted" \
        | grep -E "^[[:space:]]+$key:[[:space:]]*(\"\"|'')?[[:space:]]*\$" >/dev/null; then
      empty="${empty:+$empty }$key"
    fi
  done
  unset decrypted
  printf '%s' "$empty"
}
