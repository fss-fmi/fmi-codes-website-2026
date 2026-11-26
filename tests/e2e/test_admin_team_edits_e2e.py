"""The admin's hand edits from Mission Control's TEAMS tab, against real Postgres.

Mentors: replace one registered team's assignments, with warnings past the limits. Members:
add a teamless participant by email, remove one (handing over captaincy when needed). Before
matching is confirmed the usual slot rules apply; after it, nothing moves a slot. Every
unregister releases the team's mentors.

Every call goes through a fresh test client: a client's cookie wins over the Bearer header.
"""

import threading

import pytest
from app.services import team_service

from tests.e2e.conftest import (
    admin_token,
    bearer,
    mentor_token_for,
    register_and_token,
    register_extra_and_token,
)

pytestmark = pytest.mark.e2e


@pytest.fixture()
def notices(monkeypatch):
    posted = []
    lock = threading.Lock()

    def record(text):
        with lock:
            posted.append(text)

    monkeypatch.setattr("app.services.event_notifier.notify", record)
    return posted


def _call(flask_app, method, path, token=None, json=None):
    with flask_app.test_client() as c:
        headers = bearer(token) if token else {}
        return c.open(path, method=method, json=json, headers=headers)


def _admin(flask_app, method, path, json=None):
    return _call(flask_app, method, path, admin_token(flask_app), json)


def _confirm(flask_app):
    assert _admin(flask_app, "POST", "/api/admin/confirm-matching").status_code == 200


def _participant(flask_app, seeds, n, **overrides):
    with flask_app.test_client() as c:
        return register_and_token(c, n, seeds, **overrides)


def _team(flask_app, seeds, n, name, size):
    """A team of *size* led by participant *n*: (team_id, captain token)."""
    captain = _participant(flask_app, seeds, n)
    rv = _call(flask_app, "POST", "/api/teams", captain, {"team_name": name})
    assert rv.status_code == 201, rv.get_json()
    team_id, code = rv.get_json()["team"]["id"], rv.get_json()["team"]["join_code"]
    for _ in range(size - 1):
        with flask_app.test_client() as c:
            token = register_extra_and_token(c, seeds)
        rv = _call(flask_app, "POST", "/api/teams/join", token, {"join_code": code})
        assert rv.status_code == 200, rv.get_json()
    return team_id, captain


def _detail(flask_app, team_id):
    return _admin(flask_app, "GET", f"/api/teams/{team_id}").get_json()["team"]


def _put_mentors(flask_app, team_id, mentor_ids):
    return _admin(
        flask_app, "PUT", f"/api/admin/teams/{team_id}/mentors", {"mentor_ids": mentor_ids}
    )


def _assigned(db_conn, team_id):
    with db_conn.cursor() as cur:
        cur.execute("SELECT mentor_id FROM team_mentors WHERE team_id = %s ORDER BY 1", (team_id,))
        return [r["mentor_id"] for r in cur.fetchall()]


@pytest.fixture()
def fourth_mentor(db_conn):
    """Only 3 mentors are seeded; a team over the limit needs a 4th, removed afterwards."""
    with db_conn.cursor() as cur:
        cur.execute(
            """INSERT INTO mentors (first_name, last_name, email, phone_number, company_name,
                                    password_hash, status)
               VALUES ('Delta', 'Mentor', 'delta-edit@mentor.test', '0000000000', 'DeltaCorp',
                       '', 'active')
               RETURNING id"""
        )
        mentor_id = cur.fetchone()["id"]
    try:
        yield mentor_id
    finally:
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM team_mentors WHERE mentor_id = %s", (mentor_id,))
            cur.execute("DELETE FROM mentors WHERE id = %s", (mentor_id,))


class TestMentorEdits:
    def test_replace_then_the_same_set_changes_nothing(self, flask_app, seeds, db_conn, notices):
        m0, m1, m2 = seeds["mentor_ids"]
        team_id, _ = _team(flask_app, seeds, 1, "Hand Picked", 3)

        rv = _put_mentors(flask_app, team_id, [m0, m1])
        assert rv.status_code == 200, rv.get_json()
        assert rv.get_json() == {
            "success": True,
            "changed": True,
            "mentor_count": 2,
            "warnings": [],
        }
        assert _assigned(db_conn, team_id) == sorted([m0, m1])

        rv = _put_mentors(flask_app, team_id, [m1, m2])
        assert rv.get_json()["changed"] is True
        assert _assigned(db_conn, team_id) == sorted([m1, m2])

        rv = _put_mentors(flask_app, team_id, [m2, m1])
        assert rv.get_json()["changed"] is False
        assert notices == ["🛠️ Admin changed team *Hand Picked*'s mentors (now 2)."] * 2

    def test_an_empty_list_clears_the_team_and_warns(self, flask_app, seeds, db_conn):
        team_id, _ = _team(flask_app, seeds, 1, "Emptied", 3)
        _put_mentors(flask_app, team_id, seeds["mentor_ids"][:2])
        rv = _put_mentors(flask_app, team_id, [])
        assert rv.status_code == 200, rv.get_json()
        assert rv.get_json()["warnings"] == ["Team Emptied has 0 mentors (fewer than 2)"]
        assert _assigned(db_conn, team_id) == []

    def test_one_mentor_warns_under_the_floor(self, flask_app, seeds):
        team_id, _ = _team(flask_app, seeds, 1, "Thin", 3)
        rv = _put_mentors(flask_app, team_id, seeds["mentor_ids"][:1])
        assert rv.get_json()["warnings"] == ["Team Thin has 1 mentors (fewer than 2)"]

    def test_four_mentors_warn_over_the_team_limit(self, flask_app, seeds, fourth_mentor):
        team_id, _ = _team(flask_app, seeds, 1, "Crowded", 3)
        rv = _put_mentors(flask_app, team_id, [*seeds["mentor_ids"], fourth_mentor])
        assert rv.status_code == 200, rv.get_json()
        assert rv.get_json()["mentor_count"] == 4
        assert rv.get_json()["warnings"] == ["Team Crowded has 4 mentors (max 3)"]
        export = _admin(flask_app, "GET", "/api/admin/matching-export").get_json()
        assert export["violations"] == ["Team 'Crowded' has 4 mentors (max 3)"]

    def test_a_fourth_team_warns_over_the_mentor_limit(self, flask_app, seeds):
        m0, m1, _ = seeds["mentor_ids"]
        teams = [_team(flask_app, seeds, n, f"Load {n}", 3)[0] for n in range(1, 5)]
        for team_id in teams[:3]:
            assert _put_mentors(flask_app, team_id, [m0, m1]).get_json()["warnings"] == []
        rv = _put_mentors(flask_app, teams[3], [m0, m1])
        assert rv.get_json()["warnings"] == [
            "Mentor Alpha Mentor is assigned to 4 teams (max 3)",
            "Mentor Beta Mentor is assigned to 4 teams (max 3)",
        ]

    def test_an_inactive_mentor_is_refused(self, flask_app, seeds, db_conn):
        team_id, _ = _team(flask_app, seeds, 1, "Picky", 3)
        mentor_id = seeds["mentor_ids"][2]
        with db_conn.cursor() as cur:
            cur.execute("UPDATE mentors SET status = 'inactive' WHERE id = %s", (mentor_id,))
        try:
            rv = _put_mentors(flask_app, team_id, [seeds["mentor_ids"][0], mentor_id])
        finally:
            with db_conn.cursor() as cur:
                cur.execute("UPDATE mentors SET status = 'active' WHERE id = %s", (mentor_id,))
        assert rv.status_code == 400
        assert rv.get_json()["error"] == f"Mentor {mentor_id} not found or inactive"
        assert _assigned(db_conn, team_id) == []

    def test_only_a_registered_team_takes_mentors(self, flask_app, seeds):
        pending_id, _ = _team(flask_app, seeds, 1, "Two Only", 2)
        rv = _put_mentors(flask_app, pending_id, seeds["mentor_ids"][:2])
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "Only registered teams can be assigned mentors"
        assert _put_mentors(flask_app, 999999, []).status_code == 404

    @pytest.mark.parametrize("body", [{}, {"mentor_ids": [1, 1]}, {"mentor_ids": ["1"]}])
    def test_a_malformed_list_is_400(self, flask_app, body):
        rv = _admin(flask_app, "PUT", "/api/admin/teams/1/mentors", body)
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "mentor_ids must be a list of distinct mentor ids"

    def test_an_edit_keeps_the_confirmation(self, flask_app, seeds):
        team_id, captain = _team(flask_app, seeds, 1, "Kept", 3)
        _confirm(flask_app)
        assert _put_mentors(flask_app, team_id, seeds["mentor_ids"][:2]).status_code == 200
        assert _call(flask_app, "GET", "/api/matching-status").get_json()["confirmed"] is True
        team = _call(flask_app, "GET", f"/api/teams/{team_id}", captain).get_json()["team"]
        assert len(team["mentors"]) == 2


class TestAddMember:
    def test_add_by_email_ignores_case_and_accepts_a_pending_application(self, flask_app, seeds):
        team_id, _ = _team(flask_app, seeds, 1, "Growing", 3)
        newcomer = _participant(flask_app, seeds, 60)
        rv = _call(flask_app, "POST", f"/api/teams/{team_id}/apply", newcomer)
        assert rv.status_code == 201, rv.get_json()

        rv = _admin(
            flask_app, "POST", f"/api/admin/teams/{team_id}/members", {"email": "User60@E2E.test"}
        )
        assert rv.status_code == 200, rv.get_json()
        assert rv.get_json()["member_count"] == 4
        apps = _call(flask_app, "GET", "/api/teams/my-applications", newcomer).get_json()
        assert [a["status"] for a in apps["applications"]] == ["accepted"]

    def test_a_full_team_takes_nobody(self, flask_app, seeds):
        team_id, _ = _team(flask_app, seeds, 1, "Full House", 6)
        _participant(flask_app, seeds, 60)
        rv = _admin(
            flask_app, "POST", f"/api/admin/teams/{team_id}/members", {"email": "user60@e2e.test"}
        )
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "Team is full (max 6 members)"

    def test_someone_already_in_a_team_or_unknown_is_refused(self, flask_app, seeds):
        team_id, _ = _team(flask_app, seeds, 1, "Target", 3)
        _team(flask_app, seeds, 2, "Elsewhere", 1)
        path = f"/api/admin/teams/{team_id}/members"
        rv = _admin(flask_app, "POST", path, {"email": "user2@e2e.test"})
        assert (rv.status_code, rv.get_json()["error"]) == (
            400,
            "That participant is already in a team",
        )
        rv = _admin(flask_app, "POST", path, {"email": "nobody@e2e.test"})
        assert (rv.status_code, rv.get_json()["error"]) == (
            400,
            "No active participant has that email",
        )
        assert (
            _admin(
                flask_app, "POST", "/api/admin/teams/999999/members", {"email": "x@e2e.test"}
            ).status_code
            == 404
        )

    def test_the_admin_skips_the_verification_gate(self, flask_app, seeds, monkeypatch):
        team_id, _ = _team(flask_app, seeds, 1, "Verified Later", 1)
        monkeypatch.setitem(flask_app.config, "REQUIRE_EMAIL_VERIFICATION", True)
        unverified = _participant(flask_app, seeds, 60)
        # The participant can't join on their own while the gate is on.
        rv = _call(flask_app, "POST", f"/api/teams/{team_id}/apply", unverified)
        assert rv.status_code == 403
        rv = _admin(
            flask_app, "POST", f"/api/admin/teams/{team_id}/members", {"email": "user60@e2e.test"}
        )
        assert rv.status_code == 200, rv.get_json()


class TestRemoveMember:
    def test_the_last_member_stays(self, flask_app, seeds):
        team_id, _ = _team(flask_app, seeds, 1, "Solo", 1)
        [captain] = _detail(flask_app, team_id)["members"]
        rv = _admin(flask_app, "DELETE", f"/api/admin/teams/{team_id}/members/{captain['id']}")
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "A team's last member can't be removed."

    def test_a_captain_goes_only_with_a_successor(self, flask_app, seeds, notices):
        team_id, old_captain = _team(flask_app, seeds, 1, "Hand Over", 3)
        members = _detail(flask_app, team_id)["members"]
        captain = next(m for m in members if m["is_captain"])
        heir = next(m for m in members if not m["is_captain"])
        path = f"/api/admin/teams/{team_id}/members/{captain['id']}"

        for query in ("", f"?new_captain_id={captain['id']}", "?new_captain_id=999999"):
            rv = _admin(flask_app, "DELETE", path + query)
            assert rv.status_code == 400
            assert rv.get_json()["error"] == "Pick another member of the team as the new captain"

        rv = _admin(flask_app, "DELETE", f"{path}?new_captain_id={heir['id']}")
        assert rv.status_code == 200, rv.get_json()
        assert rv.get_json()["member_count"] == 2
        team = _detail(flask_app, team_id)
        assert team["captain_id"] == heir["id"]
        assert [m["id"] for m in team["members"] if m["is_captain"]] == [heir["id"]]
        me = _call(flask_app, "GET", "/api/auth/me", old_captain).get_json()["user"]
        assert me["team_id"] is None
        assert notices[-1] == "🛠️ Admin removed a member from team *Hand Over* (now 2)."

    def test_a_member_of_another_team_is_not_removed(self, flask_app, seeds):
        team_id, _ = _team(flask_app, seeds, 1, "Mine", 3)
        other_id, _ = _team(flask_app, seeds, 2, "Theirs", 3)
        stranger = _detail(flask_app, other_id)["members"][1]
        rv = _admin(flask_app, "DELETE", f"/api/admin/teams/{team_id}/members/{stranger['id']}")
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "Member not found in this team"


class TestSlotsBeforeAndAfterConfirmation:
    @pytest.fixture(autouse=True)
    def one_slot(self, monkeypatch):
        monkeypatch.setattr(team_service, "MAX_REGISTERED_TEAMS", 1)

    def test_before_a_removal_below_three_frees_the_slot_for_the_queue(self, flask_app, seeds):
        first, _ = _team(flask_app, seeds, 1, "First In", 3)
        second, _ = _team(flask_app, seeds, 2, "Queued", 3)
        assert _detail(flask_app, second)["queue_position"] == 1

        member = next(m for m in _detail(flask_app, first)["members"] if not m["is_captain"])
        rv = _admin(flask_app, "DELETE", f"/api/admin/teams/{first}/members/{member['id']}")
        assert rv.status_code == 200, rv.get_json()

        assert (
            _detail(flask_app, first)["status"],
            _detail(flask_app, first)["is_registered"],
        ) == (
            "pending",
            False,
        )
        assert _detail(flask_app, second)["is_registered"] is True

    def test_after_a_removal_below_three_moves_no_slot(self, flask_app, seeds):
        first, _ = _team(flask_app, seeds, 1, "First In", 3)
        second, _ = _team(flask_app, seeds, 2, "Queued", 3)
        _confirm(flask_app)

        member = next(m for m in _detail(flask_app, first)["members"] if not m["is_captain"])
        rv = _admin(flask_app, "DELETE", f"/api/admin/teams/{first}/members/{member['id']}")
        assert rv.status_code == 200, rv.get_json()
        assert rv.get_json()["member_count"] == 2

        team = _detail(flask_app, first)
        assert (team["status"], team["is_registered"]) == ("active", True)
        assert _detail(flask_app, second)["queue_position"] == 1

    def test_before_an_add_to_three_activates_and_registers(self, flask_app, seeds):
        team_id, _ = _team(flask_app, seeds, 1, "Third Wheel", 2)
        _participant(flask_app, seeds, 60)
        rv = _admin(
            flask_app, "POST", f"/api/admin/teams/{team_id}/members", {"email": "user60@e2e.test"}
        )
        assert rv.status_code == 200, rv.get_json()
        team = _detail(flask_app, team_id)
        assert (team["status"], team["is_registered"]) == ("active", True)

    def test_after_an_add_to_three_only_activates(self, flask_app, seeds):
        team_id, _ = _team(flask_app, seeds, 1, "Third Wheel", 2)
        _participant(flask_app, seeds, 60)
        _confirm(flask_app)
        rv = _admin(
            flask_app, "POST", f"/api/admin/teams/{team_id}/members", {"email": "user60@e2e.test"}
        )
        assert rv.status_code == 200, rv.get_json()
        team = _detail(flask_app, team_id)
        assert (team["status"], team["is_registered"], team["queue_position"]) == (
            "active",
            False,
            None,
        )


class TestUnregisterReleasesMentors:
    def test_admin_unregister_releases_the_mentors(self, flask_app, seeds, db_conn, notices):
        mentor_id = seeds["mentor_ids"][0]
        team_id, _ = _team(flask_app, seeds, 1, "Released", 3)
        _put_mentors(flask_app, team_id, [mentor_id])
        _confirm(flask_app)
        mentor = mentor_token_for(flask_app, mentor_id)
        teams = _call(flask_app, "GET", "/api/mentors/assigned-teams", mentor).get_json()["teams"]
        assert [t["team_id"] for t in teams] == [team_id]

        assert (
            _admin(flask_app, "POST", f"/api/admin/teams/{team_id}/unregister").status_code == 200
        )

        assert _assigned(db_conn, team_id) == []
        assert (
            _call(flask_app, "GET", "/api/mentors/assigned-teams", mentor).get_json()["teams"] == []
        )
        assert notices[-1] == "🛠️ Admin unregistered team *Released*; its mentors were released."

        # Without mentors to release, an unregister says nothing.
        notices.clear()
        assert _admin(flask_app, "POST", f"/api/admin/teams/{team_id}/register").status_code == 200
        assert (
            _admin(flask_app, "POST", f"/api/admin/teams/{team_id}/unregister").status_code == 200
        )
        assert notices == []

    def test_the_automatic_unregister_releases_the_mentors(self, flask_app, seeds, db_conn):
        team_id, captain = _team(flask_app, seeds, 1, "Shrinking", 3)
        _put_mentors(flask_app, team_id, seeds["mentor_ids"][:2])
        member = next(m for m in _detail(flask_app, team_id)["members"] if not m["is_captain"])
        rv = _call(flask_app, "DELETE", f"/api/teams/{team_id}/members/{member['id']}", captain)
        assert rv.status_code == 200, rv.get_json()
        assert _detail(flask_app, team_id)["is_registered"] is False
        assert _assigned(db_conn, team_id) == []

    def test_a_save_skips_a_team_unregistered_after_the_run(self, flask_app, seeds, db_conn):
        from app.services import matching_service

        kept, _ = _team(flask_app, seeds, 1, "Kept", 3)
        dropped, _ = _team(flask_app, seeds, 2, "Dropped", 3)
        m0, m1, _ = seeds["mentor_ids"]
        assert (
            _admin(flask_app, "POST", f"/api/admin/teams/{dropped}/unregister").status_code == 200
        )

        with flask_app.app_context():
            saved = matching_service.save_matching_results([(kept, m0), (dropped, m1)], [], 2)
        assert saved == 1
        assert _assigned(db_conn, kept) == [m0]
        assert _assigned(db_conn, dropped) == []
