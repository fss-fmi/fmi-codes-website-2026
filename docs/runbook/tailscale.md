# Tailscale

Grafana and staging are reached only over the `fss-fmi` tailnet, through the Tailscale
operator in the cluster ([ADR-008](../adr/008-grafana-over-tailscale.md),
[ADR-009](../adr/009-staging-over-tailscale.md)).

## Access Grafana and staging

Both are reachable **only over the `fss-fmi` tailnet**, at `https://grafana.<tailnet>.ts.net`
and `https://staging.<tailnet>.ts.net`. The exact addresses are the Ingresses' ADDRESS:

```bash
kubectl -n monitoring get ingress grafana
kubectl -n ingress-nginx-staging get ingress staging
```

The Tailscale operator serves each Ingress through a proxy pod that joins the tailnet as a
`tag:k8s` device and gets its own certificate. Nothing about either is reachable from the
internet or the LAN, and no hosts entry or port forward is needed. To open one: have the
Tailscale app running and signed in to the `fss-fmi` tailnet, then browse to the address. With
the app off the name doesn't resolve.

**Grafana's** proxy goes straight to the `kps-grafana` Service; it never touches ingress-nginx,
so Grafana stays up when an app env's ingress is broken or not bootstrapped. So the app's strict
`security-headers` CSP never reaches it, and Grafana's own CSP is left at its default (off). Log
in with your own Grafana account ([Add a developer](#add-or-remove-a-developer)) or, for
administration, the admin user and password from the env's SOPS secret
(`sops --decrypt infra/k8s/secrets/grafana-secret.enc.yaml`). Anonymous access and sign-up are
**disabled** in the chart values.

**Staging's** proxy goes to the `ingress-nginx-staging` controller, so a staging request takes
prod's path through nginx, headers and routing included ([ADR-009](../adr/009-staging-over-tailscale.md)).
The app's own login applies; the tailnet only decides who reaches it. Staging's `FRONTEND_ORIGIN`
(the base of password-reset and verification links, and the CORS origin) is this address, kept
in staging's SOPS app secret so the tailnet name never sits in the repo in plain text. If the
address changes (a new tailnet, or the device joined as `staging-1`), store the new one:

```bash
ENV=staging bash infra/k8s/scripts/rotate-secret.sh FRONTEND_ORIGIN   # paste https://staging.<tailnet>.ts.net
```

Operators with cluster access can skip Tailscale with a one-off port-forward:

```bash
kubectl -n monitoring port-forward svc/kps-grafana 3000:80                                 # http://localhost:3000
kubectl -n ingress-nginx-staging port-forward svc/ingress-nginx-staging-controller 8080:80 # http://localhost:8080
```

## One Tailscale client for every cluster

Every cluster, prod's included, uses **staging's** Tailscale OAuth client. There is one
`tailscale-oauth.enc.yaml`, in `overlays/staging/secrets/`, and no prod copy.
`deploy-observability.sh`, `tailscale-oauth.sh`, `rotate-secret.sh --tailscale` and the
bootstrap pre-flight read it whatever `ENV` is, and label `tailscale/operator-oauth` as
`staging`. Grafana's admin secret and the Slack webhooks still follow `ENV`. Why:
[ADR-011](../adr/011-one-tailscale-client-staging.md).

!!! warning "A machine that runs prod needs the staging age key"

    Staging's Tailscale file is encrypted to the staging key, so a prod machine needs that key
    as well as prod's. `bootstrap.sh --env prod --with-flux` asks for it (from
    `SOPS_AGE_KEY_STAGING` or a hidden prompt). Without it, Enter at the prompt or a run with no
    terminal, prod still deploys, but `deploy-observability.sh` skips the Tailscale client with
    a warning, leaves any live `operator-oauth` as it is, and Grafana and staging stay off the
    tailnet until the key is added and the script runs again. A machine that runs only prod
    would hold the staging key just for this, so revisit ADR-011 before setting one up.

## Tailscale setup (once per tailnet)

Done by an **owner of the `fss-fmi` GitHub org**, in the Tailscale admin console. Only the last
two steps touch the repo.

1. **Create the tailnet.** At tailscale.com choose **Sign up with GitHub**, authorize Tailscale
   for the org and pick `fss-fmi` on the "Select a tailnet" page. The creator becomes the
   tailnet's Owner. A GitHub org gets exactly one tailnet, and its identity provider can never be
   changed later.
2. **DNS page:** turn on **MagicDNS** and **HTTPS Certificates**. Without them the Ingress gets
   no name or certificate.
3. **Users → User management:** make sure **user approval** is on (the default for new
   tailnets). Any member of the GitHub org can ask to join; nobody reaches a device until an
   admin approves them.
4. **Access controls:** replace the default policy, which lets every device reach every other
   device, with the [policy file](#tailnet-policy-file) below.
5. **Create an OAuth client** for the operator with the scopes **General → Services** (read and
   write), **Devices → Core** (read and write) and **Keys → Auth Keys** (read and write), and the
   tag **`tag:k8s-operator`**. Make one client per cluster (dev box, server) so each can be
   revoked on its own; only the cluster on the tailnet holds one at a time
   ([handover](#move-grafana-and-staging-to-another-cluster)). Save the client ID and secret in
   the password manager only.
6. **Store it in staging's SOPS file**, whatever env the cluster runs
   ([One Tailscale client for every cluster](#one-tailscale-client-for-every-cluster)), on a
   machine that holds the staging age key. `bootstrap.sh` asks for it in its pre-flight. On an
   already running cluster:

   ```bash
   bash infra/k8s/scripts/tailscale-oauth.sh set                   # ID, then secret; hidden, typed twice
   ENV=prod bash infra/k8s/scripts/deploy-observability.sh         # the cluster's env; applies it and checks the address
   ```

   The values never touch argv, history or a temp file, and a swapped ID and secret is
   refused. Commit `infra/k8s/overlays/staging/secrets/tailscale-oauth.enc.yaml`. Replacing
   the client later is a [rotation](secrets.md#tailscale-oauth-client).

7. **Verify.** `kubectl -n tailscale get pods` shows the operator Running, the admin console's
   Machines page lists `fmi-codes-operator`, a `grafana` proxy and, on a cluster that runs
   staging, a `staging` proxy (all tagged), and `kubectl -n monitoring get ingress grafana` and
   `kubectl -n ingress-nginx-staging get ingress staging` show their `ts.net` addresses. Open
   them from a tailnet device, then confirm the same addresses do **not** load with the
   Tailscale app off. If a name resolves but the page hangs on a WSL2 dev box, the pod network is
   running at a low MTU (see the WSL2 eth0 note in [Phase 1](index.md#1--tools--cluster)).

The person hosting the server needs no Tailscale or GitHub account: the cluster joins through
the OAuth client, not as a person.

## Tailnet policy file

The reference copy. The live one is edited in the admin console (Access controls); keep this
block in sync when it changes.

```js
{
  // Who may open Grafana and staging. Copy each login exactly as the Users page shows it
  // (GitHub logins look like name@github).
  "groups": {
    "group:devs": ["<github-login>@github"],
  },
  "tagOwners": {
    "tag:k8s-operator": ["autogroup:admin"],
    "tag:k8s": ["tag:k8s-operator"],
  },
  // Devs reach the cluster's proxies on HTTPS only. No rule has a tag:k8s source, so the
  // cluster (or anyone with root on its host) can't open a connection to any other device.
  "grants": [{ "src": ["group:devs"], "dst": ["tag:k8s"], "ip": ["tcp:443"] }],
}
```

Root on the host can read the operator's OAuth secret and act as `tag:k8s`. With this policy
that buys nothing: it can add more `tag:k8s` devices, and those can't reach anyone either.

The grant covers every `tag:k8s` device, so anyone in `group:devs` can open both Grafana and
staging. Splitting them would take a tag per proxy; with a handful of developers who need both,
one group is enough.

## Add or remove a developer

**Add:** the developer installs the Tailscale app and signs in with GitHub, choosing the
`fss-fmi` tailnet (someone outside the org needs an invite link from Users → Invite external
users). An admin approves them on the Users page and adds their login to `group:devs` in the
policy file, which is all staging needs. For Grafana, also create them an account with the
**Viewer** role (Grafana → Administration → Users). Every developer takes a tailnet seat, so the
free plan's user cap counts staging testers and Grafana viewers together.

**Remove:** remove them on the Users page (their devices go with them), take them out of
`group:devs` and delete their Grafana account. Do it by hand when someone leaves the GitHub org;
Tailscale doesn't document that leaving the org removes tailnet access.

## Move Grafana and staging to another cluster

**Rule: one cluster on the tailnet at a time.** Device names are unique in a tailnet, so a
second cluster's proxies would join as `grafana-1` and `staging-1`, and the `ts.net` addresses
would keep pointing at whichever cluster got there first. For staging that also breaks
`FRONTEND_ORIGIN`, which names `staging`. Only the cluster whose SOPS file holds a **valid**
OAuth client can join, so a handover means: the old cluster gives its client up, the new one
gets its own. Use it when moving to a new server, when replacing the dev box, or when a dev box
hands Grafana and staging to the server for good.

Order matters: steps 1 and 2 must be finished before the new cluster deploys.

1. **On the old cluster, if it still runs** (skip if it is gone), whatever env it ran:

   ```bash
   bash infra/k8s/scripts/tailscale-oauth.sh release
   ```

   It stops the operator, deletes `operator-oauth`, the proxy StatefulSets and their tailnet
   state, scales the operator back to one replica that waits idle for a Secret that never comes,
   and empties staging's `tailscale-oauth.enc.yaml`. It refuses if the running Secret is not
   labelled `staging`, since it then didn't come from that file. **Commit the emptied file**
   (through a PR), or a later
   `deploy-observability.sh` would re-apply a revoked client. The rest of the old cluster keeps
   running; its monitoring stack is still reachable by port-forward.

2. **Tailscale admin console** (a tailnet admin):
   - Settings → OAuth clients (or Trust credentials): **revoke the old cluster's client**.
   - Machines: **delete the old `grafana`, `staging` and `fmi-codes-operator` devices** (they
     may carry a `-N` suffix). This logs them out at once and frees the names.

3. **Admin console:** create the new cluster's OAuth client (scopes and tag as in
   [Tailscale setup](#tailscale-setup-once-per-tailnet), step 5). Password manager only.

4. **On the new cluster:** run `./bootstrap.sh --env <env> --with-flux`. When the pre-flight
   asks whether this cluster is taking over, answer **y**; it shows steps 1 to 3 again, waits
   for Enter and then asks for the new client. (If step 1's emptied file is already in this
   checkout, it asks for the client straight away.) A prod bootstrap asks the same, because the
   client lives in staging's file there too. On a cluster that is already bootstrapped instead:
   `bash infra/k8s/scripts/tailscale-oauth.sh set`, then
   `ENV=<env> bash infra/k8s/scripts/deploy-observability.sh`. Commit the encrypted file.

5. **Verify.** `deploy-observability.sh` waits for the addresses and prints
   `Grafana is on the tailnet: https://grafana.<tailnet>.ts.net` (and the same for staging when
   the cluster runs it). The admin console lists only the new devices. Open the addresses from a
   tailnet device. Same tailnet, same names, so staging's `FRONTEND_ORIGIN` stays right.

**If the new cluster got `grafana-1` or `staging-1`** (step 2 was skipped or came too late):
finish steps 1 and 2 for the old cluster, then make the new cluster's proxies register again and
delete its stale devices on the Machines page:

```bash
kubectl -n tailscale delete statefulset,secret -l tailscale.com/managed=true   # the operator recreates it
```

Grafana's dashboards and users live on the old cluster's PVC and do not move. Recreate the
developers' Viewer accounts on the new one ([Add or remove a developer](#add-or-remove-a-developer)).

## Troubleshooting: Grafana or staging doesn't load over Tailscale

Work from your device towards the app; stop at the first step that fails. The commands use
Grafana's names; for staging read `ingress-nginx-staging` / `staging` for the Ingress,
`ts-staging-…-0` for the proxy pod and the controller for the Service (step 4 below).

1. **Your device.** `tailscale status` lists `grafana` (with the policy above you see only
   `tag:k8s` devices), `tailscale dns status` says MagicDNS is enabled, and the name resolves to
   that device's `100.x` address. Use `https://`: plain `http://` (port 80) is blocked by the
   policy and just hangs.
2. **The proxy.** `kubectl -n tailscale get pods` shows `operator` and `ts-grafana-…-0`
   Running; `kubectl -n monitoring get ingress grafana` shows an ADDRESS. No address: run
   `kubectl -n monitoring describe ingress grafana` (`no valid backends` means the Service name
   in `grafana-ingress.yaml` doesn't exist) and read the operator log
   (`kubectl -n tailscale logs deploy/operator`).
3. **Certificate and serve config.** The proxy log
   (`kubectl -n tailscale logs ts-grafana-…-0 -c tailscale`) shows `got cert`, and
   `kubectl -n tailscale exec ts-grafana-…-0 -c tailscale -- tailscale serve status` proxies to
   the Grafana Service.
4. **Proxy to Grafana.**
   `kubectl -n tailscale exec ts-grafana-…-0 -c tailscale -- wget -qO- -T 5 http://kps-grafana.monitoring.svc.cluster.local/api/health`
   returns `"database": "ok"`. For staging:
   `kubectl -n tailscale exec ts-staging-…-0 -c tailscale -- wget -qO- -T 5 http://ingress-nginx-staging-controller.ingress-nginx-staging.svc.cluster.local/api/health`
   returns `{"status":"ok"}`. A `308` redirect loop instead means the staging nginx Ingress
   has TLS or `ssl-redirect` back on ([Phase 4](index.md#4--ingress)).
5. **Policy.** `Drop: … no rules matched` lines in the proxy log for your `100.x` address on
   port 443 mean your login is missing from `group:devs`. Drops on port 80 or 137 are expected.
6. **TLS hangs on a WSL2 dev box.** TCP connects but the TLS handshake stalls and the proxy
   logs `TLS handshake error … EOF`: `eth0` or the pod network is running at a low MTU. With `eth0`
   low and `cni0` at 1450, only `eth0` needs fixing, so don't rebuild the pod network: check the
   `wsl-eth0-mtu` service. Cause, checks and fix are in the WSL2 eth0 note in
   [Phase 1](index.md#1--tools--cluster).

## Tear down the tailnet

Only the Owner can, under **Settings → General → Delete tailnet**. That permanently deletes its
users and devices (logs and backups can linger up to 60 days). Then also:

- remove `fmi-codes-tailscale`, the Grafana Ingress and `fmi-codes-staging-tailnet` from git,
  or the operator keeps retrying with a dead client and its Kustomization stays red. Staging
  then needs another way in (a port-forward, or a new access layer);
- revoke Tailscale's access on GitHub (org settings → Third-party access, and each user's
  Settings → Applications → Authorized OAuth Apps), because deleting the tailnet doesn't.

Tailscale doesn't document whether the org can create a new tailnet after deleting one; ask
their support first if you plan to start over.
