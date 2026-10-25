# Testing

How the test suite is built and how to extend it. For setup and single-test commands see [Onboarding](onboarding.md#running-tests); for the big-picture summary see [Architecture](architecture.md#testing-approach).

## Strategy

- The backend carries almost all of the testing weight. The riskiest logic (registration queue under concurrency, matching, auth and revocation, data leakage) is covered through real HTTP calls against a real PostgreSQL database.
- Pure logic with no I/O (the matching algorithm core, Redis helpers, JWT and bcrypt helpers) is unit tested directly.
- The frontend has one component test file. UI behaviour is otherwise untested.
- There is no coverage tool configured (no `pytest-cov`, no Vitest coverage) and no coverage threshold.
- No browser end-to-end tests exist.

| Layer                   | Location                     | Tests | Needs                               |
| ----------------------- | ---------------------------- | ----- | ----------------------------------- |
| Backend unit            | `tests/*.py`                 | 99    | Nothing (Redis optional)            |
| Backend API integration | `tests/e2e/*.py`             | 153   | PostgreSQL test DB (Redis optional) |
| Frontend component      | `frontend/src/**/*.test.tsx` | 3     | Node only                           |

Counts are `def test_` occurrences, so parametrised tests run more cases than listed.

## Test layers

### Backend unit tests (`tests/`)

| File                         | What it covers                                                                                                                                                                                           |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_matching.py`           | `_run_algorithm`: mutual matches, capacity limits (`TEAM_CAPACITY`, `MENTOR_CAPACITY`), displacement, greedy fill, underfill warnings                                                                    |
| `test_auth_service.py`       | bcrypt hashing, JWT generation and decoding, expiry                                                                                                                                                      |
| `test_redis_client.py`       | Sentinel parsing, limiter storage URI, jittered TTLs, fail-open helpers                                                                                                                                  |
| `test_cache_services.py`     | Cache hit/miss/corrupt paths for mentors, rankings, regulations; fallback when Redis is down                                                                                                             |
| `test_health_endpoints.py`   | `/api/health` and `/api/health/ready` across DB/Redis states                                                                                                                                             |
| `test_limiter_storage.py`    | Rate-limiter storage wiring                                                                                                                                                                              |
| `test_metrics_endpoint.py`   | `/metrics` is exposed                                                                                                                                                                                    |
| `test_team_service.py`       | Join code format and the 6 / 18 / 3 business constants                                                                                                                                                   |
| `test_email_verification.py` | Verification email contents and SMTP failure handling; the `REQUIRE_EMAIL_VERIFICATION` gate decorator                                                                                                   |
| `test_bug_report_service.py` | Slack and Discord bug-report payloads, Slack escaping (no `<!channel>` pings) and length limits, which webhooks get a report, send failures never raise                                                  |
| `test_migrate.py`            | Migration runner: file naming and ordering, no transaction control in committed migrations, Slack reporting modes, message escaping and truncation, connection settings, waiting for Postgres on startup |

Scope: a single function or a single route with dependencies replaced. No database. Runs in seconds.

Add a test here when the logic has branches or edge cases you can drive with in-memory data, or when you need to simulate a dependency failing (Redis down, DB returning junk).

### Backend API integration tests (`tests/e2e/`)

These are not browser tests. They boot the real Flask app, point it at a real PostgreSQL database and call the API through Flask's test client.

| File                             | What it covers                                                                                                                                                                           |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_auth_e2e.py`               | Register, login per role, logout revocation, `/me`, password change and reset flows, session epoch invalidation                                                                          |
| `test_teams_e2e.py`              | Team create/join/leave/kick/disband, join requests, auto-activation at 3, the 18-slot queue and promotion, public endpoints                                                              |
| `test_admin_e2e.py`              | Registration console, preference status, run/confirm matching, scoring, rankings                                                                                                         |
| `test_security.py`               | Unauthenticated access, role escalation, IDOR between captains, data leakage (join codes, hashes, emails), SQL injection and XSS inputs, validation, feature flags, business-logic abuse |
| `test_email_verification_e2e.py` | Verification tokens (single use, expiry, hash-only storage), resend, the team-action gate with the flag on and off, migration 016 grandfathering                                         |
| `test_migrate_e2e.py`            | Every committed migration applies on a `schema.sql` database and re-runs as a no-op; a failing file rolls back and stops; the advisory lock serialises runners                           |
| `test_public_exposure_e2e.py`    | Scores hidden until `RANKINGS_LIVE`, "Other" university/specialty created only through registration, bug-report attribution from a valid session and both configured webhooks used       |

Add a test here for anything that touches SQL, transactions, locking, auth guards or response shapes. Every new endpoint should get at least a happy path and a wrong-role test.

### Frontend (`frontend/src`)

Vitest with jsdom and Testing Library (`vite.config.ts` `test` block, setup in `src/test/setup.ts`). Today only `src/pages/auth/ProfilePage.test.tsx` exists. It renders `ProfileContent` with a hand-built `AuthContext` value for each role. Follow that pattern: render the inner content component (not the `RequireAuth` wrapper) inside `MemoryRouter` and supply contexts directly.

## Running tests

```bash
# Everything CI runs, from the repo root
pytest tests/ --ignore=tests/e2e -v
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fmi_hackathon_2026_test pytest tests/e2e/ -v

# Frontend (not run in CI)
cd frontend && npm test
```

Integration test database: the default URL is `postgresql://postgres:postgres@localhost:5432/fmi_hackathon_2026_test`. Create the database once (`psql -U postgres -c "CREATE DATABASE fmi_hackathon_2026_test;"`). The fixture applies `schema.sql` on first run. If Postgres is unreachable every test in `tests/e2e/` is skipped, not failed, so a green local run without Postgres proves nothing about that layer.

To reproduce CI exactly, run Postgres 16 and Redis 7 locally and export `REDIS_URL=redis://localhost:6379` for both layers.

## Writing a test

### Unit test with the DB patched out

`tests/conftest.py` provides:

- `app`: session-scoped app from `create_app("testing")` with `init_database` patched, so no pool is opened.
- `app_ctx`: pushes an app context.
- `client`: Flask test client.
- `mock_db`: patches `execute_query`, `execute_insert`, `execute_update` and `get_db_cursor` in `app.database` with MagicMocks.

```python
from unittest.mock import patch

def test_ready_returns_503_when_db_down(client):
    with patch("app.routes.api_routes.execute_query", side_effect=Exception("down")):
        rv = client.get("/api/health/ready")
    assert rv.status_code == 503
    assert rv.get_json()["db"] == "down"
```

Patch the name where it is **used** (for example `app.routes.api_routes.execute_query`), not only where it is defined, because route modules import the helpers directly.

### Pure-logic test (matching)

Call `_run_algorithm` with plain lists and dicts. No app context.

```python
from app.services.matching_service import _run_algorithm

def test_team_never_exceeds_three_mentors():
    teams = [1]
    mentors = [10, 11, 12, 13]
    mentor_prefs = {m: [1] for m in mentors}
    team_prefs = {1: {10: 1, 11: 2, 12: 3}}
    assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)
    assert len([m for t, m in assignments if t == 1]) == 3
```

### API integration test

Import helpers from `tests/e2e/conftest.py` and mark the module:

```python
import pytest
from tests.e2e.conftest import bearer, register_and_token

pytestmark = pytest.mark.e2e

def test_create_team_makes_caller_captain(client, seeds):
    token = register_and_token(client, 1, seeds)
    rv = client.post("/api/teams", json={"team_name": "Alpha"}, headers=bearer(token))
    assert rv.status_code == 201
    me = client.get("/api/auth/me", headers=bearer(token)).get_json()["user"]
    assert me["is_captain"] is True
```

## Test data

`tests/e2e/conftest.py` fixtures and helpers:

| Name                                                        | Scope             | What it does                                                                                                                                                                                                         |
| ----------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `db_url`                                                    | session           | Skips the folder if Postgres is unreachable                                                                                                                                                                          |
| `_schema_applied`                                           | session           | Runs `schema.sql` once if the `participants` table is missing                                                                                                                                                        |
| `seeds`                                                     | session           | Upserts one university, one specialty and three mentors (`alpha/beta/gamma@mentor.test`, password `mentor123`); returns their ids                                                                                    |
| `flask_app`                                                 | session           | Real app on the test DB with `REGISTRATION_OPEN=True`, rate limiting off, known admin credentials                                                                                                                    |
| `clean_db`                                                  | autouse, per test | `TRUNCATE ... RESTART IDENTITY CASCADE` on participants, teams, requests, preferences, assignments and reset tokens; resets `matching_state`; clears Redis cache keys. Universities, specialties and mentors survive |
| `client`                                                    | per test          | Fresh test client with an empty cookie jar                                                                                                                                                                           |
| `register(client, n, seeds)`                                | helper            | Registers participant `n` with deterministic email and faculty number                                                                                                                                                |
| `register_and_token(...)`                                   | helper            | Same, returns the JWT from the `Set-Cookie` header                                                                                                                                                                   |
| `register_extra_and_token(client, seeds)`                   | helper            | UUID-based filler participant for "just need another member" cases                                                                                                                                                   |
| `login_token(client, email, pw, role)`                      | helper            | Logs in and returns the JWT                                                                                                                                                                                          |
| `admin_token(flask_app)`, `mentor_token_for(flask_app, id)` | helper            | Mints tokens directly, no login round-trip                                                                                                                                                                           |
| `bearer(token)`                                             | helper            | `{"Authorization": "Bearer ..."}`                                                                                                                                                                                    |
| `new_client(flask_app)`                                     | helper            | A second client with its own cookie jar, for multi-user scenarios                                                                                                                                                    |

Tests send tokens through the `Authorization` header so several users can share one client. The SPA uses the cookie; both paths go through the same `extract_token()`.

## Mocking

| Layer       | Real                                        | Replaced                                                                                 |
| ----------- | ------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Unit        | Flask app, route wiring, pure functions     | DB helpers (MagicMock), Redis (a `FakeRedis` class or `monkeypatch`), env vars           |
| Integration | Flask app, PostgreSQL, SQL, locks, triggers | Rate limiting (disabled), SMTP, Discord and Slack (not configured, so sends are skipped) |

The boundary sits at the database: anything whose correctness depends on SQL semantics, transactions or constraints must be tested against real Postgres, because the mocks cannot reproduce locking or uniqueness races.

## CI

`.github/workflows/ci.yaml` runs on every pull request (concurrent runs on the same ref cancel each other):

| Job                  | Steps                                                                                                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit & E2E tests     | Python 3.12, Postgres 16 and Redis 7 service containers, `pytest tests/ --ignore=tests/e2e`, then `pytest tests/e2e/` with `TEST_DATABASE_URL` pointing at the service DB |
| Lint                 | `ruff check .` (blocking), `ruff format --check .` (advisory), `npm install`, `npx eslint .`, `npx tsc -p tsconfig.app.json --noEmit`                                     |
| Flux kustomize build | `kubectl kustomize infra/k8s/flux`                                                                                                                                        |

The jobs run in parallel. CI does not run on pushes to `main`, and it does not run the frontend Vitest suite.

## Known gaps

- Frontend tests are not part of CI; add `cd frontend && npm test` to the Lint job (or a new job) to gate them.
- No coverage measurement.
- `test_team_service.py` only checks constants and join codes; all queue logic is tested only at the integration layer.
- No tests for the email sender.
- No browser end-to-end tests, so bugs that live purely in the SPA (for example the admin EXPORT button reading a field the API never returns) are not caught.
