# Sourced by bootstrap.sh, deploy-observability.sh, rotate-secret.sh and tailscale-oauth.sh, not
# run on its own.

# shellcheck source=sops-keys.sh
. "$(dirname "${BASH_SOURCE[0]}")/sops-keys.sh"

# One OAuth client per tailnet name, so every cluster, prod's included, uses staging's
# (docs/adr/011-one-tailscale-client-staging.md). A prod copy would let a prod-first bootstrap
# put a second client on the tailnet. Relative to infra/k8s/.
TS_CLIENT_REL="overlays/staging/secrets/tailscale-oauth.enc.yaml"

# ts_client_incomplete FILE: true when client_id or client_secret is still empty in FILE. False
# when FILE doesn't decrypt; callers check that first.
ts_client_incomplete() {
  [ -n "$(sops_empty_keys "$1" client_id client_secret)" ]
}
