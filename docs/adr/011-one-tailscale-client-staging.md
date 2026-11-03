# ADR-011: One Tailscale OAuth client, staging's, on every cluster

**Status**: accepted. Amends [ADR-008](008-grafana-over-tailscale.md): the Tailscale OAuth client no longer has a copy per environment.

## Context

ADR-008 gave the Grafana admin password and the Tailscale OAuth client one SOPS copy per environment, and the env label on the live Secret records which copy a cluster runs. For the OAuth client that meant the first environment to run `deploy-observability.sh` on a cluster decided whose client it used. Bootstrapping prod first on a new machine would have stored a new client in prod's file and put it on the tailnet, while staging's file still held the client of the cluster that already serves `grafana` and `staging`. Two files for what the one-cluster-at-a-time rule makes a single credential leaves room for exactly the mistake that rule exists to prevent, and prod's file was never filled.

Unlike Grafana's password or the Slack webhooks, which client a cluster uses changes nothing about what it serves: any valid client on the `fss-fmi` tailnet puts Grafana and staging on it.

## Decision

- **There is one `tailscale-oauth.enc.yaml`, staging's** (`overlays/staging/secrets/`), and no prod copy or `.sops.yaml` rule. `deploy-observability.sh`, `tailscale-oauth.sh`, `rotate-secret.sh --tailscale` and the bootstrap pre-flight use it whatever `ENV` is, and label `tailscale/operator-oauth` as `staging`.
- **A machine that runs prod needs the staging age key too.** `bootstrap.sh --env prod --with-flux` checks it the way it checks the env's own key (`SOPS_AGE_KEY_STAGING` or a hidden prompt).
- Grafana's admin password and the Slack webhooks keep their copy per environment.

## Consequences

- **Easier**: a cluster's tailnet identity doesn't depend on which environment was bootstrapped first. A prod-first bootstrap on a new machine sees staging's client and asks about the handover instead of offering a second client. One file to rotate, release and hand over.
- **Harder**: the per-environment key separation is weaker. A staging key on the prod server can read the tailnet OAuth client, and a staging key leak now means rotating that client for every cluster. Accepted because every planned prod machine also runs staging and needs the staging key for it anyway.
- **Later**: a machine that runs only prod would hold the staging key just for this. Revisit this decision before setting one up.
