# Sourced by bootstrap.sh, deploy-observability.sh, rotate-secret.sh and tailscale-oauth.sh, not
# run on its own.

# One OAuth client per tailnet name, so every cluster, prod's included, uses staging's
# (docs/adr/011-one-tailscale-client-staging.md). A prod copy would let a prod-first bootstrap
# put a second client on the tailnet. Relative to infra/k8s/.
TS_CLIENT_REL="overlays/staging/secrets/tailscale-oauth.enc.yaml"
