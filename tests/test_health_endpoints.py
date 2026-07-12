"""Tests for the k8s health/readiness probe endpoints.

Both endpoints live on the `/api` blueprint, so their paths are `/api/health`
(liveness) and `/api/health/ready` (readiness). Postgres and Redis are patched
AS IMPORTED INTO the route module (`api_routes` did
`from app.database import execute_query` and
`from app.services.redis_client import get_redis_client`, so the bound names
live on the route module, not on their origin modules).

None of these tests require a live Postgres or Redis.
"""

from unittest.mock import MagicMock, patch


def test_health_returns_ok_without_dependencies(client):
    """Liveness must be 200 and touch no DB/Redis."""
    with (
        patch("app.routes.api_routes.execute_query") as db,
        patch("app.routes.api_routes.get_redis_client") as redis,
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
        patch("app.routes.api_routes.get_redis_client", return_value=fake_redis),
    ):
        resp = client.get("/api/health/ready")

    assert resp.status_code == 200
    assert resp.get_json() == {"db": "ok", "redis": "ok"}


def test_ready_reports_redis_disabled_when_client_none(client):
    """DB reachable + Redis disabled (client None) → 200, redis 'disabled'."""
    with (
        patch("app.routes.api_routes.execute_query", return_value={"ok": 1}),
        patch("app.routes.api_routes.get_redis_client", return_value=None),
    ):
        resp = client.get("/api/health/ready")

    assert resp.status_code == 200
    assert resp.get_json() == {"db": "ok", "redis": "disabled"}


def test_ready_reports_redis_down_but_stays_200(client):
    """Redis ping raising must NOT flip readiness to 503 (Redis is fail-open)."""
    fake_redis = MagicMock()
    fake_redis.ping.side_effect = ConnectionError("redis unreachable")
    with (
        patch("app.routes.api_routes.execute_query", return_value={"ok": 1}),
        patch("app.routes.api_routes.get_redis_client", return_value=fake_redis),
    ):
        resp = client.get("/api/health/ready")

    assert resp.status_code == 200
    assert resp.get_json() == {"db": "ok", "redis": "down"}


def test_ready_returns_503_when_db_down(client):
    """DB check raising → 503 (pod pulled from Service)."""
    with (
        patch("app.routes.api_routes.execute_query", side_effect=Exception("db unreachable")),
        patch("app.routes.api_routes.get_redis_client") as redis,
    ):
        resp = client.get("/api/health/ready")

    assert resp.status_code == 503
    assert resp.get_json() == {"db": "down", "redis": "unknown"}
    redis.assert_not_called()


def test_ready_returns_503_when_db_result_unexpected(client):
    """DB reachable but the query returns nothing/garbage → 503, not a false ok."""
    with (
        patch("app.routes.api_routes.execute_query", return_value=None),
        patch("app.routes.api_routes.get_redis_client") as redis,
    ):
        resp = client.get("/api/health/ready")

    assert resp.status_code == 503
    assert resp.get_json() == {"db": "down", "redis": "unknown"}
    redis.assert_not_called()
