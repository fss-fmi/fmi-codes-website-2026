"""Rate limits key on what they protect and scale with RATELIMIT_MULTIPLIER (#207, #219).

Each test builds a production app with in-memory limiter storage, so no Redis is
needed. REMOTE_ADDR plays the one trusted proxy in front of the backend
(ingress-nginx in k3s, the frontend's nginx in Compose). Every request in a test
comes from CLIENT_A unless it says otherwise: the university network, where every
device shares one address.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import bcrypt
import jwt
import pytest
from app import limiter
from app.routes import auth as auth_routes
from app.services import feature_flag_service, ranking_service
from app.services.auth_service import generate_token
from app.utils.rate_limits import account_key, identity_key, multiplier_from_env, scaled
from flask import request

PROXY = "10.42.0.7"
CLIENT_A = "203.0.113.5"
CLIENT_B = "198.51.100.20"
JWT_SECRET = "y" * 40
RIGHT_GUESS = "right-guess-1234"
# Cost 4 keeps the login tests fast; the cost doesn't change what the limiter counts.
FAST_HASH = bcrypt.hashpw(RIGHT_GUESS.encode(), bcrypt.gensalt(rounds=4)).decode()


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
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)
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
        # ProductionConfig read SECRET_KEY when config was first imported, before setenv above.
        app.config["SECRET_KEY"] = "x" * 40
        app.add_url_rule("/test/whoami", "test_whoami", whoami)
        app.add_url_rule("/test/scaled", "test_scaled", scaled_route)
        app.add_url_rule("/test/default", "test_default", lambda: "ok")
        return app

    return build


@pytest.fixture()
def limited_app(make_app):
    return make_app()


def _get(client, forwarded_for, path="/test/whoami", token=None):
    headers = {"X-Forwarded-For": forwarded_for}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.get(path, headers=headers, environ_base={"REMOTE_ADDR": PROXY})


def _post(client, path, body, forwarded_for=CLIENT_A):
    return client.post(
        path,
        json=body,
        headers={"X-Forwarded-For": forwarded_for},
        environ_base={"REMOTE_ADDR": PROXY},
    ).status_code


def _token(app, user_id, role="participant"):
    with app.app_context():
        return generate_token(user_id, role)


# --- Client address (#207) ---


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


# --- Identity keys (#219) ---


def test_identity_is_the_user_of_a_valid_token(limited_app):
    token = _token(limited_app, 7)
    with limited_app.test_request_context(headers={"Authorization": f"Bearer {token}"}):
        assert identity_key() == "user:participant:7"


@pytest.mark.parametrize("kind", ["none", "wrong secret", "expired", "garbage"])
def test_identity_falls_back_to_the_address(limited_app, kind):
    now = datetime.now(UTC)
    claims = {"user_id": 7, "role": "participant", "jti": "j", "iat": now}
    tokens = {
        "none": None,
        "wrong secret": jwt.encode({**claims, "exp": now + timedelta(days=1)}, "z" * 40),
        "expired": jwt.encode({**claims, "exp": now - timedelta(seconds=1)}, JWT_SECRET),
        "garbage": "not-a-jwt",
    }
    headers = {"Authorization": f"Bearer {tokens[kind]}"} if tokens[kind] else {}
    with limited_app.test_request_context(headers=headers, environ_base={"REMOTE_ADDR": CLIENT_A}):
        assert identity_key() == f"ip:{CLIENT_A}"


def test_account_key_hides_the_email_and_ignores_case(limited_app):
    def key(body):
        with limited_app.test_request_context(method="POST", json=body):
            return account_key()

    a = key({"email": " ANA@example.com ", "role": "participant"})
    assert a.startswith("account:") and "ana" not in a.lower()
    assert key({"email": "ana@example.com"}) == a
    assert key({"email": "ana@example.com", "role": "mentor"}) != a
    assert key({"email": "bo@example.com"}) != a


@pytest.mark.parametrize("body", [None, [], {"email": ""}, {"email": 5}, {"role": "mentor"}])
def test_account_key_without_an_email_is_the_address(limited_app, body):
    with limited_app.test_request_context(
        method="POST", json=body, environ_base={"REMOTE_ADDR": CLIENT_A}
    ):
        assert account_key() == f"ip:{CLIENT_A}"


# --- Default limit ---


def test_signed_in_users_on_one_address_get_their_own_bucket(limited_app):
    c = limited_app.test_client()
    ana, bo = _token(limited_app, 1), _token(limited_app, 2)
    statuses = [_get(c, CLIENT_A, "/test/default", ana).status_code for _ in range(201)]
    assert statuses == [200] * 200 + [429]
    assert _get(c, CLIENT_A, "/test/default", bo).status_code == 200
    assert _get(c, CLIENT_A, "/test/default").status_code == 200


def test_anonymous_default_is_per_address(limited_app):
    c = limited_app.test_client()
    statuses = [_get(c, CLIENT_A, "/test/default").status_code for _ in range(3001)]
    assert statuses == [200] * 3000 + [429]
    assert _get(c, CLIENT_B, "/test/default").status_code == 200


def test_default_limit_is_scaled(make_app):
    app = make_app("2")
    c = app.test_client()
    token = _token(app, 1)
    statuses = [_get(c, CLIENT_A, "/test/default", token).status_code for _ in range(401)]
    assert statuses == [200] * 400 + [429]


# --- Login ---


@pytest.fixture()
def login_app(limited_app, monkeypatch):
    def lookup(app, query, params, fetch_one=False):
        return {"id": 7, "password_hash": FAST_HASH} if params[0] == "ana@example.com" else None

    monkeypatch.setattr(auth_routes, "execute_query", lookup)
    monkeypatch.setattr(auth_routes, "_DUMMY_HASH", FAST_HASH)
    monkeypatch.setattr(auth_routes, "_fetch_user_profile", lambda *a, **k: {})
    return limited_app


def _login(client, email, password, forwarded_for=CLIENT_A):
    body = {"email": email, "password": password, "role": "participant"}
    return _post(client, "/api/auth/login", body, forwarded_for)


def test_failed_logins_lock_only_that_account(login_app):
    c = login_app.test_client()
    assert [_login(c, "ana@example.com", "wrong") for _ in range(15)] == [401] * 15
    assert _login(c, "ana@example.com", RIGHT_GUESS) == 429
    assert _login(c, "ana@example.com", RIGHT_GUESS, CLIENT_B) == 429
    assert _login(c, "bo@example.com", "wrong") == 401


def test_successful_logins_do_not_count(login_app):
    c = login_app.test_client()
    assert {_login(c, "ana@example.com", RIGHT_GUESS) for _ in range(30)} == {200}


def test_login_has_a_per_address_ceiling(login_app):
    c = login_app.test_client()
    statuses = [_login(c, f"user{i}@example.com", "wrong") for i in range(301)]
    assert statuses == [401] * 300 + [429]
    assert _login(c, "user0@example.com", "wrong", CLIENT_B) == 401


# --- Register and password reset ---


def test_register_is_300_per_address(limited_app, monkeypatch):
    monkeypatch.setattr(feature_flag_service, "is_enabled", lambda name: False)
    c = limited_app.test_client()
    assert [_post(c, "/api/auth/register", {}) for _ in range(301)] == [403] * 300 + [429]


def test_reset_is_limited_per_email(limited_app, monkeypatch):
    monkeypatch.setattr(auth_routes, "execute_query", lambda *a, **k: None)
    c = limited_app.test_client()

    def reset(email):
        return _post(c, "/api/auth/reset-password", {"email": email, "role": "participant"})

    assert [reset("ana@example.com") for _ in range(6)] == [200] * 5 + [429]
    assert reset("bo@example.com") == 200


def test_reset_has_a_per_address_ceiling(limited_app, monkeypatch):
    monkeypatch.setattr(auth_routes, "execute_query", lambda *a, **k: None)
    c = limited_app.test_client()
    body = [{"email": f"user{i}@example.com", "role": "participant"} for i in range(101)]
    statuses = [_post(c, "/api/auth/reset-password", b) for b in body]
    assert statuses == [200] * 100 + [429]


# --- Multiplier ---


@pytest.mark.parametrize(("multiplier", "allowed"), [(None, 2), ("1", 2), ("3", 6)])
def test_multiplier_scales_a_limit(make_app, multiplier, allowed):
    c = make_app(multiplier).test_client()
    statuses = [_get(c, CLIENT_A, "/test/scaled").status_code for _ in range(allowed + 1)]
    assert statuses == [200] * allowed + [429]


def test_route_limits_are_scaled(make_app):
    """The bug-report limit (10/min) through the real route; empty reports are 400s that count."""
    c = make_app("2").test_client()
    assert [_post(c, "/api/bug-report", {}) for _ in range(21)] == [400] * 20 + [429]


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
