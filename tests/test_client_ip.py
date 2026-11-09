"""Rate limits key on the visitor's address, not the proxy's (#207).

Each test builds a production app with in-memory limiter storage, so no Redis is
needed. REMOTE_ADDR plays the one trusted proxy in front of the backend
(ingress-nginx in k3s, the frontend's nginx in Compose).
"""

from unittest.mock import patch

import pytest
from app.services import feature_flag_service, ranking_service
from flask import request

PROXY = "10.42.0.7"
CLIENT_A = "203.0.113.5"
CLIENT_B = "198.51.100.20"


@pytest.fixture()
def limited_app(monkeypatch):
    for var in ("REDIS_SENTINELS", "REDIS_MASTER_NAME", "REDIS_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "y" * 40)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$" + "a" * 22)
    from app import create_app, limiter

    # `enabled` lives on the one module-level limiter, and init_app keeps the value the previous
    # app left (False after any testing app) and then skips hooking into the app. It has to be on
    # before create_app; monkeypatch puts it back so later e2e tests don't run rate limited.
    monkeypatch.setattr(limiter, "enabled", True)
    with patch("app.database.init_database"):
        app = create_app("production")

    @limiter.limit("2 per minute")
    def whoami():
        return request.remote_addr

    app.add_url_rule("/test/whoami", "test_whoami", whoami)
    return app


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
