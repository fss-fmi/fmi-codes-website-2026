# ADR-006: Self-hosted k3s with pull-based Flux GitOps and a manual production gate

**Status**: accepted

## Context

The platform is run by a student council with no cloud budget and must be live and reliable for one critical weekend a year. The team wanted no managed cloud or PaaS, a staging environment that genuinely mirrors production, and zero chance of an unreviewed change reaching the live event site. The server sits on a network GitHub-hosted runners cannot reach.

## Decision

- One self-hosted single-node **k3s** server runs both environments, isolated by namespace (`fmi-codes`, `fmi-codes-staging`) with separate ingress controllers, databases and SOPS age keys. Both are built from one `infra/k8s/base/` through Kustomize overlays that differ only in namespace, hostname, TLS issuer and DB host.
- Postgres and Redis Sentinel come from Bitnami Helm charts inside the cluster. App secrets are SOPS-encrypted in git; DB and Redis passwords are generated in-cluster.
- Deployment is **pull-based**: Flux runs in the cluster, watches Docker Hub and git, and auto-bumps only the staging overlay. Production moves only when the `promote-to-prod` workflow opens a PR and a human merges it.
- `bootstrap.sh` takes a bare Debian/Ubuntu box to a running cluster in resumable phases.

## Consequences

- **Easier**: no hosting bill; staging catches problems with prod-identical config; `git revert` of a promote commit is a rollback; the prod gate holds structurally (the prod overlay has no Flux image markers).
- **Harder**: one physical node is a single point of failure for both environments. The team operates the whole stack (k3s, ingress, cert-manager, Prometheus, Grafana) itself. Bitnami images are pinned to the frozen `bitnamilegacy` registry.
- **Technical debt**: no automated database backups; the Postgres PVC is the source of truth. Migrating off `bitnamilegacy` images is open work.
