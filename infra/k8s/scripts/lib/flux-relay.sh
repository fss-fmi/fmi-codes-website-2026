# Sourced by deploy-observability.sh and rotate-secret.sh, not run on its own.

# shellcheck source=sops-keys.sh
. "$(dirname "${BASH_SOURCE[0]}")/sops-keys.sh"

FLUX_RELAY_SLACK="flux-relay-slack"
FLUX_RELAY_KEYS="bot_token cluster_channel staging_channel"

# flux_relay_empty_keys FILE: print the keys still empty in FILE (a flux-relay-slack.enc.yaml),
# space-separated. Without all three the relay stays idle or skips a channel.
flux_relay_empty_keys() {
  # shellcheck disable=SC2086
  sops_empty_keys "$1" $FLUX_RELAY_KEYS
}

# flux_relay_check_key KEY: refuse anything but one of FLUX_RELAY_KEYS.
flux_relay_check_key() {
  case " $FLUX_RELAY_KEYS " in
    *" $1 "*) return 0 ;;
  esac
  echo "--flux-relay takes ${FLUX_RELAY_KEYS// /, }, got '$1'." >&2
  return 1
}

# flux_relay_check_value KEY VALUE: refuse a value that can't be right for KEY.
flux_relay_check_value() {
  case "$1" in
    bot_token)
      [[ "$2" == xoxb-* ]] || { echo "that is not a Slack bot token (xoxb-...)." >&2; return 1; } ;;
    *)
      [[ "$2" =~ ^[CG][A-Z0-9]{6,}$ ]] || { echo "that is not a Slack channel ID (C... or G..., from the channel's About tab)." >&2; return 1; } ;;
  esac
}
