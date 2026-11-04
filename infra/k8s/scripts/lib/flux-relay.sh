# Sourced by deploy-observability.sh and rotate-secret.sh, not run on its own.

FLUX_RELAY_SLACK="flux-relay-slack"
FLUX_RELAY_KEYS="bot_token cluster_channel staging_channel"

# flux_relay_empty_keys FILE: print the keys still empty in FILE (a flux-relay-slack.enc.yaml),
# space-separated. Without all three the relay stays idle or skips a channel.
flux_relay_empty_keys() {
  local decrypted key empty=""
  decrypted="$(sops --decrypt "$1")" || return 1
  for key in $FLUX_RELAY_KEYS; do
    # Not grep -q: exiting at the first match could SIGPIPE printf, and pipefail would invert it.
    if printf '%s\n' "$decrypted" \
        | grep -E "^[[:space:]]+$key:[[:space:]]*(\"\"|'')?[[:space:]]*\$" >/dev/null; then
      empty="${empty:+$empty }$key"
    fi
  done
  unset decrypted
  printf '%s' "$empty"
}

# flux_relay_check_value KEY VALUE: refuse a value that can't be right for KEY.
flux_relay_check_value() {
  case "$1" in
    bot_token)
      [[ "$2" == xoxb-* ]] || { echo "that is not a Slack bot token (xoxb-...)." >&2; return 1; } ;;
    cluster_channel|staging_channel)
      [[ "$2" =~ ^[CG][A-Z0-9]{6,}$ ]] || { echo "that is not a Slack channel ID (C... or G..., from the channel's About tab)." >&2; return 1; } ;;
    *)
      echo "--flux-relay takes ${FLUX_RELAY_KEYS// /, }, got '$1'." >&2; return 1 ;;
  esac
}
