# Event day

The registration opening is the one moment the whole site is busy at once: the design target is
500 people registering and forming teams in the first minute
([#219](https://github.com/fss-fmi/fmi-codes-website-2026/issues/219), load test in
[Testing](../testing.md#load-test)). This page is the checklist for prod around it and for the
event itself: what to check in the days before, who watches what while it runs and what to do
when a number goes wrong. The thresholds and levers below were agreed in advance (#223), so
nobody has to invent them under pressure.

Commands run on the cluster machine from the repo root, on an up-to-date `main`. The Postgres
ones use `db`, the same wrapper as the load test, pointed at prod:

```bash
NS=fmi-codes
# Reads the current password from the Secret and sends it as stdin's first line, never in an
# argument (see Testing, "Run it on staging"). Arguments pass through: db -c '...'.
db() {
  { kubectl -n $NS get secret fmi-codes-db -o jsonpath='{.data.password}' | base64 -d; echo; [ -t 0 ] || cat; } |
    kubectl -n $NS exec -i postgres-0 -- sh -c 'IFS= read -r PGPASSWORD; export PGPASSWORD; exec psql -h 127.0.0.1 -U fmi_app -d fmi_hackathon_2026 -v ON_ERROR_STOP=1 "$@"' sh "$@"
}
```

## Days before

Anything here that restarts something is done now, not on the day.

- **Prod runs the sized release.** Prod is bootstrapped and promoted with a release carrying
  #220 and #221, #267's zero-downtime rollouts ([Rollouts](../deployment.md#rollouts)) and #223's
  mail counter: the dashboards and alerts reach Grafana through Flux on their own, but the
  **Emails** panel and `MailSendFailing` stay empty until prod's backend image exports
  `mail_sent_total`. The backend is 4 pods at a 1-CPU request and a 3-CPU limit:

  ```bash
  kubectl -n $NS get deploy backend -o jsonpath='{.spec.replicas} {.spec.template.spec.containers[?(@.name=="backend")].resources}{"\n"}'
  # 4 {"limits":{"cpu":"3","memory":"512Mi"},"requests":{"cpu":"1","memory":"256Mi"}}
  ```

- **CPU time per password hash on the prod machine.** Staging measured 0.39 CPU s at a 3-core
  limit (#222), and the sizing rests on it. On the prod machine:

  ```bash
  kubectl -n $NS exec deploy/backend -c backend -- python -c \
    'import time, bcrypt; t = time.process_time(); bcrypt.hashpw(b"x" * 12, bcrypt.gensalt(12)); print(time.process_time() - t)'
  ```

  Run it three times. If it is more than 20% above 0.39 s (over 0.47 s), the machine's cores
  are slower than staging's: rerun the [load test](../testing.md#load-test) on that machine's
  staging before trusting the sizing.

- **The load test passed on the prod machine.** Its staging, in the test window that
  [Run it on staging](../testing.md#run-it-on-staging) describes, then the revert.
- **Prod Postgres allows 250 connections.** `deploy-stateful.sh` applies it and restarts
  Postgres, which is why it happens days before
  ([Stateful tier](index.md#2--stateful-tier-postgres--redis-sentinel)):

  ```bash
  db -tAc 'SHOW max_connections'                  # 250
  ```

- **The prod ingress controller requests 500m CPU** (`deploy-ingress.sh`):

  ```bash
  kubectl -n ingress-nginx get deploy ingress-nginx-controller -o jsonpath='{.spec.template.spec.containers[0].resources.requests.cpu}{"\n"}'   # 500m
  ```

- **Mail works.** Set prod's `MAIL_PASSWORD` (a Gmail app password for the account the backend
  sends from) with `ENV=prod bash infra/k8s/scripts/rotate-secret.sh MAIL_PASSWORD`, which
  restarts the backend. Registration is still closed, so send a test verification email from a
  backend pod to an address you can read, with the pod's own mail settings:

  ```bash
  kubectl -n $NS exec deploy/backend -c backend -- python -c \
    'import sys, config; from app.services.email_service import send_verification_email; c = config.ProductionConfig; print(send_verification_email({k: getattr(c, k) for k in dir(c) if k.isupper()}, sys.argv[1], "https://fmicodes.com/"))' \
    you@example.com
  ```

  It prints `True` and the email arrives (check spam too). That process isn't a Gunicorn
  worker, so the **Emails** panel doesn't count it; the first real registration does.
  `REQUIRE_EMAIL_VERIFICATION` stays off for the rush ([Mail](#mail)).
  Staging sends from the same account unless its ConfigMap sets another `MAIL_USERNAME`, so
  keep staging's `MAIL_PASSWORD` empty (it is today), or every staging registration and load
  test spends prod's quota.

- **Grafana and the alerts reach the right people.** Everyone watching has a tailnet device and
  a Grafana login ([Access Grafana and staging](tailscale.md#access-grafana-and-staging)), and
  cluster alerts post to `#cluster-alerts-prod` ([Adding prod to a staging-only box](alerts.md#adding-prod-to-a-staging-only-box)
  when the prod cluster started as a staging box).

## Day before

- **The live backend is what was sized:** 4 pods ready (the command above), the probes give a
  busy pod time (readiness drops it after 12 misses at 10 s, liveness restarts it after 30, see
  [ADR-016](../adr/016-shed-password-hashes.md)) and each worker's pool holds 8:

  ```bash
  kubectl -n $NS get deploy backend -o jsonpath='{range .spec.template.spec.containers[?(@.name=="backend")]}{.readinessProbe.failureThreshold} {.livenessProbe.failureThreshold} {.readinessProbe.timeoutSeconds}{"\n"}{end}'   # 12 30 10
  kubectl -n $NS get configmap fmi-codes-backend-config -o jsonpath='{.data.DB_POOL_MAX}{"\n"}'   # 8
  kubectl -n $NS get pods -l app.kubernetes.io/name=fmi-codes-backend   # 4 Running, 1/1, RESTARTS 0
  ```

- **The opening is scheduled.** In Mission Control (**SITE** tab), **PARTICIPANT
  REGISTRATION** shows the schedule at the right time in your time zone, and
  `#event-feed-prod` has its post ([User Guide](../user-guide.md#site-tab)).
- **The live flags are as expected:**

  ```bash
  curl -s https://fmicodes.com/api/config
  # {"MENTORS_STAY_TUNED":...,"PREFERENCES_OPEN":false,"RANKINGS_LIVE":false,"REGISTRATION_OPEN":false,"REQUIRE_EMAIL_VERIFICATION":false}
  ```

- **No release is pending.** Nothing waits to be promoted or migrated: promote now or after the
  event, never during the rush.

## Before the opening

- **The organiser logs in to Mission Control early**, the day before or the morning of. Since
  #220 the admin login is limited per account like any other (15 attempts a minute,
  [ADR-014](../adr/014-rate-limits-keyed-on-account-and-user.md)), so anyone who knows
  `ADMIN_EMAIL` can keep a fresh admin login refused for as long as they keep sending wrong
  passwords. A session that is already open lasts 3 days (`JWT_EXPIRY_DAYS`) and is not ended by
  that. A fresh login also hashes a password, so at the peak it can be shed like anyone's.
  Keep the tab open, and log in again before the 3 days run out if the event outlasts them.
- **Everyone is in place** with the role they hold ([During](#during)), 15 minutes before.
- **Nothing is merging.** A merge to `main` rolls out staging on the same node, image pull
  included, and takes CPU from prod. Hold merges until the rush is over.

## During

One person can hold several roles; every role has a name next to it before the day.

| Role            | Watches                                                                                                                                                                                            | Acts                                                         |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Mission Control | Mission Control (logged in, **SITE** tab open), `#event-feed-prod`, the REGISTRATION tab's slots and queue                                                                                         | Closes and reopens registration, nothing else                |
| Dashboard       | Grafana **FMI Codes → FMI Production**: request rate, latency, 5xx share, 429s by route, register and login p95, hash sheds, backend CPU and throttling, pods ready and restarts, emails, node CPU | Calls a threshold out to the other two                       |
| Cluster         | `#cluster-alerts-prod` and a terminal on the cluster machine: the pods and Postgres connections (below)                                                                                            | Runs the levers on the cluster ([When to act](#when-to-act)) |

The cluster terminal:

```bash
kubectl -n $NS get pods -w                      # RESTARTS stays 0, every backend pod 1/1
while sleep 5; do
  db -tAc "SELECT now()::time(0), COUNT(*) FILTER (WHERE backend_type = 'client backend'), COUNT(*) FILTER (WHERE wait_event_type = 'Lock' AND wait_event = 'advisory') FROM pg_stat_activity"
done                                            # time | connections (all databases) | waiting on the registration lock
```

Postgres has no exporter, so connections are only in this loop. It counts every database,
since `max_connections` is a cap for the whole server. Expected at the peak: about 130 at most
(4 pods x 4 workers x 8, plus a few) and a handful waiting on the lock that serialises every
team change ([ADR-004](../adr/004-advisory-lock-registration-queue.md)).

What normal looks like in the opening minutes (the staging run, #222): register p95 under half
a second, no 5xx, no restarts. A short burst of 429s at the peak is expected: password hashes
past a pod's cap are shed with a 429 (**Password Hash Sheds**), and the SPA retries register
and login by itself after `Retry-After`. **429s by Route** counts both kinds; the sheds carry no
route, so the rate-limit share of register and login is their 429 rate minus the shed rate.

Reading the panels:

- **Register and Login p95** is interpolated from the latency buckets, which step from 2.5 s
  to 5 s, so a value between them is an estimate.
- **5xx Share** has a 2-minute line for the threshold below and the 5-minute one
  `BackendHighErrorRate` uses. Both count only answers Flask finished: a 502 or 504 from
  ingress-nginx (a worker stuck until Gunicorn's 120 s timeout) is in neither
  ([Not covered](alerts.md#cluster-alerts)). A climbing p95 with flat 5xx can be that.
- **Backend Pods Ready** lags: readiness drops a pod only after 2 minutes of failed probes.
- **Node CPU Busy** is the whole machine, staging and monitoring included.

The rush is over when **Request Rate** has been back to its everyday level and **429s by
Route** near zero for 15 minutes. Then the ground rules below lift.

## Ground rules

- **No `kubectl` fixes.** Flux applies git every 5 minutes and drops what `kubectl` changed
  ([Change a config value](index.md#change-a-config-value), #187). The one exception is the
  scale lever below, which suspends Flux first.
- **No rollouts during the rush.** No promote, no `apply-config.sh`, no `rotate-secret.sh`, no
  `deploy-stateful.sh`, no restart. Each one rolls the backend, and under load more draining
  pods hold their connections at once than the budget counts
  ([Rollouts](../deployment.md#rollouts)). That rules out every config change, rate limits
  included, until the rush is over.
- **Mission Control switches are always safe.** They take effect on the next request in every
  pod and need no deploy ([Feature flags during the event](../deployment.md#feature-flags-during-the-event)).
- **A git change takes about 10 minutes to reach prod:** the PR's CI (about 4 minutes), the
  merge, then Flux within 5 minutes, or at once with
  `flux reconcile kustomization fmi-codes -n flux-system --with-source`. A ConfigMap change
  then still needs a restart, so it waits for the rush to end.

## When to act

Agreed before the event (#223). Signals are on **FMI Production** unless they say otherwise.

| Signal                                               | Threshold                                                                                   | Lever                                                                                                                                                                          |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Register and Login p95**                           | over 3 s for 5 minutes, with **Password Hash Sheds** steady and **Node CPU Busy** under 70% | [Scale the backend](#scale-the-backend) from 4 to 6 pods                                                                                                                       |
| **5xx Share** (2m line)                              | over 5% for 2 minutes                                                                       | [Read the logs](#read-the-logs). A bug or a database fault: [close registration](#close-registration)                                                                          |
| **429s by Route** on register or login, beyond sheds | steady                                                                                      | Nothing live: the address limit can only change with a rollout. The SPA retries after `Retry-After`. Note it for the next event                                                |
| **Backend Pods Ready and Restarts**                  | 2 or more pods unready or restarting                                                        | [Close registration](#close-registration), fix, reopen                                                                                                                         |
| Postgres connections (the loop)                      | over 220                                                                                    | No rollout of any kind. If the lock waiters keep climbing, [close registration](#close-registration): it stops new accounts, but people already registered keep changing teams |

`BackendHighErrorRate` (5xx over 5% for 10 minutes) and `BackendHighThrottleRate` (over 10% of
requests answered 429 for 10 minutes) post to `#cluster-alerts-prod` as well, but the
thresholds above act sooner.

### Scale the backend

More pods add hashing CPU without restarting the ones serving. Only when the node has the CPU
for it: 6 pods can burst to 18 cores, so check **Node CPU Busy** first.

```bash
flux suspend kustomization fmi-codes -n flux-system
kubectl -n $NS scale deployment/backend --replicas=6
kubectl -n $NS rollout status deployment/backend --timeout=300s
```

6 pods' pools are 192 connections, 202 with the migrate step, backups and the operator, inside 250. **No rollout while at 6:** a surge pod plus a draining one make 8 pods, 256 connections
and 266 with the reserve, against 250. While Flux is suspended nothing deploys to prod, image
bumps included. Don't commit `replicas: 6` either: `test_capacity_budget.py` fails it for the
same reason.

When the rush is over, give the pods back to git, which still says 4 (a scale-down, not a
rollout):

```bash
flux resume kustomization fmi-codes -n flux-system   # Flux drops kubectl's replicas and scales back to 4
```

### Close registration

Mission Control → **SITE** → **PARTICIPANT REGISTRATION** → **CLOSE NOW**. Registration is
refused on the next request, open pages show it closed within 30 seconds, and
`#event-feed-prod` gets the post. Accounts and teams made so far stay, and registered
participants can still create, join and leave teams. Closing by hand does not cancel a pending
schedule, so if the panel still shows one (a closing time, say), click **CANCEL SCHEDULE**
too. Tell participants where you announce (Discord) that registration paused and when it
reopens. Once fixed, reopen with **OPEN NOW**, or **SCHEDULE** it for the time you announced.

If Mission Control can't be used (the admin can't log in, or its page won't load), close it in
the database. It takes effect within 10 seconds (the flags' cache) and posts nothing to the event
feed, so post it by hand:

```bash
db -c "UPDATE feature_flags SET enabled = FALSE, scheduled_value = NULL, scheduled_at = NULL, updated_at = NOW() WHERE name = 'registration_open'"
```

### Read the logs

```bash
kubectl -n $NS logs -l app.kubernetes.io/name=fmi-codes-backend -c backend --since=10m --prefix --tail=-1 |
  grep -E 'ERROR|Traceback' | tail -50
```

`connection pool exhausted` or `connection to server ... failed` point at Postgres (the loop
above); the same error on every request of one route points at a bug.

## Mail

Every registration emails a verification link, and password resets and join requests send mail
too, all through one account: the council's Gmail, which allows about 500 recipients in any
24 hours, a rolling window rather than a calendar day (Google publishes no exact figure for
SMTP). That covers a real opening (18 teams of up to 6, about 90 coders at the last event),
but not abuse: the register limit allows 300 a minute from one address
([ADR-014](../adr/014-rate-limits-keyed-on-account-and-user.md)), so one script can spend the
quota in under two minutes. After that, verification links, password resets and join-request
mail fail for everyone for up to 24 hours.

Verification mail is queued in each worker (4 senders a worker, so up to 64 at once across 4
pods) and sent after the registration answers. Each send logs in to Gmail on its own, which at
the peak can draw Gmail's throttling. A send still queued when its pod stops is lost.

That is why `REQUIRE_EMAIL_VERIFICATION` stays off for the rush: with it on, a spent quota
would stop everyone from forming a team. With it off, a lost verification mail costs nothing
on the day, and the participant sends a new one from **PROFILE** later.

**How to tell.** Every send is counted in `mail_sent_total{kind, result}` (`kind` is
`verification`, `reset` or `join_request`; `result` is `sent`, `failed` or `skipped`, the last
when no SMTP credentials are set). The **Emails** panel shows them, and `MailSendFailing` posts
to `#cluster-alerts-prod` after 3 failed sends in 15 minutes. The log says why:

```bash
kubectl -n $NS logs -l app.kubernetes.io/name=fmi-codes-backend -c backend --since=1h --prefix --tail=-1 |
  grep 'Failed to send'
```

| The error contains                                            | Means                                                                                       |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `5.4.5` (a daily sending limit or quota exceeded)             | The day's quota is spent                                                                    |
| `421 4.7.0` or `454 4.7.0` (try again later, too many logins) | Gmail is throttling the account for now; sends recover by themselves                        |
| `5.7.8` (username and password not accepted)                  | The app password was revoked or changed: set it again with `rotate-secret.sh MAIL_PASSWORD` |
| a timeout or connection error                                 | SMTP unreachable from the cluster                                                           |

**What to do when the quota is spent.**

- During the rush: nothing in the cluster. The site keeps working, and registration never waits
  for mail. Tell participants that verification and reset emails are delayed until the next
  day. A reset request still answers that the email was sent, so expect questions.
- Wait it out: the limit lifts within 24 hours, and participants resend their verification
  link from **PROFILE**.
- Or switch to a second Gmail account once the rush is over: set `MAIL_USERNAME` in
  `infra/k8s/base/app/backend.yaml` (it is not in the ConfigMap today, so the backend uses the
  default in `backend/config.py`), merge it, then set that account's app password with
  `ENV=prod bash infra/k8s/scripts/rotate-secret.sh MAIL_PASSWORD`. Both restart the backend,
  which is why it waits. Keep that account and its app password ready in the password manager
  before the day if you want this option.
