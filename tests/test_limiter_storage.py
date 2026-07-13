"""Regression tests for rate-limiter storage wiring in create_app.

Guards the boot-time crash where the module-level Limiter was constructed with
`storage_uri=build_limiter_storage_uri` (the FUNCTION, not its result). Flask-
Limiter >=3.5 feeds `storage_uri` straight into `urllib.parse.urlparse()` at
`init_app`, so a callable raised `AttributeError: 'function' object has no
attribute 'decode'` and every gunicorn worker failed to boot. The fix resolves
the URI to a string via `RATELIMIT_STORAGE_URI` inside create_app.

The testing config disables the limiter, which is exactly why the original bug
had no coverage — these tests drive `production` (the path that actually crashed)
with the DB pool patched out so no real Postgres/Redis is needed.
"""

import os
from unittest.mock import patch

import pytest

_STRONG = "x" * 40


@pytest.fixture()
def _prod_secrets(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", _STRONG)
    monkeypatch.setenv("JWT_SECRET_KEY", _STRONG)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$" + "a" * 22)


def test_create_app_production_boots_with_string_storage_uri(_prod_secrets):
    """create_app('production') must not raise and must resolve a string URI."""
    with patch("app.database.init_database"):
        from app import create_app

        app = create_app("production")

    storage_uri = app.config.get("RATELIMIT_STORAGE_URI")
    assert isinstance(storage_uri, str) and storage_uri
    assert "://" in storage_uri


def test_storage_uri_falls_back_to_memory_without_redis(monkeypatch):
    """No Redis env → memory:// (per-process limiting, unchanged dev behaviour)."""
    for var in ("REDIS_SENTINELS", "REDIS_MASTER_NAME", "REDIS_URL"):
        monkeypatch.delenv(var, raising=False)
    from app.services.redis_client import build_limiter_storage_uri

    assert build_limiter_storage_uri() == "memory://"


def test_storage_uri_uses_sentinel_scheme_in_cluster(monkeypatch):
    """Sentinel env (as set in the k8s ConfigMap) → redis+sentinel:// URI."""
    monkeypatch.setenv("REDIS_SENTINELS", "redis.fmi-codes.svc.cluster.local:26379")
    monkeypatch.setenv("REDIS_MASTER_NAME", "mymaster")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    from app.services.redis_client import build_limiter_storage_uri

    assert build_limiter_storage_uri() == (
        "redis+sentinel://redis.fmi-codes.svc.cluster.local:26379/mymaster"
    )


def test_storage_uri_embeds_password_for_authed_sentinels(monkeypatch):
    """A password-protected Sentinel deployment must put the password in the URI.

    Without it, the limits library builds an unauthenticated Sentinel client,
    discovery hits NOAUTH, and every rate-limited request 500s. The password
    lands in the userinfo so limits threads it into both the sentinel-query and
    data-node connections.
    """
    monkeypatch.setenv("REDIS_SENTINELS", "redis.fmi-codes.svc.cluster.local:26379")
    monkeypatch.setenv("REDIS_MASTER_NAME", "mymaster")
    monkeypatch.setenv("REDIS_PASSWORD", "s3cr3t")
    monkeypatch.delenv("REDIS_URL", raising=False)
    from app.services.redis_client import build_limiter_storage_uri

    assert build_limiter_storage_uri() == (
        "redis+sentinel://:s3cr3t@redis.fmi-codes.svc.cluster.local:26379/mymaster"
    )


def test_storage_uri_url_encodes_password_special_chars(monkeypatch):
    """A password with URI-reserved characters must be percent-encoded so the
    scheme stays parseable (e.g. '@' or ':' would otherwise corrupt the authority)."""
    monkeypatch.setenv("REDIS_SENTINELS", "redis.fmi-codes.svc.cluster.local:26379")
    monkeypatch.setenv("REDIS_MASTER_NAME", "mymaster")
    monkeypatch.setenv("REDIS_PASSWORD", "p@ss:w/rd")
    monkeypatch.delenv("REDIS_URL", raising=False)
    from app.services.redis_client import build_limiter_storage_uri

    assert build_limiter_storage_uri() == (
        "redis+sentinel://:p%40ss%3Aw%2Frd@redis.fmi-codes.svc.cluster.local:26379/mymaster"
    )
