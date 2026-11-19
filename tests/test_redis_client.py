"""Pure-unit tests for app.services.redis_client.

None of these tests require a live Redis server. The connection modes that
would normally reach out to Redis are exercised by mocking redis.from_url /
redis.sentinel.Sentinel, and the fail-open helpers are tested in the
Redis-disabled (client is None) state by clearing all Redis env vars. The
breaker tests (#256) move the module's clock instead of sleeping; two tests use
a local socket that refuses or never answers, the way a dead or stalled Redis does.
"""

import logging
import socket
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.services import redis_client
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError

_REDIS_ENV_VARS = (
    "REDIS_URL",
    "REDIS_SENTINELS",
    "REDIS_MASTER_NAME",
    "REDIS_SOCKET_TIMEOUT",
    "REDIS_CONNECT_TIMEOUT",
    "REDIS_PASSWORD",
)


@pytest.fixture()
def clear_redis_env(monkeypatch):
    """Remove every Redis-related env var and rebuild the singleton around it."""
    for name in _REDIS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    redis_client.reset_client()
    yield monkeypatch
    redis_client.reset_client()


def test_jittered_ttl_within_bounds(clear_redis_env):
    for _ in range(500):
        ttl = redis_client.jittered_ttl(60, 10)
        assert 50 <= ttl <= 70


def test_jittered_ttl_never_below_one(clear_redis_env):
    """Even when jitter can push the offset below zero, the floor is 1."""
    seen_floor = False
    for _ in range(500):
        ttl = redis_client.jittered_ttl(1, 10)
        assert ttl >= 1
        assert ttl <= 11
        if ttl == 1:
            seen_floor = True
    assert seen_floor, "expected the floor of 1 to be hit at least once over 500 iterations"


def test_jittered_ttl_zero_jitter_returns_base(clear_redis_env):
    assert redis_client.jittered_ttl(60, 0) == 60


def test_jittered_ttl_negative_jitter_returns_base(clear_redis_env):
    assert redis_client.jittered_ttl(60, -5) == 60


def test_jittered_ttl_zero_jitter_floors_at_one(clear_redis_env):
    assert redis_client.jittered_ttl(0, 0) == 1


def test_build_limiter_storage_uri_sentinel_mode(clear_redis_env):
    clear_redis_env.setenv("REDIS_SENTINELS", "s1:26379,s2:26380")
    clear_redis_env.setenv("REDIS_MASTER_NAME", "mymaster")
    uri = redis_client.build_limiter_storage_uri()
    assert uri == "redis+sentinel://s1:26379,s2:26380/mymaster"


def test_build_limiter_storage_uri_sentinel_default_port(clear_redis_env):
    clear_redis_env.setenv("REDIS_SENTINELS", "s1,s2")
    clear_redis_env.setenv("REDIS_MASTER_NAME", "mymaster")
    uri = redis_client.build_limiter_storage_uri()
    assert uri == "redis+sentinel://s1:26379,s2:26379/mymaster"


def test_build_limiter_storage_uri_redis_url_mode(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    assert redis_client.build_limiter_storage_uri() == "redis://localhost:6379/0"


def test_build_limiter_storage_uri_sentinel_precedes_url(clear_redis_env):
    """Sentinel config wins over a stray REDIS_URL, mirroring _build_client."""
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    clear_redis_env.setenv("REDIS_SENTINELS", "s1:26379")
    clear_redis_env.setenv("REDIS_MASTER_NAME", "mymaster")
    assert redis_client.build_limiter_storage_uri() == "redis+sentinel://s1:26379/mymaster"


def test_build_limiter_storage_uri_nothing_set_returns_memory(clear_redis_env):
    assert redis_client.build_limiter_storage_uri() == "memory://"


def test_build_limiter_storage_uri_blank_sentinels_falls_through(clear_redis_env):
    """Sentinels that parse to zero hosts fall through to REDIS_URL / memory."""
    clear_redis_env.setenv("REDIS_SENTINELS", " , , ")
    clear_redis_env.setenv("REDIS_MASTER_NAME", "mymaster")
    assert redis_client.build_limiter_storage_uri() == "memory://"


def test_get_redis_client_nothing_set_returns_none(clear_redis_env):
    assert redis_client.get_redis_client() is None


def test_get_redis_client_redis_url_mode_uses_from_url(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    fake_client = MagicMock()
    with patch("redis.from_url", return_value=fake_client) as from_url:
        client = redis_client.get_redis_client()
    assert client is fake_client
    from_url.assert_called_once()
    assert from_url.call_args.args[0] == "redis://localhost:6379/0"
    # Building never contacts Redis, so an outage at startup can't turn it off for good.
    fake_client.ping.assert_not_called()


def test_get_redis_client_sentinel_mode_uses_sentinel(clear_redis_env):
    clear_redis_env.setenv("REDIS_SENTINELS", "s1:26379,s2:26379")
    clear_redis_env.setenv("REDIS_MASTER_NAME", "mymaster")
    fake_master = MagicMock()
    fake_sentinel = MagicMock()
    fake_sentinel.master_for.return_value = fake_master
    with patch("redis.sentinel.Sentinel", return_value=fake_sentinel) as sentinel_cls:
        client = redis_client.get_redis_client()
    assert client is fake_master
    sentinel_cls.assert_called_once()
    fake_sentinel.master_for.assert_called_once()
    assert fake_sentinel.master_for.call_args.args[0] == "mymaster"
    fake_master.ping.assert_not_called()


def test_get_redis_client_sentinel_passes_password_once(clear_redis_env):
    """master_for gets `password` exactly once; sentinels get it via sentinel_kwargs.

    Two regressions guarded here:
    1. password was passed both by-name and inside **common_kwargs, so a real
       redis-py master_for() raised 'got multiple values for keyword argument
       password' and Sentinel Redis silently fell back to disabled.
    2. the sentinel-query connections got no password, so on a password-protected
       Sentinel (Bitnami auth.enabled=true) master discovery failed with
       AuthenticationError → 'No master found'. The sentinel password must ride
       on sentinel_kwargs, distinct from the data-node password.

    A MagicMock hides both, so this fake mirrors the real signatures.
    """
    clear_redis_env.setenv("REDIS_SENTINELS", "s1:26379")
    clear_redis_env.setenv("REDIS_MASTER_NAME", "mymaster")
    clear_redis_env.setenv("REDIS_PASSWORD", "s3cr3t")

    seen = {}

    class FakeSentinel:
        def __init__(self, hosts, sentinel_kwargs=None, **kwargs):
            seen["sentinel_kwargs"] = sentinel_kwargs or {}

        def master_for(self, name, password=None, **kwargs):
            seen["password"] = password
            seen["name"] = name
            return MagicMock()

    with patch("redis.sentinel.Sentinel", FakeSentinel):
        client = redis_client.get_redis_client()

    assert client is not None
    assert seen["name"] == "mymaster"
    assert seen["password"] == "s3cr3t"
    assert seen["sentinel_kwargs"].get("password") == "s3cr3t"


def test_get_redis_client_is_singleton(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    fake_client = MagicMock()
    with patch("redis.from_url", return_value=fake_client) as from_url:
        first = redis_client.get_redis_client()
        second = redis_client.get_redis_client()
    assert first is second
    from_url.assert_called_once()


def test_redis_get_returns_default_when_client_none(clear_redis_env):
    assert redis_client.redis_get("some:key") is None
    assert redis_client.redis_get("some:key", default="fallback") == "fallback"


def test_redis_set_returns_false_when_client_none(clear_redis_env):
    assert redis_client.redis_set("some:key", "value") is False
    assert redis_client.redis_set("some:key", "value", ttl=30) is False


def test_redis_del_returns_false_when_client_none(clear_redis_env):
    assert redis_client.redis_del("some:key") is False
    assert redis_client.redis_del("a", "b", "c") is False


def test_redis_del_no_keys_returns_false(clear_redis_env):
    assert redis_client.redis_del() is False


def test_fail_open_helpers_do_not_raise_when_client_none(clear_redis_env):
    """The whole point of fail-open: none of these raise when Redis is off."""
    redis_client.redis_get("k")
    redis_client.redis_set("k", "v")
    redis_client.redis_set("k", "v", ttl=10)
    redis_client.redis_del("k")


def test_redis_get_swallows_client_errors(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    fake_client = MagicMock()
    fake_client.get.side_effect = OSError("boom")
    with patch("redis.from_url", return_value=fake_client):
        assert redis_client.redis_get("k", default="fb") == "fb"


def test_redis_set_swallows_client_errors(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    fake_client = MagicMock()
    fake_client.setex.side_effect = OSError("boom")
    with patch("redis.from_url", return_value=fake_client):
        assert redis_client.redis_set("k", "v", ttl=10) is False


def test_redact_url_strips_password():
    assert (
        redis_client._redact_url("redis://:secret@localhost:6379") == "redis://:***@localhost:6379"
    )


def test_redact_url_strips_user_and_password():
    assert redis_client._redact_url("redis://user:secret@host:6379") == "redis://user:***@host:6379"


def test_redact_url_no_password_unchanged():
    url = "redis://localhost:6379"
    assert redis_client._redact_url(url) == url


def test_redis_del_swallows_client_errors(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    fake_client = MagicMock()
    fake_client.delete.side_effect = OSError("boom")
    with patch("redis.from_url", return_value=fake_client):
        assert redis_client.redis_del("k") is False


def test_redis_incr_returns_false_when_client_none(clear_redis_env):
    assert redis_client.redis_incr("k") is False


def test_redis_incr_increments(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    fake_client = MagicMock()
    with patch("redis.from_url", return_value=fake_client):
        assert redis_client.redis_incr("k") is True
    fake_client.incr.assert_called_once_with("k")


def test_redis_incr_swallows_client_errors(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    fake_client = MagicMock()
    fake_client.incr.side_effect = OSError("boom")
    with patch("redis.from_url", return_value=fake_client):
        assert redis_client.redis_incr("k") is False


# --- Connection settings (#256) ---


def _kwargs_of_from_url(env, **extra):
    env.setenv("REDIS_URL", "redis://localhost:6379/0")
    for name, value in extra.items():
        env.setenv(name, value)
    with patch("redis.from_url", return_value=MagicMock()) as from_url:
        redis_client.get_redis_client()
    return from_url.call_args.kwargs


def _never_retries(retry):
    """redis-py's default retries 3 times, and twice over in Sentinel mode (#256 review)."""
    return retry.get_retries() == 0


def test_client_has_short_timeouts_and_never_retries(clear_redis_env):
    kwargs = _kwargs_of_from_url(clear_redis_env)
    assert kwargs["socket_timeout"] == 0.5
    assert kwargs["socket_connect_timeout"] == 0.5
    assert "retry_on_timeout" not in kwargs
    assert _never_retries(kwargs["retry"])


@pytest.mark.parametrize(("raw", "expected"), [("0.25", 0.25), ("2", 2.0), ("", 0.5)])
def test_timeouts_come_from_env(clear_redis_env, raw, expected):
    kwargs = _kwargs_of_from_url(
        clear_redis_env, REDIS_SOCKET_TIMEOUT=raw, REDIS_CONNECT_TIMEOUT=raw
    )
    assert kwargs["socket_timeout"] == kwargs["socket_connect_timeout"] == expected


@pytest.mark.parametrize("raw", ["0", "-1", "soon", "nan", "inf", "1e9", "61"])
def test_a_bad_timeout_falls_back_to_the_default(clear_redis_env, raw):
    """A 0 would make every socket non-blocking and socket.settimeout raises OverflowError
    on inf or 1e9; nothing here may refuse to boot."""
    kwargs = _kwargs_of_from_url(clear_redis_env, REDIS_SOCKET_TIMEOUT=raw)
    assert kwargs["socket_timeout"] == 0.5


def test_sentinel_client_carries_timeouts_on_both_connection_kinds(clear_redis_env):
    """CI has no Sentinel (#24), so the wiring is checked against the constructor calls."""
    clear_redis_env.setenv("REDIS_SENTINELS", "s1:26379")
    clear_redis_env.setenv("REDIS_MASTER_NAME", "mymaster")
    fake_sentinel = MagicMock()
    with patch("redis.sentinel.Sentinel", return_value=fake_sentinel) as sentinel_cls:
        redis_client.get_redis_client()
    sentinel_kwargs = sentinel_cls.call_args.kwargs["sentinel_kwargs"]
    master_kwargs = fake_sentinel.master_for.call_args.kwargs
    for kwargs in (sentinel_kwargs, master_kwargs):
        assert kwargs["socket_timeout"] == 0.5
        assert kwargs["socket_connect_timeout"] == 0.5
        assert _never_retries(kwargs["retry"])


def test_limiter_storage_options_for_memory_are_empty(clear_redis_env):
    assert redis_client.build_limiter_storage_options() == {}


def test_limiter_storage_options_for_a_url(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    options = redis_client.build_limiter_storage_options()
    assert options["socket_timeout"] == options["socket_connect_timeout"] == 0.5
    assert _never_retries(options["retry"])
    assert "sentinel_kwargs" not in options


def test_limiter_storage_options_for_sentinel_cover_the_sentinels(clear_redis_env):
    clear_redis_env.setenv("REDIS_SENTINELS", "s1:26379")
    clear_redis_env.setenv("REDIS_MASTER_NAME", "mymaster")
    clear_redis_env.setenv("REDIS_SOCKET_TIMEOUT", "0.3")
    options = redis_client.build_limiter_storage_options()
    sentinel_kwargs = options["sentinel_kwargs"]
    assert options["socket_timeout"] == sentinel_kwargs["socket_timeout"] == 0.3
    assert options["socket_connect_timeout"] == sentinel_kwargs["socket_connect_timeout"] == 0.5
    assert _never_retries(sentinel_kwargs["retry"])


def test_limiter_sentinel_storage_gets_the_options(clear_redis_env):
    """The `limits` Sentinel storage hands the options on to redis-py's Sentinel."""
    from limits.storage import storage_from_string

    clear_redis_env.setenv("REDIS_SENTINELS", "s1:26379")
    clear_redis_env.setenv("REDIS_MASTER_NAME", "mymaster")
    clear_redis_env.setenv("REDIS_PASSWORD", "pw")
    with patch("redis.sentinel.Sentinel") as sentinel_cls:
        storage_from_string(
            redis_client.build_limiter_storage_uri(),
            **redis_client.build_limiter_storage_options(),
        )
    kwargs = sentinel_cls.call_args.kwargs
    assert kwargs["socket_timeout"] == kwargs["sentinel_kwargs"]["socket_timeout"] == 0.5
    assert kwargs["sentinel_kwargs"]["password"] == "pw"
    assert _never_retries(kwargs["retry"])
    assert _never_retries(kwargs["sentinel_kwargs"]["retry"])


# --- Circuit breaker (#256) ---


@pytest.fixture()
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(redis_client, "_now", lambda: now[0])
    return now


@pytest.fixture()
def fake(clear_redis_env):
    """A client the helpers reach through the real breaker."""
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    client = MagicMock()
    client.get.return_value = "cached"
    with patch("redis.from_url", return_value=client):
        yield client


def _down(client, error=RedisConnectionError("refused")):
    client.get.side_effect = error
    assert redis_client.redis_get("k", default="db") == "db"
    client.get.side_effect = None
    client.reset_mock()


@pytest.mark.parametrize(
    "error", [RedisConnectionError("refused"), RedisTimeoutError("stalled"), OSError("reset")]
)
def test_one_failure_opens_the_breaker_for_every_helper(fake, clock, error):
    _down(fake, error)
    assert redis_client.redis_get("k", default="db") == "db"
    assert redis_client.redis_set("k", "v", ttl=10) is False
    assert redis_client.redis_del("k") is False
    assert redis_client.redis_incr("k") is False
    assert redis_client.redis_exists("k") is False
    assert redis_client.redis_status() == "down"
    assert fake.method_calls == []


def test_one_call_tries_again_after_the_open_time_and_closes_it(fake, clock):
    _down(fake)
    clock[0] += redis_client.BREAKER_OPEN_SECONDS - 0.1
    assert redis_client.redis_get("k", default="db") == "db"
    fake.get.assert_not_called()
    clock[0] += 0.2
    assert redis_client.redis_get("k", default="db") == "cached"
    assert redis_client.redis_get("k", default="db") == "cached"
    assert fake.get.call_count == 2


def test_a_failed_retry_opens_it_again(fake, clock):
    _down(fake)
    clock[0] += redis_client.BREAKER_OPEN_SECONDS + 0.1
    _down(fake)
    clock[0] += redis_client.BREAKER_OPEN_SECONDS - 0.1
    assert redis_client.redis_get("k", default="db") == "db"
    fake.get.assert_not_called()


def test_only_one_call_tries_again_at_a_time(fake, clock):
    """While the retry waits on a stalled Redis, every other call keeps its fallback."""
    _down(fake)
    clock[0] += redis_client.BREAKER_OPEN_SECONDS + 0.1
    entered, release = threading.Event(), threading.Event()

    def slow_get(_key):
        entered.set()
        release.wait(5)
        return "cached"

    fake.get.side_effect = slow_get
    probe = threading.Thread(target=redis_client.redis_get, args=("k",))
    probe.start()
    assert entered.wait(5)
    try:
        assert redis_client.redis_get("k", default="db") == "db"
        assert redis_client.redis_exists("k") is False
        fake.exists.assert_not_called()
    finally:
        release.set()
        probe.join(5)
    assert fake.get.call_count == 1
    fake.get.side_effect = None
    assert redis_client.redis_get("k", default="db") == "cached"


def test_an_error_redis_answered_with_never_opens_it(fake, clock):
    """WRONGTYPE and the like mean Redis is up: only that call falls back."""
    fake.get.side_effect = ResponseError("WRONGTYPE")
    assert redis_client.redis_get("k", default="db") == "db"
    fake.get.side_effect = None
    assert redis_client.redis_get("k", default="db") == "cached"


def test_an_answered_error_on_the_retry_lets_the_next_call_try(fake, clock):
    _down(fake)
    clock[0] += redis_client.BREAKER_OPEN_SECONDS + 0.1
    fake.get.side_effect = ResponseError("WRONGTYPE")
    assert redis_client.redis_get("k", default="db") == "db"
    fake.get.side_effect = None
    assert redis_client.redis_get("k", default="db") == "cached"


def test_outage_logs_once_down_and_once_back(fake, clock, caplog):
    caplog.set_level(logging.INFO, logger=redis_client.__name__)
    assert redis_client.redis_get("k") == "cached"
    for _ in range(3):
        _down(fake)
        clock[0] += redis_client.BREAKER_OPEN_SECONDS + 0.1
    for _ in range(5):
        assert redis_client.redis_get("k") == "cached"
    messages = [r.getMessage() for r in caplog.records if r.name == redis_client.__name__]
    assert [m.split(";")[0] for m in messages] == [
        "✓ Redis connected (redis://localhost:6379/0)",
        "Redis unreachable, so caching and token revocation are off in this process",
        "Redis reachable again",
    ]
    assert [r.levelname for r in caplog.records if r.name == redis_client.__name__] == [
        "INFO",
        "WARNING",
        "WARNING",
    ]


def test_a_late_answer_from_before_the_outage_never_closes_it(fake, clock):
    """A call already in flight when the breaker opened may still succeed; only the probe
    may close it, or a flapping Redis would put every thread back on the network."""
    entered, release = threading.Event(), threading.Event()

    def slow_get(_key):
        entered.set()
        release.wait(5)
        return "cached"

    assert redis_client.redis_get("k") == "cached"
    fake.get.side_effect = slow_get
    late = threading.Thread(target=redis_client.redis_get, args=("k",))
    late.start()
    assert entered.wait(5)
    fake.set.side_effect = RedisTimeoutError("stalled")
    assert redis_client.redis_set("k", "v") is False
    release.set()
    late.join(5)
    fake.reset_mock()
    assert redis_client.redis_get("k", default="db") == "db"
    fake.get.assert_not_called()


def test_a_probe_cut_short_still_frees_its_slot(fake, clock):
    """Without it every later call would keep its fallback for the life of the process."""
    _down(fake)
    clock[0] += redis_client.BREAKER_OPEN_SECONDS + 0.1
    fake.get.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        redis_client.redis_get("k")
    fake.get.side_effect = None
    assert redis_client.redis_get("k", default="db") == "cached"


def test_the_readiness_ping_waits_for_the_breaker_too(clear_redis_env, clock):
    """A config that fails to build is retried by the probe only, not by every readiness call."""
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    with patch("redis.from_url", side_effect=ValueError("bad")) as from_url:
        for _ in range(5):
            assert redis_client.redis_status() == "down"
        assert from_url.call_count == 1


def test_a_one_off_client_gets_its_own_timeouts(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    with patch("redis.from_url") as from_url:
        assert redis_client.new_client(timeout=5) is from_url.return_value
    assert from_url.call_args.kwargs["socket_timeout"] == 5
    assert from_url.call_args.kwargs["socket_connect_timeout"] == 5
    assert _never_retries(from_url.call_args.kwargs["retry"])


def test_a_one_off_client_without_redis_is_none(clear_redis_env):
    assert redis_client.new_client(timeout=5) is None


def test_a_build_that_fails_is_retried_behind_the_breaker(clear_redis_env, clock):
    """A process whose first client build fails picks Redis up later without a restart."""
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    client = MagicMock()
    client.get.return_value = "cached"
    with patch("redis.from_url", side_effect=[ValueError("bad"), client]) as from_url:
        assert redis_client.redis_get("k", default="db") == "db"
        assert redis_client.redis_get("k", default="db") == "db"
        assert from_url.call_count == 1
        clock[0] += redis_client.BREAKER_OPEN_SECONDS + 0.1
        assert redis_client.redis_get("k", default="db") == "cached"
        assert from_url.call_count == 2


def test_redis_status_disabled_without_config(clear_redis_env):
    assert redis_client.redis_status() == "disabled"


def test_redis_status_ok(fake):
    fake.ping.return_value = True
    assert redis_client.redis_status() == "ok"


def test_redis_exists(fake):
    fake.exists.return_value = 1
    assert redis_client.redis_exists("jti:blocked:x") is True
    fake.exists.return_value = 0
    assert redis_client.redis_exists("jti:blocked:x") is False


# --- Against a real socket ---


@pytest.fixture()
def silent_port():
    """A port that completes the TCP handshake and never answers, like a stalled Redis."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(16)
    yield server.getsockname()[1]
    server.close()


def _closed_port():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


@pytest.mark.parametrize("kind", ["stalled", "refusing"])
def test_a_dead_redis_costs_one_timeout_per_open_period(clear_redis_env, silent_port, kind):
    port = silent_port if kind == "stalled" else _closed_port()
    clear_redis_env.setenv("REDIS_URL", f"redis://127.0.0.1:{port}/0")
    start = time.monotonic()
    assert redis_client.redis_get("k", default="db") == "db"
    first = time.monotonic() - start
    start = time.monotonic()
    for _ in range(20):
        assert redis_client.redis_get("k", default="db") == "db"
        assert redis_client.redis_exists("k") is False
    rest = time.monotonic() - start
    # One connect or read timeout (0.5 s) plus margin; on Windows a refused localhost
    # connect also waits out the connect timeout.
    assert first < 1.5
    assert rest < 0.1


# --- Guard ---


def test_request_paths_never_use_the_raw_client():
    """The raw client skips the breaker, so a request using it could wait on every call."""
    app_dir = Path(__file__).parent.parent / "backend" / "app"
    users = sorted(
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if "get_redis_client" in path.read_text(encoding="utf-8")
    )
    assert users == [str(Path("services") / "redis_client.py")]
