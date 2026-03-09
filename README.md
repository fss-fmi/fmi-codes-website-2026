# FMI Codes 2026 — Developer README

Hackathon management system for FMI Codes 2026. Handles participant registration, team formation, mentor selection, and the Gale-Shapley mentor-team matching algorithm.

**Stack:** Python 3.12 / Flask 3.0, PostgreSQL 16, vanilla JS + Jinja2 templates, JWT auth.

---

## Local Setup

### Option 1 — Docker (recommended, no local installs needed)

Requires: [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```bash
# First time — builds the app image and starts both containers (app + postgres)
docker compose up --build

# Subsequent runs (no code changes)
docker compose up

# After making code changes — rebuild app image, DB untouched
docker compose up --build

# Wipe DB and start completely fresh (re-runs schema + migrations)
docker compose down -v && docker compose up --build
```

App runs at **http://localhost:5001**

---

### Option 2 — Run locally (requires manual Postgres setup)

**Prerequisites:** Python 3.12+, PostgreSQL 16 running locally

**1. Clone and install dependencies**

```bash
git clone <repo-url>
cd fmi-codes-website-2026
pip install -r requirements.txt
```

**2. Set up the database**

Create the database and apply the base schema plus all migrations in order:

```bash
psql -U postgres -c "CREATE DATABASE fmi_hackathon_2026_dev;"
psql -U postgres -d fmi_hackathon_2026_dev -f database/schema.sql
psql -U postgres -d fmi_hackathon_2026_dev -f database/migrations/002_auth_and_preferences.sql
psql -U postgres -d fmi_hackathon_2026_dev -f database/migrations/003_seed_flag_universities_specialties.sql
psql -U postgres -d fmi_hackathon_2026_dev -f database/migrations/004_mentor_technologies.sql
```

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
ADMIN_PASSWORD=admin123

# Feature flags
# Set to true to show the "stay tuned" placeholder instead of the live mentors grid
MENTORS_STAY_TUNED=false
```

All variables have sensible defaults for local dev (see `config.py`) so the app will start without a `.env`, but having one makes overrides explicit and avoids surprises.

| Variable             | Default                    | Notes                                             |
| -------------------- | -------------------------- | ------------------------------------------------- |
| `SECRET_KEY`         | `dev-secret-key-12345`     | Change in production                              |
| `JWT_SECRET_KEY`     | falls back to `SECRET_KEY` | Change in production                              |
| `JWT_EXPIRY_DAYS`    | `3`                        | Token lifetime in days                            |
| `DB_HOST`            | `localhost`                |                                                   |
| `DB_PORT`            | `5432`                     |                                                   |
| `DB_NAME`            | `fmi_hackathon_2026_dev`   |                                                   |
| `DB_USER`            | `postgres`                 |                                                   |
| `DB_PASSWORD`        | `postgres`                 |                                                   |
| `DATABASE_URL`       | built from above fields    | Override with a full connection string if needed  |
| `ADMIN_EMAIL`        | `admin@fmicodes.bg`        |                                                   |
| `ADMIN_PASSWORD`     | `admin123`                 | Change in production                              |
| `MENTORS_STAY_TUNED` | `false`                    | `true` shows placeholder; `false` shows live grid |
| `FLASK_ENV`          | `development`              |                                                   |

**4. Start the server**

```bash
python run_server.py
```

App runs at **http://localhost:5001**. On startup, seed data (mentors, universities, specialties) from `database/seeds/` is automatically loaded into the DB.

---

## Project Structure Overview

```
├── app/
│   ├── routes/         Route handlers (HTTP layer only — no business logic)
│   ├── services/       Business logic layer
│   ├── utils/          Shared utilities (auth decorators)
│   ├── templates/      Jinja2 HTML pages (each fetches data via JS + API calls)
│   ├── static/         Images, company logos, mentor pictures
│   └── database.py     DB connection management and query helpers
├── database/
│   ├── schema.sql              Base table definitions
│   ├── migrations/             Incremental schema changes (apply in numeric order)
│   │   ├── 002_auth_and_preferences.sql
│   │   ├── 003_seed_flag_universities_specialties.sql
│   │   └── 004_mentor_technologies.sql
│   └── seeds/                  Seed data (mentors, universities, specialties, rankings, regulations)
├── config.py           Environment-based configuration (dev/prod/test)
├── run_server.py       Local dev entry point
└── wsgi.py             Production entry point (used by gunicorn in Docker)
```

---

## Module Responsibilities

### Routes (`app/routes/`)

| File            | Responsibility                                                                                      |
| --------------- | --------------------------------------------------------------------------------------------------- |
| `pages.py`      | Serves HTML templates for all public pages (home, schedule, regulations, rankings, admin dashboard) |
| `auth.py`       | Participant registration and login endpoints; issues JWTs                                           |
| `teams.py`      | Team create/join/leave/disband endpoints; validates captain permissions                             |
| `mentors.py`    | Mentor listing, picture serving, and mentor preference submission/retrieval                         |
| `api_routes.py` | Rankings, regulations, admin-only endpoints (preference status, trigger matching)                   |

Routes are thin — they validate the request, call a service, and return JSON or render a template. Business logic lives in services.

### Services (`app/services/`)

| File                          | Responsibility                                                                                         |
| ----------------------------- | ------------------------------------------------------------------------------------------------------ |
| `auth_service.py`             | JWT generation/validation, bcrypt password hashing                                                     |
| `team_service.py`             | Team CRUD, join-code generation, member and mentor lookups                                             |
| `mentor_service.py`           | Mentor registration, uniqueness checks, profile and picture management                                 |
| `mentor_selection_service.py` | Enforces the "exactly 3 ranked mentors per team" preference submission rules                           |
| `matching_service.py`         | Hospital-Resident Gale-Shapley algorithm — assigns mentors to teams based on mutual ranked preferences |
| `ranking_service.py`          | Loads and sorts team rankings from seed JSON                                                           |
| `regulations_service.py`      | Loads FAQ/regulations content from seed JSON                                                           |
| `participants_service.py`     | Participant lookups with joined specialty, university, and team data                                   |

### Utils (`app/utils/`)

| File                 | Responsibility                                                                                                                                                             |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `auth_decorators.py` | Route decorators for JWT validation and role-based access control (`@token_required`, `@participant_required`, `@captain_required`, `@mentor_required`, `@admin_required`) |

### Database (`app/database.py`)

PostgreSQL connection management. Provides `execute_query()`, `execute_insert()`, `execute_update()` helpers used by all services. Uses `RealDictCursor` so query results come back as plain Python dicts.

---

## Default Credentials

| Role         | Email                             | Password    |
| ------------ | --------------------------------- | ----------- |
| Admin        | `admin@fmicodes.bg`               | `admin123`  |
| Mentor (any) | see `database/seeds/mentors.json` | `mentor123` |
