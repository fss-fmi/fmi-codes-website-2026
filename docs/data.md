# Data Model

## Overview

One PostgreSQL 16 database (`fmi_hackathon_2026` in prod, `fmi_hackathon_2026_staging` in staging, `fmi_hackathon_2026_dev` by default locally). Fourteen tables, four views, three trigger functions and one data-quality function, all defined in `backend/database/schema.sql`. The backend talks to it with psycopg2 and hand-written SQL; there is no ORM.

Domains:

- **People**: `participants`, `mentors` (separate credential spaces; the admin has no row).
- **Teams**: `teams`, `team_join_requests`.
- **Matching**: `team_mentor_preferences`, `mentor_team_preferences`, `team_mentors`, `matching_state`.
- **Lookups**: `universities`, `specialties`.
- **Auth support**: `password_reset_tokens`, `email_verification_tokens`.
- **Site switches**: `feature_flags`.
- **Unused**: `hackathon_events` (seeded with one row, nothing references it from code).

## ER diagram

```mermaid
erDiagram
    UNIVERSITIES ||--o{ PARTICIPANTS : "studies at"
    SPECIALTIES ||--o{ PARTICIPANTS : "specialises in"
    TEAMS ||--o{ PARTICIPANTS : "has members"
    PARTICIPANTS ||--o| TEAMS : "captains"
    PARTICIPANTS ||--o{ TEAM_JOIN_REQUESTS : "applies"
    TEAMS ||--o{ TEAM_JOIN_REQUESTS : "receives"
    TEAMS ||--o{ TEAM_MENTOR_PREFERENCES : "ranks"
    MENTORS ||--o{ TEAM_MENTOR_PREFERENCES : "ranked by"
    MENTORS ||--o{ MENTOR_TEAM_PREFERENCES : "ranks"
    TEAMS ||--o{ MENTOR_TEAM_PREFERENCES : "ranked by"
    TEAMS ||--o{ TEAM_MENTORS : "assigned"
    MENTORS ||--o{ TEAM_MENTORS : "assigned"

    TEAMS {
        bigint id PK
        varchar team_name UK
        varchar join_code UK
        varchar status
        int participant_count
        bool is_registered
        int queue_position
        float score
        bigint captain_id FK
    }
    PARTICIPANTS {
        bigint id PK
        bigint team_id FK
        varchar email UK
        varchar faculty_number UK
        varchar course
        bool is_captain
        bool email_verified
        timestamptz tokens_valid_from
    }
    MENTORS {
        bigint id PK
        varchar email UK
        varchar company_name
        text_array technologies
        varchar picture_url
        timestamptz tokens_valid_from
    }
    TEAM_MENTORS {
        bigint team_id PK
        bigint mentor_id PK
        bool is_active
    }
```

## Tables

### teams

| Column               | Type                       | Notes                                                                                                                       |
| -------------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `id`                 | bigserial PK               |                                                                                                                             |
| `team_name`          | varchar(100) unique        | Validated against HTML characters on create                                                                                 |
| `password_hash`      | varchar(255) not null      | Legacy column. Always written as `''` and stripped from API responses                                                       |
| `join_code`          | varchar(20) unique         | 8 chars `A-Z0-9`, generated on create                                                                                       |
| `status`             | varchar(20)                | `pending` (under 3 members), `active` (3 or more), `completed`, `disqualified`. Only `pending` and `active` are set by code |
| `participant_count`  | int                        | Denormalised; maintained by the `trig_update_participant_count` trigger on `participants.team_id` changes                   |
| `is_registered`      | bool                       | Holds one of the 18 event slots                                                                                             |
| `registered_at`      | timestamptz                | Set when registered; drives display order                                                                                   |
| `queue_position`     | int                        | 1-based waiting list position; null when not queued                                                                         |
| `score`              | double precision           | Final judged score, 0 to 100, entered by the admin                                                                          |
| `score_updated_at`   | timestamptz                |                                                                                                                             |
| `captain_id`         | bigint FK participants     | `ON DELETE SET NULL`                                                                                                        |
| `hackathon_event_id` | bigint FK hackathon_events | Never set by code                                                                                                           |

Trigger `trig_prevent_team_deletion` blocks deleting a team that still has active participants, which is why disbanding first detaches every member.

### participants

| Column                          | Type                | Notes                                                                                      |
| ------------------------------- | ------------------- | ------------------------------------------------------------------------------------------ |
| `id`                            | bigserial PK        |                                                                                            |
| `team_id`                       | bigint FK teams     | `ON DELETE RESTRICT`; null when teamless                                                   |
| `first_name`, `last_name`       | varchar(100)        |                                                                                            |
| `email`                         | varchar(255) unique | Stored lowercased                                                                          |
| `phone_number`                  | varchar(20)         |                                                                                            |
| `faculty_number`                | varchar(20) unique  |                                                                                            |
| `course`                        | varchar(30)         | CHECK: `Bachelor 1st Year` .. `Bachelor 4th Year`, `Masters 1st Year`, `Masters 2nd Year`  |
| `specialty_id`, `university_id` | bigint FK           | `ON DELETE RESTRICT`                                                                       |
| `password_hash`                 | varchar(255)        | bcrypt                                                                                     |
| `is_captain`                    | bool                |                                                                                            |
| `status`                        | varchar(20)         | `active`, `inactive`, `removed`. Only active participants can log in or count toward teams |
| `tokens_valid_from`             | timestamptz         | Session revocation epoch; any JWT with an earlier `iat` is rejected                        |
| `email_verified`                | bool                | Default false for new rows. Rows that existed before migration 016 were set to true        |
| `password_reset_requested_at`   | timestamptz         | Unused by current code                                                                     |

### mentors

| Column                                    | Type                | Notes                                                                                                             |
| ----------------------------------------- | ------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `id`                                      | bigserial PK        |                                                                                                                   |
| `first_name`, `last_name`, `company_name` | varchar             | Unique together (`uidx_mentors_identity`), used as the seed upsert key                                            |
| `email`                                   | varchar(255) unique |                                                                                                                   |
| `phone_number`                            | varchar(20)         |                                                                                                                   |
| `bio`, `availability_text`                | text                |                                                                                                                   |
| `technologies`                            | text[]              | GIN indexed                                                                                                       |
| `picture_url`                             | varchar(500)        | A path such as `/mentorPictures/alice.webp` (files in `frontend/public/mentorPictures/`, served by the frontend)  |
| `picture_filename`                        | varchar(255)        | The file name at the end of `picture_url`; the seeder derives it and ignores a `picture_filename` key in the seed |
| `password_hash`                           | varchar(255)        | bcrypt                                                                                                            |
| `status`                                  | varchar(20)         | `active`, `inactive`, `archived`. Only active mentors appear, log in or get matched                               |
| `tokens_valid_from`                       | timestamptz         | Same meaning as for participants                                                                                  |
| `password_reset_requested_at`             | timestamptz         | Unused by current code                                                                                            |

### team_join_requests

One row per (participant, team) pair; re-applying reopens the row. `status`: `pending`, `accepted` (also set when the applicant joins that team with its code), `declined`, `invalidated` (the applicant got onto a team first: accepted elsewhere, joined with a code or created a team; or the captain accepted after the applicant's account stopped being `active`, which only a direct database edit does), `cancelled` (withdrawn by the applicant). Disbanding a team deletes all its rows (`ON DELETE CASCADE` on `team_id`), whatever their status.

### team_mentor_preferences / mentor_team_preferences

A captain's ranking of mentors and a mentor's ranking of teams. Rank is 1 to 3, unique per owner, and the pair is the primary key. The API always replaces all three rows at once.

### team_mentors

Matching output. Primary key (`team_id`, `mentor_id`), `is_active` (always true when written), `assigned_at`, `notes` (unused). Every matching run deletes all rows and writes a fresh set. The goal is 2 or 3 rows per team and never more than 3.

### matching_state

A single row (`id = 1`, enforced by CHECK). `is_confirmed` flips to true when the admin confirms; every new matching run resets it.

### feature_flags

One row per flag, seeded false by migrations 017 and 020 and by `schema.sql`: `registration_open`, `rankings_live`, `mentors_stay_tuned`, `preferences_open` (the `name` primary key has a CHECK for exactly these, `feature_flags_name_check`). `enabled` is the live value and `updated_at` is when it last changed. `scheduled_value` and `scheduled_at` hold the one pending change, both set or both NULL (CHECK). Nothing runs a schedule on its own: the first read after `scheduled_at` locks the due rows (`SELECT ... FOR UPDATE`), applies them and clears the pair, so concurrent readers apply it once. Only the admin writes this table, through `/api/admin/flags*` ([ADR-013](adr/013-feature-flags-in-database.md)).

### password_reset_tokens

`user_id` + `role` (`participant` or `mentor`), `token_hash` (SHA-256 hex of the emailed token; the raw token is never stored), `expires_at` (one hour), `used_at`. Requesting a new link deletes the user's unused tokens. Nothing prunes expired rows yet.

### email_verification_tokens

`participant_id` (FK participants, `ON DELETE CASCADE`), `token_hash` (SHA-256 hex, unique; the raw token is never stored), `expires_at` (24 hours), `used_at`. Registration and every resend delete the participant's unused tokens before inserting a new one. Nothing prunes expired rows yet.

### universities / specialties

`name` unique. `is_seed = true` marks the curated list the registration dropdown shows; user-submitted "Other" entries are stored with `is_seed = false`.

## Views and functions

| Object                          | Purpose                                                               |
| ------------------------------- | --------------------------------------------------------------------- |
| `v_teams_summary`               | Teams with mentor count and mentor companies                          |
| `v_participants_full`           | Participants joined with specialty, university and team               |
| `v_mentors_assignments`         | Mentors with active team counts and names                             |
| `v_teams_participant_breakdown` | Bachelor/Masters split per team                                       |
| `check_data_consistency()`      | Reports teams under 3 or over 6 members and unassigned active mentors |

None of these are used by the application; they are for manual SQL inspection.

## Seed data

Loaded by both `run_server.py` and `wsgi.py` on every start (idempotent, `ON CONFLICT DO NOTHING`):

| File                                       | Rows                      | Loaded into                                                                                                                                                                                      |
| ------------------------------------------ | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `backend/database/seeds/universities.json` | 41                        | `universities` (`is_seed = true`)                                                                                                                                                                |
| `backend/database/seeds/specialties.json`  | 18                        | `specialties` (`is_seed = true`)                                                                                                                                                                 |
| The file `MENTORS_SEED_FILE` names         | dev 3, staging 20, prod 0 | `mentors`. An entry with no `password` gets a NULL `password_hash`, which can't log in until the mentor sets one through forgot password; bare picture filenames become `/mentorPictures/<file>` |

The mentor seed is personal data, so the real one never sits in the repo or the image. Development and testing default to `backend/database/seeds/mentors.dev.json` (three fake `@mentor.test` mentors, password `mentor123`). Production config has no default: in the cluster the seed is the SOPS-encrypted Secret `fmi-codes-mentors-seed` (`infra/k8s/overlays/staging/secrets/mentors-seed.enc.yaml` holds staging's 20 mentors, `infra/k8s/secrets/mentors-seed.enc.yaml` prod's empty list until the 2027 roster), mounted into the backend at `/etc/fmi-codes/mentors/mentors.json`. Unset, missing or unreadable, the backend logs it and seeds nobody. Seeding only inserts, so editing the Secret never changes a mentor that already exists ([Secrets](runbook/secrets.md#mentor-seed)).

Read at request time (not stored in the DB):

| File                                                     | Served by                                      |
| -------------------------------------------------------- | ---------------------------------------------- |
| `backend/database/seeds/regulations.json` (13 Q&A pairs) | `GET /api/regulations`                         |
| `backend/database/seeds/rankings.json` (21 rows)         | `GET /api/ranking` (legacy, unused by the SPA) |

`schema.sql` also inserts 6 universities, 8 specialties and one `hackathon_events` row of its own.

## Schema management

- `backend/database/schema.sql` is the authoritative, current schema. Fresh environments apply it directly: Postgres `initdb` runs it in Docker Compose and k3s (mounted as `01_schema.sql` / the `postgres-initdb` ConfigMap), and the e2e test fixture applies it once per session, then replays every migration file so an older test database catches up.
- `backend/database/migrations/NNN_name.sql` are deltas for databases created before those changes. `python -m database.migrate` (from `backend/`) applies every file not yet recorded in `schema_migrations`, in number order, each in its own transaction with its record ([ADR-007](adr/007-recorded-migrations-runner.md)). When it applied anything it then deletes the Redis caches (`cache:*`, version counters kept), so no pod serves pre-migration rows until a TTL runs out. With Redis off it skips this; with Redis down it logs a warning and still succeeds. On k3s it runs automatically as the backend's initContainer on every rollout, and on demand through **Actions → Migrate database** (see [Deployment](deployment.md#database-migrations)).
- Rules for a migration file: the next unused three-digit number, lowercase name (`017_add_x.sql`), safe to re-run (`IF NOT EXISTS`, `ON CONFLICT`, ...), no `BEGIN`/`COMMIT` and **backward compatible with the release before it**. The previous release's pods keep serving on the migrated schema until the rollout replaces them, and a rollback runs that code again ([Rollouts](deployment.md#rollouts)). Add before you take away: a new column gets a default or is nullable, and a column or table the old code reads is dropped or renamed only in a later release, after no deployed code uses it. Nothing checks this; the reviewer does. `tests/test_migrate.py` enforces the naming and transaction rules; the e2e suite applies every file against a fresh `schema.sql` database.
- `schema_migrations` (`filename` primary key, `applied_at`) is created by the runner, not by `schema.sql`. The first run on a database without it, a fresh `schema.sql` one included, runs every file and records it; on a database that is already current each file is a no-op.
- `016_email_verification.sql` adds `participants.email_verified` with `DEFAULT TRUE` (so existing participants are grandfathered as verified) and then switches the default to false for new rows. It is safe to re-run, and `schema.sql` uses the same two statements.
- `017_feature_flags.sql` creates `feature_flags` and inserts its three rows as false with `ON CONFLICT DO NOTHING`, so it never overwrites a value the admin has set. False matches the old `REGISTRATION_OPEN`, `RANKINGS_LIVE` and `MENTORS_STAY_TUNED` ConfigMap values in every environment, so deploying it changes nothing visible.
- `018_masters_two_years.sql` replaces `participants_course_check` so a Masters course is only `Masters 1st Year` or `Masters 2nd Year`. It does not rewrite stored courses: if a participant already holds `Masters 3rd Year` to `Masters 6th Year`, the migration fails and the rollout stops until those rows are fixed by hand.
- `019_mentor_pictures_webp.sql` points seeded mentors at the WebP photos the frontend serves: `picture_url` `/static/mentorPictures/<name>.jpg|jpeg|png` becomes `/mentorPictures/<name>.webp` and `picture_filename` follows. Other paths and URLs are left alone, so it is safe to re-run.
- `020_preferences_open.sql` replaces `feature_flags_name_check` to allow `preferences_open` and inserts it as false with `ON CONFLICT DO NOTHING`, so after the deploy nobody can rank until the admin opens it, and a re-run keeps a value the admin has set.
- Most statements use `IF NOT EXISTS`, but the `CREATE TRIGGER` statements do not, so running `schema.sql` a second time against an existing database fails partway. Treat it as a create-once script.
- On k3s the schema and DB password are baked into the Postgres PVC at first boot. Editing `schema.sql` does not migrate a running database.

## Concurrency rules

- Every change to team membership or registration state runs inside one transaction that first takes `pg_advisory_xact_lock(1)`, then row-locks what it touches with `SELECT ... FOR UPDATE`.
- Saving matching results takes `pg_advisory_xact_lock(2)`, a separate key so it never contends with team mutations.
- Preference writes lock the owning team or mentor row so a double submit cannot interleave.
- A ranking save reads `preferences_open` with `FOR SHARE` as the first statement of its transaction (`feature_flag_service.is_enabled_locked`), so a switch or schedule apply waits for the save to commit, and a save started during one waits and then sees the new value. A schedule that has come due counts as applied.
- Flag writes and schedule applies lock the `feature_flags` row (`SELECT ... FOR UPDATE`); a reader that loses the race to apply a due schedule waits, re-checks and finds nothing due, so a scheduled change is applied and announced once.
- UNIQUE constraints (email, faculty number, team name, join code, join request pair) are the final guard against races.

## Backups

None are automated. The Postgres PVC is the source of truth on the cluster.
