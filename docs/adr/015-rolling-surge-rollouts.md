# ADR-015: Rolling surge rollouts with drained pods, not blue-green

**Status**: accepted.

## Context

Every staging bump and every promote to prod rolls the backend and the frontend. The rollouts ran on the Deployment defaults and dropped or stalled requests (#267):

- **No drain.** A pod's server stops listening the moment SIGTERM lands (Gunicorn's arbiter closes its socket first, nginx does the same on its graceful stop), while ingress-nginx keeps sending it requests until it sees the pod leave the endpoints. On staging, a rolling restart under steady load stalled 19 frontend requests for about 5 s each, ingress-nginx's connect timeout before it retried another pod. A POST already sent to a stopping backend pod is not retried at all.
- **Lost capacity.** The default `maxUnavailable: 25%` rounds to one pod on prod's 4 backend replicas, so a quarter of the capacity sized for the registration rush (#219) was gone for the whole rollout.
- **Mixed versions.** Old and new pods serve side by side for a few seconds. A page from one frontend version could ask a pod running the other for its hashed bundle, get `index.html` from the SPA fallback and stay blank until reloaded. Old backend pods also serve on the schema the new release's migration already changed.

Blue-green was considered: bring up a full second set, switch all traffic to it at once, then stop the old set. It gives an instant rollback and only one version serving at a time. It was turned down:

- **It breaks the connection budget.** Each backend pod holds up to 4 workers x `DB_POOL_MAX` 8 = 32 connections. Two full sets on prod are 8 pods, 256 connections plus 10 reserved = 266, against `max_connections = 250`. Fitting it means shrinking the pools or raising Postgres's limit, both against the #219 sizing.
- **It leaves the hard parts unsolved.** The database is shared, so the old set serves on the migrated schema during the switch anyway. The frontend and the backend switch separately, so their versions still skew. And the old set still needs a drain when it stops.
- **It adds a controller.** Doing it with Flux means Flagger or Argo Rollouts, a new component in the deploy path of a cluster one person runs.

## Decision

- **Surge one pod, never fewer than the replica count.** Both Deployments set `maxSurge: 1` and `maxUnavailable: 0`. A new pod has to pass readiness before an old one stops.
- **Drain every stopping pod.** A `preStop` sleep of 10 s keeps the pod serving while the ingress drops it. Then the server drains: Gunicorn within `graceful_timeout` (30 s) inside a 45 s grace period, nginx on its graceful `SIGQUIT`. The sleep is the native `lifecycle.preStop.sleep`, which the pinned k3s v1.36 accepts (checked with a server-side dry run on staging), so it needs no `sleep` binary in the image.
- **Make the mixed-version window safe instead of shorter.**
  - Migrations stay backward compatible with the previous release: add first, take away a release later ([Schema management](../data.md#schema-management)).
  - Nginx answers a missing `/assets/` file with 404 instead of `index.html`, caches those hashed files as immutable and revalidates `index.html`. Any other `/assets/` status, the 404 included, is `no-store`, so neither a browser nor a CDN keeps one past the rollout that caused it.
  - `frontend/public/asset-guard.js` is a plain script loaded before the bundle. The bundle is the whole app, so the app can't notice its own failed load. When a same-origin `/assets/` script or stylesheet fails, the guard reloads after 2 s, then 4, 6, 8 and 10 s on further tries, at most 5 times per tab, counting in sessionStorage. It resets only after a load with no failed file and does nothing when storage is blocked, so it can't loop.
- `tests/test_rollout_safety.py` holds all of it, and `tests/test_capacity_budget.py` reads `maxSurge` from the manifest.

## Consequences

- **Easier**: a rollout keeps the full capacity, stopping pods finish what they hold and a page caught between versions reloads itself instead of staying blank. A returning visitor no longer downloads an unchanged bundle, and a browser never keeps an `index.html` that names files no longer deployed.
- **Harder**: prod's backend steps through its 4 pods one at a time, each taking about 15 s to become ready plus the drain, so a rollout takes longer. The restart scripts wait up to 300 s instead of 120 s.
- **Limit**: the budget counts the surge pod plus one draining pod (202 on prod). Under heavy load a draining pod can hold its pool for its full 40 s while new pods step in about every 15 s, and three draining pods are 266 connections. Don't roll out prod during the registration rush.
- **Limit**: rollback is a `git revert` plus a full rollout, minutes rather than a switch. Mixed versions still exist for a few seconds. The rules above make them harmless; nothing removes them.
- **Limit, on a rollout to or from a pre-#267 frontend**: the first rollout that ships this and any rollback to an image from before it run with pods that still answer a missing `/assets/` file, or `/asset-guard.js`, with `index.html`: a 200 with `Last-Modified` and no `Cache-Control`. A browser, and Cloudflare in front of prod ([ADR-017](017-prod-through-cloudflare-tunnel.md)), may keep that by heuristic for about a tenth of the old file's age, days for an image months old. A page whose new bundle was asked of an old pod then stays blank through any number of reloads until that copy expires, the next frontend release renames the bundle or the visitor hard-reloads (Ctrl+Shift+R); a cached answer for the guard turns it off in that browser for as long. Prod should take its first promote that carries this before it serves visitors. If it already serves them, purge Cloudflare's cache right after the rollout and expect some browsers to need a hard reload. Rollouts between images that both carry this change are covered.
- **Limit**: a migration that breaks the previous release's code is caught only in review. Nothing checks it automatically.
