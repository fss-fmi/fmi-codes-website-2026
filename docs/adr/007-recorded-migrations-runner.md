# ADR-007: Recorded migrations applied on rollout and on demand

**Status**: accepted (supersedes the "no migration runner" part of [ADR-001](001-raw-sql-no-orm.md))

## Context

[ADR-001](001-raw-sql-no-orm.md) kept migrations as hand-applied deltas with no record of which had run. Every schema change then had to be applied by an operator with cluster access, in the right order, before the code that needed it went live. Staging auto-deploys every push to `main` ([ADR-006](006-self-hosted-k3s-pull-based-gitops.md)), so a migration-carrying commit broke staging until someone applied it. GitHub-hosted runners cannot reach the cluster, so a workflow cannot run `psql` against it either. There are no automated database backups.

## Decision

- `backend/database/migrate.py` applies every file in `backend/database/migrations/` that is not yet recorded in a `schema_migrations` table, in number order. Each file runs in its own transaction together with its record, and a session-level advisory lock serialises concurrent runners. It connects with the backend's own credentials (`fmi_app` owns the tables).
- The backend Deployment runs it as an **initContainer** before every rollout, so neither environment's code can get ahead of its schema. A failed migration keeps the new pods from starting while the old ones keep serving.
- **Actions → Migrate database** opens a PR that adds a one-off Job to the chosen overlay, with an explicit backend image. Merging is the approval; Flux runs the Job in-cluster, which first `pg_dump`s into the `db-migration-backups` PVC (last 5 kept). Use it to migrate deliberately (for example prod before a promote) with a backup.
- Results go to Discord. Migration files must be safe to re-run and must not contain transaction control; the first run on an existing database re-applies 012 to 016 as no-ops and records them.
- Still plain SQL, still no ORM, and `schema.sql` is still the authoritative full schema for fresh databases.

## Consequences

- **Easier**: no hand-applied migrations; a database can say what it has run; staging no longer breaks between a push and a manual migration; a prod migration gets a backup and the same PR gate as a promote.
- **Harder**: every migration must be idempotent and transaction-free, and is still written twice (in `schema.sql` and as a migration). There are no down-migrations; undoing one means a new forward migration or restoring a dump. Backups sit on the same node as the database.
- **Technical debt**: backups are not off-site. A failed Job leaves the app Flux Kustomization not ready until the next migration run replaces it.
