"""E2E tests for the matching-phase event feed (issue #205), against real Postgres.

Each successful ranking, matching run and confirmation posts once after its
commit; refused or failed actions post nothing; no notice names a choice.
"""

import threading

import pytest

from tests.e2e.conftest import (
    _MENTOR_SEEDS,
    admin_token,
    bearer,
    mentor_token_for,
    register_and_token,
    registered_teams,
)

pytestmark = pytest.mark.e2e

MENTOR_NAMES = [f"{m['first']} {m['last']}" for m in _MENTOR_SEEDS]


@pytest.fixture()
def notices(monkeypatch):
    posted = []
    lock = threading.Lock()

    def record(text):
        with lock:
            posted.append(text)

    monkeypatch.setattr("app.services.event_notifier.notify", record)
    return posted


def _mentor_ranking(seeds):
    mid0, mid1, mid2 = seeds["mentor_ids"]
    return {
        "preferences": [
            {"mentor_id": mid2, "rank": 1},
            {"mentor_id": mid0, "rank": 2},
            {"mentor_id": mid1, "rank": 3},
        ]
    }


def _team_ranking(team_ids):
    return {"preferences": [{"team_id": t, "rank": r} for r, t in enumerate(team_ids, 1)]}


def _status(flask_app):
    with flask_app.test_client() as adm:
        return adm.get(
            "/api/admin/preference-status", headers=bearer(admin_token(flask_app))
        ).get_json()


class TestTeamRanking:
    def test_submit_then_update(self, flask_app, seeds, notices):
        [(team_id, token)] = registered_teams(flask_app, seeds, ["Night Owls"])
        with flask_app.test_client() as c:
            rv = c.post(
                f"/api/teams/{team_id}/mentor-preferences",
                json=_mentor_ranking(seeds),
                headers=bearer(token),
            )
            assert rv.status_code == 200, rv.get_json()
            status = _status(flask_app)
            assert notices == [
                "🗳️ Team *Night Owls* submitted its mentor ranking."
                f" Teams: {status['teams_submitted']} of {status['teams_total']} submitted."
            ]
            assert (status["teams_submitted"], status["teams_total"]) == (1, 1)

            rv = c.post(
                f"/api/teams/{team_id}/mentor-preferences",
                json=_mentor_ranking(seeds),
                headers=bearer(token),
            )
            assert rv.status_code == 200
        assert notices[1] == "🔁 Team *Night Owls* updated its mentor ranking."
        assert len(notices) == 2
        for text in notices:
            assert not any(name in text for name in MENTOR_NAMES)

    def test_pending_team_cannot_rank(self, flask_app, seeds, client, notices):
        token = register_and_token(client, 1, seeds)
        team_id = client.post(
            "/api/teams", json={"team_name": "Solo"}, headers=bearer(token)
        ).get_json()["team"]["id"]
        rv = client.post(
            f"/api/teams/{team_id}/mentor-preferences",
            json=_mentor_ranking(seeds),
            headers=bearer(token),
        )
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "Only registered teams can rank mentors"
        assert notices == []
        assert _status(flask_app)["teams_submitted"] == 0

    def test_unregistered_active_team_cannot_rank(self, flask_app, seeds, notices):
        [(team_id, token)] = registered_teams(flask_app, seeds, ["Dropped"])
        with flask_app.test_client() as adm:
            rv = adm.post(
                f"/api/admin/teams/{team_id}/unregister", headers=bearer(admin_token(flask_app))
            )
            assert rv.status_code == 200, rv.get_json()
        with flask_app.test_client() as c:
            rv = c.post(
                f"/api/teams/{team_id}/mentor-preferences",
                json=_mentor_ranking(seeds),
                headers=bearer(token),
            )
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "Only registered teams can rank mentors"
        assert notices == []

    def test_slack_failure_does_not_change_the_response(self, flask_app, seeds, monkeypatch):
        def broken(text):
            raise RuntimeError("pool shut down")

        monkeypatch.setattr("app.services.event_notifier.notify", broken)
        [(team_id, token)] = registered_teams(flask_app, seeds, ["Resilient"])
        with flask_app.test_client() as c:
            rv = c.post(
                f"/api/teams/{team_id}/mentor-preferences",
                json=_mentor_ranking(seeds),
                headers=bearer(token),
            )
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True
        assert _status(flask_app)["teams_submitted"] == 1


class TestMentorRanking:
    def test_submit_then_update(self, flask_app, seeds, notices):
        team_names = ["Team Red", "Team Green", "Team Blue"]
        team_ids = [t for t, _ in registered_teams(flask_app, seeds, team_names)]
        notices.clear()
        mentor_id = seeds["mentor_ids"][0]
        token = mentor_token_for(flask_app, mentor_id)
        with flask_app.test_client() as c:
            for _ in range(2):
                rv = c.post(
                    "/api/mentors/team-preferences",
                    json=_team_ranking(team_ids),
                    headers=bearer(token),
                )
                assert rv.status_code == 200, rv.get_json()
        status = _status(flask_app)
        assert notices == [
            f"🗳️ Mentor *{MENTOR_NAMES[0]}* submitted their team ranking."
            f" Mentors: 1 of {status['mentors_total']} submitted.",
            f"🔁 Mentor *{MENTOR_NAMES[0]}* updated their team ranking.",
        ]
        for text in notices:
            assert not any(name in text for name in team_names)

    def test_mentor_deactivated_after_login_cannot_rank(self, flask_app, seeds, db_conn, notices):
        team_ids = [t for t, _ in registered_teams(flask_app, seeds, ["T1", "T2", "T3"])]
        notices.clear()
        mentor_id = seeds["mentor_ids"][0]
        token = mentor_token_for(flask_app, mentor_id)
        with db_conn.cursor() as cur:
            cur.execute("UPDATE mentors SET status = 'inactive' WHERE id = %s", (mentor_id,))
        try:
            with flask_app.test_client() as c:
                rv = c.post(
                    "/api/mentors/team-preferences",
                    json=_team_ranking(team_ids),
                    headers=bearer(token),
                )
        finally:
            with db_conn.cursor() as cur:
                cur.execute("UPDATE mentors SET status = 'active' WHERE id = %s", (mentor_id,))
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "Mentor not found or inactive"
        assert notices == []
        assert _status(flask_app)["mentors_submitted"] == 0


class TestMatching:
    def test_run_confirm_and_rerun(self, flask_app, seeds, notices):
        team_names = ["Matched One", "Matched Two"]
        registered_teams(flask_app, seeds, team_names)
        notices.clear()
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            rv = adm.post("/api/admin/run-matching", headers=bearer(adm_tok))
            assert rv.status_code == 200, rv.get_json()
            run = rv.get_json()
            assert len(notices) == 1
            first = notices[0]
            assert first.startswith(
                "🧩 Mentor matching ran (Gale-Shapley, then greedy fill):"
                f" *{run['assignment_count']}* assignments for *2* teams."
            )
            for warning in run["warnings"]:
                assert f"• {warning}" in first
            assert "confirmation was cleared" not in first

            assert (
                adm.post("/api/admin/confirm-matching", headers=bearer(adm_tok)).status_code == 200
            )
            assert (
                adm.post("/api/admin/confirm-matching", headers=bearer(adm_tok)).status_code == 200
            )
            assert notices[1:] == [
                "✅ Matching confirmed as final. Teams and mentors now see their assignments."
            ]

            assert adm.post("/api/admin/run-matching", headers=bearer(adm_tok)).status_code == 200
            assert notices[2].endswith("\nThe earlier confirmation was cleared.")
            assert len(notices) == 3

        for text in notices:
            assert not any(name in text for name in team_names + MENTOR_NAMES)

    def test_run_with_nothing_to_match_posts_nothing(self, flask_app, notices):
        with flask_app.test_client() as adm:
            rv = adm.post("/api/admin/run-matching", headers=bearer(admin_token(flask_app)))
        assert rv.status_code == 400
        assert notices == []

    def test_failed_save_posts_nothing(self, flask_app, seeds, notices, monkeypatch):
        registered_teams(flask_app, seeds, ["Unlucky"])
        notices.clear()

        def broken(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr("app.services.matching_service.get_db_cursor", broken)
        with flask_app.test_client() as adm:
            rv = adm.post("/api/admin/run-matching", headers=bearer(admin_token(flask_app)))
        assert rv.status_code == 500
        assert notices == []


class TestPicksThatStillCount:
    def test_a_mentor_whose_picks_all_lost_their_slot_is_not_submitted(self, flask_app, seeds):
        team_ids = [
            t for t, _ in registered_teams(flask_app, seeds, ["Gone 1", "Gone 2", "Gone 3"])
        ]
        mentor_id = seeds["mentor_ids"][0]
        with flask_app.test_client() as c:
            rv = c.post(
                "/api/mentors/team-preferences",
                json=_team_ranking(team_ids),
                headers=bearer(mentor_token_for(flask_app, mentor_id)),
            )
            assert rv.status_code == 200, rv.get_json()

        def mentor_row():
            return next(m for m in _status(flask_app)["mentors"] if m["id"] == mentor_id)

        assert mentor_row()["submitted"] is True
        assert mentor_row()["picks_counting"] == 3

        with flask_app.test_client() as adm:
            for team_id in team_ids[:2]:
                rv = adm.post(
                    f"/api/admin/teams/{team_id}/unregister", headers=bearer(admin_token(flask_app))
                )
                assert rv.status_code == 200, rv.get_json()
        assert (mentor_row()["submitted"], mentor_row()["picks_counting"]) == (True, 1)

        with flask_app.test_client() as adm:
            rv = adm.post(
                f"/api/admin/teams/{team_ids[2]}/unregister", headers=bearer(admin_token(flask_app))
            )
            assert rv.status_code == 200, rv.get_json()
        row = mentor_row()
        assert (row["submitted"], row["picks_counting"], row["picks_saved"]) == (False, 0, 3)
        assert _status(flask_app)["mentors_submitted"] == 0
