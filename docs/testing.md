# Testing

How the test suite is built and how to extend it. For setup and single-test commands see [Onboarding](onboarding.md#running-tests); for the big-picture summary see [Architecture](architecture.md#testing-approach).

## Strategy

- The backend carries almost all of the testing weight. The riskiest logic (registration queue under concurrency, matching, auth and revocation, data leakage) is covered through real HTTP calls against a real PostgreSQL database.
- Pure logic with no I/O (the matching algorithm core, Redis helpers, JWT and bcrypt helpers) is unit tested directly.
- The frontend has six component test files (navbar height, login role picker, profile panels, Regulations chapter nav, config polling, Mission Control's SITE tab). Other UI behaviour is untested.
- There is no coverage tool configured (no `pytest-cov`, no Vitest coverage) and no coverage threshold.
- No browser end-to-end tests exist.

| Layer                   | Location                     | Tests | Needs                               |
| ----------------------- | ---------------------------- | ----- | ----------------------------------- |
| Backend unit            | `tests/*.py`                 | 439   | Nothing (Redis optional)            |
| Backend API integration | `tests/e2e/*.py`             | 208   | PostgreSQL test DB (Redis optional) |
| Frontend component      | `frontend/src/**/*.test.tsx` | 27    | Node only                           |

Counts are `def test_` occurrences, so parametrised tests run more cases than listed.

## Test layers

### Backend unit tests (`tests/`)

| File                           | What it covers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_matching.py`             | `_run_algorithm`: mutual matches, capacity limits (`TEAM_CAPACITY`, `MENTOR_CAPACITY`), displacement, greedy fill, underfill warnings                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `test_auth_service.py`         | bcrypt hashing, JWT generation and decoding, expiry                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `test_redis_client.py`         | Sentinel parsing, limiter storage URI, jittered TTLs, fail-open helpers (get, set, delete, incr)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `test_cache_services.py`       | Cache hit/miss/corrupt paths for mentors, rankings, regulations; fallback when Redis is down                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `test_health_endpoints.py`     | `/api/health` and `/api/health/ready` across DB/Redis states                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `test_limiter_storage.py`      | Rate-limiter storage wiring                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `test_client_ip.py`            | Limiter keys on the address the one trusted proxy forwarded: separate buckets per client, forged `X-Forwarded-For` entries ignored, rankings polling exempt                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `test_metrics_endpoint.py`     | `/metrics` is exposed                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `test_metrics_multiprocess.py` | Request metrics, each app in its own process: counters from separate worker processes sum into one series, unknown URLs share one `url_rule` label, health probes are not counted (with and without the shared folder), `gunicorn.conf.py` defaults the folder, removes only its `*.db` files and marks exited workers dead                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `test_team_service.py`         | Join code format and the 6 / 18 / 3 business constants                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `test_email_verification.py`   | Verification email contents and SMTP failure handling; the `REQUIRE_EMAIL_VERIFICATION` gate decorator                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `test_bug_report_service.py`   | Slack and Discord bug-report payloads, Slack escaping (no `<!channel>` pings) and length limits, which webhooks get a report, send failures never raise                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `test_feature_flags.py`        | Flag service: Redis cache hit, miss, corrupt entry, TTL capped by a pending schedule, a switch during a read never leaves the old value cached; due schedules applied with one notice, same-value schedules cleared quietly; switch, schedule (past and current value refused, pointing to cancel when a schedule is pending) and cancel; the event feed sender (log only without a webhook, never raises); `/api/config` shape, 503 and no rate limit; the admin flag routes (roles, validation, 404 for unknown flags, offset times)                                                                                                                                                                                                       |
| `test_migrate.py`              | Migration runner: file naming and ordering, no transaction control in committed migrations, Slack reporting modes, message escaping and truncation, connection settings, waiting for Postgres on startup                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `test_slack_pr_feed.py`        | Slack PR feed (`.github/scripts`): drafts stay silent, one parent per PR (racing duplicates delete themselves), thread replies only on real state changes, reviews and comments once each, the opening commit list (up to the parent's head, once per thread, finished by a re-run), new-commit replies (by ancestry, force pushes, cancelled runs covered by the next push, waiting for the ready run, lagging commit lists, nothing pushed in draft listed), only people who can push, Flux one-liners (re-rendered on new tags, CI verdict kept on re-delivery), escaping, Slack client paging, retries and `Retry-After` parsing                                                                                                         |
| `test_slack_ci_alerts.py`      | Slack CI alerts (`.github/scripts`): failed-step log tail (skips `continue-on-error` errors, strips frames, redacts credentials and private keys, caps size), one alert and one thread reply per run attempt (pipeline wording with the commit), Flux one-liner edits, passed-again detection, only runs from people who can push, fork PR lookup, GitHub token never sent on redirects                                                                                                                                                                                                                                                                                                                                                      |
| `test_flux_bump_gate.py`       | Flux bump gate (`.github/scripts`): reads every `$imagepolicy` tag (and the real staging overlay's markers), titles from the tags; matching tags open or re-arm the PR, mismatched tags open nothing and disarm an open PR, a split release opens one PR once whole, a second release arriving while a PR is open, a deleted branch or one already on `main` does nothing, a missing file on `main` and auto-merge failures fail the run, the `gh` wrapper (404s, a fork's PR from a branch of the same name ignored)                                                                                                                                                                                                                        |
| `test_flux_relay.py`           | Flux Relay (`infra/k8s/base/flux-relay`): finding Flux's error post by object and message, one incident per object (repeat posts share it), recovery from `Ready` (new transition, seen unready, quiet period, current generation only), one thread reply plus a reaction on every post, deleted objects, restarts from the state ConfigMap, no Slack traffic without a post or a token, waiting events expiring and capped, per-route channels, the closest post winning over another cluster's identical one, a channel that is gone or a deleted first post, reactions spread over ticks with saved progress, health during a slow tick, the HTTP endpoint and that each relay Alert in `flux/notifications.yaml` mirrors its Slack Alert |

Scope: a single function or a single route with dependencies replaced. No database. Runs in seconds.

Add a test here when the logic has branches or edge cases you can drive with in-memory data, or when you need to simulate a dependency failing (Redis down, DB returning junk).

### Backend API integration tests (`tests/e2e/`)

These are not browser tests. They boot the real Flask app, point it at a real PostgreSQL database and call the API through Flask's test client.

| File                             | What it covers                                                                                                                                                                                                                                                                                 |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_auth_e2e.py`               | Register, login per role, logout revocation, `/me`, password change and reset flows, session epoch invalidation                                                                                                                                                                                |
| `test_teams_e2e.py`              | Team create/join/leave/kick/disband, join requests, auto-activation at 3, the 18-slot queue and promotion, public endpoints                                                                                                                                                                    |
| `test_admin_e2e.py`              | Registration console, preference status, run/confirm matching, scoring, rankings                                                                                                                                                                                                               |
| `test_security.py`               | Unauthenticated access, role escalation, IDOR between captains, data leakage (join codes, hashes, emails), SQL injection and XSS inputs, validation, feature flags, business-logic abuse                                                                                                       |
| `test_email_verification_e2e.py` | Verification tokens (single use, expiry, hash-only storage), resend, the team-action gate with the flag on and off, migration 016 grandfathering                                                                                                                                               |
| `test_migrate_e2e.py`            | Every committed migration applies on a `schema.sql` database and re-runs as a no-op; a failing file rolls back and stops; the advisory lock serialises runners                                                                                                                                 |
| `test_public_exposure_e2e.py`    | Scores hidden until `rankings_live`, "Other" university/specialty created only through registration, bug-report attribution from a valid session and both configured webhooks used                                                                                                             |
| `test_feature_flags_e2e.py`      | Admin-only flag routes; register, rankings, team scores and `/api/config` follow a switch on the next request; cache invalidation and Redis down; a schedule applies at its time with one notice; four concurrent readers apply a due schedule once; cancel, replace and the refused schedules |

Add a test here for anything that touches SQL, transactions, locking, auth guards or response shapes. Every new endpoint should get at least a happy path and a wrong-role test.

### Frontend (`frontend/src`)

Vitest with jsdom and Testing Library (`vite.config.ts` `test` block, setup in `src/test/setup.ts`). `src/pages/auth/ProfilePage.test.tsx` renders `ProfileContent` with a hand-built `AuthContext` value for each role. Follow that pattern: render the inner content component (not the `RequireAuth` wrapper) inside `MemoryRouter` and supply contexts directly. jsdom has no `matchMedia`, `ResizeObserver` or `IntersectionObserver`: stub them with `vi.stubGlobal`, as `LoginPage.test.tsx` does to flip the phone breakpoint mid-test and `VariantARulebook.test.tsx` does for reduced motion. jsdom never opens a `<dialog>`, so `SitePanel.test.tsx` queries the confirm buttons inside it with `hidden: true`; `ConfigContext.test.tsx` drives the 30 s poll with fake timers.

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

| Name                                                        | Scope             | What it does                                                                                                                                                                                                                                                                                          |
| ----------------------------------------------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `db_url`                                                    | session           | Skips the folder if Postgres is unreachable                                                                                                                                                                                                                                                           |
| `_schema_applied`                                           | session           | Runs `schema.sql` once if the `participants` table is missing, then every migration file (each is safe to re-run)                                                                                                                                                                                     |
| `seeds`                                                     | session           | Upserts one university, one specialty and three mentors (`alpha/beta/gamma@mentor.test`, password `mentor123`); returns their ids                                                                                                                                                                     |
| `flask_app`                                                 | session           | Real app on the test DB, rate limiting off, no event feed webhook, known admin credentials                                                                                                                                                                                                            |
| `clean_db`                                                  | autouse, per test | `TRUNCATE ... RESTART IDENTITY CASCADE` on participants, teams, requests, preferences, assignments and reset tokens; resets `matching_state` and the feature flags (registration open, rankings and roster off, no schedules); clears Redis cache keys. Universities, specialties and mentors survive |
| `client`                                                    | per test          | Fresh test client with an empty cookie jar                                                                                                                                                                                                                                                            |
| `set_flag(name, enabled)`                                   | per test          | Writes a feature flag straight to the DB and clears the flag cache; `clean_db` restores the defaults                                                                                                                                                                                                  |
| `register(client, n, seeds)`                                | helper            | Registers participant `n` with deterministic email and faculty number                                                                                                                                                                                                                                 |
| `register_and_token(...)`                                   | helper            | Same, returns the JWT from the `Set-Cookie` header                                                                                                                                                                                                                                                    |
| `register_extra_and_token(client, seeds)`                   | helper            | UUID-based filler participant for "just need another member" cases                                                                                                                                                                                                                                    |
| `login_token(client, email, pw, role)`                      | helper            | Logs in and returns the JWT                                                                                                                                                                                                                                                                           |
| `admin_token(flask_app)`, `mentor_token_for(flask_app, id)` | helper            | Mints tokens directly, no login round-trip                                                                                                                                                                                                                                                            |
| `bearer(token)`                                             | helper            | `{"Authorization": "Bearer ..."}`                                                                                                                                                                                                                                                                     |
| `new_client(flask_app)`                                     | helper            | A second client with its own cookie jar, for multi-user scenarios                                                                                                                                                                                                                                     |

Tests send tokens through the `Authorization` header so several users can share one client. The SPA uses the cookie; both paths go through the same `extract_token()`.

## Mocking

| Layer       | Real                                        | Replaced                                                                                 |
| ----------- | ------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Unit        | Flask app, route wiring, pure functions     | DB helpers (MagicMock), Redis (a `FakeRedis` class or `monkeypatch`), env vars           |
| Integration | Flask app, PostgreSQL, SQL, locks, triggers | Rate limiting (disabled), SMTP, Discord and Slack (not configured, so sends are skipped) |

The boundary sits at the database: anything whose correctness depends on SQL semantics, transactions or constraints must be tested against real Postgres, because the mocks cannot reproduce locking or uniqueness races.

## CI

`.github/workflows/ci.yaml` runs on every pull request (concurrent runs on the same ref cancel each other):

| Job                  | Steps                                                                                                                                                                              |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit & E2E tests     | Python 3.12, Postgres 16 and Redis 7 service containers, `pytest tests/ --ignore=tests/e2e`, then `pytest tests/e2e/` with `TEST_DATABASE_URL` pointing at the service DB          |
| Lint                 | `ruff check .` (blocking), `ruff format --check .` (blocking), `npm install`, `npx eslint .`, `npx tsc -p tsconfig.app.json --noEmit`                                              |
| Flux kustomize build | `kubectl kustomize infra/k8s/flux`                                                                                                                                                 |
| Prometheus rules     | `bash infra/k8s/scripts/test-prometheus-rules.sh`: extracts the `fmi-codes` rules from the kps HelmRelease and runs `promtool test rules` on `infra/k8s/base/observability/tests/` |

The jobs run in parallel. CI does not run on pushes to `main`, and it does not run the frontend Vitest suite.

## Known gaps

- Frontend tests are not part of CI; add `cd frontend && npm test` to the Lint job (or a new job) to gate them.
- No coverage measurement.
- `test_team_service.py` only checks constants and join codes; all queue logic is tested only at the integration layer.
- No tests for the email sender.
- No browser end-to-end tests, so bugs that live purely in the SPA (for example the admin EXPORT button reading a field the API never returns) are not caught.
