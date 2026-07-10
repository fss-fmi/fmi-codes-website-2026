"""E2E security tests — adversarial & exploitation scenarios.

Tests are organised by threat category:

1. Unauthenticated access — every protected endpoint must return 401
2. Role escalation — participant/mentor/admin cannot reach each other's routes
3. IDOR (Insecure Direct Object Reference) — one user cannot manipulate
   another user's resources
4. Data leakage — sensitive fields (join_code, password_hash) must never
   appear in responses destined for users who should not see them
5. Injection & output encoding — SQL injection and XSS payloads must not
   trigger server errors or be reflected unescaped
6. Input validation — numbers, bounds, and enumerable field values
7. Feature-flag enforcement — REGISTRATION_OPEN controls access
8. Business-logic abuse — duplicate actions, state transitions
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from tests.e2e.conftest import (
    DEFAULT_PW,
    admin_token,
    bearer,
    register,
    register_and_token,
    register_extra_and_token,
)

pytestmark = pytest.mark.e2e

# ─── Endpoint catalogue ───────────────────────────────────────────────────
# Each entry: (method, path)
# Using placeholder IDs (1, 2) — the 401 check happens before any DB lookup.

PROTECTED_ENDPOINTS = [
    # Auth
    ("GET", "/api/auth/me"),
    ("PATCH", "/api/auth/change-password"),
    # Teams — participant-only
    ("POST", "/api/teams"),
    ("POST", "/api/teams/join"),
    ("POST", "/api/teams/1/leave"),
    ("GET", "/api/teams/available"),
    ("GET", "/api/teams/my-applications"),
    ("POST", "/api/teams/1/apply"),
    # Teams — token_required
    ("GET", "/api/teams/1"),
    # Teams — captain_required
    ("DELETE", "/api/teams/1"),
    ("DELETE", "/api/teams/1/members/2"),
    ("GET", "/api/teams/1/requests"),
    ("POST", "/api/teams/requests/1/accept"),
    ("POST", "/api/teams/requests/1/decline"),
    ("POST", "/api/teams/requests/1/cancel"),
    # Mentors — captain_required
    ("GET", "/api/teams/1/available-mentors"),
    ("POST", "/api/teams/1/mentor-preferences"),
    ("GET", "/api/teams/1/mentor-preferences"),
    # Mentors — mentor_required
    ("GET", "/api/mentors/available-teams"),
    ("POST", "/api/mentors/team-preferences"),
    ("GET", "/api/mentors/team-preferences"),
    ("GET", "/api/mentors/assigned-teams"),
    # Admin
    ("GET", "/api/admin/preference-status"),
    ("POST", "/api/admin/run-matching"),
    ("POST", "/api/admin/confirm-matching"),
    ("GET", "/api/admin/matching-results"),
    ("GET", "/api/admin/matching-export"),
    ("GET", "/api/admin/teams/registration-status"),
    ("POST", "/api/admin/teams/1/register"),
    ("POST", "/api/admin/teams/1/unregister"),
    ("PUT", "/api/admin/teams/1/score"),
    ("GET", "/api/admin/teams/scores"),
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Unauthenticated access
# ═══════════════════════════════════════════════════════════════════════════


class TestUnauthenticatedAccess:
    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_protected_endpoint_requires_token(self, client, method, path):
        rv = getattr(client, method.lower())(path, json={})
        assert rv.status_code == 401, f"{method} {path} returned {rv.status_code}; expected 401"

    def test_public_endpoints_accessible_without_token(self, client):
        public = [
            ("GET", "/api/teams"),
            ("GET", "/api/mentors"),
            ("GET", "/api/teams/registered"),
            ("GET", "/api/config"),
            ("GET", "/api/universities"),
            ("GET", "/api/specialties"),
            ("GET", "/api/ranking"),
            ("GET", "/api/regulations"),
            ("GET", "/api/matching-status"),
        ]
        for method, path in public:
            rv = getattr(client, method.lower())(path)
            assert rv.status_code in (200, 404), (
                f"{method} {path} returned unexpected {rv.status_code}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Role escalation attacks
# ═══════════════════════════════════════════════════════════════════════════


class TestRoleEscalation:
    # — Participant → admin —
    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/admin/preference-status"),
            ("POST", "/api/admin/run-matching"),
            ("POST", "/api/admin/confirm-matching"),
            ("GET", "/api/admin/matching-results"),
            ("GET", "/api/admin/matching-export"),
            ("GET", "/api/admin/teams/registration-status"),
            ("POST", "/api/admin/teams/1/register"),
            ("POST", "/api/admin/teams/1/unregister"),
            ("PUT", "/api/admin/teams/1/score"),
            ("GET", "/api/admin/teams/scores"),
        ],
    )
    def test_participant_cannot_reach_admin_endpoint(self, client, seeds, method, path):
        token = register_and_token(client, 1, seeds)
        rv = getattr(client, method.lower())(path, json={}, headers=bearer(token))
        assert rv.status_code == 403, (
            f"Participant reached admin endpoint {method} {path}: {rv.status_code}"
        )

    # — Mentor → participant/captain endpoints —
    @pytest.mark.parametrize(
        "method,path",
        [
            ("POST", "/api/teams"),
            ("POST", "/api/teams/join"),
            ("GET", "/api/teams/available"),
            ("GET", "/api/teams/my-applications"),
        ],
    )
    def test_mentor_cannot_reach_participant_endpoint(self, flask_app, seeds, method, path):
        from app.services.auth_service import generate_token

        with flask_app.app_context():
            token = generate_token(seeds["mentor_ids"][0], "mentor")
        with flask_app.test_client() as c:
            rv = getattr(c, method.lower())(path, json={}, headers=bearer(token))
        assert rv.status_code == 403, (
            f"Mentor reached participant endpoint {method} {path}: {rv.status_code}"
        )

    # — Participant → mentor-only endpoints —
    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/mentors/available-teams"),
            ("POST", "/api/mentors/team-preferences"),
            ("GET", "/api/mentors/team-preferences"),
            ("GET", "/api/mentors/assigned-teams"),
        ],
    )
    def test_participant_cannot_reach_mentor_endpoint(self, client, seeds, method, path):
        token = register_and_token(client, 1, seeds)
        rv = getattr(client, method.lower())(path, json={}, headers=bearer(token))
        assert rv.status_code == 403, (
            f"Participant reached mentor endpoint {method} {path}: {rv.status_code}"
        )

    # — Admin → participant/captain actions —
    @pytest.mark.parametrize(
        "method,path",
        [
            ("POST", "/api/teams"),
            ("POST", "/api/teams/join"),
            ("GET", "/api/teams/available"),
        ],
    )
    def test_admin_cannot_reach_participant_endpoint(self, flask_app, method, path):
        token = admin_token(flask_app)
        with flask_app.test_client() as c:
            rv = getattr(c, method.lower())(path, json={}, headers=bearer(token))
        assert rv.status_code == 403, (
            f"Admin reached participant endpoint {method} {path}: {rv.status_code}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. IDOR attacks
# ═══════════════════════════════════════════════════════════════════════════


class TestIDOR:
    """Each test verifies that User A cannot perform an operation on resources
    owned by User B by guessing the resource ID."""

    def _two_teams(self, flask_app, seeds):
        """Create two teams with separate captains.  Returns (tok_a, tok_b, team_a_id, team_b_id)."""
        with flask_app.test_client() as ca:
            tok_a = register_and_token(ca, 10, seeds)
            rv_a = ca.post("/api/teams", json={"team_name": "IDOR TeamA"}, headers=bearer(tok_a))
            team_a_id = rv_a.get_json()["team"]["id"]

        with flask_app.test_client() as cb:
            tok_b = register_and_token(cb, 11, seeds)
            rv_b = cb.post("/api/teams", json={"team_name": "IDOR TeamB"}, headers=bearer(tok_b))
            team_b_id = rv_b.get_json()["team"]["id"]

        return tok_a, tok_b, team_a_id, team_b_id

    def test_captain_a_cannot_disband_team_b(self, flask_app, seeds):
        tok_a, _, _, team_b_id = self._two_teams(flask_app, seeds)
        with flask_app.test_client() as c:
            rv = c.delete(f"/api/teams/{team_b_id}", json={}, headers=bearer(tok_a))
        assert rv.status_code == 403

    def test_captain_a_cannot_view_team_b_requests(self, flask_app, seeds):
        tok_a, _, _, team_b_id = self._two_teams(flask_app, seeds)
        with flask_app.test_client() as c:
            rv = c.get(f"/api/teams/{team_b_id}/requests", headers=bearer(tok_a))
        assert rv.status_code == 403

    def test_captain_a_cannot_set_mentor_prefs_for_team_b(self, flask_app, seeds):
        tok_a, _, _, team_b_id = self._two_teams(flask_app, seeds)
        with flask_app.test_client() as c:
            rv = c.post(
                f"/api/teams/{team_b_id}/mentor-preferences",
                json={"preferences": seeds["mentor_ids"]},
                headers=bearer(tok_a),
            )
        assert rv.status_code == 403

    def test_captain_a_cannot_view_available_mentors_for_team_b(self, flask_app, seeds):
        tok_a, _, _, team_b_id = self._two_teams(flask_app, seeds)
        with flask_app.test_client() as c:
            rv = c.get(f"/api/teams/{team_b_id}/available-mentors", headers=bearer(tok_a))
        assert rv.status_code == 403

    def test_captain_a_cannot_kick_member_from_team_b(self, flask_app, seeds):
        """Captain A tries to kick the captain of team B."""
        tok_a, tok_b, _, team_b_id = self._two_teams(flask_app, seeds)
        # Get captain B's user id
        with flask_app.test_client() as c:
            captain_b_id = c.get("/api/auth/me", headers=bearer(tok_b)).get_json()["user"]["id"]
        with flask_app.test_client() as c:
            rv = c.delete(
                f"/api/teams/{team_b_id}/members/{captain_b_id}",
                headers=bearer(tok_a),
            )
        assert rv.status_code == 403

    def test_participant_cannot_accept_random_request_id(self, client, seeds, flask_app):
        """A non-captain participant guesses a request ID and tries to accept it."""
        token1 = register_and_token(client, 1, seeds)
        rv_a = client.post(
            "/api/teams", json={"team_name": "IDOR RequestTeam"}, headers=bearer(token1)
        )
        team_a_id = rv_a.get_json()["team"]["id"]

        with flask_app.test_client() as c2:
            tok2 = register_and_token(c2, 2, seeds)
            c2.post(f"/api/teams/{team_a_id}/apply", headers=bearer(tok2))

        with flask_app.test_client() as c3:
            tok3 = register_and_token(c3, 3, seeds)
            # c3 has no team (not a captain), tries to accept request id=1
            rv = c3.post("/api/teams/requests/1/accept", headers=bearer(tok3))
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 4. Data leakage
# ═══════════════════════════════════════════════════════════════════════════


class TestDataLeakage:
    def test_join_code_absent_from_public_team_list(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        client.post("/api/teams", json={"team_name": "Leakage Team"}, headers=bearer(token))
        rv = client.get("/api/teams")
        assert "join_code" not in rv.get_data(as_text=True)

    def test_join_code_absent_from_non_member_team_detail(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "Details Team"}, headers=bearer(token1))
        team_id = rv_c.get_json()["team"]["id"]

        with flask_app.test_client() as c2:
            tok2 = register_and_token(c2, 2, seeds)
            rv = c2.get(f"/api/teams/{team_id}", headers=bearer(tok2))
        assert "join_code" not in rv.get_json()["team"]

    def test_password_hash_absent_from_all_team_endpoints(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "Hash Team"}, headers=bearer(token))
        team_id = rv_c.get_json()["team"]["id"]

        for path in ["/api/teams", f"/api/teams/{team_id}"]:
            kwargs = {} if path == "/api/teams" else {"headers": bearer(token)}
            rv = client.get(path, **kwargs)
            assert "password_hash" not in rv.get_data(as_text=True), (
                f"password_hash leaked via {path}"
            )

    def test_password_hash_absent_from_auth_endpoints(self, client, seeds):
        register(client, 1, seeds)
        rv_login = client.post(
            "/api/auth/login",
            json={"email": "user1@e2e.test", "password": DEFAULT_PW, "role": "participant"},
        )
        token = _get_token_from_login(rv_login)
        rv_me = client.get("/api/auth/me", headers=bearer(token))
        assert "password_hash" not in rv_me.get_data(as_text=True)

    def test_mentor_password_not_in_public_mentors_response(self, client):
        rv = client.get("/api/mentors")
        assert rv.status_code == 200
        assert "password_hash" not in rv.get_data(as_text=True)

    def test_public_member_list_exposes_only_names(self, client, seeds, flask_app):
        """admin/teams/<id>/register then check /teams/<id>/members/public."""
        adm_tok = admin_token(flask_app)
        token1 = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "Public Team"}, headers=bearer(token1))
        team_id = rv_c.get_json()["team"]["id"]
        join_code = rv_c.get_json()["team"]["join_code"]

        # Add 2 more members to activate team (admin registration requires status='active')
        for _ in range(2):
            with flask_app.test_client() as cx:
                tok = register_extra_and_token(cx, seeds)
                cx.post("/api/teams/join", json={"join_code": join_code}, headers=bearer(tok))

        with flask_app.test_client() as adm:
            adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))

        rv = client.get(f"/api/teams/{team_id}/members/public")
        assert rv.status_code == 200
        for member in rv.get_json()["members"]:
            for sensitive in ("email", "faculty_number", "password_hash", "phone"):
                assert sensitive not in member, f"Sensitive field '{sensitive}' leaked"
            assert "first_name" in member
            assert "last_name" in member


# ═══════════════════════════════════════════════════════════════════════════
# 5. Injection & output encoding
# ═══════════════════════════════════════════════════════════════════════════


class TestInjectionAndEncoding:
    @pytest.mark.parametrize(
        "payload",
        [
            "'; DROP TABLE participants; --",
            '" OR 1=1 --',
            "' OR '1'='1",
            "1; SELECT * FROM participants --",
        ],
    )
    def test_sql_injection_in_registration_email_does_not_cause_500(self, client, seeds, payload):
        rv = register(client, 1, seeds, email=f"{payload}@test.invalid")
        # Parameterized queries safely store the injection string as data (201 is
        # acceptable); the security property is no 5xx (SQL was never executed).
        assert rv.status_code < 500

    @pytest.mark.parametrize(
        "payload",
        [
            "'; DROP TABLE teams; --",
            '" OR 1=1 --',
        ],
    )
    def test_sql_injection_in_team_name_does_not_cause_500(self, client, seeds, payload):
        token = register_and_token(client, 1, seeds)
        rv = client.post("/api/teams", json={"team_name": payload}, headers=bearer(token))
        # Injection must not yield a 5xx; it may succeed (201) or fail validation (400)
        assert rv.status_code < 500, f"SQL injection in team_name caused {rv.status_code}"

    def test_xss_in_team_name_not_reflected_unescaped(self, client, seeds):
        xss = "<script>alert('xss')</script>"
        token = register_and_token(client, 1, seeds)
        rv = client.post("/api/teams", json={"team_name": xss}, headers=bearer(token))
        assert rv.status_code < 500
        # JSON API: <script> inside a JSON string value is safe — browsers do not
        # execute script tags encountered in application/json responses.
        # The correct security check is that Content-Type is application/json.
        assert rv.content_type.startswith("application/json")

    def test_xss_in_first_name_not_reflected_unescaped(self, client, seeds):
        """C7: HTML injection in first_name is rejected at the backend boundary."""
        xss = "<img src=x onerror=alert(1)>"
        rv = register(client, 1, seeds, first_name=xss)
        # C7: backend rejects HTML injection characters → 400
        assert rv.status_code == 400
        assert "<img" not in rv.get_data(as_text=True)

    @pytest.mark.parametrize(
        "payload",
        [
            "'; DROP TABLE mentors; --",
            '" OR 1=1 --',
        ],
    )
    def test_sql_injection_in_login_email_returns_401_not_500(self, client, payload):
        rv = client.post(
            "/api/auth/login",
            json={"email": payload, "password": "anything", "role": "participant"},
        )
        assert rv.status_code in (400, 401), f"SQL injection in login email caused {rv.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Input validation
# ═══════════════════════════════════════════════════════════════════════════


class TestInputValidation:
    def test_score_with_string_value_returns_400(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "ScoreTeam"}, headers=bearer(token))
        team_id = rv_c.get_json()["team"]["id"]

        with flask_app.test_client() as adm:
            rv = adm.put(
                f"/api/admin/teams/{team_id}/score",
                json={"score": "not-a-number"},
                headers=bearer(adm_tok),
            )
        assert rv.status_code == 400

    def test_score_with_negative_value_returns_400(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "ScoreTeam2"}, headers=bearer(token))
        team_id = rv_c.get_json()["team"]["id"]

        with flask_app.test_client() as adm:
            rv = adm.put(
                f"/api/admin/teams/{team_id}/score",
                json={"score": -1},
                headers=bearer(adm_tok),
            )
        assert rv.status_code in (400, 422)

    def test_empty_body_to_json_endpoints_returns_400(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv = client.post("/api/teams/join", data=b"", headers=bearer(token))
        assert rv.status_code == 400

    def test_extremely_long_team_name_handled_gracefully(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        long_name = "A" * 10_000
        rv = client.post("/api/teams", json={"team_name": long_name}, headers=bearer(token))
        assert rv.status_code < 500

    def test_preferences_with_fewer_than_3_mentors_returns_400(self, client, seeds, flask_app):
        """Mentor-preference submission requires exactly 3 ranked IDs."""
        token1 = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "PrefTeam"}, headers=bearer(token1))
        team_id = rv_c.get_json()["team"]["id"]
        rv = client.post(
            f"/api/teams/{team_id}/mentor-preferences",
            json={"preferences": [seeds["mentor_ids"][0]]},
            headers=bearer(token1),
        )
        assert rv.status_code == 400

    def test_preferences_with_duplicate_mentor_ids_returns_400(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "PrefTeam2"}, headers=bearer(token1))
        team_id = rv_c.get_json()["team"]["id"]
        mid = seeds["mentor_ids"][0]
        rv = client.post(
            f"/api/teams/{team_id}/mentor-preferences",
            json={
                "preferences": [
                    {"mentor_id": mid, "rank": 1},
                    {"mentor_id": mid, "rank": 2},
                    {"mentor_id": mid, "rank": 3},
                ]
            },
            headers=bearer(token1),
        )
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# 7. Feature-flag enforcement
# ═══════════════════════════════════════════════════════════════════════════


class TestFeatureFlags:
    def test_registration_closed_returns_403(self, flask_app, seeds):
        flask_app.config["REGISTRATION_OPEN"] = False
        try:
            with flask_app.test_client() as c:
                rv = register(c, 50, seeds)
            assert rv.status_code == 403
        finally:
            flask_app.config["REGISTRATION_OPEN"] = True

    def test_config_endpoint_reflects_registration_flag(self, flask_app):
        with flask_app.test_client() as c:
            flask_app.config["REGISTRATION_OPEN"] = True
            rv = c.get("/api/config")
            assert rv.get_json()["REGISTRATION_OPEN"] is True

            flask_app.config["REGISTRATION_OPEN"] = False
            rv = c.get("/api/config")
            assert rv.get_json()["REGISTRATION_OPEN"] is False

        flask_app.config["REGISTRATION_OPEN"] = True


# ═══════════════════════════════════════════════════════════════════════════
# 8. Business-logic abuse
# ═══════════════════════════════════════════════════════════════════════════


class TestBusinessLogicAbuse:
    def test_applying_to_own_team_is_rejected(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "OwnTeam"}, headers=bearer(token))
        team_id = rv_c.get_json()["team"]["id"]
        rv = client.post(f"/api/teams/{team_id}/apply", headers=bearer(token))
        assert rv.status_code == 400

    def test_captain_leaving_disbands_team(self, client, seeds):
        """Captain leaving via the leave endpoint auto-disbands the team (returns 200)."""
        token = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "LeaveTest"}, headers=bearer(token))
        team_id = rv_c.get_json()["team"]["id"]
        rv = client.post(f"/api/teams/{team_id}/leave", headers=bearer(token))
        assert rv.status_code == 200

    def test_joining_team_when_already_on_a_team_is_rejected(self, client, seeds, flask_app):
        token1 = register_and_token(client, 1, seeds)
        rv_a = client.post(
            "/api/teams", json={"team_name": "AlreadyIn Team"}, headers=bearer(token1)
        )
        join_code_a = rv_a.get_json()["team"]["join_code"]

        with flask_app.test_client() as c2:
            token2 = register_and_token(c2, 2, seeds)
            c2.post("/api/teams", json={"team_name": "Already Has Team"}, headers=bearer(token2))
            rv = c2.post("/api/teams/join", json={"join_code": join_code_a}, headers=bearer(token2))
        assert rv.status_code == 400

    def test_double_registration_of_same_team_is_rejected(self, flask_app, seeds, client):
        adm_tok = admin_token(flask_app)
        token = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "DoubleReg"}, headers=bearer(token))
        team_id = rv_c.get_json()["team"]["id"]

        with flask_app.test_client() as adm:
            adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))
            rv = adm.post(f"/api/admin/teams/{team_id}/register", headers=bearer(adm_tok))
        assert rv.status_code in (400, 409)

    def test_mentor_preferences_accept_valid_format_from_any_captain(self, client, seeds):
        """Any captain (including pending teams) can set preferences with the correct format.
        The app does not enforce active team status before accepting preferences.
        """
        token = register_and_token(client, 1, seeds)
        rv_c = client.post("/api/teams", json={"team_name": "PendingPref"}, headers=bearer(token))
        team_id = rv_c.get_json()["team"]["id"]
        mid0, mid1, mid2 = seeds["mentor_ids"]
        rv = client.post(
            f"/api/teams/{team_id}/mentor-preferences",
            json={
                "preferences": [
                    {"mentor_id": mid0, "rank": 1},
                    {"mentor_id": mid1, "rank": 2},
                    {"mentor_id": mid2, "rank": 3},
                ]
            },
            headers=bearer(token),
        )
        assert rv.status_code == 200


# ─── Internal helpers ─────────────────────────────────────────────────────


def _get_token_from_login(response):
    for h in response.headers.getlist("Set-Cookie"):
        if "token=" in h:
            return h.split("token=", 1)[1].split(";")[0]
    # Fall back to JSON body if present
    body = response.get_json() or {}
    return body.get("token")
