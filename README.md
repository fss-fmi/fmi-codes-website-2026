# FMI Codes 2026 — Developer README

Hackathon management system for FMI Codes 2026. Handles participant registration, team formation, mentor selection, join-request flows, registration queue management, and the Gale-Shapley mentor-team matching algorithm.

**Stack:** Python 3.12 / Flask 3.0, PostgreSQL 16, vanilla JS + Jinja2 templates, JWT auth, Gunicorn (production).

---

## Local Setup

### Option 1 — Docker (recommended, no local installs needed)

Requires: [Docker Desktop](https://www.docker.com/products/docker-desktop/)

Docker runs the app under Gunicorn (4 workers × 8 threads) against a containerised PostgreSQL 16 instance. The database name inside Docker is `fmi_hackathon_2026` (no `_dev` suffix).

```bash
# First time — builds the app image and starts both containers (app + postgres)
docker compose up --build

# Subsequent runs (no code changes to rebuild)
docker compose up

# After making code changes — rebuild app image, DB volume is kept intact
docker compose up --build

# Wipe DB and start completely fresh (re-runs schema + migrations + seeds)
docker compose down -v && docker compose up --build
```

Docker reads variables from a `.env` file in the project root. Create one with at minimum:

```dotenv
DB_PASSWORD=postgres
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-here
ADMIN_EMAIL=admin@fmicodes.bg
ADMIN_PASSWORD=admin-pass
MENTORS_STAY_TUNED=false
```

App runs at **http://localhost:5001**

---

### Option 2 — Run locally (requires manual Postgres setup)

**Prerequisites:** Python 3.12+, PostgreSQL 16 running locally

**1. Clone and install dependencies**

```bash
git clone <repo-url>
cd fmi-codes-website-2026
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

**2. Set up the database**

Create the database and apply the base schema. The `schema.sql` already incorporates all migrations, so for a fresh setup this is all you need:

```bash
psql -U postgres -c "CREATE DATABASE fmi_hackathon_2026_dev;"
psql -U postgres -d fmi_hackathon_2026_dev -f database/schema.sql
```

The files under `database/migrations/` are incremental patches for upgrading an existing database. If you are starting from scratch, ignore them — `schema.sql` is authoritative.

**3. Create a `.env` file**

Create a `.env` file in the project root. Copy the block below and fill in your values:

```dotenv
# Flask
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-secret-key-here

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=fmi_hackathon_2026_dev
DB_USER=postgres
DB_PASSWORD=postgres

# JWT
JWT_SECRET_KEY=local-dev-jwt-secret-key
JWT_EXPIRY_DAYS=3

# Admin account (seeded on first run)
ADMIN_EMAIL=admin@fmicodes.bg
ADMIN_PASSWORD=admin-pass

# Email / SMTP (used for password reset emails)
MAIL_HOST=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_USE_TLS=true

# Discord webhook for bug reports (optional)
DISCORD_BUG_WEBHOOK_URL=

# Feature flags
# Set to true to show the "stay tuned" placeholder instead of the live mentors grid
MENTORS_STAY_TUNED=false
```

All variables have sensible defaults for local dev (see `config.py`) so the app will start without a `.env`, but having one makes overrides explicit and avoids surprises.

| Variable                  | Default                       | Notes                                                 |
| ------------------------- | ----------------------------- | ----------------------------------------------------- |
| `SECRET_KEY`              | `dev-secret-key-12345`        | Change in production                                  |
| `JWT_SECRET_KEY`          | falls back to `SECRET_KEY`    | Change in production                                  |
| `JWT_EXPIRY_DAYS`         | `3`                           | Token lifetime in days                                |
| `DB_HOST`                 | `localhost`                   |                                                       |
| `DB_PORT`                 | `5432`                        |                                                       |
| `DB_NAME`                 | `fmi_hackathon_2026_dev`      |                                                       |
| `DB_USER`                 | `postgres`                    |                                                       |
| `DB_PASSWORD`             | `postgres`                    |                                                       |
| `DATABASE_URL`            | built from above fields       | Override with a full connection string if needed      |
| `ADMIN_EMAIL`             | `admin@fmicodes.bg`           |                                                       |
| `ADMIN_PASSWORD`          | `admin-pass`                  | Change in production                                  |
| `MENTORS_STAY_TUNED`      | `false`                       | `true` shows coming-soon placeholder; `false` is live |
| `FLASK_ENV`               | `development`                 |                                                       |
| `MAIL_HOST`               | `smtp.gmail.com`              | SMTP server for password reset emails                 |
| `MAIL_PORT`               | `587`                         |                                                       |
| `MAIL_USERNAME`           | `fss.fmi.uni.sofia@gmail.com` | Sender address                                        |
| `MAIL_PASSWORD`           | _(none)_                      | **Must be set** — Gmail App Password recommended      |
| `MAIL_USE_TLS`            | `true`                        |                                                       |
| `DISCORD_BUG_WEBHOOK_URL` | _(none)_                      | If empty, bug reports are silently dropped            |
| `DB_POOL_MIN`             | `2`                           | Min connections per worker                            |
| `DB_POOL_MAX`             | `20`                          | Max connections per worker                            |
| `DB_POOL_TIMEOUT`         | `5`                           | Seconds to wait for a free connection                 |

**4. Start the server**

```bash
python run_server.py
```

App runs at **http://localhost:5001**. On startup, seed data (mentors, universities, specialties) from `database/seeds/` is automatically loaded into the DB.

---

## Main Functionalities

### Participant registration & authentication

Participants register with their name, email, university, specialty, and year. On login, a JWT (HS256, 3-day expiry) is issued and stored in `localStorage`. All protected routes validate this token via the `@token_required` decorator family.

Password reset is also supported — participants request a reset link by email; the service sends a time-limited token via SMTP.

### Team management

A participant creates a team and becomes its **captain**, receiving a unique `join_code`. The two supported paths to joining a team are:

- **Direct join** — enter the `join_code` on the Join Team page.
- **Browse & apply** — browse the available teams grid (`/browseTeams`), apply to one or more teams, and wait for the captain to accept or decline.

Teams auto-activate when they reach 3 members and auto-deactivate if they fall below 3. Max team size is 6.

### Registration queue

The first 18 active teams are automatically **registered** for the hackathon (`is_registered = TRUE`). Additional active teams sit in a numbered queue. When a registered team loses its status (members leave, disbands, etc.), the first queued team is automatically promoted. All queue mutations use `pg_advisory_xact_lock(1)` for concurrency safety.

Admins can manually register or unregister individual teams via the admin endpoints; manual unregistration does **not** trigger auto-promotion (explicit control).

### Mentors

All mentors are seeded from `database/seeds/mentors.json` and displayed on `/mentors` as a grid with technology-stack pills and availability chips. A feature flag (`MENTORS_STAY_TUNED`) can swap the live grid out for a coming-soon placeholder page.

Captains rank exactly 3 mentors as team preferences. Mentors also rank exactly 3 teams.

### Gale-Shapley matching

An admin triggers the matching manually via `POST /api/admin/run-matching`. The algorithm runs Hospital-Resident Gale-Shapley (mentor-proposing): each team can be matched to up to 3 mentors, each mentor to exactly 1 team. Results are persisted to the `team_mentors` table and visible on each team's Mentors page.

### Bug reporting

Any logged-in user can submit a bug report from the UI. Reports are forwarded to a Discord channel via a webhook (`DISCORD_BUG_WEBHOOK_URL`). Delivery is fire-and-forget using a bounded `ThreadPoolExecutor` (20 workers) so it never blocks the request thread. If the webhook URL is not configured, reports are silently dropped and a warning is logged.

---

## Project Structure

```
├── app/
│   ├── routes/             Route handlers (HTTP layer only — no business logic)
│   │   ├── pages.py
│   │   ├── auth.py
│   │   ├── teams.py
│   │   ├── mentors.py
│   │   └── api_routes.py
│   ├── services/           Business logic layer
│   ├── utils/              Shared utilities (auth decorators)
│   ├── templates/          Jinja2 HTML pages
│   │   ├── base.html / navbar.html / home.html
│   │   ├── auth/           login, registration, profile
│   │   ├── teams/          team, createTeam, joinTeam, browseTeams, teamMentors, teamSchedule, teamRegulations
│   │   ├── mentors/        mentors, mentorsStayTuned, chooseMentor, mentorDashboard, selectedMentors
│   │   ├── rankings/       ranking, teamRanking
│   │   └── admin/          matching dashboard
│   ├── static/             Images, company logos, mentor pictures
│   └── database.py         DB connection pool and query helpers
├── database/
│   ├── schema.sql          Authoritative table definitions (includes all changes)
│   ├── migrations/         Incremental patches for upgrading an existing DB
│   └── seeds/              JSON data — mentors, universities, specialties, rankings, regulations
├── config.py               Environment-based configuration (dev / prod / test)
├── run_server.py           Local dev entry point (Flask dev server, port 5001)
└── wsgi.py                 Production entry point (loaded by Gunicorn in Docker)
```

---

## Module Responsibilities

### Routes (`app/routes/`)

Routes are thin: validate the request, call a service, return JSON or render a template. No business logic lives here.

| File            | Responsibility                                                                                                              |
| --------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `pages.py`      | Serves HTML templates for public pages: home, schedule, regulations, rankings, admin matching dashboard                     |
| `auth.py`       | Participant register, login, logout, password reset request & confirm; issues JWTs                                          |
| `teams.py`      | Team create / join (code) / leave / disband / kick; browse available teams; join-request apply / accept / decline / cancel  |
| `mentors.py`    | Mentor listing, picture serving, team and mentor preference submission / retrieval                                          |
| `api_routes.py` | Universities & specialties lookups; rankings & regulations data; admin endpoints (matching, registration queue, bug report) |

### Services (`app/services/`)

| File                          | Responsibility                                                                                              |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `auth_service.py`             | JWT generation / validation, bcrypt password hashing, password reset token lifecycle                        |
| `email_service.py`            | Sends password reset emails via SMTP/TLS; reads `MAIL_*` config                                             |
| `team_service.py`             | Team CRUD, join-code generation, member management, registration queue, join-request flow                   |
| `mentor_service.py`           | Mentor profile management, picture serving, availability and technology data                                |
| `mentor_selection_service.py` | Enforces the "exactly 3 ranked mentors per team" preference rules                                           |
| `matching_service.py`         | Hospital-Resident Gale-Shapley — assigns mentors to teams from mutual ranked preferences                    |
| `ranking_service.py`          | Loads and serves team rankings from `seeds/rankings.json` with 60 s in-memory TTL cache                     |
| `regulations_service.py`      | Loads FAQ / regulations content from `seeds/regulations.json` with 60 s in-memory TTL cache                 |
| `participants_service.py`     | Participant lookups with joined specialty, university, and team data                                        |
| `bug_report_service.py`       | Fire-and-forget Discord webhook delivery (bounded `ThreadPoolExecutor`, stdlib only, never blocks requests) |

### Utils (`app/utils/`)

| File                 | Responsibility                                                                                                                                                    |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `auth_decorators.py` | Route decorators for JWT validation and role-based access: `@token_required`, `@participant_required`, `@captain_required`, `@mentor_required`, `@admin_required` |

### Database (`app/database.py`)

PostgreSQL `ThreadedConnectionPool` (min 2, max 20 per worker, 5 s timeout). Provides `execute_query()`, `execute_insert()`, and `execute_update()` helpers used by all services. Results come back as plain Python dicts via `RealDictCursor`. All team-mutating operations use `SELECT ... FOR UPDATE` row locks plus `pg_advisory_xact_lock(1)` for full concurrency safety.

---

## Database Migrations

`database/schema.sql` is the single source of truth for a fresh install. The files under `database/migrations/` are ordered incremental patches for upgrading an existing database without dropping it.

| File                                         | What it adds                                                      |
| -------------------------------------------- | ----------------------------------------------------------------- |
| `002_auth_and_preferences.sql`               | Auth tables and preference columns                                |
| `003_seed_flag_universities_specialties.sql` | `is_seed` flag on universities / specialties                      |
| `004_mentor_technologies.sql`                | `technologies TEXT[]` column on mentors                           |
| `005_course_bachelor_masters.sql`            | Bachelor / master course options                                  |
| `006_password_reset_cooldown.sql`            | Rate-limiting columns for password reset                          |
| `007_team_registration_queue.sql`            | `is_registered`, `registered_at`, `queue_position` on teams       |
| `008_mentor_availability.sql`                | `availability_text` column on mentors                             |
| `009_backfill_mentor_availability.sql`       | Idempotent back-fill for seeded mentor availability data          |
| `010_fix_availability_text_encoding.sql`     | Fixes encoding issues in availability text                        |
| `011_team_join_requests.sql`                 | `team_join_requests` table with status workflow + partial indexes |

---

## Default Credentials

| Role         | Email                             | Password     |
| ------------ | --------------------------------- | ------------ |
| Admin        | `admin@fmicodes.bg`               | `admin-pass` |
| Mentor (any) | see `database/seeds/mentors.json` | `mentor123`  |
