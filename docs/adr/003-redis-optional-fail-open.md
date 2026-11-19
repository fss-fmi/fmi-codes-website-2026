# ADR-003: Redis is optional and every use fails open

**Status**: accepted

## Context

Redis gives the app three things: shared rate-limit counters across Gunicorn workers and pods, the JWT revocation blocklist, and caches for hot public reads (seed lookups, mentor list, registered teams, rankings, regulations). None of these is the source of truth. A hackathon platform sees sharp spikes (registration opening, results going live) where a cache outage turning into a site outage would be the worst possible failure.

## Decision

All Redis access goes through `backend/app/services/redis_client.py`, which picks Sentinel mode (`REDIS_SENTINELS` + `REDIS_MASTER_NAME`), single-instance mode (`REDIS_URL`) or disabled, from config alone. Losing Redis means: rate limiting falls back to each worker's memory, revocation checks pass, caches miss and the DB serves every read. A hanging Redis (a stalled master, a dead pod's IP during a Sentinel failover) is handled like a refusing one, and nothing waits on it for long (#256):

- **Timeouts.** Every connection, the limiter's and the Sentinel queries' included, has a 0.5 s socket and connect timeout (`REDIS_SOCKET_TIMEOUT`, `REDIS_CONNECT_TIMEOUT`). A dropped connection is retried once at once; a timeout never is.
- **Circuit breaker.** Application code uses fail-open helpers (`redis_get`, `redis_set`, `redis_del`, `redis_incr`, `redis_exists`, `redis_status`) that return a default on any error. They share one breaker per process: a connection error or timeout skips Redis for 5 s (`BREAKER_OPEN_SECONDS`), then one call tries again while the others keep their fallback; an answer closes it. The token blocklist and the readiness ping go through it too, so a request pays at most one timeout per open period. The raw client (`get_redis_client()`) is only for the migration runner.
- **Reconnect.** Building the client never contacts Redis, and a build that raises is retried behind the breaker, so a pod that starts while Redis is away picks it up once it answers. Only "no Redis configured" turns Redis off for good.
- **Limiter.** Flask-Limiter runs with `in_memory_fallback_enabled`: on a storage error each worker keeps the same limits in its own memory and pings Redis after 1, 2, 4, 8, 16 and 32 s (then again from 1 s) until it answers. Each ping makes one request wait for it. `swallow_errors` lets a request through with a log line on any other limiter error.
- **Visibility.** Each process logs one warning when it marks Redis down and one when Redis answers again; the limiter logs the same pair (`Rate limit storage unreachable - falling back to in-memory storage`, `Rate limit storage recovered`).

Production runs Bitnami Redis as 3 `redis-node` pods, each with a Sentinel: 1 master and 2 replicas (quorum 2); local dev can run with no Redis at all.

## Consequences

- **Easier**: local development needs only Postgres; a Redis failover or outage never returns a 500 and never makes a request wait more than one timeout per process and open period.
- **Harder**: during an outage security is weaker. Revoked tokens are accepted, and limits are per worker: prod's 4 pods x 4 workers keep 16 counters, so the 15/min login limit per account allows up to 240/min while it lasts. Readiness reports Redis state but never gates on it, so this degraded mode is visible only in the logs.
- **Technical debt**: none beyond the security trade-off above, which is deliberate.
