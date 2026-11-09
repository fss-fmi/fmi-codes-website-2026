"""Rate limits key on the visitor's address and scale with RATELIMIT_MULTIPLIER (#207).

Each test builds a production app with in-memory limiter storage, so no Redis is
needed. REMOTE_ADDR plays the one trusted proxy in front of the backend
(ingress-nginx in k3s, the frontend's nginx in Compose).
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from app import limiter
from app.services import feature_flag_service, ranking_service
from app.utils.rate_limits import multiplier_from_env, scaled
from flask import request

PROXY = "10.42.0.7"
CLIENT_A = "203.0.113.5"
CLIENT_B = "198.51.100.20"


@limiter.limit("2 per minute")
def whoami():
    return request.remote_addr


@limiter.limit(scaled("2 per minute"))
def scaled_route():
    return "ok"


@pytest.fixture()
def make_app(monkeypatch):
    for var in ("REDIS_SENTINELS", "REDIS_MASTER_NAME", "REDIS_URL", "RATELIMIT_MULTIPLIER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "y" * 40)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$" + "a" * 22)
    # `enabled` lives on the one module-level limiter, and init_app keeps the value the previous
    # app left (False after any testing app) and then skips hooking into the app. It has to be on
    # before create_app; monkeypatch puts it back so later e2e tests don't run rate limited.
    monkeypatch.setattr(limiter, "enabled", True)

    def build(multiplier=None):
        if multiplier is not None:
            monkeypatch.setenv("RATELIMIT_MULTIPLIER", multiplier)
        from app import create_app

        with patch("app.database.init_database"):
            app = create_app("production")
        app.add_url_rule("/test/whoami", "test_whoami", whoami)
        app.add_url_rule("/test/scaled", "test_scaled", scaled_route)
        app.add_url_rule("/test/default", "test_default", lambda: "ok")
        return app

    return build


@pytest.fixture()
def limited_app(make_app):
    return make_app()


def _get(client, forwarded_for, path="/test/whoami"):
    return client.get(
        path,
        headers={"X-Forwarded-For": forwarded_for},
        environ_base={"REMOTE_ADDR": PROXY},
    )


def test_remote_addr_is_the_address_the_proxy_saw(limited_app):
    assert _get(limited_app.test_client(), CLIENT_A).text == CLIENT_A


def test_entries_a_client_forged_before_the_proxy_are_ignored(limited_app):
    # The Compose nginx appends its peer to whatever X-Forwarded-For the client sent.
    assert _get(limited_app.test_client(), f"1.2.3.4, {CLIENT_A}").text == CLIENT_A


def test_each_client_gets_its_own_bucket(limited_app):
    c = limited_app.test_client()
    assert [_get(c, CLIENT_A).status_code for _ in range(3)] == [200, 200, 429]
    assert _get(c, CLIENT_B).status_code == 200


def test_forged_header_cannot_escape_a_full_bucket(limited_app):
    c = limited_app.test_client()
    for _ in range(2):
        _get(c, CLIENT_A)
    assert _get(c, f"{CLIENT_B}, {CLIENT_A}").status_code == 429


def test_rankings_route_is_not_rate_limited(limited_app, monkeypatch):
    """Results are revealed at the venue, where every polling phone shares one NAT address."""
    monkeypatch.setattr(feature_flag_service, "is_enabled", lambda name: True)
    monkeypatch.setattr(ranking_service, "get_team_rankings", lambda: [])
    c = limited_app.test_client()
    statuses = {_get(c, CLIENT_A, "/api/teams/rankings").status_code for _ in range(210)}
    assert statuses == {200}


@pytest.mark.parametrize(("multiplier", "allowed"), [(None, 2), ("1", 2), ("3", 6)])
def test_multiplier_scales_a_limit(make_app, multiplier, allowed):
    c = make_app(multiplier).test_client()
    statuses = [_get(c, CLIENT_A, "/test/scaled").status_code for _ in range(allowed + 1)]
    assert statuses == [200] * allowed + [429]


def test_route_limits_are_scaled(make_app):
    """The bug-report limit (10/min) through the real route; empty reports are 400s that count."""
    c = make_app("2").test_client()

    def post():
        return c.post(
            "/api/bug-report",
            json={},
            headers={"X-Forwarded-For": CLIENT_A},
            environ_base={"REMOTE_ADDR": PROXY},
        ).status_code

    assert [post() for _ in range(21)] == [400] * 20 + [429]


def test_default_limit_is_scaled(make_app):
    """Routes without their own limit get 200/min times the multiplier."""
    c = make_app("2").test_client()
    statuses = [_get(c, CLIENT_A, "/test/default").status_code for _ in range(401)]
    assert statuses == [200] * 400 + [429]


def test_every_route_limit_is_scaled():
    """A bare string limit would stay at prod's value on staging."""
    routes = Path(__file__).parent.parent / "backend" / "app" / "routes"
    bare = [
        f"{path.name}:{number}"
        for path in sorted(routes.glob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if line.strip().startswith("@limiter.limit(") and "scaled(" not in line
    ]
    assert bare == []


@pytest.mark.parametrize(("raw", "expected"), [(None, 1), ("", 1), ("1", 1), (" 10 ", 10)])
def test_multiplier_from_env(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("RATELIMIT_MULTIPLIER", raising=False)
    else:
        monkeypatch.setenv("RATELIMIT_MULTIPLIER", raw)
    assert multiplier_from_env() == expected


@pytest.mark.parametrize("raw", ["0", "-3", "1.5", "ten"])
def test_bad_multiplier_refuses_to_boot(make_app, raw):
    with pytest.raises(ValueError, match="RATELIMIT_MULTIPLIER"):
        make_app(raw)
