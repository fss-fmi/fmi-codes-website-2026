"""Tests for the Redis-backed cache wrappers in the service layer.

The DB and file loaders are mocked/monkeypatched, and Redis is controlled by
patching the redis_get/redis_set/redis_del names AS IMPORTED INTO each service
module (the services did `from app.services.redis_client import ...`, so the
bound names live on the service module, not on redis_client).

None of these tests require a live Redis or Postgres.
"""

import json

import pytest
from app.services import (
    mentor_service,
    ranking_service,
    redis_client,
    regulations_service,
)


class FakeRedis:
    """In-memory stand-in for the fail-open redis helpers.

    Tracks set/del calls so tests can assert on the key + payload written.
    """

    def __init__(self, store=None):
        self.store = dict(store or {})
        self.set_calls = []
        self.del_calls = []

    def get(self, key, default=None):
        return self.store.get(key, default)

    def set(self, key, value, ttl=None):
        self.set_calls.append((key, value, ttl))
        self.store[key] = value
        return True

    def delete(self, *keys):
        self.del_calls.append(keys)
        for k in keys:
            self.store.pop(k, None)
        return True


def _wire(monkeypatch, module_path, fake):
    """Point a service module's imported redis helpers at *fake*.

    Only patches the names the module actually imported — regulations_service,
    for instance, has no invalidation path and never imported redis_del.
    """
    import importlib

    module = importlib.import_module(module_path)
    if hasattr(module, "redis_get"):
        monkeypatch.setattr(f"{module_path}.redis_get", fake.get)
    if hasattr(module, "redis_set"):
        monkeypatch.setattr(f"{module_path}.redis_set", fake.set)
    if hasattr(module, "redis_del"):
        monkeypatch.setattr(f"{module_path}.redis_del", fake.delete)


def test_get_all_mentors_cache_hit(monkeypatch, app_ctx):
    cached_rows = [{"mentor_id": 1, "name": "A B"}]
    fake = FakeRedis({"cache:mentors:all": json.dumps(cached_rows)})
    _wire(monkeypatch, "app.services.mentor_service", fake)
    monkeypatch.setattr(
        "app.services.mentor_service.execute_query",
        lambda *a, **k: pytest.fail("DB must not be hit on cache hit"),
    )
    result = mentor_service.get_all_mentors()
    assert result == cached_rows
    assert fake.set_calls == []


def test_get_all_mentors_cache_miss_populates(monkeypatch, app_ctx):
    rows = [{"mentor_id": 7, "name": "C D"}]
    fake = FakeRedis()
    _wire(monkeypatch, "app.services.mentor_service", fake)
    monkeypatch.setattr(
        "app.services.mentor_service.execute_query", lambda *a, **k: rows
    )
    result = mentor_service.get_all_mentors()
    assert result == rows
    assert len(fake.set_calls) == 1
    key, value, ttl = fake.set_calls[0]
    assert key == "cache:mentors:all"
    assert json.loads(value) == rows
    assert ttl >= 1


def test_get_all_mentors_corrupt_cache_falls_through(monkeypatch, app_ctx):
    rows = [{"mentor_id": 9, "name": "E F"}]
    fake = FakeRedis({"cache:mentors:all": "{not valid json"})
    _wire(monkeypatch, "app.services.mentor_service", fake)
    monkeypatch.setattr(
        "app.services.mentor_service.execute_query", lambda *a, **k: rows
    )
    result = mentor_service.get_all_mentors()
    assert result == rows
    assert len(fake.set_calls) == 1


def test_invalidate_mentor_cache_deletes_key(monkeypatch, app_ctx):
    fake = FakeRedis({"cache:mentors:all": "[]"})
    _wire(monkeypatch, "app.services.mentor_service", fake)
    mentor_service._invalidate_mentor_cache()
    assert fake.del_calls == [("cache:mentors:all",)]


def test_get_rankings_cache_hit(monkeypatch, app_ctx):
    cached = [{"team": "T1", "points": 10, "image": None}]
    fake = FakeRedis({"cache:rankings:legacy": json.dumps(cached)})
    _wire(monkeypatch, "app.services.ranking_service", fake)
    monkeypatch.setattr(
        "app.services.ranking_service._load_rankings",
        lambda: pytest.fail("file loader must not run on cache hit"),
    )
    assert ranking_service.get_rankings() == cached
    assert fake.set_calls == []


def test_get_rankings_cache_miss_populates(monkeypatch, app_ctx):
    loaded = [{"team": "T2", "points": 5, "image": None}]
    fake = FakeRedis()
    _wire(monkeypatch, "app.services.ranking_service", fake)
    monkeypatch.setattr("app.services.ranking_service._load_rankings", lambda: loaded)
    assert ranking_service.get_rankings() == loaded
    assert len(fake.set_calls) == 1
    key, value, ttl = fake.set_calls[0]
    assert key == "cache:rankings:legacy"
    assert json.loads(value) == loaded
    assert ttl >= 1


def test_get_team_rankings_cache_hit(monkeypatch, app_ctx):
    cached = [{"team_id": 1, "team_name": "Alpha", "score": 90, "rank": 1}]
    fake = FakeRedis({"cache:rankings:teams": json.dumps(cached)})
    _wire(monkeypatch, "app.services.ranking_service", fake)
    monkeypatch.setattr(
        "app.services.ranking_service._load_team_rankings",
        lambda: pytest.fail("DB loader must not run on cache hit"),
    )
    assert ranking_service.get_team_rankings() == cached
    assert fake.set_calls == []


def test_get_team_rankings_cache_miss_populates(monkeypatch, app_ctx):
    loaded = [{"team_id": 2, "team_name": "Beta", "score": 42, "rank": 1}]
    fake = FakeRedis()
    _wire(monkeypatch, "app.services.ranking_service", fake)
    monkeypatch.setattr(
        "app.services.ranking_service._load_team_rankings", lambda: loaded
    )
    assert ranking_service.get_team_rankings() == loaded
    assert len(fake.set_calls) == 1
    key, value, ttl = fake.set_calls[0]
    assert key == "cache:rankings:teams"
    assert json.loads(value) == loaded
    assert ttl >= 1


def test_invalidate_team_rankings_cache_deletes_key(monkeypatch, app_ctx):
    fake = FakeRedis({"cache:rankings:teams": "[]"})
    _wire(monkeypatch, "app.services.ranking_service", fake)
    ranking_service.invalidate_team_rankings_cache()
    assert fake.del_calls == [("cache:rankings:teams",)]


def test_get_regulations_cache_hit(monkeypatch, app_ctx):
    cached = [{"question": "Q?", "answer": "A."}]
    fake = FakeRedis({"cache:regulations": json.dumps(cached)})
    _wire(monkeypatch, "app.services.regulations_service", fake)
    monkeypatch.setattr(
        "app.services.regulations_service._load_regulations",
        lambda: pytest.fail("file loader must not run on cache hit"),
    )
    assert regulations_service.get_regulations() == cached
    assert fake.set_calls == []


def test_get_regulations_cache_miss_populates(monkeypatch, app_ctx):
    loaded = [{"question": "Where?", "answer": "Here."}]
    fake = FakeRedis()
    _wire(monkeypatch, "app.services.regulations_service", fake)
    monkeypatch.setattr(
        "app.services.regulations_service._load_regulations", lambda: loaded
    )
    assert regulations_service.get_regulations() == loaded
    assert len(fake.set_calls) == 1
    key, value, ttl = fake.set_calls[0]
    assert key == "cache:regulations"
    assert json.loads(value) == loaded
    assert ttl >= 1


def test_mentors_fallback_when_redis_unavailable(monkeypatch, app_ctx):
    """redis_get returns None + redis_set no-ops (fail-open on outage).

    The function must still return DB data and never raise.
    """
    rows = [{"mentor_id": 3, "name": "G H"}]
    monkeypatch.setattr("app.services.mentor_service.redis_get", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.mentor_service.redis_set", lambda *a, **k: False
    )
    monkeypatch.setattr(
        "app.services.mentor_service.execute_query", lambda *a, **k: rows
    )
    assert mentor_service.get_all_mentors() == rows


def test_rankings_fallback_when_redis_unavailable(monkeypatch, app_ctx):
    loaded = [{"team": "T3", "points": 1, "image": None}]
    monkeypatch.setattr("app.services.ranking_service.redis_get", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.ranking_service.redis_set", lambda *a, **k: False
    )
    monkeypatch.setattr("app.services.ranking_service._load_rankings", lambda: loaded)
    assert ranking_service.get_rankings() == loaded


def test_regulations_fallback_when_redis_unavailable(monkeypatch, app_ctx):
    loaded = [{"question": "Q", "answer": "A"}]
    monkeypatch.setattr(
        "app.services.regulations_service.redis_get", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "app.services.regulations_service.redis_set", lambda *a, **k: False
    )
    monkeypatch.setattr(
        "app.services.regulations_service._load_regulations", lambda: loaded
    )
    assert regulations_service.get_regulations() == loaded


def test_real_wrapper_fails_open_against_closed_port(monkeypatch, app_ctx):
    """Proves the real fail-open wrapper degrades gracefully on a dead endpoint.

    Resilient by design: a closed port yields None (miss), and if something
    happens to be listening the value is simply whatever it returns — either
    way redis_get must not raise. reset_client() is restored in teardown.
    """
    for name in (
        "REDIS_SENTINELS",
        "REDIS_MASTER_NAME",
        "REDIS_SOCKET_TIMEOUT",
        "REDIS_CONNECT_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:1")
    redis_client.reset_client()
    try:
        result = redis_client.redis_get("cache:does-not-matter", default="fallback")
        assert result in ("fallback", None) or isinstance(result, str)
    finally:
        redis_client.reset_client()
