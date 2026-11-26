"""Confirmed matching freezes participant team changes and preferences, against real Postgres.

Once the admin confirms, every participant change to a team's members and both preference
saves are refused with 403; declining or withdrawing an application stays open, since it
changes no team. A new matching run clears the confirmation and lifts the freeze.

Every call goes through a fresh test client: a client's cookie wins over the Bearer header,
so sharing one would run every call as whoever registered last. Matching is confirmed only
through the admin endpoint, never a raw UPDATE: CI runs Redis, and the endpoint is what
retires the cached /api/config answer.
"""

import pytest

from tests.e2e.conftest import (
    admin_token,
    bearer,
    mentor_token_for,
    register_and_token,
    register_extra_and_token,
    registered_teams,
)

pytestmark = pytest.mark.e2e

TEAMS_LOCKED = "Teams are locked while the event runs. For any changes, contact the organizers."
PREFERENCES_CONFIRMED = "Matching is confirmed, so preferences can no longer change."


def _call(flask_app, method, path, token=None, json=None):
    with flask_app.test_client() as c:
        headers = bearer(token) if token else {}
        return c.open(path, method=method, json=json, headers=headers)


def _confirm(flask_app):
    rv = _call(flask_app, "POST", "/api/admin/confirm-matching", admin_token(flask_app))
    assert rv.status_code == 200, rv.get_json()


def _participant(flask_app, seeds, n):
    with flask_app.test_client() as c:
        return register_and_token(c, n, seeds)


def _team_of_three(flask_app, seeds, n, name):
    """A registered team: (team_id, join code, captain token, member token, member id)."""
    captain = _participant(flask_app, seeds, n)
    rv = _call(flask_app, "POST", "/api/teams", captain, {"team_name": name})
    assert rv.status_code == 201, rv.get_json()
    team_id, code = rv.get_json()["team"]["id"], rv.get_json()["team"]["join_code"]
    members = []
    for _ in range(2):
        with flask_app.test_client() as c:
            token = register_extra_and_token(c, seeds)
        rv = _call(flask_app, "POST", "/api/teams/join", token, {"join_code": code})
        assert rv.status_code == 200, rv.get_json()
        members.append(token)
    team = _call(flask_app, "GET", f"/api/teams/{team_id}", captain).get_json()["team"]
    assert team["is_registered"], team
    member_id = next(m["id"] for m in team["members"] if not m["is_captain"])
    return team_id, code, captain, members[0], member_id


def _assert_locked(rv):
    assert rv.status_code == 403, rv.get_json()
    assert rv.get_json() == {"success": False, "error": TEAMS_LOCKED}


def _mentor_ranking(seeds):
    return {
        "preferences": [{"mentor_id": m, "rank": r} for r, m in enumerate(seeds["mentor_ids"], 1)]
    }


class TestTeamChangesFreeze:
    def test_every_participant_team_change_is_refused_once_confirmed(self, flask_app, seeds):
        team_id, code, captain, member, member_id = _team_of_three(flask_app, seeds, 1, "Frozen")
        applicant = _participant(flask_app, seeds, 2)
        rv = _call(flask_app, "POST", f"/api/teams/{team_id}/apply", applicant)
        assert rv.status_code == 201, rv.get_json()
        [request] = _call(flask_app, "GET", f"/api/teams/{team_id}/requests", captain).get_json()[
            "requests"
        ]
        outsider = _participant(flask_app, seeds, 3)

        _confirm(flask_app)

        _assert_locked(_call(flask_app, "POST", "/api/teams", outsider, {"team_name": "Late"}))
        _assert_locked(_call(flask_app, "POST", "/api/teams/join", outsider, {"join_code": code}))
        _assert_locked(_call(flask_app, "POST", f"/api/teams/{team_id}/apply", outsider))
        _assert_locked(_call(flask_app, "POST", f"/api/teams/{team_id}/leave", member))
        _assert_locked(
            _call(flask_app, "DELETE", f"/api/teams/{team_id}/members/{member_id}", captain)
        )
        _assert_locked(_call(flask_app, "DELETE", f"/api/teams/{team_id}", captain))
        _assert_locked(
            _call(flask_app, "POST", f"/api/teams/requests/{request['request_id']}/accept", captain)
        )

        team = _call(flask_app, "GET", f"/api/teams/{team_id}", captain).get_json()["team"]
        assert len(team["members"]) == 3
        assert team["is_registered"] is True

    def test_decline_and_withdraw_stay_open_while_accept_is_refused(self, flask_app, seeds):
        team_id, _, captain, _, _ = _team_of_three(flask_app, seeds, 1, "Still Deciding")
        declined, withdrawn = (_participant(flask_app, seeds, n) for n in (2, 3))
        for token in (declined, withdrawn):
            rv = _call(flask_app, "POST", f"/api/teams/{team_id}/apply", token)
            assert rv.status_code == 201, rv.get_json()
        requests = _call(flask_app, "GET", f"/api/teams/{team_id}/requests", captain).get_json()[
            "requests"
        ]
        by_name = {r["first_name"]: r["request_id"] for r in requests}

        _confirm(flask_app)

        # Accept first, so the pair below can't pass on a build that freezes nothing.
        _assert_locked(
            _call(flask_app, "POST", f"/api/teams/requests/{by_name['First2']}/accept", captain)
        )
        rv = _call(flask_app, "POST", f"/api/teams/requests/{by_name['First2']}/decline", captain)
        assert rv.status_code == 200, rv.get_json()
        rv = _call(flask_app, "POST", f"/api/teams/requests/{by_name['First3']}/cancel", withdrawn)
        assert rv.status_code == 200, rv.get_json()

    def test_registered_list_offers_no_apply_once_confirmed(self, flask_app, seeds):
        _team_of_three(flask_app, seeds, 1, "Listed")
        teamless = _participant(flask_app, seeds, 2)
        assert _call(flask_app, "GET", "/api/teams/registered", teamless).get_json()["can_apply"]

        _confirm(flask_app)

        body = _call(flask_app, "GET", "/api/teams/registered", teamless).get_json()
        assert body["can_apply"] is False
        assert len(body["teams"]) == 1

    def test_config_says_when_matching_is_confirmed(self, flask_app):
        assert _call(flask_app, "GET", "/api/config").get_json()["MATCHING_CONFIRMED"] is False
        _confirm(flask_app)
        assert _call(flask_app, "GET", "/api/config").get_json()["MATCHING_CONFIRMED"] is True

    def test_a_new_run_lifts_the_freeze(self, flask_app, seeds):
        registered_teams(flask_app, seeds, ["Matched"])
        teamless = _participant(flask_app, seeds, 20)
        _confirm(flask_app)
        _assert_locked(_call(flask_app, "POST", "/api/teams", teamless, {"team_name": "Late"}))

        rv = _call(flask_app, "POST", "/api/admin/run-matching", admin_token(flask_app))
        assert rv.status_code == 200, rv.get_json()

        assert _call(flask_app, "GET", "/api/config").get_json()["MATCHING_CONFIRMED"] is False
        rv = _call(flask_app, "POST", "/api/teams", teamless, {"team_name": "Late"})
        assert rv.status_code == 201, rv.get_json()


class TestPreferencesFreeze:
    @pytest.mark.parametrize("open_", [True, False])
    def test_both_rankings_are_refused_with_the_confirmed_text(
        self, flask_app, seeds, set_flag, open_
    ):
        teams = registered_teams(flask_app, seeds, ["Rank A", "Rank B", "Rank C"])
        team_id, captain = teams[0]
        _confirm(flask_app)
        # The admin closes submissions before the final run; the text must still say why.
        set_flag("preferences_open", open_)

        rv = _call(
            flask_app,
            "POST",
            f"/api/teams/{team_id}/mentor-preferences",
            captain,
            _mentor_ranking(seeds),
        )
        assert rv.status_code == 403, rv.get_json()
        assert rv.get_json()["error"] == PREFERENCES_CONFIRMED

        ranking = {"preferences": [{"team_id": t, "rank": r} for r, (t, _) in enumerate(teams, 1)]}
        mentor = mentor_token_for(flask_app, seeds["mentor_ids"][0])
        rv = _call(flask_app, "POST", "/api/mentors/team-preferences", mentor, ranking)
        assert rv.status_code == 403, rv.get_json()
        assert rv.get_json()["error"] == PREFERENCES_CONFIRMED
