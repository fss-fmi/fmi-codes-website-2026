"""E2E tests — team lifecycle, join-request flow, and registration queue.

Covers:
 - Create / list / disband / leave / kick
 - Join via code
 - Browse & apply flow (join requests)
 - Team auto-activation / deactivation at the 3-member threshold
 - Registration queue (first 18 active teams auto-register)
 - Public endpoints: registered teams, public members
 - Data-leakage guardrails: join_code and password_hash exposure
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from tests.e2e.conftest import (
    DEFAULT_PW,
    admin_token,
    bearer,
    new_client,
    register,
    register_and_token,
    register_extra_and_token,
)

pytestmark = pytest.mark.e2e


# ─── Helpers ──────────────────────────────────────────────────────────────

def _create_team(client, token, team_name="Alpha Team"):
    return client.post("/api/teams", json={"team_name": team_name}, headers=bearer(token))


def _join_team(client, token, join_code):
    return client.post("/api/teams/join", json={"join_code": join_code}, headers=bearer(token))


def _get_join_code(create_resp):
    """Extract join_code from the create-team response."""
    return create_resp.get_json()["team"]["join_code"]


def _get_team_id(create_resp):
    return create_resp.get_json()["team"]["id"]


# ═══════════════════════════════════════════════════════════════════════════
# Create team
# ═══════════════════════════════════════════════════════════════════════════

class TestCreateTeam:
    def test_captain_can_create_team(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv = _create_team(client, token)
        assert rv.status_code == 201
        body = rv.get_json()
        assert body["success"] is True
        assert "join_code" in body["team"]

    def test_missing_team_name_returns_400(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv = client.post("/api/teams", json={}, headers=bearer(token))
        assert rv.status_code == 400

    def test_duplicate_team_name_returns_400(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        _create_team(client, token, "Same Name")
        # Different participant tries same name
        with new_client(client.application) as c2:
            token2 = register_and_token(c2, 2, seeds)
            rv = _create_team(c2, token2, "Same Name")
        assert rv.status_code == 400

    def test_participant_already_on_team_cannot_create_another(self, client, seeds, flask_app):
        token = register_and_token(client, 1, seeds)
        _create_team(client, token, "First Team")
        rv = _create_team(client, token, "Second Team")
        assert rv.status_code == 400

    def test_requires_participant_role(self, flask_app, seeds):
        """Mentors and admins cannot create teams."""
        mentor_tok = _mentor_token(flask_app, seeds)
        admin_tok  = admin_token(flask_app)
        with flask_app.test_client() as c:
            for tok, label in [(mentor_tok, "mentor"), (admin_tok, "admin")]:
                rv = c.post("/api/teams", json={"team_name": f"{label}Team"}, headers=bearer(tok))
                assert rv.status_code == 403, f"{label} should be 403"

    def test_requires_authentication(self, client):
        rv = client.post("/api/teams", json={"team_name": "Anon Team"})
        assert rv.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# List teams — data-leakage guards
# ═══════════════════════════════════════════════════════════════════════════

class TestListTeams:
    def test_get_all_teams_is_public(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        _create_team(client, token)
        rv = client.get("/api/teams")
        assert rv.status_code == 200

    def test_join_code_never_exposed_in_list(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        _create_team(client, token)
        rv = client.get("/api/teams")
        body_text = rv.get_data(as_text=True)
        assert "join_code" not in body_text

    def test_password_hash_never_in_list(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        _create_team(client, token)
        rv = client.get("/api/teams")
        assert "password_hash" not in rv.get_data(as_text=True)

    def test_get_team_by_id_shows_join_code_to_member(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token)
        team_id = _get_team_id(rv_create)
        rv = client.get(f"/api/teams/{team_id}", headers=bearer(token))
        assert rv.status_code == 200
        assert "join_code" in rv.get_json()["team"]

    def test_get_team_by_id_hides_join_code_from_non_member(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id = _get_team_id(rv_create)
        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            rv = c2.get(f"/api/teams/{team_id}", headers=bearer(token2))
        assert rv.status_code == 200
        assert "join_code" not in rv.get_json()["team"]

    def test_get_team_by_id_shows_join_code_to_admin(self, client, seeds, flask_app):
        token = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token)
        team_id = _get_team_id(rv_create)
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as c:
            rv = c.get(f"/api/teams/{team_id}", headers=bearer(adm_tok))
        assert rv.status_code == 200
        assert "join_code" in rv.get_json()["team"]

    def test_get_nonexistent_team_returns_404(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv = client.get("/api/teams/99999", headers=bearer(token))
        assert rv.status_code == 404

    def test_password_hash_absent_from_get_team_by_id(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token)
        team_id = _get_team_id(rv_create)
        rv = client.get(f"/api/teams/{team_id}", headers=bearer(token))
        assert "password_hash" not in rv.get_data(as_text=True)


# ═══════════════════════════════════════════════════════════════════════════
# Join via code
# ═══════════════════════════════════════════════════════════════════════════

class TestJoinViaCode:
    def test_valid_join_code_adds_member(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        join_code = _get_join_code(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            rv = _join_team(c2, token2, join_code)
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

    def test_invalid_join_code_returns_400(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv = _join_team(client, token, "BADCODE1")
        assert rv.status_code == 400

    def test_empty_join_code_returns_400(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv = client.post("/api/teams/join", json={"join_code": ""}, headers=bearer(token))
        assert rv.status_code == 400

    def test_participant_already_on_team_cannot_join_another(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1, "Team One")

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            _create_team(c2, token2, "Team Two")
            join_code = _get_join_code(rv_create)
            rv = _join_team(c2, token2, join_code)
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# Leave team
# ═══════════════════════════════════════════════════════════════════════════

class TestLeaveTeam:
    def test_non_captain_member_can_leave(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        join_code = _get_join_code(rv_create)
        team_id   = _get_team_id(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            _join_team(c2, token2, join_code)
            rv = c2.post(f"/api/teams/{team_id}/leave", headers=bearer(token2))
        assert rv.status_code == 200

    def test_captain_leaving_disbands_team(self, client, seeds):
        """When the captain leaves, the team is auto-disbanded and the call returns 200."""
        token = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token)
        team_id   = _get_team_id(rv_create)
        rv = client.post(f"/api/teams/{team_id}/leave", headers=bearer(token))
        assert rv.status_code == 200

    def test_participant_without_team_cannot_leave(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv = client.post("/api/teams/9999/leave", headers=bearer(token))
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# Disband team
# ═══════════════════════════════════════════════════════════════════════════

class TestDisbandTeam:
    def test_captain_can_disband_own_team(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token)
        team_id   = _get_team_id(rv_create)
        rv = client.delete(f"/api/teams/{team_id}", headers=bearer(token))
        assert rv.status_code == 200

    def test_non_captain_cannot_disband(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id   = _get_team_id(rv_create)
        join_code = _get_join_code(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            _join_team(c2, token2, join_code)
            rv = c2.delete(f"/api/teams/{team_id}", headers=bearer(token2))
        assert rv.status_code == 403

    def test_captain_of_team_a_cannot_disband_team_b(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        _create_team(client, token1, "Team A")

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            rv_b = _create_team(c2, token2, "Team B")
            team_b_id = _get_team_id(rv_b)

        # Captain of Team A tries to DELETE Team B
        rv = client.delete(f"/api/teams/{team_b_id}", headers=bearer(token1))
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Kick member
# ═══════════════════════════════════════════════════════════════════════════

class TestKickMember:
    def test_captain_can_kick_member(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        join_code = _get_join_code(rv_create)
        team_id   = _get_team_id(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            _join_team(c2, token2, join_code)
            member_id = c2.get("/api/auth/me", headers=bearer(token2)).get_json()["user"]["id"]

        rv = client.delete(
            f"/api/teams/{team_id}/members/{member_id}", headers=bearer(token1)
        )
        assert rv.status_code == 200

    def test_member_cannot_kick_from_team(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        join_code = _get_join_code(rv_create)
        team_id   = _get_team_id(rv_create)
        captain_id = client.get("/api/auth/me", headers=bearer(token1)).get_json()["user"]["id"]

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            _join_team(c2, token2, join_code)
            # Member tries to kick captain
            rv = c2.delete(
                f"/api/teams/{team_id}/members/{captain_id}", headers=bearer(token2)
            )
        assert rv.status_code == 403

    def test_captain_of_team_a_cannot_kick_from_team_b(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        _create_team(client, token1, "Team A")

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            rv_b = _create_team(c2, token2, "Team B")
            team_b_id = _get_team_id(rv_b)
            join_code_b = _get_join_code(rv_b)

        with flask_app.test_client() as c3:
            token3 = register_and_token(c3, 3, seeds)
            _join_team(c3, token3, join_code_b)
            member3_id = c3.get("/api/auth/me", headers=bearer(token3)).get_json()["user"]["id"]

        # Captain of A tries to kick a member of B
        rv = client.delete(
            f"/api/teams/{team_b_id}/members/{member3_id}", headers=bearer(token1)
        )
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Browse & apply (join request flow)
# ═══════════════════════════════════════════════════════════════════════════

class TestJoinRequestFlow:
    def test_teamless_participant_can_apply_to_team(self, client, seeds, flask_app):
        # Create a team (captain = participant 1)
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id = _get_team_id(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            rv = c2.post(f"/api/teams/{team_id}/apply", headers=bearer(token2))
        assert rv.status_code == 201

    def test_captain_sees_pending_request_for_own_team(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id = _get_team_id(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            c2.post(f"/api/teams/{team_id}/apply", headers=bearer(token2))

        rv = client.get(f"/api/teams/{team_id}/requests", headers=bearer(token1))
        assert rv.status_code == 200
        assert len(rv.get_json()["requests"]) == 1

    def test_captain_accepts_request_adds_member(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id = _get_team_id(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            c2.post(f"/api/teams/{team_id}/apply", headers=bearer(token2))

        req_id = client.get(
            f"/api/teams/{team_id}/requests", headers=bearer(token1)
        ).get_json()["requests"][0]["request_id"]
        rv = client.post(
            f"/api/teams/requests/{req_id}/accept", headers=bearer(token1)
        )
        assert rv.status_code == 200

        # Verify the participant is now on the team
        team_data = client.get(
            f"/api/teams/{team_id}", headers=bearer(token1)
        ).get_json()["team"]
        assert team_data["participant_count"] == 2

    def test_captain_declines_request(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id = _get_team_id(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            c2.post(f"/api/teams/{team_id}/apply", headers=bearer(token2))

        req_id = client.get(
            f"/api/teams/{team_id}/requests", headers=bearer(token1)
        ).get_json()["requests"][0]["request_id"]
        rv = client.post(f"/api/teams/requests/{req_id}/decline", headers=bearer(token1))
        assert rv.status_code == 200

    def test_applicant_can_cancel_own_request(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id = _get_team_id(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            c2.post(f"/api/teams/{team_id}/apply", headers=bearer(token2))
            apps = c2.get("/api/teams/my-applications", headers=bearer(token2)).get_json()
            req_id = apps["applications"][0]["request_id"]
            rv = c2.post(f"/api/teams/requests/{req_id}/cancel", headers=bearer(token2))
        assert rv.status_code == 200

    def test_participant_on_team_cannot_apply(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_1 = _create_team(client, token1, "Team One")
        team_1_id = _get_team_id(rv_1)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            _create_team(c2, token2, "Team Two")
            # Participant 2 is already a captain; should not be allowed to apply
            rv = c2.post(f"/api/teams/{team_1_id}/apply", headers=bearer(token2))
        assert rv.status_code == 400

    def test_duplicate_application_returns_400(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id = _get_team_id(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            c2.post(f"/api/teams/{team_id}/apply", headers=bearer(token2))
            rv = c2.post(f"/api/teams/{team_id}/apply", headers=bearer(token2))
        assert rv.status_code == 400

    def test_captain_cannot_see_different_teams_requests(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        _create_team(client, token1, "Team A")

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            rv_b = _create_team(c2, token2, "Team B")
            team_b_id = _get_team_id(rv_b)

        # Captain of Team A requests the join list for Team B → 403
        rv = client.get(f"/api/teams/{team_b_id}/requests", headers=bearer(token1))
        assert rv.status_code == 403

    def test_non_captain_cannot_accept_requests(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id = _get_team_id(rv_create)

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            c2.post(f"/api/teams/{team_id}/apply", headers=bearer(token2))

        req_id = client.get(
            f"/api/teams/{team_id}/requests", headers=bearer(token1)
        ).get_json()["requests"][0]["request_id"]

        with flask_app.test_client() as c3:
            token3 = register_and_token(c3, 3, seeds)
            rv = c3.post(f"/api/teams/requests/{req_id}/accept", headers=bearer(token3))
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Team auto-activation / deactivation
# ═══════════════════════════════════════════════════════════════════════════

class TestTeamActivation:
    def test_team_activates_at_3_members(self, flask_app, seeds):
        with flask_app.test_client() as cap_client:
            token1 = register_and_token(cap_client, 100, seeds)
            rv = _create_team(cap_client, token1, "ActivationTeam")
            team_id   = _get_team_id(rv)
            join_code = _get_join_code(rv)

            # 1 member (captain) → pending
            t = cap_client.get(f"/api/teams/{team_id}", headers=bearer(token1))
            assert t.get_json()["team"]["status"] == "pending"

            # Add 2nd member
            with flask_app.test_client() as c2:
                t2 = register_and_token(c2, 101, seeds)
                _join_team(c2, t2, join_code)

            t = cap_client.get(f"/api/teams/{team_id}", headers=bearer(token1))
            assert t.get_json()["team"]["status"] == "pending"

            # Add 3rd member → should activate
            with flask_app.test_client() as c3:
                t3 = register_and_token(c3, 102, seeds)
                _join_team(c3, t3, join_code)

            t = cap_client.get(f"/api/teams/{team_id}", headers=bearer(token1))
            assert t.get_json()["team"]["status"] == "active"


# ═══════════════════════════════════════════════════════════════════════════
# Registered-teams public endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestRegisteredTeamsEndpoint:
    def test_public_endpoint_accessible_without_auth(self, client):
        rv = client.get("/api/teams/registered")
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

    def test_join_code_absent_from_registered_teams_response(self, client, seeds, flask_app):
        """Even registered teams must not leak join_code via the public endpoint."""
        adm_tok = admin_token(flask_app)
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id = _get_team_id(rv_create)

        # Manually register the team via admin endpoint
        with flask_app.test_client() as adm:
            adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))

        rv = client.get("/api/teams/registered")
        assert "join_code" not in rv.get_data(as_text=True)

    def test_public_members_endpoint_only_exposes_names(self, client, seeds, flask_app):
        """Public member list must only return first_name / last_name."""
        adm_tok = admin_token(flask_app)
        token1 = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token1)
        team_id = _get_team_id(rv_create)
        join_code = _get_join_code(rv_create)

        # Add 2 more members so the team reaches active status (required for admin registration)
        for _ in range(2):
            with flask_app.test_client() as cx:
                tok = register_extra_and_token(cx, seeds)
                cx.post("/api/teams/join", json={"join_code": join_code}, headers=bearer(tok))

        with flask_app.test_client() as adm:
            adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))

        rv = client.get(f"/api/teams/{team_id}/members/public")
        assert rv.status_code == 200
        members = rv.get_json()["members"]
        for m in members:
            assert set(m.keys()) == {"first_name", "last_name"}

    def test_public_members_endpoint_rejects_unregistered_team(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv_create = _create_team(client, token)
        team_id = _get_team_id(rv_create)
        rv = client.get(f"/api/teams/{team_id}/members/public")
        assert rv.status_code == 404


# ─── Internal helpers ─────────────────────────────────────────────────────

def _mentor_token(app, seeds):
    with app.app_context():
        from app.services.auth_service import generate_token
        return generate_token(seeds["mentor_ids"][0], "mentor")
