"""E2E test fixtures — require a live PostgreSQL test database.

Tests under tests/e2e/ are automatically skipped when Postgres is not
reachable.  To run them:

    # Start local Postgres (or docker-compose.dev.yml)
    # Create the test database:
    psql -U postgres -c "CREATE DATABASE fmi_hackathon_2026_test;"

    # Then run (schema is applied automatically on first run):
    pytest tests/e2e/ -v

    # Or point at a different DB:
    TEST_DATABASE_URL=postgresql://user:pw@host/testdb pytest tests/e2e/
"""

import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import flask
import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

# ── Path bootstrap ─────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# ── DB constants ───────────────────────────────────────────────────────────
_DEFAULT_TEST_DB = "postgresql://postgres:postgres@localhost:5432/fmi_hackathon_2026_test"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DB)

SCHEMA_PATH = BACKEND_DIR / "database" / "schema.sql"

# ── Seed data used across all E2E tests ────────────────────────────────────
_UNIV_NAME = "E2E Test University"
_SPEC_NAME = "E2E Test Specialty"

# Three mentors are required so that preference-submission tests can rank exactly 3.
_MENTOR_SEEDS = [
    {"first": "Alpha", "last": "Mentor", "email": "alpha@mentor.test", "company": "AlphaCorp"},
    {"first": "Beta", "last": "Mentor", "email": "beta@mentor.test", "company": "BetaCorp"},
    {"first": "Gamma", "last": "Mentor", "email": "gamma@mentor.test", "company": "GammaCorp"},
]

DEFAULT_PW = "SecurePass1!"
DEFAULT_COURSE = "Bachelor 1st Year"

# ── Admin credentials (matched to flask_app config) ────────────────────────
ADMIN_EMAIL = "admin@fmicodes.bg"
ADMIN_PW = "test-admin-pw!"


# ═══════════════════════════════════════════════════════════════════════════
# Session fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def db_url():
    """Skip every test in this directory if Postgres is unreachable."""
    try:
        conn = psycopg2.connect(TEST_DB_URL, connect_timeout=3, cursor_factory=RealDictCursor)
        conn.close()
    except Exception as exc:
        pytest.skip(
            f"Test PostgreSQL not reachable ({exc}).\n"
            "Set TEST_DATABASE_URL or start PostgreSQL to run E2E tests."
        )
    return TEST_DB_URL


@pytest.fixture(scope="session")
def db_conn(db_url):
    """Session-level raw psycopg2 connection for schema setup and cleanup."""
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def _schema_applied(db_conn):
    """Apply the full schema SQL to the test database once per session.

    Skips if the schema is already present (idempotent).
    """
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_schema = 'public' AND table_name = 'participants'"
            ")"
        )
        if cur.fetchone()["exists"]:
            return  # schema already applied
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        cur.execute(sql)


@pytest.fixture(scope="session")
def seeds(db_conn, _schema_applied):
    """Seed test-specific lookup data once per session.  Returns IDs dict."""
    # Import here so BACKEND_DIR is already on sys.path
    from app.services.auth_service import hash_password

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO universities (name, city, country, is_seed) VALUES (%s, %s, %s, TRUE) "
            "ON CONFLICT (name) DO UPDATE SET is_seed = TRUE RETURNING id",
            (_UNIV_NAME, "Sofia", "Bulgaria"),
        )
        univ_id = cur.fetchone()["id"]

        cur.execute(
            "INSERT INTO specialties (name, is_seed) VALUES (%s, TRUE) "
            "ON CONFLICT (name) DO UPDATE SET is_seed = TRUE RETURNING id",
            (_SPEC_NAME,),
        )
        spec_id = cur.fetchone()["id"]

        pw_hash = hash_password("mentor123")
        mentor_ids = []
        for m in _MENTOR_SEEDS:
            cur.execute(
                """INSERT INTO mentors
                       (first_name, last_name, email, phone_number, company_name,
                        password_hash, status)
                   VALUES (%s, %s, %s, '0888000000', %s, %s, 'active')
                   ON CONFLICT (email) DO UPDATE SET status = 'active'
                   RETURNING id""",
                (m["first"], m["last"], m["email"], m["company"], pw_hash),
            )
            mentor_ids.append(cur.fetchone()["id"])

    return {"univ_id": univ_id, "spec_id": spec_id, "mentor_ids": mentor_ids}


@pytest.fixture(scope="session")
def flask_app(db_url, seeds):
    """Session-scoped Flask app pointing at the test PostgreSQL database."""
    # Override the DATABASE_URL env var before any config class is evaluated.
    os.environ["DATABASE_URL"] = db_url

    # Patch TestingConfig at the class level so init_database connects to the
    # right DB regardless of what was cached at import time.
    import config as _cfg
    from app.database import close_pool

    _cfg.TestingConfig.DATABASE_URL = db_url

    from app import create_app
    from app.services.auth_service import hash_password as _hash_pw

    app = create_app("testing")
    app.config.update(
        TESTING=True,
        SECRET_KEY="e2e-secret-key-that-is-at-least-32-bytes-long!",
        JWT_SECRET_KEY="e2e-jwt-secret-key-that-is-at-least-32-bytes-long!",
        JWT_EXPIRY_DAYS=3,
        DATABASE_URL=db_url,
        ADMIN_EMAIL=ADMIN_EMAIL,
        ADMIN_PASSWORD_HASH=_hash_pw(ADMIN_PW),
        REGISTRATION_OPEN=True,
        # RATELIMIT_ENABLED already False via TestingConfig — set again to be safe
        RATELIMIT_ENABLED=False,
        DB_POOL_MIN=1,
        DB_POOL_MAX=5,
        DB_POOL_TIMEOUT=5,
    )

    yield app

    close_pool()


# ═══════════════════════════════════════════════════════════════════════════
# Per-test fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def clean_db(db_conn, flask_app):
    """Truncate all entity tables before each E2E test.

    Universities, specialties, and mentors are deliberately preserved —
    they're seeded once per session.  The matching_state row is reset to
    is_confirmed=FALSE.
    """
    _wipe_entities(db_conn)
    _reset_caches()
    yield
    # Post-test wipe is optional but keeps the DB tidy between runs.
    _wipe_entities(db_conn)
    _reset_caches()


def _wipe_entities(conn):
    """Truncate all per-test entity tables atomically.

    TRUNCATE ... CASCADE:
    - Bypasses all row-level triggers (including trig_prevent_team_deletion),
      avoiding the "Cannot delete team with active participants" exception.
    - Handles circular FKs (participants ↔ teams) without manual NULL-outs.
    - Cascades to referencing tables (team_join_requests, team_mentors, etc.)
      so explicit ordering is unnecessary.
    - Seeds tables (universities, specialties, mentors) are NOT cascade-targets
      because they reference nothing — they're only referenced BY participants.
    """
    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE TABLE "
            "  team_join_requests, "
            "  team_mentor_preferences, "
            "  mentor_team_preferences, "
            "  team_mentors, "
            "  participants, "
            "  teams "
            "RESTART IDENTITY CASCADE"
        )
        cur.execute(
            "INSERT INTO matching_state (id, is_confirmed) VALUES (1, FALSE) "
            "ON CONFLICT (id) DO UPDATE SET is_confirmed = FALSE, confirmed_at = NULL"
        )


def _reset_caches():
    """Invalidate all module-level TTL caches so tests see fresh DB data."""
    try:
        import app.services.mentor_service as ms

        ms._cached_mentors = None  # type: ignore[attr-defined]
        ms._cache_ts = 0  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        import app.services.ranking_service as rs

        rs._cached_rankings = None
        rs._cache_ts = 0
        rs._team_rankings_cache = None
        rs._team_rankings_cache_ts = 0
    except Exception:
        pass


@pytest.fixture()
def client(flask_app):
    """Per-test Flask test client (fresh cookie jar)."""
    with flask_app.test_client() as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
# Helper utilities (imported by test modules)
# ═══════════════════════════════════════════════════════════════════════════


def make_payload(
    n: int,
    *,
    univ_id: int,
    spec_id: int,
    password: str = DEFAULT_PW,
    course: str = DEFAULT_COURSE,
    **overrides,
) -> dict:
    """Build a valid participant registration payload numbered N."""
    payload = {
        "first_name": f"First{n}",
        "last_name": f"Last{n}",
        "email": f"user{n}@e2e.test",
        "password": password,
        "phone_number": f"088800{n:04d}",
        "faculty_number": f"FAC{n:06d}",
        "course": course,
        "specialty_id": spec_id,
        "university_id": univ_id,
    }
    payload.update(overrides)
    return payload


def register(client, n: int, seeds: dict, **overrides) -> "flask.Response":
    """POST /api/auth/register for participant N."""
    return client.post(
        "/api/auth/register",
        json=make_payload(n, univ_id=seeds["univ_id"], spec_id=seeds["spec_id"], **overrides),
    )


def register_extra(client, seeds: dict) -> "flask.Response":
    """Register a one-off filler participant with UUID-based unique credentials.

    Use this instead of numbered register() calls whenever a test only needs an
    extra team member and has no reason to refer to that participant by index.
    Guarantees collision-free credentials regardless of test order or parallelism.
    """
    uid = uuid.uuid4().hex[:12]
    payload = {
        "first_name": "Filler",
        "last_name": uid.upper(),
        "email": f"filler-{uid}@e2e.test",
        "password": DEFAULT_PW,
        "phone_number": f"07{uid[:9]}",
        "faculty_number": f"F{uid[:7].upper()}",
        "course": DEFAULT_COURSE,
        "specialty_id": seeds["spec_id"],
        "university_id": seeds["univ_id"],
    }
    return client.post("/api/auth/register", json=payload)


def register_extra_and_token(client, seeds: dict) -> str:
    """Register a filler participant and return their JWT. See register_extra()."""
    rv = register_extra(client, seeds)
    assert rv.status_code == 201, rv.get_json()
    token = _extract_token(rv)
    assert token, "No token cookie after filler registration"
    return token


def _extract_token(response) -> str | None:
    """Pull the JWT value out of the Set-Cookie response header."""
    for cookie_str in response.headers.getlist("Set-Cookie"):
        if "token=" in cookie_str:
            return cookie_str.split("token=", 1)[1].split(";")[0]
    return None


def login_token(client, email: str, password: str, role: str = "participant") -> str:
    """Login and return the JWT string from the Set-Cookie header."""
    rv = client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "role": role},
    )
    assert rv.status_code == 200, rv.get_json()
    token = _extract_token(rv)
    assert token, "No token cookie returned by login"
    return token


def register_and_token(client, n: int, seeds: dict, **overrides) -> str:
    """Register participant N and return their JWT from the cookie."""
    rv = register(client, n, seeds, **overrides)
    assert rv.status_code == 201, rv.get_json()
    token = _extract_token(rv)
    assert token, "No token cookie after registration"
    return token


def bearer(token: str) -> dict:
    """Return an Authorization header dict for the given token."""
    return {"Authorization": f"Bearer {token}"}


def admin_token(flask_app) -> str:
    """Generate an admin JWT directly (no DB lookup needed)."""
    with flask_app.app_context():
        from app.services.auth_service import generate_token

        return generate_token(0, "admin")


def mentor_token_for(flask_app, mentor_id: int) -> str:
    """Generate a mentor JWT directly."""
    with flask_app.app_context():
        from app.services.auth_service import generate_token

        return generate_token(mentor_id, "mentor")


def new_client(flask_app):
    """Context manager that yields a brand-new test client (separate cookie jar)."""
    return flask_app.test_client()
