"""E2E tests — email verification on registration (issue #4).

Covers:
 - Registration issues a single-use, 24-hour verification link
 - POST /api/auth/verify-email: success, reuse, expiry, invalid token
 - email_verified in /api/auth/me
 - POST /api/auth/resend-verification
 - REQUIRE_EMAIL_VERIFICATION gating create / join / apply
 - Migration 016 grandfathers existing participants as verified
"""

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from tests.e2e.conftest import bearer, register_and_token, register_extra_and_token

pytestmark = pytest.mark.e2e

MIGRATION_016 = (
    Path(__file__).parent.parent.parent
    / "backend"
    / "database"
    / "migrations"
    / "016_email_verification.sql"
)


@pytest.fixture()
def issued_links(monkeypatch):
    """Record every verification link the API issues, in order."""
    from app.routes import auth

    links = []
    original = auth._issue_verification_link

    def recording(participant_id):
        url = original(participant_id)
        links.append(url)
        return url

    monkeypatch.setattr(auth, "_issue_verification_link", recording)
    return links


@pytest.fixture()
def sent_emails(monkeypatch):
    """Replace SMTP with an in-memory outbox that always succeeds."""
    outbox = []

    def fake_send(app_config, to_email, verify_url):
        outbox.append((to_email, verify_url))
        return True

    monkeypatch.setattr("app.services.email_service.send_verification_email", fake_send)
    return outbox


@pytest.fixture()
def require_verification(flask_app, monkeypatch):
    monkeypatch.setitem(flask_app.config, "REQUIRE_EMAIL_VERIFICATION", True)


def _token(url):
    return parse_qs(urlparse(url).query)["token"][0]


def _me(client, token):
    return client.get("/api/auth/me", headers=bearer(token)).get_json()["user"]


class TestVerifyEmail:
    def test_registration_issues_link_and_verify_marks_account(
        self, client, seeds, issued_links, sent_emails
    ):
        token = register_and_token(client, 1, seeds)
        assert _me(client, token)["email_verified"] is False
        assert len(issued_links) == 1
        assert "/verify-email?token=" in issued_links[0]

        rv = client.post("/api/auth/verify-email", json={"token": _token(issued_links[0])})
        assert rv.status_code == 200
        assert _me(client, token)["email_verified"] is True

    def test_token_is_single_use(self, client, seeds, issued_links, sent_emails):
        register_and_token(client, 1, seeds)
        raw = _token(issued_links[0])
        assert client.post("/api/auth/verify-email", json={"token": raw}).status_code == 200
        rv = client.post("/api/auth/verify-email", json={"token": raw})
        assert rv.status_code == 400
        assert "already used" in rv.get_json()["error"]

    def test_expired_token_is_rejected(self, client, seeds, db_conn, issued_links, sent_emails):
        token = register_and_token(client, 1, seeds)
        with db_conn.cursor() as cur:
            cur.execute(
                "UPDATE email_verification_tokens SET expires_at = NOW() - INTERVAL '1 minute'"
            )
        rv = client.post("/api/auth/verify-email", json={"token": _token(issued_links[0])})
        assert rv.status_code == 400
        assert "expired" in rv.get_json()["error"]
        assert _me(client, token)["email_verified"] is False

    @pytest.mark.parametrize("payload", [{}, {"token": ""}, {"token": "not-a-real-token"}])
    def test_missing_or_unknown_token_is_rejected(self, client, payload):
        rv = client.post("/api/auth/verify-email", json=payload)
        assert rv.status_code == 400
        assert rv.get_json()["success"] is False

    def test_only_the_token_hash_is_stored(self, client, seeds, db_conn, issued_links, sent_emails):
        register_and_token(client, 1, seeds)
        with db_conn.cursor() as cur:
            cur.execute("SELECT token_hash FROM email_verification_tokens")
            stored = cur.fetchone()["token_hash"]
        assert stored != _token(issued_links[0])
        assert len(stored) == 64


class TestResendVerification:
    def test_resend_replaces_the_previous_link(self, client, seeds, issued_links, sent_emails):
        token = register_and_token(client, 1, seeds)
        rv = client.post("/api/auth/resend-verification", headers=bearer(token))
        assert rv.status_code == 200
        first, second = issued_links
        assert (
            client.post("/api/auth/verify-email", json={"token": _token(first)}).status_code == 400
        )
        assert (
            client.post("/api/auth/verify-email", json={"token": _token(second)}).status_code == 200
        )

    def test_resend_when_already_verified(self, client, seeds, issued_links, sent_emails):
        token = register_and_token(client, 1, seeds)
        client.post("/api/auth/verify-email", json={"token": _token(issued_links[0])})
        rv = client.post("/api/auth/resend-verification", headers=bearer(token))
        assert rv.status_code == 400

    def test_resend_reports_smtp_failure(self, client, seeds, monkeypatch):
        token = register_and_token(client, 1, seeds)
        monkeypatch.setattr(
            "app.services.email_service.send_verification_email", lambda *a, **k: False
        )
        rv = client.post("/api/auth/resend-verification", headers=bearer(token))
        assert rv.status_code == 503

    def test_resend_requires_participant(self, client):
        assert client.post("/api/auth/resend-verification").status_code == 401


class TestVerificationGate:
    def test_flag_is_exposed_in_config(self, client, require_verification):
        assert client.get("/api/config").get_json()["REQUIRE_EMAIL_VERIFICATION"] is True

    def test_unverified_participant_can_create_team_when_flag_off(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        rv = client.post("/api/teams", json={"team_name": "Open Team"}, headers=bearer(token))
        assert rv.status_code == 201

    def test_unverified_participant_is_blocked_when_flag_on(
        self, client, seeds, flask_app, db_conn, require_verification
    ):
        with flask_app.test_client() as cap:
            cap_token = register_extra_and_token(cap, seeds)
            with db_conn.cursor() as cur:
                cur.execute("UPDATE participants SET email_verified = TRUE")
            team = cap.post(
                "/api/teams", json={"team_name": "Gated Team"}, headers=bearer(cap_token)
            ).get_json()["team"]

        token = register_and_token(client, 1, seeds)
        attempts = [
            client.post("/api/teams", json={"team_name": "Nope"}, headers=bearer(token)),
            client.post(
                "/api/teams/join", json={"join_code": team["join_code"]}, headers=bearer(token)
            ),
            client.post(f"/api/teams/{team['id']}/apply", headers=bearer(token)),
        ]
        for rv in attempts:
            assert rv.status_code == 403
            assert rv.get_json()["code"] == "email_unverified"

    def test_verified_participant_passes_gate(
        self, client, seeds, issued_links, sent_emails, require_verification
    ):
        token = register_and_token(client, 1, seeds)
        client.post("/api/auth/verify-email", json={"token": _token(issued_links[0])})
        rv = client.post("/api/teams", json={"team_name": "Verified Team"}, headers=bearer(token))
        assert rv.status_code == 201


class TestMigration016:
    def test_existing_participants_are_grandfathered(self, client, seeds, db_conn):
        """Re-adding the column marks existing rows verified; new rows start unverified."""
        register_and_token(client, 1, seeds)
        sql = MIGRATION_016.read_text(encoding="utf-8")
        with db_conn.cursor() as cur:
            cur.execute("DROP TABLE email_verification_tokens")
            cur.execute("ALTER TABLE participants DROP COLUMN email_verified")
            try:
                cur.execute(sql)
                cur.execute(sql)  # must be safe to re-run
                cur.execute("SELECT email_verified FROM participants")
                verified = [r["email_verified"] for r in cur.fetchall()]
            finally:
                cur.execute(sql)  # leave the schema intact for later tests
        assert verified == [True]

        new_token = register_and_token(client, 2, seeds)
        assert _me(client, new_token)["email_verified"] is False
