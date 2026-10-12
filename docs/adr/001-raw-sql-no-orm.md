# ADR-001: Raw SQL with an authoritative schema file, no ORM

**Status**: accepted

## Context

The backend owns a small, highly relational model (participants, teams, mentors, preferences, assignments) where the important behaviour lives in transactions: row locks, advisory locks, uniqueness races and a trigger-maintained member count. The team wanted full control over every query and a schema that reads as one document.

## Decision

We use psycopg2 with hand-written SQL through a thin helper layer (`backend/app/database.py`). `backend/database/schema.sql` is the single authoritative schema. Numbered files in `backend/database/migrations/` exist only as deltas for databases created before a change. There is no migration runner; fresh environments apply `schema.sql` directly through Postgres `initdb`.

## Consequences

- **Easier**: locking and transaction semantics are explicit in the code that needs them; the whole schema is reviewable in one file; no ORM magic to debug.
- **Harder**: every schema change must be made twice (in `schema.sql` and as a migration) and applied by hand to running databases. Nothing records which migrations a database has. Query results are dicts, so typos in column names surface at runtime.
- **Technical debt**: `schema.sql` is not fully idempotent (its `CREATE TRIGGER` statements fail on re-run), and on k3s the schema is baked into the Postgres PVC at first boot. Adopting a migration runner would remove both problems.
