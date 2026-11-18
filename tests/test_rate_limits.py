"""Rate limits key on what they protect and scale with RATELIMIT_MULTIPLIER (#207, #219).

Each test builds a production app with in-memory limiter storage, so no Redis is
needed. Tests marked with the `storage` parameter run on Redis too when REDIS_URL is
set (CI sets it), since the moving window runs Lua scripts there (#251).
REMOTE_ADDR plays the one trusted proxy in front of the backend
(ingress-nginx in k3s, the frontend's nginx in Compose). Every request in a test
comes from CLIENT_A unless it says otherwise: the university network, where every
device shares one address.
"""

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app as app_module
import bcrypt
import jwt
import pytest
from app import limiter
from app.routes import auth as auth_routes
from app.services import feature_flag_service, ranking_service
from app.services.auth_service import generate_token
from app.utils import auth_decorators
from app.utils.rate_limits import (
    LIMITER_KEY_PREFIX,
    LOGIN_ACCOUNT_LIMIT,
    identity_key,
    login_account_key,
    multiplier_from_env,
    reset_account_key,
    scaled,
)
from flask import request
from flask_limiter import RequestLimit
from limits import parse
from limits.storage import memory as memory_storage
from limits.storage import redis as redis_storage
from limits.storage import storage_from_string
from limits.strategies import FixedWindowRateLimiter, MovingWindowRateLimiter
from limits.util import WindowStats

import redis

REDIS_URL = os.environ.get("REDIS_URL")
BOTH_STORAGES = pytest.mark.parametrize("storage", ["memory", "redis"], indirect=True)
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


def _clear_redis_limits():
    connection = redis.Redis.from_url(REDIS_URL)
    try:
        keys = list(connection.scan_iter(f"{LIMITER_KEY_PREFIX}:*"))
        if keys:
            connection.delete(*keys)
    finally:
        connection.close()


@pytest.fixture()
def storage(request):
    """memory unless a test parametrizes it; redis skips without REDIS_URL."""
    name = getattr(request, "param", "memory")
    if name == "redis":
        if not REDIS_URL:
            pytest.skip("Redis not configured (set REDIS_URL)")
        _clear_redis_limits()
        request.addfinalizer(_clear_redis_limits)
    return name


@pytest.fixture()
def make_app(monkeypatch, storage):
    for var in ("REDIS_SENTINELS", "REDIS_MASTER_NAME", "REDIS_URL", "RATELIMIT_MULTIPLIER"):
        monkeypatch.delenv(var, raising=False)
    if storage == "redis":
        monkeypatch.setenv("REDIS_URL", REDIS_URL)
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
        for name in ("default", "default2", "default3"):
            app.add_url_rule(f"/test/{name}", f"test_{name}", lambda: "ok")
        return app

    return build


@pytest.fixture()
def limited_app(make_app):
    return make_app()


@pytest.fixture()
def clock(monkeypatch):
    """Time as the limiter's storage and the Retry-After header see it; tests move it."""
    now = SimpleNamespace(value=1_800_000_000.0)
    fake = SimpleNamespace(time=lambda: now.value)
    for module in (memory_storage, redis_storage, app_module):
        monkeypatch.setattr(module, "time", fake)
    return now


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


@BOTH_STORAGES
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


def _key(app, key_func, body):
    with app.test_request_context(method="POST", json=body, environ_base={"REMOTE_ADDR": CLIENT_A}):
        return key_func()


def test_account_key_hides_the_email_and_ignores_case(limited_app):
    a = _key(limited_app, login_account_key, {"email": " ANA@example.com ", "role": "participant"})
    assert a.startswith("account:") and "ana" not in a.lower()
    assert _key(limited_app, login_account_key, {"email": "ana@example.com"}) == a
    assert (
        _key(limited_app, reset_account_key, {"email": "ana@example.com", "role": "participant"})
        == a
    )
    assert _key(limited_app, login_account_key, {"email": "ana@example.com", "role": "mentor"}) != a
    assert _key(limited_app, login_account_key, {"email": "bo@example.com"}) != a


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {"email": ""},
        {"email": 5},
        {"role": "mentor"},
        {"email": "\ud800@example.com"},
        {"email": "a\x00@example.com"},
    ],
)
def test_account_key_without_an_email_is_the_address(limited_app, body):
    assert _key(limited_app, login_account_key, body) == f"ip:{CLIENT_A}"


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/reset-password"])
def test_an_email_that_is_not_valid_text_is_a_400_not_a_limiter_crash(limited_app, path):
    """The key function runs before the route and must not fail on what the route rejects."""
    body = {"email": "\ud800@example.com", "password": "x", "role": "participant"}
    assert _post(limited_app.test_client(), path, body) == 400


@pytest.mark.parametrize("role", [None, "admin", "nobody"])
def test_a_reset_the_route_rejects_never_counts_against_the_account(limited_app, role):
    """Reset answers these with a 400 and sends nothing, so they must not fill a victim's bucket."""
    body = {"email": "ana@example.com"} | ({"role": role} if role else {})
    assert _key(limited_app, reset_account_key, body) == f"ip:{CLIENT_A}"


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


def test_one_anonymous_address_is_capped_across_routes(limited_app):
    c = limited_app.test_client()
    for path in ("/test/default", "/test/default2"):
        assert {_get(c, CLIENT_A, path).status_code for _ in range(3000)} == {200}
    assert _get(c, CLIENT_A, "/test/default3").status_code == 429
    assert _get(c, CLIENT_A, "/test/default3", _token(limited_app, 1)).status_code == 200
    assert _get(c, CLIENT_B, "/test/default3").status_code == 200


def test_429_says_why(limited_app):
    c = limited_app.test_client()
    for _ in range(2):
        _get(c, CLIENT_A)
    response = _get(c, CLIENT_A)
    assert response.status_code == 429
    assert response.get_json()["error"].startswith("Too many requests")


@BOTH_STORAGES
def test_429_says_when_to_retry(limited_app):
    """The oldest hit was a moment ago, so nearly the whole window is left."""
    c = limited_app.test_client()
    for _ in range(2):
        _get(c, CLIENT_A)
    assert 55 <= int(_get(c, CLIENT_A).headers["Retry-After"]) <= 60


@pytest.mark.parametrize(
    ("left", "expected"),
    [(10.0, 10), (10.2, 11), (10.6, 11), (59.7, 60), (60.4, 60), (0.1, 1), (-0.8, 1)],
)
def test_retry_after_is_never_early_and_never_past_the_window(
    limited_app, monkeypatch, left, expected
):
    """The reset is an exact timestamp, so rounding up is enough; capped at the window."""
    c = limited_app.test_client()
    for _ in range(2):
        _get(c, CLIENT_A)
    monkeypatch.setattr(
        RequestLimit, "window", property(lambda _self: WindowStats(time.time() + left, 0))
    )
    assert _get(c, CLIENT_A).headers["Retry-After"] == str(expected)


@BOTH_STORAGES
def test_retry_after_is_the_breached_limits_window(limited_app, monkeypatch):
    """Reset requests are 5 an hour, so the wait is far past the 60 s fallback."""
    monkeypatch.setattr(auth_routes, "execute_query", lambda *a, **k: None)
    c = limited_app.test_client()
    body = {"email": "ana@example.com", "role": "participant"}
    for _ in range(5):
        _post(c, "/api/auth/reset-password", body)
    response = c.post(
        "/api/auth/reset-password",
        json=body,
        headers={"X-Forwarded-For": CLIENT_A},
        environ_base={"REMOTE_ADDR": PROXY},
    )
    assert response.status_code == 429
    assert 3500 < int(response.headers["Retry-After"]) <= 3600


def test_a_storage_error_still_answers_429(limited_app, monkeypatch):
    c = limited_app.test_client()
    for _ in range(2):
        _get(c, CLIENT_A)

    def unreachable(_self):
        raise ConnectionError("storage down")

    monkeypatch.setattr(RequestLimit, "window", property(unreachable))
    response = _get(c, CLIENT_A)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_only_429s_carry_rate_limit_headers(limited_app):
    response = _get(limited_app.test_client(), CLIENT_A)
    assert response.status_code == 200
    assert not [
        h for h in response.headers.keys() if h.lower().startswith(("x-ratelimit", "retry-after"))
    ]


# --- Moving window (#251) ---


@BOTH_STORAGES
def test_slots_free_one_at_a_time_as_the_oldest_hits_age_out(limited_app, clock):
    """A fixed window would let both requests at 60.5 through: its counter reset at 60."""
    c = limited_app.test_client()

    def at(t):
        clock.value = 1_800_000_000.0 + t
        response = _get(c, CLIENT_A)
        return response.status_code, response.headers.get("Retry-After")

    assert at(0) == (200, None)
    assert at(20) == (200, None)
    assert at(30) == (429, "30")
    # Refused requests take no slot, so retrying early never pushes the wait back.
    assert [at(30 + i)[0] for i in range(1, 30)] == [429] * 29
    assert at(60.5) == (200, None)
    assert at(60.5) == (429, "20")
    assert at(80.5) == (200, None)


@pytest.mark.skipif(not REDIS_URL, reason="Redis not configured (set REDIS_URL)")
@pytest.mark.parametrize("storage", ["redis"], indirect=True)
def test_a_counter_the_fixed_window_left_never_breaks_a_request(limited_app):
    """A backend still on the fixed window during a rollout writes a string where the moving
    window keeps a list. Under the same key, every hit on it would fail with WRONGTYPE."""
    item, identifiers = parse("2 per minute"), (f"ip:{CLIENT_A}", "test_whoami")
    old = storage_from_string(REDIS_URL)
    try:
        FixedWindowRateLimiter(old).hit(item, *identifiers)
        with pytest.raises(redis.ResponseError, match="WRONGTYPE"):
            MovingWindowRateLimiter(old).hit(item, *identifiers)
        assert _get(limited_app.test_client(), CLIENT_A).status_code == 200
    finally:
        old.clear(item.key_for(*identifiers))


def test_default_limit_is_scaled(make_app):
    app = make_app("2")
    c = app.test_client()
    token = _token(app, 1)
    statuses = [_get(c, CLIENT_A, "/test/default", token).status_code for _ in range(401)]
    assert statuses == [200] * 400 + [429]


# --- Login ---


@pytest.fixture()
def login_app(limited_app, monkeypatch):
    remaining = []

    def lookup(app, query, params, fetch_one=False):
        window = limiter.limiter.get_window_stats(
            parse(LOGIN_ACCOUNT_LIMIT), login_account_key(), "auth.login"
        )
        remaining.append(window.remaining)
        return {"id": 7, "password_hash": FAST_HASH} if params[0] == "ana@example.com" else None

    monkeypatch.setattr(auth_routes, "execute_query", lookup)
    monkeypatch.setattr(auth_routes, "_DUMMY_HASH", FAST_HASH)
    monkeypatch.setattr(auth_routes, "_fetch_user_profile", lambda *a, **k: {})
    limited_app.config["ADMIN_EMAIL"] = "admin@example.com"
    limited_app.config["ADMIN_PASSWORD_HASH"] = FAST_HASH
    limited_app.remaining_during_login = remaining
    return limited_app


def _login(client, email, password, forwarded_for=CLIENT_A, role="participant"):
    body = {"email": email, "password": password, "role": role}
    return _post(client, "/api/auth/login", body, forwarded_for)


@BOTH_STORAGES
def test_failed_logins_lock_only_that_account(login_app):
    c = login_app.test_client()
    assert [_login(c, "ana@example.com", "wrong") for _ in range(15)] == [401] * 15
    assert _login(c, "ana@example.com", RIGHT_GUESS) == 429
    assert _login(c, "ana@example.com", RIGHT_GUESS, CLIENT_B) == 429
    assert _login(c, "bo@example.com", "wrong") == 401


@BOTH_STORAGES
def test_an_attempt_counts_before_bcrypt_runs(login_app):
    """Counting after the response would let parallel guesses all pass the check first."""
    _login(login_app.test_client(), "ana@example.com", "wrong")
    assert login_app.remaining_during_login == [14]


@BOTH_STORAGES
def test_a_successful_login_clears_the_failures(login_app):
    c = login_app.test_client()
    assert [_login(c, "ana@example.com", "wrong") for _ in range(14)] == [401] * 14
    assert _login(c, "ana@example.com", RIGHT_GUESS) == 200
    assert [_login(c, "ana@example.com", "wrong") for _ in range(15)] == [401] * 15
    assert _login(c, "ana@example.com", "wrong") == 429


def test_successful_logins_never_block(login_app):
    c = login_app.test_client()
    assert {_login(c, "ana@example.com", RIGHT_GUESS) for _ in range(30)} == {200}


def _admin(client, password, forwarded_for=CLIENT_A):
    return _login(client, "admin@example.com", password, forwarded_for, role="admin")


def test_the_admin_is_limited_per_account_like_anyone(login_app):
    c = login_app.test_client()
    assert [_admin(c, "wrong") for _ in range(15)] == [401] * 15
    assert _admin(c, RIGHT_GUESS) == 429
    assert _admin(c, RIGHT_GUESS, CLIENT_B) == 429


def test_a_successful_admin_login_clears_the_failures(login_app):
    c = login_app.test_client()
    assert [_admin(c, "wrong") for _ in range(14)] == [401] * 14
    assert _admin(c, RIGHT_GUESS) == 200
    assert [_admin(c, "wrong") for _ in range(15)] == [401] * 15
    assert _admin(c, "wrong") == 429


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


@pytest.mark.parametrize(
    ("path", "ceiling"),
    [("/api/auth/reset-password/confirm", 100), ("/api/auth/verify-email", 300)],
)
def test_token_routes_have_a_per_address_ceiling(limited_app, path, ceiling):
    """Empty bodies are 400s that count, the same as guessed tokens."""
    c = limited_app.test_client()
    statuses = [_post(c, path, {}) for _ in range(ceiling + 1)]
    assert statuses == [400] * ceiling + [429]
    assert _post(c, path, {}, CLIENT_B) == 400


# --- Routes limited per user with a per-address ceiling ---


def _post_as(client, path, token):
    return client.post(
        path,
        json={},
        headers={"X-Forwarded-For": CLIENT_A, "Authorization": f"Bearer {token}"},
        environ_base={"REMOTE_ADDR": PROXY},
    ).status_code


def test_bug_reports_from_many_accounts_hit_the_address_ceiling(limited_app):
    """Accounts are cheap, so the per-user limit alone would let one address flood the webhooks."""
    c = limited_app.test_client()
    tokens = [_token(limited_app, i) for i in range(4)]
    statuses = [_post_as(c, "/api/bug-report", t) for t in tokens for _ in range(10)]
    assert statuses == [400] * 30 + [429] * 10


def test_resends_from_many_accounts_hit_the_address_ceiling(limited_app, monkeypatch):
    monkeypatch.setattr(auth_decorators, "_token_predates_revocation_epoch", lambda p: False)
    monkeypatch.setattr("app.services.token_blocklist.is_revoked", lambda jti: False)
    monkeypatch.setattr(auth_routes, "execute_query", lambda *a, **k: None)
    c = limited_app.test_client()
    tokens = [_token(limited_app, i) for i in range(11)]
    statuses = [_post_as(c, "/api/auth/resend-verification", t) for t in tokens for _ in range(3)]
    assert statuses == [404] * 30 + [429] * 3


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
