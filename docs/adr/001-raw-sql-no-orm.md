# ADR-001: Raw SQL with an authoritative schema file, no ORM

**Status**: accepted. The "no migration runner" part is superseded by [ADR-007](007-recorded-migrations-runner.md).

## Context

The backend owns a small, highly relational model (participants, teams, mentors, preferences, assignments) where the important behaviour lives in transactions: row locks, advisory locks, uniqueness races and a trigger-maintained member count. The team wanted full control over every query and a schema that reads as one document.

## Decision

We use psycopg2 with hand-written SQL through a thin helper layer (`backend/app/database.py`). `backend/database/schema.sql` is the single authoritative schema. Numbered files in `backend/database/migrations/` exist only as deltas for databases created before a change. There is no migration runner; fresh environments apply `schema.sql` directly through Postgres `initdb`.

## Consequences

- **Easier**: locking and transaction semantics are explicit in the code that needs them; the whole schema is reviewable in one file; no ORM magic to debug.
- **Harder**: every schema change must be made twice (in `schema.sql` and as a migration) and applied by hand to running databases. Nothing records which migrations a database has (both superseded by ADR-007's runner, which applies them and records each one). Query results are dicts, so typos in column names surface at runtime.
- **Technical debt**: on k3s the schema is baked into the Postgres PVC at first boot, so a running database changes only through migrations, which the runner from [ADR-007](007-recorded-migrations-runner.md) now applies. `schema.sql` also used to fail on re-run at its `CREATE TRIGGER` statements; they are now `CREATE OR REPLACE TRIGGER`, so a re-run on a database with every migration applied gives no error.
