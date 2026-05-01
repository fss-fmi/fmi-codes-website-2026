"""Shared pytest fixtures for the FMI Codes test suite.

Strategy:
- A minimal Flask app is created with TESTING=True and a fake JWT secret.
- The database connection pool is patched out so tests never need a real Postgres
  instance.  Individual tests can inject their own execute_query side-effects via
  the `mock_db` fixture.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make sure `backend/` is on sys.path so that `from app... import ...` works.
BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# App fixture — creates a Flask app with TESTING mode, no real DB
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """Session-scoped minimal Flask app (no real DB pool)."""
    # Patch init_database so the factory never tries to open a Postgres connection
    with patch("app.database.init_database"):
        from app import create_app

        flask_app = create_app("testing")
        flask_app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret-key-that-is-at-least-32-bytes-long",
            JWT_SECRET_KEY="test-jwt-secret-key-that-is-at-least-32-bytes-long",
            JWT_EXPIRY_DAYS=3,
        )

    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def app_ctx(app):
    """Push an application context for the duration of a test."""
    with app.app_context():
        yield app


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# DB mock helper — patches execute_query / execute_insert / execute_update
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_db():
    """Returns a namespace of MagicMocks that replace the DB helper functions.

    Usage in a test::

        def test_something(app_ctx, mock_db):
            mock_db.execute_query.return_value = [{"id": 1}]
            ...
    """
    mocks = MagicMock()
    with (
        patch("app.database.execute_query", mocks.execute_query),
        patch("app.database.execute_insert", mocks.execute_insert),
        patch("app.database.execute_update", mocks.execute_update),
        patch("app.database.get_db_cursor", mocks.get_db_cursor),
    ):
        yield mocks
