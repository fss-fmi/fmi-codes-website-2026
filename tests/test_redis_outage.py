"""A Redis outage only turns off what Redis provides (#256).

The limiter and the app's Redis client run against a real Redis behind a TCP proxy
(tests/redis_proxy.py) that each test switches between up, hanging and refusing, so
the timeouts, the limiter's in-memory fallback and its recovery run for real. They
need REDIS_URL (CI sets it) and skip without it. The database is stubbed per route
the way tests/test_rate_limits.py does it.
"""

import importlib
import inspect
import os
import threading
import time
from unittest.mock import patch

import bcrypt
import flask
import pytest
from app import limiter
from app.routes import auth as auth_routes
from app.services import feature_flag_service, mentor_service, redis_client
from app.utils import fail_open_limiter
from app.utils.fail_open_limiter import FailOpenLimiter
from app.utils.rate_limits import (
    LIMITER_KEY_PREFIX,
    LOGIN_ACCOUNT_LIMIT,
    forget_login_attempts,
    login_account_key,
    scaled,
)
from flask_limiter import Limiter
from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter

import redis
from tests.redis_proxy import RedisProxy

REDIS_URL = os.environ.get("REDIS_URL")
RIGHT_GUESS = "right-guess-1234"
FAST_HASH = bcrypt.hashpw(RIGHT_GUESS.encode(), bcrypt.gensalt(rounds=4)).decode()
# A request that meets the outage first waits out one limiter timeout and one app-client
# timeout (0.5 s each); with margin for a slow runner. Before #256 a hanging Redis never
# answered at all. Every request after that answers at normal speed.
FIRST_REQUEST_BOUND = 2.0
LATER_REQUEST_BOUND = 0.3


@limiter.limit("2 per minute")
def two_per_minute():
    return "ok"


def _direct():
    return redis.Redis.from_url(REDIS_URL, socket_timeout=2)


def _limiter_keys():
    connection = _direct()
    try:
        return list(connection.scan_iter(f"{LIMITER_KEY_PREFIX}:*"))
    finally:
        connection.close()


def _clear_limiter_keys():
    keys = _limiter_keys()
    if keys:
        connection = _direct()
        try:
            connection.delete(*keys)
        finally:
            connection.close()


@pytest.fixture()
def proxy():
    if not REDIS_URL:
        pytest.skip("Redis not configured (set REDIS_URL)")
    _clear_limiter_keys()
    proxy = RedisProxy(REDIS_URL)
    yield proxy
    proxy.close()
    _clear_limiter_keys()


# During an outage the limiter pings its storage as the hold after the last Redis error
# ends, then 2, 4, 8, 16 and 32 s after each ping (then again from 1 s), and each ping makes
# one request wait for it. The fixture pushes the next ping out of reach so timings don't depend
# on when it lands; recheck_limiter_storage() lets the next request ping. Name-mangled
# attributes: a rename fails these tests, never silently.
def recheck_limiter_storage(monkeypatch):
    monkeypatch.setattr(limiter, "_hold_until", 0.0)
    monkeypatch.setattr(limiter, "_Limiter__last_check_backend", 0.0)


@pytest.fixture()
def app(proxy, monkeypatch):
    for var in ("REDIS_SENTINELS", "REDIS_MASTER_NAME", "RATELIMIT_MULTIPLIER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REDIS_URL", proxy.url)
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "y" * 40)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$" + "a" * 22)
    # The module-level limiter keeps its state from one app to the next; monkeypatch puts
    # every piece back, so no later test inherits a dead storage or this test's options.
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(limiter, "_storage_dead", False)
    monkeypatch.setattr(limiter, "_storage_options", {"key_prefix": LIMITER_KEY_PREFIX})
    monkeypatch.setattr(limiter, "_Limiter__check_backend_count", 0)
    monkeypatch.setattr(limiter, "_Limiter__last_check_backend", time.time() + 3600)
    monkeypatch.setattr(limiter, "_hold_until", 0.0)
    monkeypatch.setattr(limiter, "_last_storage_error", float("-inf"))
    monkeypatch.setattr(limiter, "_pending_clears", set())
    monkeypatch.setattr(feature_flag_service, "is_enabled", lambda name: False)
    monkeypatch.setattr(auth_routes, "execute_query", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "_DUMMY_HASH", FAST_HASH)
    monkeypatch.setattr(mentor_service, "execute_query", lambda *a, **k: [])
    redis_client.reset_client()

    from app import create_app

    with patch("app.database.init_database"):
        app = create_app("production")
    app.config["SECRET_KEY"] = "x" * 40
    app.add_url_rule("/test/two", "test_two", two_per_minute)
    app.add_url_rule("/test/plain", "test_plain", lambda: "ok")
    yield app
    redis_client.reset_client()


def _timed(call):
    start = time.monotonic()
    response = call()
    return response, time.monotonic() - start


def _issue_table(client):
    """The routes the issue measured, with the status each answers when Redis is fine."""
    login = {"email": "ana@example.com", "password": "x", "role": "participant"}
    return [
        ("/api/health", client.get("/api/health").status_code, 200),
        ("/test/plain", client.get("/test/plain").status_code, 200),
        ("/api/auth/me", client.get("/api/auth/me").status_code, 401),
        ("/api/auth/login", client.post("/api/auth/login", json=login).status_code, 401),
        ("/api/auth/register", client.post("/api/auth/register", json={}).status_code, 403),
        ("/api/universities", client.get("/api/universities").status_code, 200),
    ]


@pytest.mark.parametrize("outage", ["refuse", "hang"])
def test_no_route_fails_while_redis_is_away(app, proxy, outage):
    getattr(proxy, outage)()
    client = app.test_client()
    start = time.monotonic()
    table = _issue_table(client)
    assert [(path, status) for path, status, _ in table] == [
        (path, expected) for path, _, expected in table
    ]
    assert time.monotonic() - start < FIRST_REQUEST_BOUND


@pytest.mark.parametrize("outage", ["refuse", "hang"])
def test_limits_still_apply_in_memory(app, proxy, outage):
    getattr(proxy, outage)()
    client = app.test_client()
    responses = [client.get("/test/two") for _ in range(3)]
    assert [r.status_code for r in responses] == [200, 200, 429]
    assert 55 <= int(responses[2].headers["Retry-After"]) <= 60


def test_a_hanging_redis_costs_one_wait_then_none(app, proxy):
    proxy.hang()
    client = app.test_client()
    _, first = _timed(lambda: client.get("/test/plain"))
    later = [_timed(lambda: client.get("/test/plain"))[1] for _ in range(10)]
    assert first < FIRST_REQUEST_BOUND
    assert max(later) < LATER_REQUEST_BOUND


def test_the_readiness_probe_never_waits_on_a_hanging_redis(app, proxy, monkeypatch):
    monkeypatch.setattr("app.routes.api_routes.execute_query", lambda *a, **k: {"ok": 1})
    proxy.hang()
    client = app.test_client()
    first, first_took = _timed(lambda: client.get("/api/health/ready"))
    second, second_took = _timed(lambda: client.get("/api/health/ready"))
    assert first.status_code == second.status_code == 200
    assert first.get_json() == second.get_json() == {"db": "ok", "redis": "down"}
    assert first_took < FIRST_REQUEST_BOUND
    assert second_took < LATER_REQUEST_BOUND


def test_counts_land_in_redis_again_after_recovery(app, proxy, monkeypatch):
    """A second app instance (another pod) shares the limit again once Redis is back."""
    client = app.test_client()
    proxy.refuse()
    assert client.get("/test/two").status_code == 200
    assert _limiter_keys() == []

    proxy.up()
    recheck_limiter_storage(monkeypatch)
    # A decorated route pings in its own check, after the app-wide check has already
    # counted the request in memory, so this request stays there (#261) and the next one
    # lands in Redis.
    assert client.get("/test/two").status_code == 200
    assert limiter._storage_dead is False
    assert _limiter_keys() == []
    assert client.get("/test/two").status_code == 200
    assert _limiter_keys() != []

    other_pod = storage_from_string(REDIS_URL, key_prefix=LIMITER_KEY_PREFIX)
    try:
        MovingWindowRateLimiter(other_pod).hit(parse("2 per minute"), "ip:127.0.0.1", "test_two")
    finally:
        other_pod.get_connection().close()
    assert client.get("/test/two").status_code == 429


def test_the_limiter_logs_once_down_and_once_back(app, proxy, monkeypatch, caplog):
    caplog.set_level("INFO", logger="flask-limiter")
    client = app.test_client()
    proxy.refuse()
    for _ in range(5):
        client.get("/test/plain")
    proxy.up()
    recheck_limiter_storage(monkeypatch)
    for _ in range(5):
        client.get("/test/plain")
    messages = [r.getMessage() for r in caplog.records if r.name == "flask-limiter"]
    assert messages == [
        "Rate limit storage unreachable - falling back to in-memory storage",
        "Rate limit storage recovered",
    ]


def test_redis_dying_inside_the_limiter_still_answers(app, proxy):
    client = app.test_client()
    assert client.get("/test/plain").status_code == 200
    proxy.hang()
    result = {}
    request = threading.Thread(
        target=lambda: result.update(response=client.get("/api/universities"))
    )
    start = time.monotonic()
    request.start()
    time.sleep(0.1)
    proxy.refuse()
    request.join(10)
    assert result["response"].status_code == 200
    assert time.monotonic() - start < FIRST_REQUEST_BOUND


def test_redis_dying_inside_a_cache_call_still_answers(proxy, monkeypatch):
    monkeypatch.delenv("REDIS_SENTINELS", raising=False)
    monkeypatch.setenv("REDIS_URL", proxy.url)
    redis_client.reset_client()
    try:
        assert redis_client.redis_set("cache:outage-test", "v", ttl=30) is True
        proxy.hang()
        threading.Timer(0.1, proxy.refuse).start()
        start = time.monotonic()
        assert redis_client.redis_get("cache:outage-test", default="db") == "db"
        assert time.monotonic() - start < 1.0
    finally:
        redis_client.reset_client()
        connection = _direct()
        connection.delete("cache:outage-test")
        connection.close()


# --- Switching to the fallback (#261) ---


def _wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


@pytest.mark.parametrize("outage", ["hang", "refuse"])
def test_a_request_in_flight_when_its_worker_falls_back_still_answers(app, proxy, outage):
    """The first request whose Redis call fails switches the worker to memory. A second
    one whose call was already in flight fails after that and used to answer 500, since
    Flask-Limiter only fell back for the first. Whichever fails second is the one."""
    proxy.hang()
    statuses = {}

    def call(name):
        statuses[name] = app.test_client().get("/test/two").status_code

    requests = [threading.Thread(target=call, args=(name,)) for name in ("a", "b")]
    requests[0].start()
    time.sleep(0.2)
    requests[1].start()
    if outage == "refuse":
        # The first call has timed out; the second is still waiting on its socket.
        _wait_for(lambda: limiter._storage_dead)
        proxy.refuse()
    for request in requests:
        request.join(10)

    assert statuses == {"a": 200, "b": 200}
    third = app.test_client().get("/test/two")
    assert third.status_code == 429
    assert 55 <= int(third.headers["Retry-After"]) <= 60
    assert _limiter_keys() == []


def test_a_ping_that_answers_while_hits_fail_cannot_loop(app, proxy, monkeypatch):
    """During a failover the storage ping can answer while every hit still fails. A rerun
    that went back to Redis on that answer could fail and rerun again with no end."""
    proxy.refuse()
    monkeypatch.setattr(limiter.storage, "check", lambda: True)
    monkeypatch.setattr(limiter, "_Limiter__should_check_backend", lambda: True)
    client = app.test_client()
    assert [client.get("/test/two").status_code for _ in range(3)] == [200, 200, 429]


def test_a_limiter_bug_leaves_the_worker_on_redis(app, monkeypatch, caplog):
    """A key function that raises is not a storage outage: no switch to memory and no
    "storage unreachable" line, which would send an operator after Redis."""

    def broken(_role):
        raise RuntimeError("bug")

    caplog.set_level("INFO", logger="flask-limiter")
    monkeypatch.setattr("app.utils.rate_limits._account_key", broken)
    body = {"email": "ana@example.com", "password": "x", "role": "participant"}
    assert app.test_client().post("/api/auth/login", json=body).status_code == 500
    assert limiter._storage_dead is False
    assert [r for r in caplog.records if r.name == "flask-limiter"] == []


def test_the_worker_holds_the_fallback_after_a_redis_error(app, proxy, monkeypatch):
    """Pinging right after a switch let a failover flip the worker back and forth within
    milliseconds. The ping now waits out a hold after the last Redis error."""
    client = app.test_client()
    proxy.refuse()
    assert client.get("/test/plain").status_code == 200
    proxy.up()
    pings = []
    check = limiter.storage.check
    monkeypatch.setattr(limiter.storage, "check", lambda: pings.append(1) or check())
    monkeypatch.setattr(limiter, "_Limiter__last_check_backend", 0.0)
    assert client.get("/test/plain").status_code == 200
    assert pings == []
    assert limiter._storage_dead is True

    switched = time.monotonic()
    monkeypatch.setattr(
        fail_open_limiter, "_now", lambda: switched + redis_client.BREAKER_OPEN_SECONDS - 0.2
    )
    assert client.get("/test/plain").status_code == 200
    assert pings == []
    monkeypatch.setattr(
        fail_open_limiter, "_now", lambda: switched + redis_client.BREAKER_OPEN_SECONDS + 0.1
    )
    assert client.get("/test/plain").status_code == 200
    assert pings == [1]
    assert limiter._storage_dead is False


def test_a_ping_answered_after_a_fresh_redis_error_is_ignored(app, proxy, monkeypatch):
    """A ping can take a whole timeout; a Redis error while it is in flight means its
    answer is stale, and taking it would put the worker back on a failing Redis."""
    client = app.test_client()
    proxy.refuse()
    assert client.get("/test/plain").status_code == 200
    proxy.up()
    recheck_limiter_storage(monkeypatch)
    in_flight, release = threading.Event(), threading.Event()

    class SlowPing:
        def ping(self):
            in_flight.set()
            release.wait(5)
            return True

    monkeypatch.setattr(limiter.storage, "get_connection", lambda: SlowPing())
    result = {}
    request = threading.Thread(target=lambda: result.update(response=client.get("/test/plain")))
    request.start()
    assert in_flight.wait(5)
    limiter._switch_to_memory()  # what another request's failing Redis call does
    release.set()
    request.join(10)
    assert result["response"].status_code == 200
    assert limiter._storage_dead is True


def test_a_request_counted_in_memory_stays_there(app, proxy):
    """Another thread's ping can put the worker back on Redis mid-request. The rest of the
    request (a later check, the 429's Retry-After) must read where it was counted."""

    def store():
        limiter._storage_dead = False  # another thread's ping answered
        return "memory" if limiter.limiter is limiter._fallback_limiter else "redis"

    app.add_url_rule("/test/store", "test_store", store)
    client = app.test_client()
    proxy.refuse()
    assert client.get("/test/plain").status_code == 200
    assert client.get("/test/store").get_data(as_text=True) == "memory"


def test_a_request_refused_on_redis_reads_its_retry_after_there(app, proxy, monkeypatch):
    """The worker can switch to memory between a refusal on Redis and the 429 handler. An
    older window in memory could then make the Retry-After early."""
    retry_after = importlib.import_module("app")._retry_after_seconds
    seen = {}

    def switched_first():
        limiter._storage_dead = True  # another thread's Redis error lands
        seen["store"] = "redis" if limiter.limiter is limiter._limiter else "memory"
        return retry_after()

    monkeypatch.setattr("app._retry_after_seconds", switched_first)
    client = app.test_client()
    assert [client.get("/test/two").status_code for _ in range(3)] == [200, 200, 429]
    assert seen == {"store": "redis"}


def _login_context(app):
    body = {"email": "ana@example.com", "password": "x", "role": "participant"}
    return app.test_request_context("/api/auth/login", method="POST", json=body)


def _login_limit():
    """The account limit's item and identifiers, inside _login_context."""
    return parse(scaled(LOGIN_ACCOUNT_LIMIT)()), (login_account_key(), flask.request.endpoint)


@pytest.mark.parametrize("on_fallback", [False, True])
def test_a_good_login_clears_failed_attempts_in_both_stores(app, proxy, monkeypatch, on_fallback):
    """On the fallback the Redis clear waits for recovery, so a hung Redis costs the login
    no wait."""
    with _login_context(app):
        item, ids = _login_limit()
        stores = {"memory": limiter._fallback_limiter, "redis": limiter._limiter}
        for store in stores.values():
            for _ in range(item.amount):
                store.hit(item, *ids)
        if on_fallback:
            monkeypatch.setattr(limiter, "_storage_dead", True)
            proxy.hang()
        _, took = _timed(forget_login_attempts)
        proxy.up()
        cleared = {name: store.test(item, *ids) for name, store in stores.items()}
    assert cleared == {"memory": True, "redis": not on_fallback}
    assert took < LATER_REQUEST_BOUND


def test_a_login_on_the_fallback_clears_redis_once_the_worker_is_back(app, proxy, monkeypatch):
    """Typos counted in Redis just before an outage would otherwise still block the owner
    for up to a minute once Redis is back."""
    with _login_context(app):
        item, ids = _login_limit()
        for _ in range(item.amount):
            limiter._limiter.hit(item, *ids)
    client = app.test_client()
    proxy.refuse()
    assert client.get("/test/plain").status_code == 200
    with _login_context(app):
        forget_login_attempts()
    proxy.up()
    assert not limiter._limiter.test(item, *ids)

    recheck_limiter_storage(monkeypatch)
    assert client.get("/test/plain").status_code == 200
    assert limiter._storage_dead is False
    assert limiter._limiter.test(item, *ids)
    assert limiter._pending_clears == set()


def test_a_redis_error_while_clearing_switches_the_worker(app, proxy):
    proxy.refuse()
    with _login_context(app):
        forget_login_attempts()
    assert limiter._storage_dead is True
    assert len(limiter._pending_clears) == 1


# --- Login after an outage ---


@pytest.fixture()
def login_app(app, monkeypatch):
    def lookup(app, query, params, fetch_one=False):
        return {"id": 7, "password_hash": FAST_HASH} if params[0] == "ana@example.com" else None

    monkeypatch.setattr(auth_routes, "execute_query", lookup)
    monkeypatch.setattr(auth_routes, "_fetch_user_profile", lambda *a, **k: {})
    return app


def _login(client, password):
    body = {"email": "ana@example.com", "password": password, "role": "participant"}
    return client.post("/api/auth/login", json=body)


@pytest.mark.parametrize("phase", ["fallback", "recovered"])
def test_login_limits_and_their_reset_work_through_an_outage(login_app, proxy, monkeypatch, phase):
    client = login_app.test_client()
    proxy.refuse()
    assert client.get("/test/plain").status_code == 200
    if phase == "recovered":
        proxy.up()
        recheck_limiter_storage(monkeypatch)
        assert client.get("/test/plain").status_code == 200

    assert [_login(client, "wrong").status_code for _ in range(14)] == [401] * 14
    assert _login(client, RIGHT_GUESS).status_code == 200
    assert [_login(client, "wrong").status_code for _ in range(15)] == [401] * 15
    refused = _login(client, RIGHT_GUESS)
    assert refused.status_code == 429
    assert 55 <= int(refused.headers["Retry-After"]) <= 60
    assert (_limiter_keys() != []) is (phase == "recovered")


# --- Guards ---


def test_the_limiter_is_built_to_survive_its_storage():
    assert isinstance(limiter, FailOpenLimiter)
    assert limiter._in_memory_fallback_enabled is True
    assert not limiter._swallow_errors


def _signature(function):
    return [(p.name, p.default) for p in inspect.signature(function).parameters.values()]


def test_the_private_flask_limiter_api_it_overrides_is_unchanged():
    """FailOpenLimiter overrides and calls these; a Flask-Limiter release that changes them
    must fail here before it can change how an outage is handled."""
    empty = inspect.Parameter.empty
    assert _signature(Limiter._check_request_limit) == [
        ("self", empty),
        ("callable_name", None),
        ("in_middleware", True),
    ]
    assert _signature(Limiter._Limiter__filter_limits) == [
        ("self", empty),
        ("endpoint", empty),
        ("blueprint", empty),
        ("callable_name", empty),
        ("in_middleware", False),
    ]
    assert _signature(Limiter._Limiter__evaluate_limits) == [
        ("self", empty),
        ("endpoint", empty),
        ("limits", empty),
    ]
    assert _signature(Limiter._Limiter__should_check_backend) == [("self", empty)]
    assert isinstance(Limiter.__dict__["limiter"], property)


def test_the_limiter_state_it_reads_exists(app):
    with app.test_request_context("/"):
        assert callable(limiter.context.seen_limits.clear)
    assert isinstance(limiter._storage_dead, bool)
    assert limiter._fallback_limiter is not None
    assert limiter._limiter is not None
    assert callable(limiter.storage.get_connection)


def test_a_limiter_bug_fails_the_request_instead_of_lifting_the_limit(app, monkeypatch):
    """With errors swallowed, a key function that raises would let every login through
    unlimited; a 500 is loud and lets nothing through."""

    def broken(_role):
        raise RuntimeError("bug")

    monkeypatch.setattr("app.utils.rate_limits._account_key", broken)
    body = {"email": "ana@example.com", "password": "x", "role": "participant"}
    assert app.test_client().post("/api/auth/login", json=body).status_code == 500


def test_the_limiters_redis_connections_carry_the_timeouts(app):
    pool = limiter.storage.storage.connection_pool
    assert pool.connection_kwargs["socket_timeout"] == 0.5
    assert pool.connection_kwargs["socket_connect_timeout"] == 0.5
    assert pool.connection_kwargs["retry"].get_retries() == 0


def test_the_limiters_sentinel_connections_carry_the_timeouts(monkeypatch):
    """CI has no Sentinel (#24); building the storage contacts nothing."""
    monkeypatch.setenv("REDIS_SENTINELS", "s1:26379")
    monkeypatch.setenv("REDIS_MASTER_NAME", "mymaster")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "y" * 40)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$" + "a" * 22)
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(limiter, "_storage_options", {"key_prefix": LIMITER_KEY_PREFIX})
    from app import create_app

    with patch("app.database.init_database"):
        create_app("production")
    sentinel = limiter.storage.sentinel
    for kwargs in (sentinel.sentinel_kwargs, sentinel.connection_kwargs):
        assert kwargs["socket_timeout"] == 0.5
        assert kwargs["socket_connect_timeout"] == 0.5
        assert kwargs["retry"].get_retries() == 0
