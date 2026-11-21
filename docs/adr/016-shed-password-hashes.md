# ADR-016: Shed password hashes past a per-pod cap, and probes that don't act on a busy pod

**Status**: accepted.

## Context

On staging, about 3.3 logins a second for 240 s took the site down (#269). Each login runs bcrypt, about 0.42 CPU-seconds, and staging's 2 backend pods could hash about 2.4 a second. Gunicorn refuses nothing: each gthread worker accepts up to 1000 connections and queues them for its 8 threads, so the queue grew by the difference every second and every request waited behind it. Clients gave up after 15 s while the server still hashed for them, and the share of logins that succeeded fell from about 60% to almost none. The probes waited in the same queue: readiness dropped both pods, liveness restarted both within about 40 s of each other and for the last 40 s every backend request got 503 or 502. Load reaches every pod evenly through ingress-nginx, so a probe that acts on a busy pod acts on all of them at once.

Prod has more room (4 pods with a 3-core limit, about 28 hashes a second), but the registration rush is exactly a burst of logins and registrations, and the address ceilings allow 300 a minute of each from one address ([ADR-014](014-rate-limits-keyed-on-account-and-user.md)).

## Decision

- **A per-pod cap on concurrent password hashes** (`backend/app/utils/hash_slots.py`). `hash_password` and `verify_password` run bcrypt inside a hash slot, so register, login (the timing dummy included), password change and reset confirm are all capped. A pod has `HASH_SLOTS` slots: its own CPU limit in whole cores, set through the downward API (`limits.cpu`, divisor 1), so prod has 3 per pod and staging 1. Every env's backend CPU limit is whole cores, because the downward API rounds up and half a core would get a whole slot.
- **A waiting room.** A request that finds no free slot needs one of the waiting slots, two per hash slot, to wait for one, polling every 25 ms for up to 2 s. With no waiting slot free it is shed at once. Waiting holds a Gunicorn thread, so without the room a flood would park every thread in a wait and the probes would queue again. With it, hashing ties up at most 9 of a prod pod's 32 threads at any load.
- **Slots are `flock` lock files** shared by all the workers of a pod, opened by every attempt itself. A `flock` belongs to the open file, so two threads of one worker exclude each other, and the kernel releases it when its holder dies, so a worker Gunicorn kills on its 120 s timeout can't keep its slot. `fcntl` and `lockf` locks belong to the process and wouldn't exclude threads. A `multiprocessing` semaphore loses the slot of a killed holder until the pod restarts.
- **A shed answers 429** with `Retry-After: 2` and `The server is busy. Wait a moment and try again.`, before the route has written anything, so sending the same request again is safe. The login and registration pages already wait out a 429's `Retry-After` plus 0 to 3 s of jitter and send again, up to 3 times (#250). `password_hash_shed_total{reason}` counts sheds by `waiting_room_full` and `wait_timeout`, so a shed 429 can be told apart from a rate-limit one.
- **Hashes a booting worker runs are never shed.** Every worker hashes the login timing dummy at import and the new mentors of the seed while it loads (`wsgi.py`). A shed there would fail the boot, and Gunicorn stops when a worker can't boot. They pass `shed=False`. A worker Gunicorn replaces mid-rush (after a crash or its 120 s timeout) boots the same way, so each replacement runs the dummy hash once on top of the pod's cap; the seed only hashes mentors missing from the database, which after the first boot is none.
- **Probes that don't act on a busy pod.** Readiness drops a pod after 2 min of misses (12 x 10 s), liveness restarts it after 5 min (30 x 10 s). Shedding keeps the hash paths from queueing; the thresholds cover any other pile-up, such as a join rush queued on the advisory lock or a slow Postgres. Dropping every pod at once never helps anyone with one shared Postgres, and a new pod during a rollout still has to pass readiness before an old one stops, which the failure threshold doesn't change.
- **`HASH_SLOTS` unset means no cap** (local dev, where Windows has no `flock`, and the unit tests). A value that isn't a positive whole number, or a cap on a platform without `flock`, refuses to boot.

Considered and turned down:

- **An exec liveness probe that checks the Gunicorn arbiter.** Gunicorn runs as PID 1, so a dead arbiter ends the container and the kubelet restarts it anyway; the probe could only ever pass. Dropping liveness was also turned down: the gthread worker heartbeats from its main loop, so a pod whose every thread is stuck looks alive to Gunicorn, and the 5 min liveness is the only thing that restarts it.
- **A probe served outside the request queue** (a second port in the arbiter). A busy pod would never fail it, but neither would one with every thread stuck, which stays in the Service forever.
- **Longer thresholds alone.** A queue that keeps growing outlasts any threshold, and every request still waits behind it.
- **A per-worker semaphore.** Simpler, and no slot can leak, but its smallest cap is 4 per pod (one per worker). On staging's 1 core that is 4 hashes at a quarter of prod's speed each, so staging would shed at a different rate from prod and a staging load test would not predict prod.
- **503 instead of 429.** It needs new handling in the SPA and counts as a 5xx in every alert and dashboard.
- **Lower bcrypt rounds.** More capacity, but every new password hash gets weaker to survive one rush.
- **More replicas or an autoscaler.** The node's CPU is the ceiling, the connection budget caps prod at 5 pods and an autoscaler reacts in tens of seconds while a rush peaks sooner.

## Consequences

- **Easier**: overload no longer takes the site down. Each pod hashes at its full CPU, latency stays bounded and probes, `/api/config` and team pages keep getting threads. Past capacity some users see the pages' "retrying" countdown for a few seconds instead of a 15 s timeout. Staging has prod's slots per core, so a staging load test at a sixth of prod's expected rate shows how prod sheds (2 slots against 12).
- **Harder**: a pod broken on its own, such as one with a bad connection pool, stays in the Service for 2 min instead of 30 s, and a pod with every thread stuck is restarted after 5 min instead of 1.
- **Limit**: it adds no capacity. Prod still hashes about 28 a second and staging about 4.8; above that some logins and registrations are shed. Each retry counts against the address limits and the login's account limit again, so a user retried 3 times has spent 4 of the 15 login attempts a minute. A shed attempt is not refunded: the account limit counts every attempt when it arrives so parallel guesses can't slip past ([ADR-014](014-rate-limits-keyed-on-account-and-user.md)), and clearing the count on a shed would let anyone who can flood the pods reset it.
- **Limit**: polling is not first come, first served. A request that arrives just as a slot frees can take it ahead of one already waiting, which then waits longer or is shed. A waiter tries for a slot as soon as it holds its waiting slot, then every 25 ms.
- **Limit**: only bcrypt is capped. Any other path that piles up still queues, and the 2 min readiness threshold is what keeps that from dropping every pod.
