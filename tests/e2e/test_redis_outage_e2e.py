"""The rule of #256, end to end: Redis failing never stops the app from working.

A participant journey runs on a real Postgres with the limiter on, while Redis sits
behind a TCP proxy (tests/redis_proxy.py) the test switches between up, hanging,
refusing and up again, then a cold start with Redis away. Every step must answer with
the status it answers while Redis is up, within one timeout plus margin. The only
thing allowed to change is what Redis provides: a token logged out while Redis is away
still works (ADR-003). Needs REDIS_URL (CI sets it).
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from tests.e2e.conftest import ADMIN_EMAIL, ADMIN_PW, DEFAULT_PW, bearer, register_and_token
from tests.redis_proxy import RedisProxy

pytestmark = pytest.mark.e2e

REDIS_URL = os.environ.get("REDIS_URL")
STEP_BOUND = 2.0
LOGGED_OUT = "me after logout"


@pytest.fixture()
def proxy():
    if not REDIS_URL:
        pytest.skip("Redis not configured (set REDIS_URL)")
    proxy = RedisProxy(REDIS_URL)
    yield proxy
    proxy.close()


@pytest.fixture()
def outage_app(flask_app, proxy, monkeypatch):
    """A second app on the session's database pool, with the limiter on and Redis proxied."""
    import config
    from app import create_app, limiter
    from app.services import redis_client
    from app.services.auth_service import hash_password
    from app.utils.rate_limits import LIMITER_KEY_PREFIX

    monkeypatch.delenv("REDIS_SENTINELS", raising=False)
    monkeypatch.setenv("REDIS_URL", proxy.url)
    monkeypatch.setattr(config.TestingConfig, "RATELIMIT_ENABLED", True)
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(limiter, "_storage_dead", False)
    monkeypatch.setattr(limiter, "_storage_options", {"key_prefix": LIMITER_KEY_PREFIX})
    monkeypatch.setattr(limiter, "_Limiter__check_backend_count", 0)
    # Flask-Limiter's recovery pings run on a backoff; the test triggers them explicitly.
    monkeypatch.setattr(limiter, "_Limiter__last_check_backend", time.time() + 3600)
    monkeypatch.setattr(limiter, "_hold_until", 0.0)
    monkeypatch.setattr(limiter, "_last_storage_error", float("-inf"))
    monkeypatch.setattr(limiter, "_pending_clears", set())
    monkeypatch.setattr(redis_client, "BREAKER_OPEN_SECONDS", 1.0)
    redis_client.reset_client()

    with patch("app.database.init_database"):
        app = create_app("testing")
    app.config.update(
        SECRET_KEY=flask_app.config["SECRET_KEY"],
        JWT_SECRET_KEY=flask_app.config["JWT_SECRET_KEY"],
        ADMIN_EMAIL=ADMIN_EMAIL,
        ADMIN_PASSWORD_HASH=hash_password(ADMIN_PW),
        SLACK_EVENTS_WEBHOOK_URL="",
        MAIL_PASSWORD="",
    )

    def recheck_limiter():
        monkeypatch.setattr(limiter, "_hold_until", 0.0)
        monkeypatch.setattr(limiter, "_Limiter__last_check_backend", 0.0)

    app.recheck_limiter = recheck_limiter
    yield app
    redis_client.reset_client()


def _journey(app, seeds, n):
    """[(step, status, seconds)] for one participant, from the register page to logout."""
    steps = []
    client = app.test_client()

    def step(name, call):
        start = time.monotonic()
        response = call()
        steps.append((name, response.status_code, time.monotonic() - start))
        return response

    step("config", lambda: client.get("/api/config"))
    step("universities", lambda: client.get("/api/universities"))
    step("mentors", lambda: client.get("/api/mentors"))
    token = {}

    def sign_up():
        start = time.monotonic()
        token["value"] = register_and_token(client, n, seeds)
        steps.append(("register", 201, time.monotonic() - start))

    sign_up()
    auth = bearer(token["value"])
    login = {"email": f"user{n}@e2e.test", "password": DEFAULT_PW, "role": "participant"}
    step("login", lambda: client.post("/api/auth/login", json=login))
    step("me", lambda: client.get("/api/auth/me", headers=auth))
    team = step(
        "create team", lambda: client.post("/api/teams", json={"team_name": f"T{n}"}, headers=auth)
    )
    team_id = team.get_json()["team"]["id"]
    step("team page", lambda: client.get(f"/api/teams/{team_id}", headers=auth))
    step("registered teams", lambda: client.get("/api/teams/registered"))
    step("rankings", lambda: client.get("/api/teams/rankings"))
    step("readiness", lambda: client.get("/api/health/ready"))
    # Without cookies, so logout revokes the bearer token rather than the login cookie.
    fresh = app.test_client()
    step("logout", lambda: fresh.post("/api/auth/logout", headers=auth))
    step(LOGGED_OUT, lambda: fresh.get("/api/auth/me", headers=auth))
    return steps


def _statuses(steps):
    return {name: status for name, status, _ in steps}


def _direct():
    import redis

    return redis.Redis.from_url(REDIS_URL, socket_timeout=2, decode_responses=True)


def _wait_for_redis_again(app):
    """Let the app client's breaker and the limiter try Redis again."""
    from app.services import redis_client

    time.sleep(redis_client.BREAKER_OPEN_SECONDS + 0.1)
    app.recheck_limiter()


def test_a_redis_outage_turns_off_only_what_redis_provides(outage_app, proxy, seeds):
    from app.utils.rate_limits import LIMITER_KEY_PREFIX

    normal = _statuses(_journey(outage_app, seeds, 1))
    assert normal[LOGGED_OUT] == 401
    away = dict(normal, **{LOGGED_OUT: 200})

    for n, outage in ((2, proxy.hang), (3, proxy.refuse)):
        outage()
        steps = _journey(outage_app, seeds, n)
        assert _statuses(steps) == away, outage.__name__
        slow = [(name, round(took, 2)) for name, _, took in steps if took > STEP_BOUND]
        assert slow == [], outage.__name__

    proxy.up()
    _wait_for_redis_again(outage_app)
    connection = _direct()
    try:
        for key in connection.scan_iter(f"{LIMITER_KEY_PREFIX}:*"):
            connection.delete(key)
        connection.delete("cache:lookups:universities")
        assert _statuses(_journey(outage_app, seeds, 4)) == normal
        assert connection.exists("cache:lookups:universities")
        assert list(connection.scan_iter(f"{LIMITER_KEY_PREFIX}:*")) != []
    finally:
        connection.close()


def test_a_process_that_starts_while_redis_is_away_picks_it_up(outage_app, proxy, seeds):
    """Before #256 the first failed connection turned Redis off until the pod restarted."""
    from app.services import redis_client

    normal = _statuses(_journey(outage_app, seeds, 1))
    proxy.refuse()
    redis_client.reset_client()
    steps = _journey(outage_app, seeds, 2)
    assert _statuses(steps) == dict(normal, **{LOGGED_OUT: 200})
    assert [name for name, _, took in steps if took > STEP_BOUND] == []

    proxy.up()
    _wait_for_redis_again(outage_app)
    connection = _direct()
    try:
        connection.delete("cache:lookups:universities")
        assert outage_app.test_client().get("/api/universities").status_code == 200
        assert connection.exists("cache:lookups:universities")
    finally:
        connection.close()
    assert _statuses(_journey(outage_app, seeds, 3)) == normal
