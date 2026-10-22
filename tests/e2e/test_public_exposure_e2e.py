"""E2E tests for what anonymous and low-privilege callers can see or create.

1. Scores stay hidden until RANKINGS_LIVE, even when the API is called directly
2. "Other" universities/specialties are created only through registration
3. Bug reports are attributed to a valid session and anonymous otherwise
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from tests.e2e.conftest import (
    DEFAULT_PW,
    _extract_token,
    admin_token,
    bearer,
    register,
    register_and_token,
)

pytestmark = pytest.mark.e2e


@pytest.fixture()
def rankings_live(flask_app):
    """Yield a setter for RANKINGS_LIVE and restore it afterwards."""
    original = flask_app.config.get("RANKINGS_LIVE")

    def _set(value):
        flask_app.config["RANKINGS_LIVE"] = value

    yield _set
    flask_app.config["RANKINGS_LIVE"] = original


def _scored_team(flask_app, client, seeds, score=77.5):
    token = register_and_token(client, 1, seeds)
    rv = client.post("/api/teams", json={"team_name": "Scored Team"}, headers=bearer(token))
    team_id = rv.get_json()["team"]["id"]
    with flask_app.test_client() as adm:
        rv = adm.put(
            f"/api/admin/teams/{team_id}/score",
            json={"score": score},
            headers=bearer(admin_token(flask_app)),
        )
        assert rv.status_code == 200, rv.get_json()
    return team_id, token


# ═══════════════════════════════════════════════════════════════════════════
# 1. Score secrecy
# ═══════════════════════════════════════════════════════════════════════════


class TestScoreSecrecy:
    def test_team_rankings_forbidden_until_live(self, client, rankings_live):
        rankings_live(False)
        rv = client.get("/api/teams/rankings")
        assert rv.status_code == 403
        assert "rankings" not in rv.get_json()

    def test_team_rankings_public_once_live(self, client, rankings_live):
        rankings_live(True)
        rv = client.get("/api/teams/rankings")
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

    def test_team_detail_hides_score_from_participant_until_live(
        self, flask_app, client, seeds, rankings_live
    ):
        rankings_live(False)
        team_id, token = _scored_team(flask_app, client, seeds)
        team = client.get(f"/api/teams/{team_id}", headers=bearer(token)).get_json()["team"]
        assert "score" not in team
        assert "score_updated_at" not in team

    def test_team_detail_shows_score_to_admin_before_live(
        self, flask_app, client, seeds, rankings_live
    ):
        rankings_live(False)
        team_id, _ = _scored_team(flask_app, client, seeds, score=77.5)
        with flask_app.test_client() as adm:
            rv = adm.get(f"/api/teams/{team_id}", headers=bearer(admin_token(flask_app)))
        assert rv.get_json()["team"]["score"] == 77.5

    def test_team_detail_shows_score_once_live(self, flask_app, client, seeds, rankings_live):
        rankings_live(True)
        team_id, token = _scored_team(flask_app, client, seeds, score=77.5)
        team = client.get(f"/api/teams/{team_id}", headers=bearer(token)).get_json()["team"]
        assert team["score"] == 77.5


# ═══════════════════════════════════════════════════════════════════════════
# 2. "Other" university / specialty via registration
# ═══════════════════════════════════════════════════════════════════════════


def _other_payload(tag):
    return {
        "university_id": "other",
        "university_other": {"name": f"Uni {tag}", "city": "Plovdiv", "country": "Bulgaria"},
        "specialty_id": "other",
        "specialty_other": {"name": f"Spec {tag}"},
    }


def _count(db_conn, table, name):
    with db_conn.cursor() as cur:
        # table is a fixed literal from the tests below, never user input
        cur.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE name = %s", (name,))
        return cur.fetchone()["n"]


class TestOtherLookupsOnRegister:
    def test_register_creates_other_university_and_specialty(self, client, seeds, db_conn):
        tag = uuid.uuid4().hex[:8]
        rv = register(client, 1, seeds, **_other_payload(tag))
        assert rv.status_code == 201, rv.get_json()
        user = rv.get_json()["user"]
        assert user["university"] == f"Uni {tag}"
        assert user["specialty"] == f"Spec {tag}"

        with db_conn.cursor() as cur:
            cur.execute("SELECT is_seed FROM universities WHERE name = %s", (f"Uni {tag}",))
            assert cur.fetchone()["is_seed"] is False
            cur.execute("SELECT is_seed FROM specialties WHERE name = %s", (f"Spec {tag}",))
            assert cur.fetchone()["is_seed"] is False

    def test_same_other_name_reuses_existing_row(self, client, seeds, db_conn, flask_app):
        tag = uuid.uuid4().hex[:8]
        assert register(client, 1, seeds, **_other_payload(tag)).status_code == 201
        with flask_app.test_client() as c2:
            assert register(c2, 2, seeds, **_other_payload(tag)).status_code == 201

        assert _count(db_conn, "universities", f"Uni {tag}") == 1
        assert _count(db_conn, "specialties", f"Spec {tag}") == 1

    def test_missing_other_details_rejected(self, client, seeds):
        rv = register(client, 1, seeds, university_id="other")
        assert rv.status_code == 400
        assert "University name" in rv.get_json()["error"]

    def test_html_in_other_name_rejected(self, client, seeds, db_conn):
        payload = _other_payload("x")
        payload["specialty_other"] = {"name": "<script>alert(1)</script>"}
        rv = register(client, 1, seeds, **payload)
        assert rv.status_code == 400
        assert _count(db_conn, "specialties", "<script>alert(1)</script>") == 0

    def test_failed_registration_leaves_no_other_rows(self, client, seeds, db_conn, flask_app):
        assert register(client, 1, seeds).status_code == 201
        tag = uuid.uuid4().hex[:8]
        with flask_app.test_client() as c2:
            # Same participant number → duplicate email/faculty number → 409
            rv = register(c2, 1, seeds, **_other_payload(tag))
        assert rv.status_code == 409
        assert _count(db_conn, "universities", f"Uni {tag}") == 0
        assert _count(db_conn, "specialties", f"Spec {tag}") == 0

    def test_non_numeric_lookup_id_rejected(self, client, seeds):
        rv = register(client, 1, seeds, university_id="abc")
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# 3. Bug report attribution
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def captured_reports(monkeypatch):
    reports = []
    monkeypatch.setattr(
        "app.services.bug_report_service.submit_bug_report_async",
        lambda webhook_url, **kwargs: reports.append(kwargs),
    )
    return reports


BUG = {"what_did": "clicked", "what_happened": "broke", "page": "/register"}


class TestBugReportAttribution:
    def test_anonymous_report_accepted(self, client, captured_reports):
        rv = client.post("/api/bug-report", json=BUG)
        assert rv.status_code == 202
        assert captured_reports[0]["reporter_name"] == "Anonymous"
        assert captured_reports[0]["reporter_role"] == "unknown"

    def test_cookie_session_attributes_report(self, client, seeds, captured_reports):
        register(client, 1, seeds)  # sets the httpOnly token cookie on this client
        rv = client.post("/api/bug-report", json=BUG)
        assert rv.status_code == 202
        report = captured_reports[0]
        assert report["reporter_name"] == "First1 Last1"
        assert report["reporter_email"] == "user1@e2e.test"
        assert report["reporter_role"] == "participant"

    def test_invalid_token_falls_back_to_anonymous(self, client, captured_reports):
        rv = client.post("/api/bug-report", json=BUG, headers=bearer("not-a-jwt"))
        assert rv.status_code == 202
        assert captured_reports[0]["reporter_name"] == "Anonymous"

    def test_token_revoked_by_password_change_is_anonymous(
        self, client, seeds, flask_app, captured_reports
    ):
        rv = register(client, 1, seeds)
        user_id = rv.get_json()["user_id"]
        token = _extract_token(rv)

        # Backdate the stale token: one minted in the same second as the password
        # change legitimately survives the epoch check (whole-second `iat`).
        now = datetime.now(UTC)
        old_token = jwt.encode(
            {
                "user_id": user_id,
                "role": "participant",
                "jti": str(uuid.uuid4()),
                "iat": now - timedelta(minutes=5),
                "exp": now + timedelta(days=1),
            },
            flask_app.config["JWT_SECRET_KEY"],
            algorithm="HS256",
        )
        rv = client.patch(
            "/api/auth/change-password",
            json={"current_password": DEFAULT_PW, "new_password": DEFAULT_PW + "-new"},
            headers=bearer(token),
        )
        assert rv.status_code == 200, rv.get_json()

        with flask_app.test_client() as c2:
            rv = c2.post("/api/bug-report", json=BUG, headers=bearer(old_token))
        assert rv.status_code == 202
        assert captured_reports[0]["reporter_name"] == "Anonymous"
