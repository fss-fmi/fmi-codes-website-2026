"""E2E tests for the preferences_open feature flag (issue #239), against real Postgres.

1. Closed, both ranking POSTs answer 403 and write nothing; the GETs still show the saved ranking
2. A switch from Mission Control locks and unlocks both routes on the next request
3. A close that commits while a save is under way still refuses it, and a due schedule counts
4. Migration 020 adds the flag, closed, to a database from before it, and re-runs as a no-op
"""

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg2
import pytest

from tests.e2e.conftest import admin_token, bearer, mentor_token_for, registered_teams

pytestmark = pytest.mark.e2e

MIGRATION_020 = (
    Path(__file__).parent.parent.parent
    / "backend"
    / "database"
    / "migrations"
    / "020_preferences_open.sql"
)

CLOSED = {"success": False, "error": "Preference submission is closed"}


@pytest.fixture()
def admin(flask_app):
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


@pytest.fixture()
def rankers(flask_app, seeds):
    """A registered team's captain and a mentor, each with a ranking to POST."""
    teams = registered_teams(flask_app, seeds, ["Lockstep", "Keystone", "Latchkey"])
    team_id, captain = teams[0]
    mid0, mid1, mid2 = seeds["mentor_ids"]
    team = (
        f"/api/teams/{team_id}/mentor-preferences",
        captain,
        {
            "preferences": [
                {"mentor_id": mid0, "rank": 1},
                {"mentor_id": mid1, "rank": 2},
                {"mentor_id": mid2, "rank": 3},
            ]
        },
    )
    mentor = (
        "/api/mentors/team-preferences",
        mentor_token_for(flask_app, mid0),
        {"preferences": [{"team_id": t, "rank": r} for r, (t, _) in enumerate(teams, 1)]},
    )
    return {"team": team, "mentor": mentor}


def _post(client, ranker):
    path, token, body = ranker
    return client.post(path, json=body, headers=bearer(token))


def _saved(client, ranker):
    path, token, _ = ranker
    rv = client.get(path, headers=bearer(token))
    assert rv.status_code == 200, rv.get_json()
    return rv.get_json()["preferences"]


def _counts(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT COUNT(*) FROM team_mentor_preferences) AS team,"
            " (SELECT COUNT(*) FROM mentor_team_preferences) AS mentor"
        )
        row = cur.fetchone()
    return row["team"], row["mentor"]


class TestClosed:
    def test_both_posts_403_and_write_nothing(self, client, set_flag, rankers, db_conn):
        set_flag("preferences_open", False)
        for ranker in rankers.values():
            rv = _post(client, ranker)
            assert rv.status_code == 403
            assert rv.get_json() == CLOSED
        assert _counts(db_conn) == (0, 0)

    def test_saved_ranking_stays_readable_and_unchanged(self, client, set_flag, rankers):
        team_path, captain, team_body = rankers["team"]
        assert _post(client, rankers["team"]).status_code == 200
        assert _post(client, rankers["mentor"]).status_code == 200
        before = {name: _saved(client, r) for name, r in rankers.items()}

        set_flag("preferences_open", False)
        mentor_ids = [p["mentor_id"] for p in reversed(team_body["preferences"])]
        reordered = {
            "preferences": [{"mentor_id": m, "rank": r} for r, m in enumerate(mentor_ids, 1)]
        }
        rv = client.post(team_path, json=reordered, headers=bearer(captain))
        assert rv.status_code == 403
        assert {name: _saved(client, r) for name, r in rankers.items()} == before

    def test_config_reports_the_flag(self, client, set_flag):
        assert client.get("/api/config").get_json()["PREFERENCES_OPEN"] is True
        set_flag("preferences_open", False)
        assert client.get("/api/config").get_json()["PREFERENCES_OPEN"] is False


class TestSwitch:
    def test_admin_switch_locks_and_unlocks_both_routes(
        self, admin, client, rankers, notices, db_conn
    ):
        rv = admin.put("/api/admin/flags/preferences_open", json={"enabled": False})
        assert rv.get_json() == {"success": True, "changed": True}
        for ranker in rankers.values():
            assert _post(client, ranker).status_code == 403
        assert _counts(db_conn) == (0, 0)

        rv = admin.put("/api/admin/flags/preferences_open", json={"enabled": True})
        assert rv.get_json()["changed"] is True
        for ranker in rankers.values():
            rv = _post(client, ranker)
            assert rv.status_code == 200, rv.get_json()
        assert _counts(db_conn) == (3, 3)

        switches = [n for n in notices if n.startswith("🚦")]
        assert switches == [
            "🚦 *Preference submissions*: ON → *OFF* (switched by the admin)",
            "🚦 *Preference submissions*: OFF → *ON* (switched by the admin)",
        ]

    def test_flag_can_be_scheduled_and_cancelled(self, admin):
        rv = admin.put(
            "/api/admin/flags/preferences_open/schedule",
            json={"value": False, "at": "2099-01-01T00:00:00Z"},
        )
        assert rv.status_code == 200, rv.get_json()
        rv = admin.delete("/api/admin/flags/preferences_open/schedule")
        assert rv.get_json() == {"success": True, "cancelled": True}


class TestDeadline:
    def test_a_close_committing_during_a_save_refuses_it(self, flask_app, rankers, db_url, db_conn):
        """The cached check passes, but the save waits for the close and then sees it."""
        closer = psycopg2.connect(db_url)
        try:
            with closer.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM feature_flags WHERE name = 'preferences_open' FOR UPDATE"
                )
                cur.execute(
                    "UPDATE feature_flags SET enabled = FALSE WHERE name = 'preferences_open'"
                )
            result = {}

            def save():
                with flask_app.test_client() as c:
                    result["rv"] = _post(c, rankers["team"])

            worker = threading.Thread(target=save)
            worker.start()
            time.sleep(0.5)
            assert worker.is_alive(), "the save did not wait for the close's row lock"
            closer.commit()
            worker.join(10)
        finally:
            closer.close()
        assert result["rv"].status_code == 403
        assert result["rv"].get_json() == CLOSED
        assert _counts(db_conn) == (0, 0)

    def test_a_due_schedule_counts_before_anything_applies_it(self, flask_app, rankers, db_conn):
        from app.services import mentor_selection_service

        _, _, body = rankers["team"]
        team_id = int(rankers["team"][0].split("/")[3])
        with db_conn.cursor() as cur:
            cur.execute(
                "UPDATE feature_flags SET scheduled_value = FALSE, scheduled_at = %s"
                " WHERE name = 'preferences_open'",
                (datetime.now(UTC) - timedelta(seconds=1),),
            )
        with flask_app.app_context():
            result = mentor_selection_service.set_team_mentor_preferences(
                team_id, body["preferences"]
            )
        assert result == (False, mentor_selection_service.PREFERENCES_CLOSED)
        assert _counts(db_conn) == (0, 0)


class TestMigration020:
    def test_adds_the_flag_closed_and_reruns_as_a_no_op(self, db_conn):
        sql = MIGRATION_020.read_text(encoding="utf-8")
        with db_conn.cursor() as cur:
            try:
                # The database as migration 017 left it.
                cur.execute("DELETE FROM feature_flags WHERE name = 'preferences_open'")
                cur.execute("ALTER TABLE feature_flags DROP CONSTRAINT feature_flags_name_check")
                cur.execute(
                    "ALTER TABLE feature_flags ADD CONSTRAINT feature_flags_name_check CHECK"
                    " (name IN ('registration_open', 'rankings_live', 'mentors_stay_tuned'))"
                )
                cur.execute(sql)
                cur.execute(sql)
                cur.execute(
                    "SELECT enabled, scheduled_at FROM feature_flags"
                    " WHERE name = 'preferences_open'"
                )
                assert cur.fetchall() == [{"enabled": False, "scheduled_at": None}]
                cur.execute("SELECT COUNT(*) AS n FROM feature_flags")
                assert cur.fetchone()["n"] == 4
                with pytest.raises(psycopg2.errors.CheckViolation):
                    cur.execute("INSERT INTO feature_flags (name) VALUES ('not_a_flag')")
            finally:
                cur.execute(sql)

    def test_keeps_a_flag_the_admin_already_opened(self, db_conn):
        sql = MIGRATION_020.read_text(encoding="utf-8")
        with db_conn.cursor() as cur:
            cur.execute("UPDATE feature_flags SET enabled = TRUE WHERE name = 'preferences_open'")
            cur.execute(sql)
            cur.execute("SELECT enabled FROM feature_flags WHERE name = 'preferences_open'")
            assert cur.fetchone()["enabled"] is True
