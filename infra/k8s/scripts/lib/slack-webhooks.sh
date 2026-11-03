# Sourced by deploy-observability.sh and rotate-secret.sh, not run on its own.

FLUX_NS="${FLUX_NS:-flux-system}"
# Alertmanager Secret key -> the flux-system Secret its Flux Provider reads.
SLACK_WEBHOOK_KEYS="url:flux-slack staging_url:flux-slack-staging"

# copy_slack_webhooks_for_flux NAMESPACE SECRET: Flux's Providers can only read Secrets in their
# own namespace, under the key `address`, so each webhook in the live Alertmanager Secret is
# copied to its own Secret there. An empty key deletes its copy, so a cleared webhook stops
# Flux too. Sets SLACK_EMPTY_KEYS to the keys that are still empty.
copy_slack_webhooks_for_flux() {
  local ns="$1" secret="$2" pair key target value
  SLACK_EMPTY_KEYS=""
  if ! kubectl get namespace "$FLUX_NS" >/dev/null 2>&1; then
    echo "No $FLUX_NS namespace yet (Flux not installed): the Slack webhooks are not copied for Flux." >&2
    return 0
  fi
  for pair in $SLACK_WEBHOOK_KEYS; do
    key="${pair%%:*}"
    target="${pair#*:}"
    value="$(kubectl -n "$ns" get secret "$secret" -o jsonpath="{.data.$key}" | base64 -d)"
    if [ -z "$value" ]; then
      SLACK_EMPTY_KEYS="${SLACK_EMPTY_KEYS:+$SLACK_EMPTY_KEYS }$key"
      kubectl -n "$FLUX_NS" delete secret "$target" --ignore-not-found >/dev/null
    else
      # printf is a builtin: the URL goes through a pipe, never argv.
      printf '%s' "$value" | kubectl -n "$FLUX_NS" create secret generic "$target" \
        --from-file=address=/dev/stdin --dry-run=client -o yaml | kubectl apply -f - >/dev/null
      echo "Copied '$key' to $FLUX_NS/$target for Flux."
    fi
  done
  unset value
}
