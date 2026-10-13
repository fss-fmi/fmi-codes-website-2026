# ADR-004: One Postgres advisory lock serialises all registration-state changes

**Status**: accepted

## Context

Only 18 teams can attend. Teams register automatically the moment they reach 3 members, the rest queue, and a freed slot promotes the next team. Joins, leaves, kicks, accepts, disbands and admin overrides all change member counts or slot ownership, and they arrive concurrently when registration opens. Row locks alone cannot protect a global invariant like "at most 18 registered teams".

## Decision

Every operation that can change team membership, registration or queue state runs in a single transaction that starts with `SELECT pg_advisory_xact_lock(1)`, then row-locks the rows it touches with `SELECT ... FOR UPDATE`. Saving matching results uses a different key (`pg_advisory_xact_lock(2)`) so it never contends with team mutations. UNIQUE constraints remain the last line of defence. CPU-heavy work (bcrypt) runs before any connection is taken.

## Consequences

- **Easier**: the 18-slot cap, queue ordering and auto-promotion are correct by construction; the logic in `team_service.py` can be written as straightforward sequential code.
- **Harder**: all team mutations across all workers and pods are serialised through one lock, which caps their throughput. At 18 teams and roughly 100 participants this is far below any real limit.
- **Technical debt**: the lock key is a bare constant (`1`, `2`). Any new code path that changes registration state must remember to take lock 1 or it can break the invariant.
