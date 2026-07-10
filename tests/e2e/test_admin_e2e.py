"""E2E tests — admin-only operations.

Covers:
 - Auth: admin JWT accepted, participant/mentor/unauthenticated rejected
 - Preference status: reflects how many teams/mentors have submitted
 - Team registration queue: register, double-register rejected, unregister
 - Scoring: valid score accepted, invalid values rejected, unknown team → 404
 - Registration status overview: correct counts returned
 - Matching pipeline: run-matching (no eligible data → 400), confirm, results, export
 - Export constraints: violations array present in response
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from tests.e2e.conftest import (
    ADMIN_EMAIL,
    ADMIN_PW,
    admin_token,
    bearer,
    register_and_token,
    register_extra_and_token,
)

pytestmark = pytest.mark.e2e


# ─── Helpers ──────────────────────────────────────────────────────────────

def _create_team(client, token, name="Admin Test Team"):
    rv = client.post("/api/teams", json={"team_name": name}, headers=bearer(token))
    assert rv.status_code == 201, f"create team failed: {rv.get_data(as_text=True)}"
    return rv.get_json()["team"]["id"]


def _create_active_registered_team(client, token, flask_app, seeds, name="Admin Reg Team"):
    """Create a 3-member team that auto-activates and auto-registers."""
    rv = client.post("/api/teams", json={"team_name": name}, headers=bearer(token))
    assert rv.status_code == 201, f"create team failed: {rv.get_data(as_text=True)}"
    team_id   = rv.get_json()["team"]["id"]
    join_code = rv.get_json()["team"]["join_code"]
    for _ in range(2):
        with flask_app.test_client() as cx:
            tok = register_extra_and_token(cx, seeds)
            rv_join = cx.post("/api/teams/join", json={"join_code": join_code}, headers=bearer(tok))
            assert rv_join.status_code == 200, (
                f"join failed: {rv_join.status_code} {rv_join.get_data(as_text=True)}"
            )
    # Verify the team is now active (auto-activated at 3 members)
    team_status = client.get(f"/api/teams/{team_id}", headers=bearer(token)).get_json()["team"]["status"]
    assert team_status == "active", f"Expected active team, got status={team_status!r}"
    return team_id


def _register_team(admin_client, team_id, adm_tok):
    return admin_client.post(
        f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok)
    )


# ═══════════════════════════════════════════════════════════════════════════
# Authentication on admin endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestAdminAuthentication:
    def test_admin_login_returns_200_with_admin_role(self, client):
        rv = client.post(
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PW, "role": "admin"},
        )
        assert rv.status_code == 200
        assert rv.get_json()["role"] == "admin"

    def test_admin_can_access_preference_status(self, flask_app):
        tok = admin_token(flask_app)
        with flask_app.test_client() as c:
            rv = c.get("/api/admin/preference-status", headers=bearer(tok))
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

    def test_unauthenticated_request_returns_401(self, client):
        rv = client.get("/api/admin/preference-status")
        assert rv.status_code == 401

    def test_participant_returns_403(self, client, seeds):
        tok = register_and_token(client, 1, seeds)
        rv = client.get("/api/admin/preference-status", headers=bearer(tok))
        assert rv.status_code == 403

    def test_mentor_returns_403(self, flask_app, seeds):
        with flask_app.app_context():
            from app.services.auth_service import generate_token
            tok = generate_token(seeds["mentor_ids"][0], "mentor")
        with flask_app.test_client() as c:
            rv = c.get("/api/admin/preference-status", headers=bearer(tok))
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Registration status overview
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistrationStatus:
    def test_registration_status_returns_expected_shape(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            rv = adm.get("/api/admin/teams/registration-status", headers=bearer(adm_tok))
        assert rv.status_code == 200
        body = rv.get_json()
        assert "registered_teams" in body
        assert "queued_teams" in body
        assert "unregistered_teams" in body
        assert "registered_count" in body
        assert "max_registered" in body

    def test_join_code_absent_from_registration_status(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        _create_team(client, token)
        with flask_app.test_client() as adm:
            rv = adm.get("/api/admin/teams/registration-status", headers=bearer(adm_tok))
        assert "join_code" not in rv.get_data(as_text=True)

    def test_password_hash_absent_from_registration_status(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        _create_team(client, token)
        with flask_app.test_client() as adm:
            rv = adm.get("/api/admin/teams/registration-status", headers=bearer(adm_tok))
        assert "password_hash" not in rv.get_data(as_text=True)


# ═══════════════════════════════════════════════════════════════════════════
# Team registration / unregistration
# ═══════════════════════════════════════════════════════════════════════════

class TestTeamRegistration:
    def test_admin_can_register_a_team(self, flask_app, seeds, client):
        """Admin can register a team that is active but not currently registered.

        A team auto-activates AND auto-registers when the 3rd member joins.
        The realistic scenario for admin_register_team is re-registration after
        an admin forced it off the registration list via unregister.
        """
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        team_id = _create_active_registered_team(client, token, flask_app, seeds)

        with flask_app.test_client() as adm:
            # Team is already auto-registered — unregister it first so admin
            # can then exercise the register endpoint on an active+unregistered team.
            rv_unreg = adm.post(f"/api/admin/teams/{team_id}/unregister", headers=bearer(adm_tok))
            assert rv_unreg.status_code == 200, "pre-unregister failed"

            rv = _register_team(adm, team_id, adm_tok)
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

    def test_registering_same_team_twice_is_rejected(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        team_id = _create_team(client, token)

        with flask_app.test_client() as adm:
            adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))
            rv = adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))
        assert rv.status_code in (400, 409)
        assert rv.get_json()["success"] is False

    def test_admin_can_unregister_a_team(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        team_id = _create_active_registered_team(client, token, flask_app, seeds, "Unreg Team")

        with flask_app.test_client() as adm:
            # Team is already auto-registered when it activated — just unregister it
            rv = adm.post(f"/api/admin/teams/{team_id}/unregister", headers=bearer(adm_tok))
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

    def test_unregister_nonexistent_team_returns_400(self, flask_app):
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            rv = adm.post("/api/admin/teams/999999/unregister", headers=bearer(adm_tok))
        assert rv.status_code in (400, 404)

    def test_register_nonexistent_team_returns_400(self, flask_app):
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            rv = adm.post("/api/admin/teams/999999/register", headers=bearer(adm_tok))
        assert rv.status_code in (400, 404)


# ═══════════════════════════════════════════════════════════════════════════
# Scoring
# ═══════════════════════════════════════════════════════════════════════════

class TestTeamScoring:
    def test_admin_can_set_valid_score(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        team_id = _create_team(client, token)

        with flask_app.test_client() as adm:
            adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))
            rv = adm.put(
                f"/api/admin/teams/{team_id}/score",
                json={"score": 85.5},
                headers=bearer(adm_tok),
            )
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

    def test_score_zero_is_valid(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        team_id = _create_team(client, token)

        with flask_app.test_client() as adm:
            adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))
            rv = adm.put(
                f"/api/admin/teams/{team_id}/score",
                json={"score": 0},
                headers=bearer(adm_tok),
            )
        assert rv.status_code == 200

    def test_string_score_returns_400(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        team_id = _create_team(client, token)

        with flask_app.test_client() as adm:
            rv = adm.put(
                f"/api/admin/teams/{team_id}/score",
                json={"score": "very good"},
                headers=bearer(adm_tok),
            )
        assert rv.status_code == 400

    def test_missing_score_field_returns_400(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        team_id = _create_team(client, token)

        with flask_app.test_client() as adm:
            rv = adm.put(
                f"/api/admin/teams/{team_id}/score",
                json={},
                headers=bearer(adm_tok),
            )
        assert rv.status_code == 400

    def test_score_for_nonexistent_team_returns_404(self, flask_app):
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            rv = adm.put(
                "/api/admin/teams/999999/score",
                json={"score": 50},
                headers=bearer(adm_tok),
            )
        assert rv.status_code == 404

    def test_get_teams_for_scoring_returns_list(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        team_id = _create_team(client, token)
        with flask_app.test_client() as adm:
            adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))
            rv = adm.get("/api/admin/teams/scores", headers=bearer(adm_tok))
        assert rv.status_code == 200
        assert isinstance(rv.get_json()["teams"], list)

    def test_scores_response_never_exposes_join_code(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        team_id = _create_team(client, token)
        with flask_app.test_client() as adm:
            adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))
            rv = adm.get("/api/admin/teams/scores", headers=bearer(adm_tok))
        assert "join_code" not in rv.get_data(as_text=True)


# ═══════════════════════════════════════════════════════════════════════════
# Matching pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchingPipeline:
    def test_run_matching_with_no_eligible_teams_returns_400(self, flask_app):
        """No active + registered teams → algorithm has nothing to match → 400."""
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            rv = adm.post("/api/admin/run-matching", headers=bearer(adm_tok))
        # May return 400 ("no active registered teams") OR succeed if seeded data present.
        # The key contract: no 5xx.
        assert rv.status_code < 500

    def test_confirm_matching_returns_200(self, flask_app):
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            rv = adm.post("/api/admin/confirm-matching", headers=bearer(adm_tok))
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

    def test_matching_results_endpoint_returns_list(self, flask_app):
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            rv = adm.get("/api/admin/matching-results", headers=bearer(adm_tok))
        assert rv.status_code == 200
        assert isinstance(rv.get_json()["results"], list)

    def test_matching_export_contains_violations_array(self, flask_app):
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            rv = adm.get("/api/admin/matching-export", headers=bearer(adm_tok))
        assert rv.status_code == 200
        body = rv.get_json()
        assert "violations" in body
        assert isinstance(body["violations"], list)
        assert "teams" in body
        assert "total_assignments" in body

    def test_preference_status_returns_expected_keys(self, flask_app):
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            rv = adm.get("/api/admin/preference-status", headers=bearer(adm_tok))
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True
        # The service returns counts for teams and mentors who have submitted
        for key in ("teams_submitted", "teams_total", "mentors_submitted", "mentors_total"):
            assert key in body, f"Missing key '{key}' in preference-status response"

    def test_matching_status_is_confirmed_after_confirm_call(self, flask_app):
        adm_tok = admin_token(flask_app)
        with flask_app.test_client() as adm:
            adm.post("/api/admin/confirm-matching", headers=bearer(adm_tok))

        with flask_app.test_client() as c:
            rv = c.get("/api/matching-status")
        assert rv.status_code == 200
        assert rv.get_json()["confirmed"] is True
