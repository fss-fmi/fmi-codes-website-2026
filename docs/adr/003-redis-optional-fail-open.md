# ADR-003: Redis is optional and every use fails open

**Status**: accepted

## Context

Redis gives the app three things: shared rate-limit counters across Gunicorn workers and pods, the JWT revocation blocklist, and short-lived caches for hot public reads (mentor list, rankings, regulations). None of these is the source of truth. A hackathon platform sees sharp spikes (registration opening, results going live) where a cache outage turning into a site outage would be the worst possible failure.

## Decision

All Redis access goes through `backend/app/services/redis_client.py`, which picks Sentinel mode (`REDIS_SENTINELS` + `REDIS_MASTER_NAME`), single-instance mode (`REDIS_URL`) or disabled, from config alone. Application code uses fail-open helpers (`redis_get`, `redis_set`, `redis_del`) that log and return a default on any error. Losing Redis means: rate limiting falls back to in-process memory, revocation checks pass, caches miss and the DB serves every read.

Production runs Bitnami Redis with 1 master, 3 replicas and 3 sentinels (quorum 2); local dev can run with no Redis at all.

## Consequences

- **Easier**: local development needs only Postgres; a Redis failover or outage never returns a 500.
- **Harder**: during an outage security is weaker (revoked tokens are accepted, rate limits are per process). Readiness reports Redis state but never gates on it, so this degraded mode is silent apart from logs.
- **Technical debt**: none beyond the security trade-off above, which is deliberate.
