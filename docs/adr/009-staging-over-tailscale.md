# ADR-009: Staging reached over the tailnet, in front of its own ingress-nginx

**Status**: accepted

## Context

Staging was reachable only by whoever held the cluster, and only through local plumbing. On the WSL2 dev box a `kubectl port-forward` unit served it on `127.0.0.1:9443` behind a Windows hosts entry for `staging.fmicodes.com`. On the server the `ingress-nginx-staging` controller bound host ports 8080 and 8443, again behind a hosts entry. Both served a self-signed certificate, so every visit was a browser warning, and the URL carried a port suffix. `FRONTEND_ORIGIN` was `https://staging.fmicodes.com` with no port, so staging's password-reset and verification links pointed at a URL that loaded nowhere. Other developers could not reach staging at all.

[ADR-008](008-grafana-over-tailscale.md) had already put Grafana on the `fss-fmi` tailnet, with a Tailscale operator in the cluster and an approved group of developers.

## Decision

- **Staging is served only over the tailnet**, as `https://staging.<tailnet>.ts.net`, with the Tailscale proxy's browser-trusted certificate. Nothing about staging is reachable from the internet or the LAN.
- **The Tailscale Ingress fronts the `ingress-nginx-staging` controller, not the app Services.** Path: device → Tailscale proxy (TLS) → `ingress-nginx-staging-controller:80` (plain HTTP) → app. Staging exists to mirror prod's request path, so it keeps sending the `security-headers` ConfigMap (CSP, HSTS and the rest) and exercising prod's `/api` and `/static` routing. A CSP regression is caught on staging before it reaches prod.
- The operator only resolves backends in the Ingress's own namespace, so the Tailscale Ingress lives in `ingress-nginx-staging` (`overlays/staging/tailnet`) with its own Flux Kustomization. The staging nginx Ingress matches any host, has no TLS block and turns `ssl-redirect` off, because the proxy forwards plain HTTP with the `ts.net` Host header kept. The staging controller becomes a `ClusterIP` Service, and staging needs no certificate and no cert-manager.
- **Staging's `FRONTEND_ORIGIN` lives in its SOPS app secret**, not the ConfigMap, so the tailnet name, which ties the random `ts.net` name to the `fss-fmi` org, never sits in the public repo in plain text. The backend reads it with an optional `secretKeyRef`: a secret without it never blocks a rollout or a fresh bootstrap, and `deploy-app.sh` and `tailscale-oauth.sh check` warn when it is missing or differs from the Ingress's address.

Rejected: a Tailscale Ingress straight to `frontend` and `backend` (the Grafana shape). It is simpler and lets the staging controller go, but staging would stop testing prod's edge. That shape fits internal tools with no prod twin, like Grafana. Also rejected: committing the tailnet URL in the ConfigMap. It is not a credential and Certificate Transparency logs already list the name, but the repo would link it to the org; the team chose to keep it encrypted.

## Consequences

- **Easier**: every approved developer opens staging from any device with a trusted certificate, no hosts entry and no port. Emailed links work. The WSL2 box loses its staging port-forward unit, and the server opens no staging ports.
- **Harder**: every staging tester needs a tailnet seat, so the free plan's user limit covers staging testers and Grafana viewers together. The policy grants `group:devs` every `tag:k8s` device on 443, so anyone who can open Grafana can open staging and the reverse. Staging needs Flux (which installs the operator) and the OAuth client, so a bootstrap without them reaches staging only by `kubectl port-forward`.
- **Technical debt**: the staging URL depends on the tailnet name and on the device staying `staging`. A second cluster on the tailnet gets `staging-1` and breaks `FRONTEND_ORIGIN`, which is the "one cluster on the tailnet at a time" rule from ADR-008. Changing the tailnet means re-storing `FRONTEND_ORIGIN`.
