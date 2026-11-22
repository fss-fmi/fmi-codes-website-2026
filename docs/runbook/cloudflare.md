# Cloudflare Tunnel

Prod is reached only through a Cloudflare Tunnel that `cloudflared` in the `fmi-codes`
namespace dials out to; why is in [ADR-017](../adr/017-prod-through-cloudflare-tunnel.md).

```
visitor → Cloudflare (TLS, https://fmicodes.com) → cloudflared (fmi-codes, 2 pods) → ingress-nginx-controller:80 (HTTP) → app
```

## Serving the tunnel

Serving the tunnel is opt-in: `SERVE_PROD_TUNNEL=true`. Every cluster that holds the
tunnel's credentials becomes a connector of the one prod tunnel, and Cloudflare splits visitors
between them: two prods with two databases. So only with the flag does `deploy-ingress.sh` apply the
credentials (`secrets/cloudflared-tunnel.enc.yaml`, with the prod age key) and wait for
`cloudflared` to be ready, which means connected: a pod passes readiness (`/ready`) only while
it holds a connection to Cloudflare. Set it only on the one cluster that runs prod
([Move prod to another cluster](#move-prod-to-another-cluster)). Without it, Flux still runs
`cloudflared`, but its pods wait for the missing Secret, `fmicodes.com` never reaches that
cluster, and the script prints how to reach prod there with a port-forward.
`CloudflareTunnelDown` fires only where the Secret exists, so such a cluster doesn't report the
real site down; the stock warnings for the waiting pods (`KubePodNotReady`,
`KubeDeploymentReplicasMismatch`, `KubeDeploymentRolloutStuck`) still post, titled `prod`, and
repeat every 12 hours while that prod runs. A cluster that already holds
the Secret from an earlier run keeps serving, and the script warns. The tunnel itself, its DNS
record and the Cloudflare settings are made once ([Set up the tunnel](#set-up-the-tunnel)).

Cloudflare terminates TLS and sends http to https at its edge, so the Ingress has no TLS block
and `ssl-redirect` is off. Cloudflare puts the visitor's address in `CF-Connecting-IP`, and prod's
controller runs with `enable-real-ip`, `forwarded-for-header: CF-Connecting-IP` and
`proxy-real-ip-cidr: 10.42.0.0/16` (k3s's pod network, `POD_CIDR` in the script). It takes the
header only from a pod, which on prod means `cloudflared`, and passes the address on as the
backend's one `X-Forwarded-For` hop, so every visitor keeps their own rate-limit bucket.
`use-forwarded-headers` stays off: it would also trust a client's `X-Forwarded-Proto` and
`X-Forwarded-Host`. After a deploy, read the client address in the controller's access log: it
must be the visitor's public address, not `10.42.x.x`.

```bash
kubectl -n ingress-nginx logs deploy/ingress-nginx-controller --tail=5
```

A client can't pick its own bucket. Cloudflare replaces any `CF-Connecting-IP` a client sends,
and the controller replaces `X-Forwarded-For`. Check both from outside: after these two requests
the two log lines must both show your real address, not `203.0.113.7`.

```bash
curl -s -o /dev/null -H 'CF-Connecting-IP: 203.0.113.7' https://fmicodes.com/api/health
curl -s -o /dev/null -H 'X-Forwarded-For: 203.0.113.7' https://fmicodes.com/api/health
```

Open prod from the server like from anywhere else, the WSL2 box's Windows browser included:
`https://fmicodes.com` goes through Cloudflare, with no hosts entry. Without the tunnel, or before
its DNS record exists, port-forward the controller:

```bash
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8081:80
curl -H 'Host: fmicodes.com' http://127.0.0.1:8081/api/health
```

## Set up the tunnel

`fmicodes.com` is a zone on Cloudflare's free plan. The repo already holds the tunnel
`fmi-codes-prod`: its ID is in `overlays/prod/ingress/cloudflared-config.yaml` and its encrypted
credentials in `secrets/cloudflared-tunnel.enc.yaml`. A new server needs none of steps 1 to 3,
only the prod age key and `SERVE_PROD_TUNNEL=true`
([Move prod to another cluster](#move-prod-to-another-cluster)). Steps 1 to 3 are for a new tunnel (a fork, or
[replacing leaked credentials](#cloudflare-tunnel-credentials)); steps 4 to 6 are done once per
zone and checked after any change in the Cloudflare dashboard.

1. **Install `cloudflared` and sign in**, on a Linux or WSL shell with a browser at hand. The
   login prints a URL: open it and pick `fmicodes.com`. It writes `~/.cloudflared/cert.pem`, which
   can manage every tunnel and DNS record of the zone, so it stays on that machine and goes once
   step 4 is done.

   ```bash
   curl -fsSL -o /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i /tmp/cloudflared.deb && rm /tmp/cloudflared.deb
   cloudflared tunnel login
   ```

2. **Create the tunnel.** It writes the tunnel's secret to `~/.cloudflared/<tunnel-id>.json` and
   prints the ID.

   ```bash
   cloudflared tunnel create fmi-codes-prod
   ```

3. **Encrypt the credentials into the repo**, from the repo root. Only the encrypted copy lands
   in it; `.sops.yaml` picks the prod key by path. Put the ID in `tunnel:` in
   `cloudflared-config.yaml` and commit both through a PR. Delete the plaintext `.json` once the
   tunnel connects on prod.

   ```bash
   CRED=$(ls ~/.cloudflared/*.json)    # must be exactly one file
   kubectl create secret generic cloudflared-tunnel -n fmi-codes \
     --from-file=credentials.json="$CRED" --dry-run=client -o yaml \
     | sops --encrypt --filename-override infra/k8s/secrets/cloudflared-tunnel.enc.yaml \
         --input-type yaml --output-type yaml /dev/stdin \
     > infra/k8s/secrets/cloudflared-tunnel.enc.yaml
   ```

4. **Point `fmicodes.com` at the tunnel**, once prod's `cloudflared` is ready
   (`kubectl -n fmi-codes get deployment cloudflared` shows `2/2`). First delete any `A`, `AAAA`
   or `CNAME` record for the bare `fmicodes.com` in the dashboard's DNS records; `route dns`
   refuses to replace one. It then adds a proxied `CNAME` to `<tunnel-id>.cfargotunnel.com`. The
   record names the tunnel, not a server, so moving prod never touches DNS.

   ```bash
   cloudflared tunnel route dns fmi-codes-prod fmicodes.com
   ```

5. **`www`.** Add a proxied `CNAME` record `www` → `fmicodes.com`, and a Redirect Rule (the
   dashboard's "Redirect from WWW to root" template does it): requests for `www.fmicodes.com` get a
   301 to `https://fmicodes.com` with the path and query string kept. It answers at the edge; if
   the rule is ever missing, the tunnel's catch-all answers 404.

6. **Dashboard settings.** They live in Cloudflare, not in git:
   - **Always Use HTTPS** on (SSL/TLS, Edge Certificates). It is what sends http to https now.
   - **Rocket Loader**, **Email Address Obfuscation** and Web Analytics' automatic setup off. Each
     injects a script the CSP blocks (`script-src 'self'`, `connect-src 'self'`), which shows up as
     console errors and a broken page.
   - **Bot Fight Mode** off. Its JavaScript challenge answers the SPA's `/api` calls with an HTML
     page instead of JSON.
   - **Caching**: the defaults, with no "Cache Everything" rule. Cloudflare caches static file
     types by their `Cache-Control` (the hashed `/assets/` files are `immutable`, `index.html` is
     `no-cache`, [ADR-015](../adr/015-rolling-surge-rollouts.md)) and caches no HTML or `/api` JSON.

Then check, from any machine:

```bash
curl -sI https://fmicodes.com/api/health      # 200, with the security headers (CSP, HSTS, ...)
curl -sI http://fmicodes.com/x                # 301 to https://fmicodes.com/x
curl -sI https://www.fmicodes.com/x           # 301 to https://fmicodes.com/x
```

Open the site with the browser's console open: no CSP errors. Then run the
[real-address checks](#serving-the-tunnel).

`cloudflared` reads its config only at start. The config is a generated ConfigMap whose name
changes with its content, so a merged routing change rolls the pods by itself. A tunnel with no
ready pod for 3 minutes posts `CloudflareTunnelDown` ([Cluster alerts](alerts.md#cluster-alerts)).

## Move prod to another cluster

**Rule: one cluster runs the prod tunnel at a time.** Every cluster that runs prod's ingress
overlay with the tunnel's credentials registers as a connector of the same tunnel, and Cloudflare
splits visitors between them: two prods with two databases. That is why only a run with
`SERVE_PROD_TUNNEL=true` applies the credentials. Moving prod (to the event server, say) means
stopping the old tunnel first:

1. **On the old cluster**, delete the tunnel's Secret and pods. Flux doesn't manage the Secret, so
   it stays gone, and the new pods wait for it and never connect. Without the Secret
   `CloudflareTunnelDown` stays quiet there; the stock warnings for the waiting pods
   (`KubePodNotReady`, `KubeDeploymentReplicasMismatch`) post until its prod is torn down.
   Never run `deploy-ingress.sh` with `SERVE_PROD_TUNNEL=true` there again: it applies the
   Secret again.

   ```bash
   kubectl -n fmi-codes delete secret cloudflared-tunnel
   kubectl -n fmi-codes delete pod -l app.kubernetes.io/name=cloudflared
   ```

2. **On the new cluster**, run `SERVE_PROD_TUNNEL=true ./bootstrap.sh --env prod --with-flux`.
   `deploy-ingress.sh` applies the Secret and waits for the tunnel. DNS doesn't change.
3. **Tear down the old cluster's prod** ([Tear down](index.md#tear-down)). The database doesn't move with
   the tunnel: there are no off-site backups, so move it with a `pg_dump` first if it holds data.

## Cloudflare Tunnel credentials

A tunnel's credentials can't be rotated in place, so replace the tunnel. Don't just merge the
new tunnel and move DNS after: the rollout (`maxSurge: 1`, `maxUnavailable: 0`) ends the old
tunnel's last connector seconds after the first new pod is ready, before DNS can follow, and
visitors get Cloudflare's error 1033 in between. A temporary second Deployment,
`cloudflared-next`, serves the new tunnel first, so DNS moves to a tunnel that is already
connected. Run every step from the PR's branch, on a machine with `kubectl` access to prod and
step 1's `cert.pem`:

1. Steps 1 to 3 of [Set up the tunnel](#set-up-the-tunnel) with a new name
   (`fmi-codes-prod-2`). Open the PR, but don't merge it yet.
2. **Start the bridge**: the new credentials as `cloudflared-tunnel-next`, the PR's config and a
   copy of the Deployment that reads both. None of it is in git, so Flux leaves it alone. Wait
   until it is ready, which means connected to the new tunnel:

   ```bash
   sops --decrypt infra/k8s/secrets/cloudflared-tunnel.enc.yaml \
     | sed -E 's/^( +name: )cloudflared-tunnel$/\1cloudflared-tunnel-next/' | kubectl apply -f -
   kubectl -n fmi-codes create configmap cloudflared-next --dry-run=client -o yaml \
     --from-file=config.yaml=infra/k8s/overlays/prod/ingress/cloudflared-config.yaml \
     | kubectl apply -f -
   sed -E -e 's/^( +(name|app\.kubernetes\.io\/name): )cloudflared$/\1cloudflared-next/' \
       -e 's/^( +secretName: )cloudflared-tunnel$/\1cloudflared-tunnel-next/' \
       -e 's/^( +app\.kubernetes\.io\/managed-by: )flux$/\1kubectl/' \
       infra/k8s/overlays/prod/ingress/cloudflared.yaml | kubectl apply -f -
   kubectl -n fmi-codes rollout status deployment/cloudflared-next
   ```

3. **Move the DNS record.** Visitors now reach the bridge. The old pods still hold the old
   tunnel, which gets no traffic:

   ```bash
   cloudflared tunnel route dns --overwrite-dns fmi-codes-prod-2 fmicodes.com
   ```

4. **Apply the new credentials under the real name, then merge the PR.** Until the merge, the
   running pods keep the old credentials they started with, and one that restarts reads the new
   ones with the old tunnel ID and stays unready, which no longer matters: the bridge serves.
   After the merge the config's generated name changes, so Flux rolls `cloudflared` onto the new
   tunnel next to the bridge:

   ```bash
   sops --decrypt infra/k8s/secrets/cloudflared-tunnel.enc.yaml | kubectl apply -f -
   # merge the PR, then:
   flux reconcile kustomization fmi-codes-ingress -n flux-system --with-source
   kubectl -n fmi-codes rollout status deployment/cloudflared
   ```

5. **Remove the bridge and delete the old tunnel**, which ends the leaked credentials.
   `tunnel delete` refuses while anything is still connected to the old tunnel:

   ```bash
   kubectl -n fmi-codes delete deployment cloudflared-next
   kubectl -n fmi-codes delete configmap cloudflared-next
   kubectl -n fmi-codes delete secret cloudflared-tunnel-next
   cloudflared tunnel delete fmi-codes-prod
   ```
