# ADR-017: Prod served only through a Cloudflare Tunnel run inside the cluster

**Status**: accepted.

## Context

`fmicodes.com` was bought and moved to Cloudflare's nameservers, proxied, with nothing behind it (#271). The repo still assumed the old way in: a public A record pointing at the server, prod's ingress-nginx bound to the host's ports 80 and 443 through k3s servicelb with `externalTrafficPolicy: Local` (so the backend saw each visitor's address), and cert-manager issuing a Let's Encrypt certificate over HTTP-01, which needs port 80 open to the internet.

That only works on a machine with a public address and a router forwarding both ports to it. Prod runs on one server now and moves to the event server for the hackathon, which may be Linux or a Mac running k3s in a Linux VM. Each sits behind NAT, the forwarding chain differs on every OS (router to Windows to WSL, router to a Mac to its VM), and venue and university networks often give no public address at all.

Cloudflare also offers git-connected builds (Workers and Pages) that deploy on every push to `main`. They can't run the Flask backend or Postgres, and putting only the SPA there would ship the frontend to prod on every merge, past the promote gate ([ADR-006](006-self-hosted-k3s-pull-based-gitops.md)).

## Decision

- **A Cloudflare Tunnel is the only way into prod.** `cloudflared` runs as a 2-replica Deployment in `fmi-codes` (`overlays/prod/ingress/cloudflared.yaml`), reconciled by Flux with the rest of prod's edge (`fmi-codes-ingress`). It only dials out to Cloudflare, so it needs no open port, no public address and nothing on the host, and the same manifests run on every OS the cluster sits on. Prod's release flow doesn't change: Cloudflare serves whatever the cluster runs, and prod still moves only when a human merges the promote PR.
- **The tunnel's routing lives in git.** It is a locally managed tunnel: its rules (`fmicodes.com` to `ingress-nginx-controller.ingress-nginx:80`, then a 404 for any other host) are a ConfigMap, so a routing change goes through a PR and Flux reverts drift. The credentials file is SOPS-encrypted in `secrets/cloudflared-tunnel.enc.yaml` and applied by `deploy-ingress.sh` only with `SERVE_PROD_TUNNEL=true`: holding the prod age key is not enough, since a dev box that brings up prod would otherwise join the real tunnel. Flux runs `cloudflared` on every cluster with prod, but its pods connect only where the Secret exists.
- **Cloudflare serves the certificate; cert-manager leaves prod.** Browsers get Cloudflare's edge certificate, renewed by Cloudflare. `cloudflared` talks plain HTTP to ingress-nginx over the pod network on the same node. The `Certificate`, the `ClusterIssuer` and the Ingress `tls:` block are gone, and `ssl-redirect` is off: ingress-nginx only redirects for a host it holds a certificate for, and Cloudflare's "Always Use HTTPS" sends http to https at the edge.
- **Prod's controller is a `ClusterIP` Service, like staging's.** Nothing reaches it except pods on the node, which is what makes the next point safe.
- **The visitor's address comes from `CF-Connecting-IP`, trusted only from the pod network.** Cloudflare sets that header to the visitor's address. The controller runs with `enable-real-ip`, `forwarded-for-header: CF-Connecting-IP` and `proxy-real-ip-cidr` set to k3s's pod CIDR (`10.42.0.0/16`), so nginx takes the header only from `cloudflared`'s pods and sets the backend's `X-Forwarded-For` to that one address, which is the hop `ProxyFix(x_for=1)` reads. The per-address limits of [ADR-014](014-rate-limits-keyed-on-account-and-user.md) keep seeing one bucket per visitor. `use-forwarded-headers` stays off, since it would also trust a client's `X-Forwarded-Proto` and `X-Forwarded-Host`.
- **`www.fmicodes.com`** is a proxied DNS record with a Cloudflare Redirect Rule (301 to `https://fmicodes.com`, path kept). It never reaches the cluster; the tunnel's 404 rule answers if the rule is ever missing.
- **`CloudflareTunnelDown`** (critical, after 3 min) fires when prod's `cloudflared` Deployment has no available replica on a cluster that holds the tunnel's Secret (`kube_secret_info`), so a cluster that runs prod without serving it never reports the real site down. A pod is ready only while it holds a connection to Cloudflare (`/ready`), so the rule reads readiness through kube-state-metrics. `cloudflared`'s own `cloudflared_tunnel_ha_connections` gauge was tried and turned down: it stayed at 1 for as long as the server kept rejecting the tunnel. A cluster without prod, or without the Secret, never fires it.

Considered and turned down:

- **Forwarding 80 and 443 to the server, with Cloudflare proxying in front.** It needs a public address, a different forwarding chain per OS and router access at the venue, and it exposes the server's address, which lets anyone skip Cloudflare.
- **`cloudflared` as a host service** (systemd, launchd). Visitors see the same thing, but the setup differs per OS and lives outside git and the cluster's alerts.
- **A remotely managed tunnel** (rules in the Cloudflare dashboard, one token). Quicker to set up, but routing changes skip review and git.
- **Keeping Let's Encrypt** through DNS-01 with a Cloudflare API token, or a Cloudflare Origin CA certificate. Either encrypts the hop inside the node, which never leaves the machine, at the cost of a token or a long-lived key to keep and a renewal or rotation to watch.

## Consequences

- **Easier**: prod comes up on any machine with outbound internet, with no DNS change per server, no router setup and no certificate to renew. The server's address stays hidden. WSL2's changing NAT address no longer matters, so the WSL forward services and the Windows hosts entry for prod are gone.
- **Harder**: Cloudflare is now in prod's path, and some of its settings live in its dashboard, outside git: the DNS records, the `www` redirect, "Always Use HTTPS", and the features that inject scripts the CSP blocks or challenge the SPA's API calls, which must stay off ([runbook](../runbook.md#cloudflare-tunnel)).
- **Limit**: only one cluster may run the prod tunnel at a time. Two clusters with the same credentials both register as connectors, and Cloudflare splits visitors between two prods with two databases. The `SERVE_PROD_TUNNEL` opt-in keeps a second cluster from joining by accident, and moving prod means stopping the old tunnel first, like the one-cluster-on-the-tailnet rule ([ADR-008](008-grafana-over-tailscale.md)).
- **Limit**: the tunnel doesn't keep the server up. A stopped server shows Cloudflare's error page, and since every alert runs inside the cluster, a dead server posts nothing.
- **Limit**: `CloudflareTunnelDown` takes a missing Secret to mean "this cluster doesn't serve", so a Secret deleted by mistake on the live cluster pages only the stock pod warnings, and a prod that doesn't serve posts those warnings every 12 hours. Telling the two apart needs a check from outside the cluster ([#282](https://github.com/fss-fmi/fmi-codes-website-2026/issues/282)).
- **Limit**: any pod on the node can reach the controller and set its own `CF-Connecting-IP`. The pod network is the trust boundary, as it already is for the backend's Service.
