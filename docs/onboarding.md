# Onboarding

Get the platform running locally, run the tests and ship a change without asking anyone. For what the pieces are, read [Architecture](architecture.md) first.

## Prerequisites

| Tool                | Version    | Where the version comes from                              |
| ------------------- | ---------- | --------------------------------------------------------- |
| Python              | 3.12       | CI (`.github/workflows/ci.yaml`) and `backend/Dockerfile` |
| Node.js             | 22         | CI and `frontend/Dockerfile`                              |
| PostgreSQL          | 16         | CI service container and both compose files               |
| Docker + Compose v2 | any recent | Only for the Docker workflows                             |
| Redis 7             | optional   | The app runs without it                                   |

## Clone and install

```bash
git clone https://github.com/fss-fmi/fmi-codes-website-2026.git
cd fmi-codes-website-2026

# Python: the venv lives at the repo root (.lintstagedrc.js and pyrightconfig.json look for ./.venv)
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

# Root Node deps install Husky + lint-staged (the pre-commit hook)
npm install

# Frontend
cd frontend && npm install && cd ..

cp .env.example .env
```

`frontend/package-lock.json` is committed, so `npm install` (or `npm ci`) in `frontend/` gets the same dependency tree CI uses, and `frontend/Dockerfile` builds the production image with `npm ci` from it. Commit lockfile changes together with any `package.json` change. The root `package-lock.json` (Husky and lint-staged only) stays gitignored.

Keep vitest and its `@vitest/*` companions on the same major version. On 2026-10-12 vitest 4 left the tree mixed with the new vitest 5 packages and every fresh `npm install` crashed npm 10 with `Cannot read properties of null (reading 'edgesOut')`; moving to vitest 5 fixed it.

## Environment setup

`.env.example` documents every variable inline. For local development you must fill in:

| Variable                       | How to get a value                                                                              |
| ------------------------------ | ----------------------------------------------------------------------------------------------- |
| `SECRET_KEY`, `JWT_SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` (run twice)                          |
| `ADMIN_PASSWORD_HASH`          | `python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt(12)).decode())"` |
| `DB_PASSWORD`                  | Password of the Postgres role in `DB_USER`                                                      |

Also check:

- `DB_USER` defaults to `fmi_app` in `.env.example`. Either create that role or change it to `postgres`.
- `REGISTRATION_OPEN=false` in `.env.example`. Set it to `true` or participant registration returns 403 and the register page shows "REGISTRATION CLOSED".
- `MAIL_*` and `DISCORD_BUG_WEBHOOK_URL` are optional. Without them password-reset and verification mail and bug reports are dropped with a logged warning.
- `REQUIRE_EMAIL_VERIFICATION=false` in `.env.example`. Leave it off locally unless `MAIL_*` works, or no participant can create or join a team.
- Leave every `REDIS_*` blank to run without Redis (in-memory rate limiting, no token revocation).

## Running locally

### Option A: `python dev.py` (daily driver)

Needs a Postgres you can reach with the `DB_*` values. Create the database once and load the schema:

```bash
psql -U postgres -c "CREATE DATABASE fmi_hackathon_2026;"
psql -U postgres -d fmi_hackathon_2026 -f backend/database/schema.sql
```

Then:

```bash
python dev.py
```

- Backend: http://localhost:5001 (Flask with reload, bound to 127.0.0.1)
- Frontend: http://localhost:5173 (Vite HMR, proxies `/api` and `/static` to the backend)

Open the frontend URL. Seed universities, specialties and mentors load on backend start. Ctrl+C stops both.

### Option B: `docker compose up --build`

`.env.example` sets `COMPOSE_FILE=docker-compose.dev.yml`, so a bare `docker compose` uses the dev stack: Postgres (host port **5433**), a single Redis, the backend with source mounted and the Vite dev server. Postgres applies `schema.sql` on its first boot. Frontend at http://localhost:5173.

### Option C: prod-like stack

```bash
docker compose -f docker-compose.yml up -d
```

Runs the published `fssfmi/*:latest` images behind Nginx on port 80 with Redis Sentinel (1 master, 2 replicas, 3 sentinels). Use it to rehearse a Redis failover: `docker kill fmi-codes-redis-master`.

### Logging in

| Role        | How                                                                        |
| ----------- | -------------------------------------------------------------------------- |
| Participant | Register at `/registration` (needs `REGISTRATION_OPEN=true`)               |
| Mentor      | Any email from `backend/database/seeds/mentors.json`, password `mentor123` |
| Admin       | `ADMIN_EMAIL` with the plaintext you hashed into `ADMIN_PASSWORD_HASH`     |

On the login page pick the role tab first; the role is part of the login request.

## Running tests

Run everything from the **repo root**.

| What                          | Command                                                             |
| ----------------------------- | ------------------------------------------------------------------- |
| Backend unit tests (no DB)    | `pytest tests/ --ignore=tests/e2e`                                  |
| Backend API integration tests | `pytest tests/e2e/`                                                 |
| One file                      | `pytest tests/test_matching.py`                                     |
| One test by name              | `pytest -k "test_captain_leaving_disbands_team"`                    |
| Frontend tests                | `cd frontend && npm test`                                           |
| One frontend file             | `cd frontend && npx vitest run src/pages/auth/ProfilePage.test.tsx` |

The integration tests need an existing `fmi_hackathon_2026_test` database at `postgresql://postgres:postgres@localhost:5432/` (override with `TEST_DATABASE_URL`). The schema is applied automatically; if Postgres is unreachable the whole folder skips. See [Testing](testing.md) for fixtures and patterns.

## Lint and format

| Check       | Command                                                | Gate               |
| ----------- | ------------------------------------------------------ | ------------------ |
| Ruff lint   | `ruff check .`                                         | CI fails on errors |
| Ruff format | `ruff format .`                                        | CI reports only    |
| ESLint      | `cd frontend && npx eslint .`                          | CI fails           |
| Type check  | `cd frontend && npx tsc -p tsconfig.app.json --noEmit` | CI fails           |
| Prettier    | `npm run format` (root)                                | pre-commit only    |

The Husky pre-commit hook runs lint-staged: Prettier on html/js/json/css/md, ESLint + Prettier on frontend TS, `ruff check --fix` + `ruff format` on Python.

## Project structure

```
backend/
  app/routes/      HTTP layer (auth, teams, mentors, api_routes)
  app/services/    business logic: teams and queue, matching, auth, Redis, mail
  app/utils/       auth decorators, input validation
  app/static/      mentorPictures/ served at /static
  database/        schema.sql (authoritative), migrations/ (deltas), seeds/ (JSON)
  config.py        all settings, read from env
  run_server.py    dev entry point
  wsgi.py          Gunicorn entry point
frontend/src/
  pages/           one folder per area (auth, teams, mentors, admin, rankings, regulations)
  components/      shared UI, grouped by area
  context/         AuthContext, ConfigContext
  lib/api.ts       the only fetch wrapper
tests/             backend unit tests; tests/e2e/ = API integration tests
infra/k8s/         cluster manifests and scripts
docs/              this documentation (published to GitHub Pages by mkdocs.yml)
dev.py             runs backend + frontend together
bootstrap.sh       one-shot cluster installer
```

## Making a change

1. Branch off `main`.
2. Backend change: add or update a service function, keep the route thin, add a unit test in `tests/` and an integration test in `tests/e2e/` if it touches HTTP or SQL.
3. Schema change: edit `backend/database/schema.sql` **and** add the next numbered file in `backend/database/migrations/` for existing databases. Running clusters need the migration applied by hand.
4. New endpoint: update the frontend types in `frontend/src/types/` by hand and document it in the [API reference](api.md).
5. Commit (the pre-commit hook formats), open a PR. CI runs both test layers against real Postgres and Redis, both linters, the type check and a Flux kustomize build.
6. Merging to `main` builds images and auto-deploys **staging**. Production needs the `Promote to production` workflow plus a merged PR. See [Deployment](deployment.md).
7. Docs change: edit the page in `docs/` and preview the site with `pip install -r docs/requirements.txt` then `mkdocs serve` (http://127.0.0.1:8000). Merging to `main` publishes it to GitHub Pages.

## Common issues

**`Database connection attempt N/10 failed`** then a crash. The backend retries 10 times, 3 seconds apart, then exits. Check Postgres is up and the `DB_*` values (with compose, the host port is 5433).

**Log says `Database schema not found. Please run schema.sql manually.`** The pool connected but there is no `teams` table. Load `backend/database/schema.sql` into the database.

**Registration page says REGISTRATION CLOSED / API returns 403.** `REGISTRATION_OPEN` is false. Set it to `true` and restart the backend.

**Admin login returns 503 "Admin login not configured".** `ADMIN_PASSWORD_HASH` is empty.

**Production config refuses to start (`CRITICAL: SECRET_KEY ...`).** `FLASK_ENV=production` validates secrets and rejects the built-in dev values. Set real `SECRET_KEY`, `JWT_SECRET_KEY` and `ADMIN_PASSWORD_HASH`.

**`relation ... already exists` / trigger errors when re-running `schema.sql`.** The trigger statements are not idempotent. Load the schema only into an empty database.

**Port 5001 or 5173 in use.** Another dev server is running. Find it with `lsof -i :5001` (Windows: `netstat -ano | findstr 5001`).
