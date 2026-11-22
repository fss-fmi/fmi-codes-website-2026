# Cluster alerts

Failures inside the cluster are posted to Slack by two senders
([ADR-010](../adr/010-cluster-alerts-to-slack.md)). What happens on GitHub up to a merge is
covered separately, by the [Slack PR feed](../github-automation.md#slack-pr-feed) and [Slack CI alerts](../github-automation.md#slack-ci-alerts).

There are two channels, `#cluster-alerts-prod` and `#cluster-alerts-staging`, split by who has
to act:

| Goes to                                                                      | On the prod server        | On a staging-only box     |
| ---------------------------------------------------------------------------- | ------------------------- | ------------------------- |
| the `fmi-codes-staging` namespace, staging's Flux objects, image automation  | `#cluster-alerts-staging` | `#cluster-alerts-staging` |
| everything else: `fmi-codes`, the node, monitoring, Flux core, Helm releases | `#cluster-alerts-prod`    | `#cluster-alerts-staging` |

Alerts shared by both envs go to the channel of the env the cluster serves: on a shared node a
node problem is a prod problem. The `alertmanager-slack` Secret holds two webhooks: `cluster_url` for
that channel and `staging_url` for the staging one. On a staging-only box both hold the staging
webhook. Flux picks its two sets by the `fmi-codes/alerts: cluster | staging` label on each
Kustomization in `flux/source.yaml` and `flux/self.yaml`; a new Kustomization needs that label,
or its errors are not posted. Flux doesn't re-apply `self.yaml` by itself, so on a cluster
bootstrapped before the label existed run `kubectl apply -f infra/k8s/flux/self.yaml` once.

- **Alertmanager** (part of `kps`) posts Prometheus alerts about pods, Jobs, rollouts, the node,
  volumes, scrape targets and the monitoring stack itself. One message per alert name and
  namespace, a `✅ Resolved` message when it clears, and a reminder every 12 hours while it
  keeps firing. The title names the env: `prod` (`fmi-codes`), `staging` (`fmi-codes-staging`)
  or `cluster` for everything else (node alerts carry the exporter's `monitoring` namespace, so
  the namespace alone can't tell them from the monitoring stack's own); the text names the
  namespace. The title links to this page. A crash loop inhibits the `KubePodNotReady` of the
  same pod and the replica and rollout alerts of its namespace, so one incident posts once.
  `CloudflareTunnelDown` does the same for `cloudflared`'s own pod and Deployment alerts.
- **Flux** (`flux/notifications.yaml`) posts reconcile errors: a Kustomization that won't apply
  or fails its health check after a merge, a failed HelmRelease, a source or image scan that
  can't fetch, image automation that can't push its bump. Info events (successful applies,
  "dependency not ready") are not posted. Once the failing object is healthy again, the
  Flux Relay replies "recovered" in the error's thread ([Recovery replies](#recovery-replies)).

The alerts most likely to matter:

| Alert                                                                                             | Fires when                                                                                                                           | After   |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------- |
| `KubePodCrashLooping`                                                                             | a container is in CrashLoopBackOff                                                                                                   | 5m      |
| `KubeInitContainerCrashLooping`                                                                   | an initContainer is, like the backend's `migrate` step when Postgres stays unreachable (the step itself no longer posts that)        | 5m      |
| `ContainerOOMKilled`                                                                              | a container was restarted after running out of memory                                                                                | at once |
| `KubePodNotReady`                                                                                 | a pod stays Pending, Unknown or Failed: ImagePullBackOff, unschedulable, stuck in Init                                               | 10m     |
| `KubeContainerWaiting`                                                                            | a container stays waiting for any other reason                                                                                       | 1h      |
| `KubeDeploymentRolloutStuck`, `KubeDeploymentReplicasMismatch`, `KubeStatefulSetReplicasMismatch` | a rollout stops progressing or replicas stay unavailable                                                                             | 15m     |
| `KubeJobFailed`                                                                                   | a Job failed (the manual `db-migrate` Job also posts its own result)                                                                 | 1m      |
| `KubePersistentVolumeFillingUp`                                                                   | a PVC (Postgres, Prometheus, Grafana) is almost full, or will be within 4 days                                                       | 1m / 1h |
| `KubeNodeNotReady`                                                                                | the node is not ready                                                                                                                | 15m     |
| `TargetDown`                                                                                      | a scrape target, like the backend's `/metrics`, is unreachable                                                                       | 10m     |
| `BackendHighErrorRate`                                                                            | over 5% of backend requests in a namespace return a 5xx (health probes not counted)                                                  | 10m     |
| `CloudflareTunnelDown` (critical)                                                                 | prod's `cloudflared` has no ready pod on the cluster that holds the tunnel's Secret, so `fmicodes.com` shows Cloudflare's error page | 3m      |

The custom rules (`additionalPrometheusRulesMap` in `base/observability/helmrelease.yaml`) have
promtool unit tests in `base/observability/tests/`. CI runs them; locally, with Docker running:
`bash infra/k8s/scripts/test-prometheus-rules.sh`.

Kept quiet on purpose:

- `Watchdog` (always fires, by design), `InfoInhibitor` and every `severity=info` alert go to a
  `null` receiver.
- k3s runs the controller manager, scheduler, proxy and etcd inside its own process and exposes
  no endpoints for them, so those monitors and their rules are off. They only ever produced
  permanent "down" alerts here.
- Flux errors containing `namespaces "fmi-codes" not found` (or `"fmi-codes-staging"`). Every
  cluster gets both envs' Kustomizations, so on a cluster that runs one env the other's fail on
  every retry.
- Flux errors that are network blips (`dial tcp`, `i/o timeout`, `no such host`,
  `TLS handshake timeout`, `connection reset by peer`): a GitHub, Docker Hub or chart repo
  outage would repost every few minutes until it ends. Auth errors, like a revoked deploy key,
  still post.
- Every pod restarts on a WSL boot, but that is neither a CrashLoopBackOff nor an OOM kill, so
  it posts nothing. Over the 14 days of history checked when this was set up, only the alerts
  silenced above ever fired.

Posts that look like noise but aren't:

- **Tailscale not set up yet.** Until the OAuth client exists, the operator pod waits for its
  `operator-oauth` Secret, so `KubePodNotReady` and `KubeDeploymentReplicasMismatch` for
  namespace `tailscale` post every 12 hours. Grafana and staging have no tailnet address until
  then, so it is a real gap; it stops once [Tailscale setup](tailscale.md#tailscale-setup-once-per-tailnet)
  is done.
- **One webhook key set, the other empty.** Every send to the empty one fails, and
  `AlertmanagerFailedToSendAlerts` posts to the cluster's channel. Set both keys. With both
  empty nothing is posted at all.

Not covered:

- **The whole cluster down.** Nothing inside a cluster can report its own death. A dead
  cluster also takes the site down, which is noticed anyway, so there is no external dead
  man's switch. `CloudflareTunnelDown` runs in the same cluster, so a dead server posts it
  neither; visitors get Cloudflare's tunnel error page. An outside check is
  [#282](https://github.com/fss-fmi/fmi-codes-website-2026/issues/282).
- **The tunnel's Secret lost on the live cluster.** `CloudflareTunnelDown` fires only where the
  `cloudflared-tunnel` Secret exists, so it reads a Secret deleted by mistake (the
  [Move prod](cloudflare.md#move-prod-to-another-cluster) or teardown commands run on the wrong cluster) as
  "not serving". The site goes down at the next `cloudflared` restart and only the stock
  `KubePodNotReady` warning posts, after 10 minutes. Inside the cluster this can't be told
  apart from a deliberate stop ([#282](https://github.com/fss-fmi/fmi-codes-website-2026/issues/282)).
- **5xx answers Flask never produced.** `BackendHighErrorRate` counts only responses the
  backend finished. A 502 or 504 from ingress-nginx (a worker stuck until Gunicorn's 120s
  timeout) or a 503 with no ready pod is not in it. Partly covered elsewhere: when every
  worker hangs, the scrape fails and `TargetDown` fires; with no ready pod,
  `KubePodNotReady` and the replica alerts fire. The ingress controllers export no metrics
  today, so there is no user-side 5xx rate. What to do about it is open for debate in
  [issue #192](https://github.com/fss-fmi/fmi-codes-website-2026/issues/192).

## Setup

1. In Slack, create both channels. In the Slack app that holds the other webhooks, add an
   incoming webhook for each (**Incoming Webhooks → Add New Webhook**).
2. Store them (hidden prompt, typed twice; anything that isn't a
   `https://hooks.slack.com/services/…` URL is refused). Each env's file needs both keys:

   ```bash
   # prod's file (the server): cluster_url = the prod webhook, staging_url = the staging webhook
   ENV=prod bash infra/k8s/scripts/rotate-secret.sh --alertmanager cluster_url
   ENV=prod bash infra/k8s/scripts/rotate-secret.sh --alertmanager staging_url
   # staging's file (a staging-only box): both = the staging webhook
   ENV=staging bash infra/k8s/scripts/rotate-secret.sh --alertmanager cluster_url
   ENV=staging bash infra/k8s/scripts/rotate-secret.sh --alertmanager staging_url
   ```

   Each run writes that key in the env's `alertmanager-slack.enc.yaml`, applies
   `monitoring/alertmanager-slack` and copies the webhooks for Flux: `cluster_url` to
   `flux-system/flux-slack`, `staging_url` to `flux-system/flux-slack-staging` (key `address`;
   an empty key deletes its copy). It reminds you when the other key is still empty.
   Like the other cluster-wide Secrets, it refuses to overwrite the other env's copy on a
   running cluster, so run each env's pair against its own cluster. For an env whose cluster
   doesn't exist yet, fill its file without touching any cluster with
   `sops infra/k8s/secrets/alertmanager-slack.enc.yaml` (opens it decrypted in `$EDITOR` and
   re-encrypts on save); `deploy-observability.sh` applies it at bootstrap. Nothing restarts:
   Alertmanager reads the file on every send, Flux reads its Secret on every event, and the
   kubelet updates the mounted Secret within a minute or two.

3. Commit the changed `alertmanager-slack.enc.yaml` files.

The Alertmanager pod mounts `alertmanager-slack`, so without the Secret it stays in
`ContainerCreating` and nothing posts, including about itself. The operator creates that pod,
not Helm, so don't expect the `kps` release to fail; check the pod:
`kubectl -n monitoring get pods -l app.kubernetes.io/name=alertmanager`. `deploy-observability.sh`
applies the Secret, empty or not, so run it once on an existing cluster before a change that
turns Alertmanager on reaches it. On a fresh cluster the pod starts by itself once the script
has run.

## Adding prod to a staging-only box

The usual order on one machine is staging first
(`./bootstrap.sh`), then prod next to it (`ENV=prod bash bootstrap.sh`, which the staging run
suggests; with `SERVE_PROD_TUNNEL=true` only if this box is the one that serves `fmicodes.com`).
That second run sets up prod's namespace, data, app and ingress (steps 1 to 5) and
leaves the cluster-wide Secrets alone, so they still hold staging's copies. With `--with-flux`
its step 7 stops on the env guard instead (`monitoring/grafana-admin holds the staging
credentials`). Either way `cluster_url` is still the staging webhook, so on the now-shared box:

- prod's own alerts (`fmi-codes`: a crash loop, an OOM kill, a full Postgres volume, a failed
  promotion) post to `#cluster-alerts-staging`, titled `· prod`;
- node, monitoring, Flux-core and Helm alerts post there too, although a node problem now
  takes prod down;
- `#cluster-alerts-prod` gets nothing, and nothing warns: the routing can't tell the box
  changed hands.

Nothing about this is wrong in the config; the box now belongs to prod and its Secrets don't
say so yet. Make prod the env this cluster belongs to, right after `ENV=prod bash bootstrap.sh`
(prod alerts from the minutes in between go to the staging channel):

```bash
ALLOW_ENV_SWITCH=true ENV=prod bash infra/k8s/scripts/deploy-observability.sh
```

- `alertmanager-slack` becomes prod's copy (`cluster_url` = the prod webhook, `staging_url` =
  the staging webhook) and both Flux copies follow. Nothing restarts.
- `flux-relay-slack` becomes prod's copy too (`cluster_channel` = the prod channel), so
  recovery replies follow the errors into `#cluster-alerts-prod`. Incidents the relay already
  tracks keep the channel they were posted in.
- `grafana-admin` becomes prod's copy, but Grafana keeps the password it stored on its first
  start. To log in with prod's, run
  `ENV=prod bash infra/k8s/scripts/rotate-secret.sh --grafana admin-password` and enter it
  ([Grafana admin password](secrets.md#grafana-admin-password)).
- `operator-oauth` is re-applied from staging's file, the only one there is, so the operator
  keeps its client and Grafana and staging keep their tailnet addresses
  ([One Tailscale client for every cluster](tailscale.md#one-tailscale-client-for-every-cluster)). If the
  prod bootstrap runs with `--with-flux`, answer `N` when its pre-flight asks whether this
  cluster is taking over from another one: it is the same cluster.

From then on it is a prod cluster: run `deploy-observability.sh` and `rotate-secret.sh
--grafana` / `--alertmanager` with `ENV=prod`. Staging's app secrets still rotate with
`ENV=staging`. Staging's `alertmanager-slack.enc.yaml` isn't used until a staging-only box
exists again. Check with the test below: the scratch-namespace pod posts in
`#cluster-alerts-prod`.

Both scripts print the switch command when they find the mix: the prod bootstrap when the
shared Secrets are still staging's, and `deploy-observability.sh` when it runs with
`ENV=staging` on a cluster that has the `fmi-codes` namespace. The env guard's refusal of
`ENV=prod` points here too.

## Silence an alert

During planned work or while a known issue is being fixed:

```bash
kubectl -n monitoring port-forward svc/kps-alertmanager 9093:9093
# http://localhost:9093 -> New Silence: match alertname (and namespace), pick a duration
```

Alertmanager has no volume, so silences are lost when its pod restarts (every WSL boot). To
mute something for good, change the route or the rule in `base/observability/helmrelease.yaml`.

## Test it

A crash-looping pod should post within about 6 minutes and resolve a few minutes
after it's gone. One in a scratch namespace goes to the cluster's own channel, one in
`fmi-codes-staging` to the staging channel:

```bash
kubectl create namespace alert-test
kubectl -n alert-test run crasher --image=busybox:1.37 -- sh -c 'exit 1'
kubectl -n fmi-codes-staging run alert-test-crasher --image=busybox:1.37 -- sh -c 'exit 1'
# 🚨 Warning: KubePodCrashLooping · cluster        (cluster_url channel)
# 🚨 Warning: KubePodCrashLooping · staging        (staging channel)
kubectl delete namespace alert-test
kubectl -n fmi-codes-staging delete pod alert-test-crasher
# ✅ Resolved: ... for both
```

A Flux error, posted within a minute (`staging` here; `cluster` tests the other channel):

```bash
kubectl apply -f - <<'EOF'
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: alert-test
  namespace: flux-system
  labels:
    fmi-codes/alerts: staging
spec:
  interval: 1m
  sourceRef:
    kind: GitRepository
    name: fmi-codes
  path: ./does-not-exist
  prune: false
EOF
kubectl -n flux-system delete kustomization alert-test
```

With the [Flux Relay](#recovery-replies) set up, deleting it gets a 🗑️ reply in the error's
thread within about 15 seconds.

## Recovery replies

A Flux error stays in the channel, and the **Flux Relay** answers under it once the object is
healthy again ([ADR-012](../adr/012-flux-recovery-replies.md)):

- one reply in the thread of the incident's first error,
  `✅ Recovered <time> · <Ready message>`, with the time shown in each reader's own time zone;
- a ✅ reaction on **every** error post of the incident. Flux reposts a lasting error about
  every 5 minutes (notification-controller drops an identical event only for 5 minutes), so an
  outage of 20 minutes leaves about four posts; all of them read as resolved at a glance;
- `🗑️ … was deleted` instead, if the object is gone (like `alert-test` above).

What an operator needs to know (the design is in [ADR-012](../adr/012-flux-recovery-replies.md)):

- Each Slack Alert in `flux/notifications.yaml` has a `flux-relay` twin with the same sources
  and exclusions, sending the same errors to the relay (`base/flux-relay`, Kustomization
  `fmi-codes-flux-relay`) at `/cluster` or `/staging`. Change both together:
  `tests/test_flux_relay.py` fails if a twin drifts from its Slack Alert.
- The relay claims an error's post within 3 minutes. An error that never reached Slack
  (excluded, or the webhook failed) gets no reply.
- It checks each open incident's `Ready` condition every 15 seconds. An error that never made
  the object unready (a Helm drift, a failed prune) closes after 15 quiet minutes.
- Open incidents live in the ConfigMap `flux-system/flux-relay-state`, so a restart (every WSL
  boot) picks up where it left off.
- Two clusters posting to one channel (the prod server and a staging-only box in
  `#cluster-alerts-staging`) can swap posts only if the same object fails with the same message
  on both within seconds.
- If the relay is down or has no token, errors still post exactly as before; only the reply is
  missing. Without a token it idles and logs once, and errors that arrive meanwhile are dropped
  after 3 minutes.

### Set up the Flux Relay

Once per workspace, then per env file:

1. The Slack app **Flux Relay**, separate from the CI bot so the cluster never holds a token
   that can reach `#pr-updates` or `#actions-notifications`. At
   [api.slack.com/apps](https://api.slack.com/apps): **Create New App → From a manifest**:

   ```yaml
   display_information:
     name: Flux Relay
   features:
     bot_user:
       display_name: Flux Relay
       always_online: false
   oauth_config:
     scopes:
       bot:
         - channels:history
         - chat:write
         - reactions:write
   settings:
     org_deploy_enabled: false
     socket_mode_enabled: false
     token_rotation_enabled: false
   ```

   Add `groups:history` if an alert channel is private. **Install to Workspace**, then
   `/invite @Flux Relay` in both `#cluster-alerts-prod` and `#cluster-alerts-staging`. The bot
   token (`xoxb-…`) is on **OAuth & Permissions**; each channel's ID (`C…`) is at the bottom of
   the channel's **About** tab.

2. Store them (hidden prompt, typed twice; a value of the wrong shape is refused). The channel
   keys mirror the webhook keys: `cluster_channel` is the channel `cluster_url` posts to,
   `staging_channel` is `staging_url`'s:

   ```bash
   # prod's file (the server): cluster_channel = #cluster-alerts-prod
   ENV=prod bash infra/k8s/scripts/rotate-secret.sh --flux-relay bot_token
   ENV=prod bash infra/k8s/scripts/rotate-secret.sh --flux-relay cluster_channel
   ENV=prod bash infra/k8s/scripts/rotate-secret.sh --flux-relay staging_channel
   # staging's file (a staging-only box): both channel keys = #cluster-alerts-staging
   ENV=staging bash infra/k8s/scripts/rotate-secret.sh --flux-relay bot_token
   ENV=staging bash infra/k8s/scripts/rotate-secret.sh --flux-relay cluster_channel
   ENV=staging bash infra/k8s/scripts/rotate-secret.sh --flux-relay staging_channel
   ```

   Each run writes the key, applies `flux-system/flux-relay-slack` and names the keys still
   empty. Same env guard as `alertmanager-slack`; for an env whose cluster doesn't exist yet
   use `sops infra/k8s/secrets/flux-relay-slack.enc.yaml`. Nothing restarts: the relay rereads
   the mounted Secret, which the kubelet updates within a minute or two.

3. Commit the changed `flux-relay-slack.enc.yaml` files.

Check it: `kubectl -n flux-system logs deploy/flux-relay` says `No Slack bot token` until the
token is set, `Tracking …` when it claims an error post and `Closed …` when it replies.

### Test the Flux Relay

A failure that recovers, like the clone timeout that started this. Neither test
object applies anything; each fails, gets fixed and is deleted. A source with a branch that
doesn't exist tests the `cluster` route:

```bash
kubectl apply -f - <<'EOF'
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: alert-test
  namespace: flux-system
spec:
  interval: 1m
  url: ssh://git@github.com/fss-fmi/fmi-codes-website-2026.git
  ref:
    branch: does-not-exist
  secretRef:
    name: flux-git-auth
EOF
# wait for the error post in the cluster_url channel, then fix it:
kubectl -n flux-system patch gitrepository alert-test --type merge -p '{"spec":{"ref":{"branch":"main"}}}'
# within about a minute: "✅ Recovered …" in the error's thread and a ✅ on the post
kubectl -n flux-system delete gitrepository alert-test
```

An image scan of a repository that doesn't exist tests the `staging` route the same way:

```bash
kubectl apply -f - <<'EOF'
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImageRepository
metadata:
  name: alert-test
  namespace: flux-system
spec:
  image: fssfmi/does-not-exist
  interval: 1m
EOF
kubectl -n flux-system patch imagerepository alert-test --type merge -p '{"spec":{"image":"fssfmi/fmi-codes-backend"}}'
kubectl -n flux-system delete imagerepository alert-test
```

Restart test: break one again, wait for the post, run `kubectl -n flux-system delete pod -l
app=flux-relay`, then fix it. The reply still comes, from the state ConfigMap. Delete the pod
rather than a plain `rollout restart`: Flux undoes that restart annotation on its next apply of
`fmi-codes-flux-relay` (within 5 minutes), which restarts the relay a second time
([Restarting by hand](index.md#change-a-config-value)). Leave it
broken for 6 minutes or more to see a second post join the incident: one reply, ✅ on both.
