"""Pure-unit tests for app.services.redis_client.

None of these tests require a live Redis server. The connection modes that
would normally reach out to Redis are exercised by mocking redis.from_url /
redis.sentinel.Sentinel, and the fail-open helpers are tested in the
Redis-disabled (client is None) state by clearing all Redis env vars.
"""

from unittest.mock import MagicMock, patch

import pytest
from app.services import redis_client

_REDIS_ENV_VARS = (
    "REDIS_URL",
    "REDIS_SENTINELS",
    "REDIS_MASTER_NAME",
    "REDIS_SOCKET_TIMEOUT",
    "REDIS_CONNECT_TIMEOUT",
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
    fake_client.ping.assert_called_once()


def test_get_redis_client_redis_url_ping_failure_returns_none(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    fake_client = MagicMock()
    fake_client.ping.side_effect = OSError("connection refused")
    with patch("redis.from_url", return_value=fake_client):
        assert redis_client.get_redis_client() is None


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
    fake_master.ping.assert_called_once()


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


def test_redis_del_swallows_client_errors(clear_redis_env):
    clear_redis_env.setenv("REDIS_URL", "redis://localhost:6379/0")
    fake_client = MagicMock()
    fake_client.delete.side_effect = OSError("boom")
    with patch("redis.from_url", return_value=fake_client):
        assert redis_client.redis_del("k") is False
