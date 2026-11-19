"""Tests for the k8s health/readiness probe endpoints.

Both endpoints live on the `/api` blueprint, so their paths are `/api/health`
(liveness) and `/api/health/ready` (readiness). Postgres is patched AS IMPORTED
INTO the route module (`api_routes` did `from app.database import execute_query`).
Redis is patched at `redis_client.get_redis_client`, behind the breaker the
readiness ping goes through.

None of these tests require a live Postgres or Redis.
"""

from unittest.mock import MagicMock, patch

from redis.exceptions import ConnectionError as RedisConnectionError

REDIS = "app.services.redis_client.get_redis_client"


def test_health_returns_ok_without_dependencies(client):
    """Liveness must be 200 and touch no DB/Redis."""
    with (
        patch("app.routes.api_routes.execute_query") as db,
        patch(REDIS) as redis,
    ):
        resp = client.get("/api/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}
    db.assert_not_called()
    redis.assert_not_called()


def test_ready_returns_200_when_db_ok_and_redis_ok(client):
    """DB reachable + Redis ping succeeds → 200 with both ok."""
    fake_redis = MagicMock()
    fake_redis.ping.return_value = True
    with (
        patch("app.routes.api_routes.execute_query", return_value={"ok": 1}),
        patch(REDIS, return_value=fake_redis),
    ):
        resp = client.get("/api/health/ready")

    assert resp.status_code == 200
    assert resp.get_json() == {"db": "ok", "redis": "ok"}


def test_ready_reports_redis_disabled_without_redis_config(client, monkeypatch):
    """DB reachable + no Redis configured → 200, redis 'disabled'."""
    for name in ("REDIS_URL", "REDIS_SENTINELS", "REDIS_MASTER_NAME"):
        monkeypatch.delenv(name, raising=False)
    with patch("app.routes.api_routes.execute_query", return_value={"ok": 1}):
        resp = client.get("/api/health/ready")

    assert resp.status_code == 200
    assert resp.get_json() == {"db": "ok", "redis": "disabled"}


def test_ready_reports_redis_down_but_stays_200(client):
    """Redis ping raising must NOT flip readiness to 503 (Redis is fail-open), and while
    the breaker is open the next probe reports down without pinging again."""
    fake_redis = MagicMock()
    fake_redis.ping.side_effect = RedisConnectionError("redis unreachable")
    with (
        patch("app.routes.api_routes.execute_query", return_value={"ok": 1}),
        patch(REDIS, return_value=fake_redis),
    ):
        first = client.get("/api/health/ready")
        second = client.get("/api/health/ready")

    assert first.status_code == second.status_code == 200
    assert first.get_json() == second.get_json() == {"db": "ok", "redis": "down"}
    fake_redis.ping.assert_called_once()


def test_ready_returns_503_when_db_down(client):
    """DB check raising → 503 (pod pulled from Service)."""
    with (
        patch("app.routes.api_routes.execute_query", side_effect=Exception("db unreachable")),
        patch(REDIS) as redis,
    ):
        resp = client.get("/api/health/ready")

    assert resp.status_code == 503
    assert resp.get_json() == {"db": "down", "redis": "unknown"}
    redis.assert_not_called()


def test_ready_returns_503_when_db_result_unexpected(client):
    """DB reachable but the query returns nothing/garbage → 503, not a false ok."""
    with (
        patch("app.routes.api_routes.execute_query", return_value=None),
        patch(REDIS) as redis,
    ):
        resp = client.get("/api/health/ready")

    assert resp.status_code == 503
    assert resp.get_json() == {"db": "down", "redis": "unknown"}
    redis.assert_not_called()
