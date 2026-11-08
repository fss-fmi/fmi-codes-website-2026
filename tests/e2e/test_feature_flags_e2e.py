"""E2E tests for the feature flags in the feature_flags table (issue #201).

1. Only the admin can read or change flags through /api/admin/flags*
2. A switch takes effect on the next request: register, rankings, team scores, /api/config
3. /api/config is right with Redis up (cache invalidated) and with Redis down
4. Scheduled changes apply at their time, once, with one notice, even under concurrent reads
"""

import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from tests.e2e.conftest import (
    admin_token,
    bearer,
    mentor_token_for,
    register,
    register_and_token,
)

pytestmark = pytest.mark.e2e


@pytest.fixture()
def admin(flask_app):
    # Not a `with` client: two preserved request contexts (this and `client`) pop out of order.
    c = flask_app.test_client()
    c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {admin_token(flask_app)}"
    return c


@pytest.fixture()
def notices(monkeypatch):
    posted = []
    lock = threading.Lock()

    def record(text):
        with lock:
            posted.append(text)

    monkeypatch.setattr("app.services.event_notifier.notify", record)
    return posted


def _flags(admin):
    rv = admin.get("/api/admin/flags")
    assert rv.status_code == 200, rv.get_json()
    return {f["name"]: f for f in rv.get_json()["flags"]}


def _schedule_in_db(db_conn, name, value, at):
    """Write a schedule directly, bypassing the API's must-be-future check."""
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE feature_flags SET scheduled_value = %s, scheduled_at = %s WHERE name = %s",
            (value, at, name),
        )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Access
# ═══════════════════════════════════════════════════════════════════════════


class TestAccess:
    PATHS = [
        ("get", "/api/admin/flags", None),
        ("put", "/api/admin/flags/registration_open", {"enabled": False}),
        (
            "put",
            "/api/admin/flags/registration_open/schedule",
            {"value": False, "at": "2099-01-01T00:00:00Z"},
        ),
        ("delete", "/api/admin/flags/registration_open/schedule", None),
    ]

    @pytest.mark.parametrize(("method", "path", "body"), PATHS)
    def test_anonymous_gets_401(self, client, method, path, body):
        assert getattr(client, method)(path, json=body).status_code == 401

    @pytest.mark.parametrize(("method", "path", "body"), PATHS)
    def test_participant_and_mentor_get_403(self, flask_app, client, seeds, method, path, body):
        participant = register_and_token(client, 1, seeds)
        mentor = mentor_token_for(flask_app, seeds["mentor_ids"][0])
        for token in (participant, mentor):
            rv = getattr(client, method)(path, json=body, headers=bearer(token))
            assert rv.status_code == 403

    def test_nothing_changed_by_rejected_callers(self, admin):
        assert _flags(admin)["registration_open"]["enabled"] is True
        assert _flags(admin)["registration_open"]["scheduled_at"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. Switching now
# ═══════════════════════════════════════════════════════════════════════════


class TestSwitch:
    def test_admin_lists_all_three_flags(self, admin):
        flags = _flags(admin)
        assert set(flags) == {"registration_open", "rankings_live", "mentors_stay_tuned"}
        assert flags["registration_open"]["enabled"] is True
        assert flags["rankings_live"]["enabled"] is False
        assert flags["mentors_stay_tuned"]["scheduled_value"] is None

    def test_closing_and_reopening_registration(self, admin, client, seeds, notices):
        rv = admin.put("/api/admin/flags/registration_open", json={"enabled": False})
        assert rv.get_json() == {"success": True, "changed": True}
        assert register(client, 1, seeds).status_code == 403

        rv = admin.put("/api/admin/flags/registration_open", json={"enabled": True})
        assert rv.get_json()["changed"] is True
        assert register(client, 1, seeds).status_code == 201

        assert len(notices) == 2
        assert "Participant registration" in notices[0] and "ON → *OFF*" in notices[0]

    def test_switch_is_idempotent_and_quiet(self, admin, notices):
        before = _flags(admin)["registration_open"]["updated_at"]
        rv = admin.put("/api/admin/flags/registration_open", json={"enabled": True})
        assert rv.get_json() == {"success": True, "changed": False}
        assert _flags(admin)["registration_open"]["updated_at"] == before
        assert notices == []

    def test_rankings_and_scores_follow_the_switch(self, flask_app, admin, client, seeds):
        token = register_and_token(client, 1, seeds)
        team_id = client.post(
            "/api/teams", json={"team_name": "Flag Team"}, headers=bearer(token)
        ).get_json()["team"]["id"]
        assert admin.put(f"/api/admin/teams/{team_id}/score", json={"score": 50}).status_code == 200

        assert client.get("/api/teams/rankings").status_code == 403
        team = client.get(f"/api/teams/{team_id}", headers=bearer(token)).get_json()["team"]
        assert "score" not in team

        admin.put("/api/admin/flags/rankings_live", json={"enabled": True})
        assert client.get("/api/teams/rankings").status_code == 200
        team = client.get(f"/api/teams/{team_id}", headers=bearer(token)).get_json()["team"]
        assert team["score"] == 50

    def test_config_reflects_each_switch(self, admin, client):
        assert client.get("/api/config").get_json()["MENTORS_STAY_TUNED"] is False
        admin.put("/api/admin/flags/mentors_stay_tuned", json={"enabled": True})
        assert client.get("/api/config").get_json()["MENTORS_STAY_TUNED"] is True
        admin.put("/api/admin/flags/mentors_stay_tuned", json={"enabled": False})
        assert client.get("/api/config").get_json()["MENTORS_STAY_TUNED"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. Redis up and down
# ═══════════════════════════════════════════════════════════════════════════


class TestRedis:
    def test_switch_invalidates_a_cached_value(self, admin, client):
        from app.services.redis_client import get_redis_client, redis_get

        if get_redis_client() is None:
            pytest.skip("Redis not configured (set REDIS_URL)")
        assert client.get("/api/config").get_json()["RANKINGS_LIVE"] is False
        assert redis_get("cache:feature_flags") is not None

        admin.put("/api/admin/flags/rankings_live", json={"enabled": True})
        assert client.get("/api/config").get_json()["RANKINGS_LIVE"] is True

    def test_flags_work_with_redis_down(self, admin, client, seeds, monkeypatch):
        monkeypatch.setattr("app.services.redis_client.get_redis_client", lambda: None)
        assert client.get("/api/config").get_json()["REGISTRATION_OPEN"] is True
        admin.put("/api/admin/flags/registration_open", json={"enabled": False})
        assert client.get("/api/config").get_json()["REGISTRATION_OPEN"] is False
        assert register(client, 1, seeds).status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 4. Schedules
# ═══════════════════════════════════════════════════════════════════════════


class TestSchedule:
    def test_scheduled_change_applies_at_its_time(self, admin, client, notices):
        at = datetime.now(UTC) + timedelta(seconds=2)
        local = at.astimezone(datetime.now().astimezone().tzinfo).isoformat()
        rv = admin.put("/api/admin/flags/rankings_live/schedule", json={"value": True, "at": local})
        assert rv.status_code == 200, rv.get_json()

        pending = _flags(admin)["rankings_live"]
        assert pending["scheduled_value"] is True
        assert datetime.fromisoformat(pending["scheduled_at"]) == at
        assert client.get("/api/config").get_json()["RANKINGS_LIVE"] is False

        time.sleep(max(0.0, (at - datetime.now(UTC)).total_seconds()) + 0.5)
        assert client.get("/api/config").get_json()["RANKINGS_LIVE"] is True
        assert client.get("/api/config").get_json()["RANKINGS_LIVE"] is True

        done = _flags(admin)["rankings_live"]
        assert done["scheduled_at"] is None and done["scheduled_value"] is None
        assert len(notices) == 1
        assert "Live rankings" in notices[0] and "scheduled for <!date^" in notices[0]

    def test_concurrent_reads_apply_a_due_schedule_once(
        self, flask_app, db_conn, notices, monkeypatch
    ):
        from app.services import feature_flag_service

        # Every reader goes to the DB, as several workers with a cold cache would.
        monkeypatch.setattr("app.services.redis_client.get_redis_client", lambda: None)
        _schedule_in_db(
            db_conn, "mentors_stay_tuned", True, datetime.now(UTC) - timedelta(seconds=1)
        )

        readers = 4  # the e2e pool holds 5 connections
        barrier = threading.Barrier(readers)
        results, errors = [], []

        def read():
            try:
                with flask_app.app_context():
                    barrier.wait()
                    results.append(feature_flag_service.get_flags()["mentors_stay_tuned"])
            except Exception as e:  # surfaced below; a thread can't fail the test itself
                errors.append(e)

        threads = [threading.Thread(target=read) for _ in range(readers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        assert results == [True] * readers
        assert len(notices) == 1

    def test_due_schedule_matching_a_manual_switch_clears_quietly(
        self, admin, client, db_conn, notices
    ):
        admin.put("/api/admin/flags/rankings_live", json={"enabled": True})
        notices.clear()
        _schedule_in_db(db_conn, "rankings_live", True, datetime.now(UTC) - timedelta(seconds=1))

        assert client.get("/api/config").get_json()["RANKINGS_LIVE"] is True
        assert _flags(admin)["rankings_live"]["scheduled_at"] is None
        assert notices == []

    def test_past_time_is_rejected(self, admin):
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        rv = admin.put(
            "/api/admin/flags/registration_open/schedule", json={"value": False, "at": past}
        )
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "Scheduled time must be in the future"

    def test_current_value_is_rejected(self, admin):
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        rv = admin.put(
            "/api/admin/flags/registration_open/schedule", json={"value": True, "at": future}
        )
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "The flag is already on"

    def test_cancel(self, admin, client):
        future = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
        admin.put(
            "/api/admin/flags/registration_open/schedule", json={"value": False, "at": future}
        )
        rv = admin.delete("/api/admin/flags/registration_open/schedule")
        assert rv.get_json() == {"success": True, "cancelled": True}
        rv = admin.delete("/api/admin/flags/registration_open/schedule")
        assert rv.get_json() == {"success": True, "cancelled": False}

        time.sleep(1.5)
        assert client.get("/api/config").get_json()["REGISTRATION_OPEN"] is True

    def test_new_schedule_replaces_the_pending_one(self, admin):
        first = datetime.now(UTC) + timedelta(hours=1)
        second = first + timedelta(hours=1)
        for at in (first, second):
            rv = admin.put(
                "/api/admin/flags/registration_open/schedule",
                json={"value": False, "at": at.isoformat()},
            )
            assert rv.status_code == 200
        assert datetime.fromisoformat(_flags(admin)["registration_open"]["scheduled_at"]) == second
