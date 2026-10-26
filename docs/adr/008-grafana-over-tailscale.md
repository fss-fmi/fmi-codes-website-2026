# ADR-008: One shared Grafana, reached over Tailscale

**Status**: accepted

## Context

One kube-prometheus-stack serves both environments ([ADR-006](006-self-hosted-k3s-pull-based-gitops.md) puts them on one node). Grafana used to be exposed as `grafana.fmicodes.com` on the prod ingress-nginx controller, and its Flux Kustomization depended on the prod ingress. That had three problems:

- On a cluster where only staging is bootstrapped, the prod ingress never exists, so the whole monitoring stack never installed.
- Grafana went down together with the prod ingress, which is exactly when it is needed.
- The cluster runs on a home server. The ingress host had no TLS, so publishing it would have put a dashboard login on the internet in plaintext. The only alternative was SSH plus `kubectl port-forward` for every viewer.

A second, per-environment stack was rejected: kube-prometheus-stack CRDs are cluster-scoped, node-exporter binds a host port, the node has no spare memory for a second Prometheus, and two Flux Kustomizations writing the same HelmRelease already overwrote each other once. A public host behind TLS and GitHub login was also considered. It needs the same amount of setup, but a mistake (a wrong `allowed_organizations`, a missing TLS block) fails open, and Grafana itself stays exposed to the internet.

## Decision

- **One stack for both environments**, installed by its own Flux Kustomization that depends on no app environment. A single ServiceMonitor scrapes `fmi-codes` and `fmi-codes-staging`.
- **Grafana is reachable only over a Tailscale tailnet.** The Tailscale Kubernetes operator (its own Flux Kustomization) serves an Ingress with `ingressClassName: tailscale` as `https://grafana.<tailnet>.ts.net`, with a certificate it provisions. Traffic goes from the viewer's device to a proxy pod and then to the Grafana Service, without touching ingress-nginx.
- **The tailnet belongs to the `fss-fmi` GitHub org.** Developers join with their GitHub login and an admin approves them. The cluster joins as tagged devices (`tag:k8s`) through an OAuth client, so whoever hosts the hardware needs no account. The tailnet policy lets one group of named developers reach `tag:k8s` on port 443 and lets `tag:k8s` reach nothing.
- **The Grafana admin password and the Tailscale OAuth client are SOPS secrets with one copy per environment.** They are cluster-wide objects, so `deploy-observability.sh` and `rotate-secret.sh` label the live Secret with the environment it came from and refuse to replace it with the other environment's copy.
- **One cluster on the tailnet at a time, each with its own OAuth client.** Moving Grafana to another cluster revokes the old client and deletes the old devices before the new cluster joins, so `grafana.<tailnet>.ts.net` always means one cluster. Revoking clients and deleting devices stays a manual admin-console step: automating it would hand a script a tailnet-wide admin credential. `bootstrap.sh` asks for the client, guides the handover, and `deploy-observability.sh` flags a cluster that joined as `grafana-1`.

## Consequences

- **Easier**: monitoring comes up on any cluster, including a staging-only one, and survives an ingress outage. Nothing about Grafana is reachable from the internet, and a misconfiguration leaves it unreachable rather than open. No router ports are opened at the hosting site. The same tailnet can later carry SSH and `kubectl` access to the server.
- **Harder**: every viewer installs the Tailscale client and needs approval. Adding or removing a developer means changing the tailnet and Grafana's user list. One more operator runs in the cluster, and one more external account (Tailscale) holds a credential.
- **Technical debt**: the tailnet policy lives in the Tailscale admin console, not in git; the runbook holds the reference copy. Whether leaving the GitHub org removes tailnet access is not documented, so offboarding is a manual step. The free plan's user limit caps the number of viewers.
- **Later**: staging moved onto the same tailnet and operator, in front of its own ingress-nginx ([ADR-009](009-staging-over-tailscale.md)). The one-cluster rule and the handover now cover the `staging` device too.
