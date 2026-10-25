# FMI{Codes} 2026

The **FMI{Codes} hackathon platform**: one web app for participants, mentors and the organizers. Participants register, form teams (join by code or browse-and-apply) and land on the registration queue. Mentors publish their profiles and rank teams. An admin runs a Gale-Shapley matching pass that gives every team 2-3 mentors (never more than 3) from their mutual preferences, then enters final scores that publish to a live leaderboard.

## Documentation

The full documentation is published at **https://fss-fmi.github.io/fmi-codes-website-2026/**. The source is the Markdown in [`docs/`](docs/):

| Doc                                          | What it covers                                                     |
| -------------------------------------------- | ------------------------------------------------------------------ |
| [docs/architecture.md](docs/architecture.md) | Components, request flow, matching algorithm, key decisions        |
| [docs/onboarding.md](docs/onboarding.md)     | Get it running locally, run tests, make a change                   |
| [docs/testing.md](docs/testing.md)           | Test layers, fixtures, mocking boundary, CI                        |
| [docs/deployment.md](docs/deployment.md)     | How a change reaches staging and prod (summary of the k3s runbook) |
| [docs/runbook.md](docs/runbook.md)           | Full operator runbook for the cluster                              |
| [docs/glossary.md](docs/glossary.md)         | Domain terms: teams, queue, captain, preferences, matching         |
| [docs/api.md](docs/api.md)                   | Every REST endpoint with auth, request and response shapes         |
| [docs/data.md](docs/data.md)                 | Database schema, ER diagram, seeds, migrations                     |
| [docs/user-guide.md](docs/user-guide.md)     | How participants, mentors and admins use the site                  |
| [docs/adr/](docs/adr/)                       | Architecture Decision Records                                      |

Preview the site locally with `pip install -r docs/requirements.txt` then `mkdocs serve`.

**Stack:** Flask 3 / Python 3.12 (Gunicorn in prod) · PostgreSQL 16 · Redis (rate limiting, JWT revocation, caches) · React 19 + TypeScript + Vite + Tailwind SPA. Deployed to a self-hosted **k3s** cluster with a staging/prod split (Kustomize + SOPS + Flux GitOps).

---

## Repo layout

```
backend/     Flask API — app/ (routes, services, utils), database/ (schema.sql, migrations, seeds),
             config.py, run_server.py (dev), wsgi.py (gunicorn), Dockerfile
frontend/    React + Vite SPA — src/, vite.config.ts, nginx.conf, Dockerfile
infra/k8s/   Full cluster deployment — scripts/, base/, overlays/{prod,staging}, helm-values/, flux/
docs/        All documentation (published to GitHub Pages via mkdocs.yml), incl. runbook.md
dev.py       One-command local dev: backend hot-reload + frontend HMR together
docker-compose.dev.yml   Local full stack in Docker (single Redis, hot reload)
docker-compose.yml       Prod-like stack (Redis Sentinel HA — for exercising failover locally)
.env.example             Environment template — copy to .env
```

---

## Local development

**1. Configure env**

```bash
cp .env.example .env
```

Fill in `SECRET_KEY`, `JWT_SECRET_KEY`, `DB_PASSWORD`, and `ADMIN_PASSWORD_HASH` (the file has the generator commands inline). Everything else has a sane local default. `.env` is gitignored.

**2. Pick a way to run it**

| Command                                      | What you get                                                                                                                                                                                               |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `python dev.py`                              | Backend (`:5001`, Flask reload) + frontend (`:5173`, Vite HMR) together. Needs Python 3.12, Node 22, and a reachable Postgres. **The daily driver.**                                                       |
| `docker compose up --build`                  | The whole stack in Docker — Postgres + single Redis + backend + frontend, all hot-reloading. Only needs Docker.                                                                                            |
| `docker compose -f docker-compose.yml up -d` | Prod-like stack with the Redis Sentinel topology (1 master + 2 replicas + 3 sentinels). Use it to rehearse a failover: `docker kill fmi-codes-redis-master` and watch the app follow the promoted replica. |

API → **http://localhost:5001** (JSON only, every route lives under `/api`), SPA dev server → **http://localhost:5173** (proxies `/api` and `/static` to the backend). Seed data (universities, specialties, mentors) loads automatically on first backend start.

**Database (for `python dev.py`)** — create it once and apply the authoritative schema; `schema.sql` already folds in every migration, so a fresh setup needs nothing from `database/migrations/`:

```bash
psql -U postgres -c "CREATE DATABASE fmi_hackathon_2026;"
psql -U postgres -d fmi_hackathon_2026 -f backend/database/schema.sql
```

---

## Tests

```bash
# Run from the repo root (tests/ lives there, not under backend/)
# Backend unit tests: no DB or .env needed
pytest tests/ --ignore=tests/e2e -v
# Backend API integration tests: need a reachable Postgres with an existing
# fmi_hackathon_2026_test database (schema is applied automatically; the suite
# skips itself if Postgres is unreachable). Override with TEST_DATABASE_URL.
pytest tests/e2e/ -v

# Frontend
cd frontend && npm test
```

---

## Environment variables

`.env.example` is the complete list with inline notes — copy it and fill in the blanks. The ones with no safe default that **must** be set:

| Variable                       | Notes                                                                                    |
| ------------------------------ | ---------------------------------------------------------------------------------------- |
| `SECRET_KEY`, `JWT_SECRET_KEY` | Flask/JWT signing. Production **hard-fails at startup** if unset or weak.                |
| `ADMIN_PASSWORD_HASH`          | bcrypt hash of the admin password (never the plaintext). Production hard-fails if unset. |
| `DB_PASSWORD`                  | Postgres password.                                                                       |

Everything else (mail, feature flags, contact links, Redis timeouts, pool sizes) has a default and is optional for local dev. Redis is optional entirely — leave every `REDIS_*` unset and the app degrades gracefully (in-memory rate limiting, DB/file fallbacks), though token revocation is effectively off without a shared Redis, so configure it in production.

---

## Deployment (k3s: staging + prod)

The app is deployed to a self-hosted single-node **k3s** cluster. Staging and prod live on the same node, isolated by namespace, built from one shared `base/` via Kustomize overlays:

|           | prod                             | staging                           |
| --------- | -------------------------------- | --------------------------------- |
| namespace | `fmi-codes`                      | `fmi-codes-staging`               |
| host      | `fmicodes.com` (443)             | `staging.fmicodes.com` (8443)     |
| TLS       | Let's Encrypt (browser-trusted)  | self-signed (`curl -k`)           |
| deploy    | manual promote (human-merged PR) | automatic on every push to `main` |

Images are built and pushed to Docker Hub (`fssfmi/fmi-codes-backend`, `fssfmi/fmi-codes-frontend`) by `.github/workflows/docker-cd.yaml` on each push to `main`. Flux, running **inside** the cluster, pulls: it auto-bumps the **staging** overlay to the newest tag; **prod** only moves when the `promote-to-prod` workflow opens a PR and a human merges it.

### Stand it up on a fresh Linux server

The full step-by-step runbook — with per-phase verification, secret rotation, GitOps wiring, and teardown — is **[`docs/runbook.md`](docs/runbook.md)**. The short version:

**Prerequisites**

- Debian/Ubuntu Linux (the scripts are apt + bash; k3s is Linux-native).
- For **prod**: a public DNS A-record for `fmicodes.com` → the server's IP, resolving _before_ you deploy ingress (Let's Encrypt verifies it over HTTP-01). For **staging** a hosts-file entry is enough.
- The **age private key** for the environment you're deploying (SOPS decrypts the committed secrets with it). Generate/obtain per the runbook's Phase 5.

**Bring it up** — one front-door script runs the whole sequence (tools → k3s → Postgres/Redis → app → ingress) in order:

```bash
./bootstrap.sh              # staging (the default)
./bootstrap.sh --env prod   # production — deliberate opt-in
```

It's idempotent and resumable (`--from N`). Flux (continuous deploy) is opt-in: `bash infra/k8s/scripts/init-linux.sh --with-flux` after a one-time SSH deploy-key setup.

### What changes to hit _your own_ cluster

Runtime config is split in two — this is what you edit to point the deployment at your infrastructure:

- **Non-secret config → the `fmi-codes-backend-config` ConfigMap.** Keys: `FLASK_ENV`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `REDIS_SENTINELS`, `REDIS_MASTER_NAME`, `REDIS_URL`, `FRONTEND_ORIGIN`, `MENTORS_STAY_TUNED`, `REGISTRATION_OPEN`, `RANKINGS_LIVE`. Global values live in `infra/k8s/base/app/backend.yaml`; per-env overrides in `infra/k8s/overlays/<env>/backend-config-patch.yaml`. Change one live with `bash infra/k8s/scripts/apply-config.sh <KEY> <VALUE>` (then commit the source YAML too).
- **App secrets → SOPS-encrypted `Secret` (`fmi-codes-app`).** Keys: `SECRET_KEY`, `JWT_SECRET_KEY`, `ADMIN_PASSWORD_HASH`, `MAIL_PASSWORD`, `DISCORD_BUG_WEBHOOK_URL`. Edit with `sops infra/k8s/secrets/secrets.enc.yaml` (prod) or `sops infra/k8s/overlays/staging/secrets/secrets.enc.yaml` (staging), or rotate one key with `bash infra/k8s/scripts/rotate-secret.sh <KEY>` (prompts for the value; never pass it as an argument). Per-secret rotation guide: [docs/runbook.md](docs/runbook.md#rotate-a-secret).
- **DB / Redis passwords** are generated in-cluster by `deploy-stateful.sh` and never committed (they're coupled to the datastore PVC). Rotate them without data loss with `bash infra/k8s/scripts/rotate-datastore-password.sh db|db-admin|redis`.

Forking this to a different domain or registry means updating the hostnames (`base/ingress/ingress.yaml`, `overlays/*/ingress/*`, and `FRONTEND_ORIGIN`), the image names (`base/app/*.yaml`, `overlays/*/kustomization.yaml`, `docker-cd.yaml`, `flux/image-automation.yaml`), the age recipients in `.sops.yaml`, and the Flux git URL/deploy key. Details in the runbook.

---

## How it works

### Teams & registration queue

A participant who creates a team becomes its **captain** and gets a unique `join_code`. Others join by entering that code, or by browsing `/browseTeams` and applying for the captain to accept. Teams auto-activate at 3 members, auto-deactivate below 3, and cap at 6. The first 18 active teams are auto-**registered**; the rest sit in a numbered queue, and when a registered team drops out the first queued team is promoted. All queue mutations take `pg_advisory_xact_lock(1)` for concurrency safety.

### Mentors & Gale-Shapley matching

Mentors are seeded from `backend/database/seeds/mentors.json` and shown on `/mentors`. Captains rank exactly 3 mentors; mentors rank exactly 3 registered teams. An admin triggers `POST /api/admin/run-matching`, which runs in two phases:

1. **Gale-Shapley (mentor-proposing, many-to-many).** Each team holds at most 3 mentors, each mentor at most 3 teams. Teams keep the mentors they ranked highest and bump the rest.
2. **Greedy fill.** Any team still below 3 mentors is topped up with the least-loaded mentors that have room, even ones the team did not rank.

The goal is 2-3 mentors per team and never more than 3. If there are not enough mentor slots, the run succeeds with a warning naming how many teams came up short. Results go to `team_mentors`; teams and mentors only see them after the admin confirms. Full walkthrough in [docs/architecture.md](docs/architecture.md#matching-algorithm).

### Auth

JWT (HS256, 3-day expiry) issued on login and set as an **httpOnly `token` cookie** (`SameSite=Lax`, `Secure` in production). The backend also accepts `Authorization: Bearer <token>` for tooling. Tokens are validated by the `@token_required` decorator family. Logout and password changes revoke the token's `jti` in a Redis blocklist; a password change or reset also bumps a per-user `tokens_valid_from` epoch that kills every older session. Password reset uses a one-hour emailed link.

### Bug reporting

The bug bubble on every page posts to `/api/bug-report`, which forwards to Discord via `DISCORD_BUG_WEBHOOK_URL` (fire-and-forget on a bounded thread pool, never blocks the request). No webhook configured means the report is dropped with a logged warning. Reports from logged-in users carry their name and email; everyone else, including visitors on the registration page, reports anonymously.

---

## Default credentials

| Role   | Email                                       | Password                                                                                       |
| ------ | ------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Admin  | `ADMIN_EMAIL` (default `admin@fmicodes.bg`) | Whatever plaintext you bcrypt-hashed into `ADMIN_PASSWORD_HASH`. There is no built-in default. |
| Mentor | see `backend/database/seeds/mentors.json`   | `mentor123` (the seed loader's default when an entry has no `password`)                        |
