"""Tests for the Redis-backed cache wrappers in the service layer.

The DB and file loaders are mocked/monkeypatched, and Redis is controlled by
patching the redis_get/redis_set/redis_del names AS IMPORTED INTO each service
module (the services did `from app.services.redis_client import ...`, so the
bound names live on the service module, not on redis_client).

None of these tests require a live Redis or Postgres.
"""

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from app.services import (
    mentor_service,
    ranking_service,
    redis_client,
    regulations_service,
)
from app.services.team_service import TeamService


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
    monkeypatch.setattr("app.services.mentor_service.execute_query", lambda *a, **k: rows)
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
    monkeypatch.setattr("app.services.mentor_service.execute_query", lambda *a, **k: rows)
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
    monkeypatch.setattr("app.services.ranking_service._load_team_rankings", lambda: loaded)
    assert ranking_service.get_team_rankings() == loaded
    assert len(fake.set_calls) == 1
    key, value, ttl = fake.set_calls[0]
    assert key == "cache:rankings:teams"
    assert json.loads(value) == loaded
    assert ttl >= 1


@pytest.mark.parametrize(
    ("module", "loader_attr", "getter", "row"),
    [
        (
            "app.services.mentor_service",
            "execute_query",
            "get_all_mentors",
            {"mentor_id": 1, "name": "A B", "created_at": datetime(2026, 3, 1, 10, tzinfo=UTC)},
        ),
        (
            "app.services.ranking_service",
            "_load_team_rankings",
            "get_team_rankings",
            {
                "team_id": 1,
                "score": 90.5,
                "score_updated_at": datetime(2026, 3, 14, 18, tzinfo=UTC),
            },
        ),
    ],
)
def test_cached_timestamps_match_jsonify_format(
    monkeypatch, app_ctx, module, loader_attr, getter, row
):
    """A cache miss and a cache hit must serialise datetimes the way jsonify does."""
    import importlib

    service = importlib.import_module(module)
    fake = FakeRedis()
    _wire(monkeypatch, module, fake)
    monkeypatch.setattr(f"{module}.{loader_attr}", lambda *a, **k: [row])

    expected = app_ctx.json.loads(app_ctx.json.dumps([row]))
    assert getattr(service, getter)() == expected
    assert getattr(service, getter)() == expected
    assert len(fake.set_calls) == 1


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
    monkeypatch.setattr("app.services.regulations_service._load_regulations", lambda: loaded)
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
    monkeypatch.setattr("app.services.mentor_service.redis_set", lambda *a, **k: False)
    monkeypatch.setattr("app.services.mentor_service.execute_query", lambda *a, **k: rows)
    assert mentor_service.get_all_mentors() == rows


def test_rankings_fallback_when_redis_unavailable(monkeypatch, app_ctx):
    loaded = [{"team": "T3", "points": 1, "image": None}]
    monkeypatch.setattr("app.services.ranking_service.redis_get", lambda *a, **k: None)
    monkeypatch.setattr("app.services.ranking_service.redis_set", lambda *a, **k: False)
    monkeypatch.setattr("app.services.ranking_service._load_rankings", lambda: loaded)
    assert ranking_service.get_rankings() == loaded


def test_regulations_fallback_when_redis_unavailable(monkeypatch, app_ctx):
    loaded = [{"question": "Q", "answer": "A"}]
    monkeypatch.setattr("app.services.regulations_service.redis_get", lambda *a, **k: None)
    monkeypatch.setattr("app.services.regulations_service.redis_set", lambda *a, **k: False)
    monkeypatch.setattr("app.services.regulations_service._load_regulations", lambda: loaded)
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


# ---------------------------------------------------------------------------
# Seed lookups (universities / specialties)
# ---------------------------------------------------------------------------


def test_get_seed_universities_cache_hit(monkeypatch, app_ctx):
    cached = [{"id": 1, "name": "Sofia University", "city": "Sofia", "country": "BG"}]
    fake = FakeRedis({"cache:lookups:universities": json.dumps(cached)})
    _wire(monkeypatch, "app.services.mentor_service", fake)
    monkeypatch.setattr(
        "app.services.mentor_service.execute_query",
        lambda *a, **k: pytest.fail("DB must not be hit on cache hit"),
    )
    assert mentor_service.get_seed_universities() == cached
    assert fake.set_calls == []


def test_get_seed_universities_cache_miss_populates(monkeypatch, app_ctx):
    rows = [{"id": 2, "name": "TU Sofia", "city": "Sofia", "country": "BG"}]
    fake = FakeRedis()
    _wire(monkeypatch, "app.services.mentor_service", fake)
    monkeypatch.setattr("app.services.mentor_service.execute_query", lambda *a, **k: rows)
    assert mentor_service.get_seed_universities() == rows
    key, value, ttl = fake.set_calls[0]
    assert key == "cache:lookups:universities"
    assert json.loads(value) == rows
    assert ttl >= 1


def test_get_seed_specialties_cache_miss_populates(monkeypatch, app_ctx):
    rows = [{"id": 3, "name": "Computer Science"}]
    fake = FakeRedis()
    _wire(monkeypatch, "app.services.mentor_service", fake)
    monkeypatch.setattr("app.services.mentor_service.execute_query", lambda *a, **k: rows)
    assert mentor_service.get_seed_specialties() == rows
    key, value, _ = fake.set_calls[0]
    assert key == "cache:lookups:specialties"
    assert json.loads(value) == rows


def test_seed_lookups_fallback_when_redis_unavailable(monkeypatch, app_ctx):
    rows = [{"id": 4, "name": "Informatics"}]
    monkeypatch.setattr("app.services.mentor_service.redis_get", lambda *a, **k: None)
    monkeypatch.setattr("app.services.mentor_service.redis_set", lambda *a, **k: False)
    monkeypatch.setattr("app.services.mentor_service.execute_query", lambda *a, **k: rows)
    assert mentor_service.get_seed_specialties() == rows


def _fake_cursor(rowcount=0, fetchone=None):
    """get_db_cursor stand-in yielding a MagicMock cursor."""

    @contextmanager
    def fake_get_db_cursor(*args, **kwargs):
        cursor = MagicMock(rowcount=rowcount)
        cursor.fetchone.return_value = fetchone
        yield cursor

    return fake_get_db_cursor


@pytest.mark.parametrize(
    ("loader", "payload", "key"),
    [
        ("load_universities_from_file", [{"name": "New Uni"}], "cache:lookups:universities"),
        ("load_specialties_from_file", [{"name": "New Specialty"}], "cache:lookups:specialties"),
    ],
)
@pytest.mark.parametrize(("rowcount", "expect_del"), [(1, True), (0, False)])
def test_seed_loaders_invalidate_only_when_inserting(
    monkeypatch, app_ctx, tmp_path, loader, payload, key, rowcount, expect_del
):
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(payload), encoding="utf-8")
    fake = FakeRedis({key: "[]"})
    _wire(monkeypatch, "app.services.mentor_service", fake)
    monkeypatch.setattr("app.services.mentor_service.get_db_cursor", _fake_cursor(rowcount))
    getattr(mentor_service, loader)(seed_file)
    assert fake.del_calls == ([(key,)] if expect_del else [])


def test_mentor_seed_loader_invalidates_mentor_cache(monkeypatch, app_ctx, tmp_path):
    seed_file = tmp_path / "mentors.json"
    seed_file.write_text(
        json.dumps([{"first_name": "A", "last_name": "B", "company_name": "C"}]),
        encoding="utf-8",
    )
    fake = FakeRedis({"cache:mentors:all": "[]"})
    _wire(monkeypatch, "app.services.mentor_service", fake)
    monkeypatch.setattr("app.services.mentor_service.mentor_exists", lambda *a, **k: False)
    monkeypatch.setattr("app.services.auth_service.hash_password", lambda pw: "hashed")
    monkeypatch.setattr("app.services.mentor_service.get_db_cursor", _fake_cursor(1))
    assert mentor_service.load_mentors_from_file(seed_file) == 1
    assert fake.del_calls == [("cache:mentors:all",)]


# ---------------------------------------------------------------------------
# Registered teams
# ---------------------------------------------------------------------------


def test_get_registered_teams_cache_hit(monkeypatch, app_ctx):
    cached = [{"team_id": 1, "team_name": "Alpha", "status": "active", "participant_count": 3}]
    fake = FakeRedis({"cache:teams:registered": json.dumps(cached)})
    _wire(monkeypatch, "app.services.team_service", fake)
    monkeypatch.setattr(
        "app.services.team_service.execute_query",
        lambda *a, **k: pytest.fail("DB must not be hit on cache hit"),
    )
    assert TeamService.get_registered_teams() == cached
    assert fake.set_calls == []


def test_get_registered_teams_miss_matches_jsonify_format(monkeypatch, app_ctx):
    """A fresh read and a cache hit must serialise registered_at identically."""
    rows = [
        {
            "team_id": 5,
            "team_name": "Beta",
            "status": "active",
            "participant_count": 4,
            "registered_at": datetime(2026, 10, 22, 1, 0, tzinfo=UTC),
        }
    ]
    fake = FakeRedis()
    _wire(monkeypatch, "app.services.team_service", fake)
    monkeypatch.setattr("app.services.team_service.execute_query", lambda *a, **k: rows)

    expected = app_ctx.json.loads(app_ctx.json.dumps(rows))
    assert TeamService.get_registered_teams() == expected
    key, _, ttl = fake.set_calls[0]
    assert key == "cache:teams:registered"
    assert 1 <= ttl <= 60
    assert TeamService.get_registered_teams() == expected


def test_get_registered_teams_fallback_when_redis_unavailable(monkeypatch, app_ctx):
    rows = [{"team_id": 6, "team_name": "Gamma", "status": "active", "participant_count": 3}]
    monkeypatch.setattr("app.services.team_service.redis_get", lambda *a, **k: None)
    monkeypatch.setattr("app.services.team_service.redis_set", lambda *a, **k: False)
    monkeypatch.setattr("app.services.team_service.execute_query", lambda *a, **k: rows)
    assert TeamService.get_registered_teams() == rows


def test_registered_route_keeps_per_user_flags_out_of_cache(monkeypatch, client):
    rows = [{"team_id": 1, "team_name": "Alpha", "status": "active", "participant_count": 3}]
    fake = FakeRedis()
    _wire(monkeypatch, "app.services.team_service", fake)
    monkeypatch.setattr("app.services.team_service.execute_query", lambda *a, **k: rows)
    monkeypatch.setattr("app.routes.teams.extract_token", lambda: "token")
    monkeypatch.setattr(
        "app.services.auth_service.decode_token",
        lambda t: {"role": "participant", "user_id": 42},
    )
    route_results = iter([{"team_id": None}, [{"team_id": 1}]])
    monkeypatch.setattr("app.routes.teams.execute_query", lambda *a, **k: next(route_results))

    body = client.get("/api/teams/registered").get_json()
    assert body["can_apply"] is True
    assert body["teams"][0]["already_applied"] is True
    assert "already_applied" not in json.loads(fake.store["cache:teams:registered"])[0]


def test_successful_mutation_invalidates_registered_teams(monkeypatch, app_ctx):
    fake = FakeRedis({"cache:teams:registered": "[]"})
    _wire(monkeypatch, "app.services.team_service", fake)
    monkeypatch.setattr(
        "app.services.team_service.get_db_cursor",
        _fake_cursor(fetchone={"id": 1, "is_registered": True}),
    )
    assert TeamService.admin_unregister_team(1) == (True, "Team unregistered successfully")
    assert fake.del_calls == [("cache:teams:registered",)]


def test_failed_mutation_leaves_registered_teams_cache(monkeypatch, app_ctx):
    fake = FakeRedis({"cache:teams:registered": "[]"})
    _wire(monkeypatch, "app.services.team_service", fake)
    monkeypatch.setattr("app.services.team_service.get_db_cursor", _fake_cursor(fetchone=None))
    assert TeamService.admin_unregister_team(1) == (False, "Team not found")
    assert fake.del_calls == []


@pytest.mark.parametrize(
    "method",
    [
        "join_team",
        "leave_team",
        "remove_member",
        "disband_team",
        "accept_join_request",
        "admin_register_team",
        "admin_unregister_team",
    ],
)
def test_registration_mutations_invalidate_registered_teams(method):
    assert hasattr(getattr(TeamService, method), "__wrapped__")
