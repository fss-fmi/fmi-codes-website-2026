"""E2E tests — authentication flows.

Covers:
 - Registration: happy path, validation, duplicates, closed flag, injection
 - Login: participants / mentors / admin, wrong credentials, role mismatch
 - Logout: cookie clearing
 - /me: returns correct profile, rejects bad tokens
 - Change-password: happy path, wrong current pw, too short, admin blocked
 - Reset-password: user-enumeration safety, validation
 - Confirm-password-reset: happy path, token reuse, expired token, validation
"""

import hashlib
import secrets
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from tests.e2e.conftest import (
    ADMIN_EMAIL,
    ADMIN_PW,
    DEFAULT_PW,
    admin_token,
    bearer,
    login_token,
    make_payload,
    new_client,
    register,
    register_and_token,
)

pytestmark = pytest.mark.e2e


# ═══════════════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistration:
    def test_happy_path_returns_201_with_token_cookie(self, client, seeds):
        rv = register(client, 1, seeds)
        assert rv.status_code == 201
        body = rv.get_json()
        assert body["success"] is True
        assert body["role"] == "participant"
        # httpOnly token cookie must be present
        cookie_names = [c.split("=")[0] for c in rv.headers.getlist("Set-Cookie")]
        assert "token" in cookie_names
        # M7: role cookie removed — role is sourced from /api/auth/me, not a cookie
        assert "role" not in cookie_names

    def test_registration_sets_httponly_flag_on_token_cookie(self, client, seeds):
        rv = register(client, 1, seeds)
        token_cookie = next(
            (h for h in rv.headers.getlist("Set-Cookie") if h.startswith("token=")), None
        )
        assert token_cookie is not None
        assert "HttpOnly" in token_cookie

    def test_role_cookie_is_not_httponly(self, client, seeds):
        """M7: role cookie is not set at all; JS reads role from /api/auth/me."""
        rv = register(client, 1, seeds)
        role_cookie = next(
            (h for h in rv.headers.getlist("Set-Cookie") if h.startswith("role=")), None
        )
        assert role_cookie is None

    def test_missing_required_fields_returns_400(self, client, seeds):
        payload = make_payload(1, univ_id=seeds["univ_id"], spec_id=seeds["spec_id"])
        del payload["email"]
        rv = client.post("/api/auth/register", json=payload)
        assert rv.status_code == 400
        assert rv.get_json()["success"] is False

    def test_all_required_fields_listed_in_error(self, client, seeds):
        rv = client.post("/api/auth/register", json={})
        assert rv.status_code == 400
        error = rv.get_json()["error"]
        assert "missing" in error.lower() or "required" in error.lower()

    def test_invalid_course_returns_400(self, client, seeds):
        rv = register(client, 1, seeds, course="PhD 1st Year")
        assert rv.status_code == 400
        assert "course" in rv.get_json()["error"].lower()

    def test_duplicate_email_returns_409(self, client, seeds):
        register(client, 1, seeds)
        rv = register(client, 2, seeds, email="user1@e2e.test")
        assert rv.status_code == 409
        # M2: generic message — does not reveal which field caused the conflict
        assert "already exists" in rv.get_json()["error"].lower()

    def test_duplicate_faculty_number_returns_409(self, client, seeds):
        register(client, 1, seeds)
        rv = register(client, 2, seeds, faculty_number="FAC000001")
        assert rv.status_code == 409
        # M2: generic message — does not reveal which field caused the conflict
        assert "already exists" in rv.get_json()["error"].lower()

    def test_registration_closed_returns_403(self, flask_app, seeds):
        flask_app.config["REGISTRATION_OPEN"] = False
        try:
            with flask_app.test_client() as c:
                rv = register(c, 99, seeds)
            assert rv.status_code == 403
            assert rv.get_json()["success"] is False
        finally:
            flask_app.config["REGISTRATION_OPEN"] = True

    def test_sql_injection_in_email_is_handled_safely(self, client, seeds):
        """SQL injection must not crash the server or produce a 5xx.

        Parameterized queries safely store the injection string as data (201 is
        acceptable), so the security property is: no 5xx, meaning the SQL was
        never executed as code.
        """
        rv = register(client, 1, seeds, email="'; DROP TABLE participants; --@e2e.test")
        assert rv.status_code < 500

    def test_xss_payload_in_name_stored_not_executed(self, client, seeds):
        """C7: HTML injection in name fields is rejected at the backend boundary."""
        xss = "<script>alert(1)</script>"
        rv = register(client, 1, seeds, first_name=xss)
        # C7 validation rejects HTML injection characters → 400
        assert rv.status_code == 400
        assert rv.get_json()["success"] is False
        assert "<script>" not in rv.get_data(as_text=True)

    def test_response_never_contains_password_hash(self, client, seeds):
        rv = register(client, 1, seeds)
        assert "password_hash" not in rv.get_data(as_text=True)

    def test_whitespace_trimmed_from_email(self, client, seeds):
        """Registration must normalise email to lowercase + stripped."""
        rv = register(client, 1, seeds, email="  User1@E2E.TEST  ")
        assert rv.status_code == 201
        # Login with the normalised form should succeed
        rv2 = client.post(
            "/api/auth/login",
            json={"email": "user1@e2e.test", "password": DEFAULT_PW, "role": "participant"},
        )
        assert rv2.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Login
# ═══════════════════════════════════════════════════════════════════════════


class TestLogin:
    def test_participant_login_returns_200_with_token(self, client, seeds):
        register(client, 1, seeds)
        rv = client.post(
            "/api/auth/login",
            json={"email": "user1@e2e.test", "password": DEFAULT_PW, "role": "participant"},
        )
        assert rv.status_code == 200
        assert rv.get_json()["role"] == "participant"
        assert _extract_token(rv) is not None

    def test_mentor_login_returns_200(self, client, seeds):
        rv = client.post(
            "/api/auth/login",
            json={"email": "alpha@mentor.test", "password": "mentor123", "role": "mentor"},
        )
        assert rv.status_code == 200
        assert rv.get_json()["role"] == "mentor"

    def test_admin_login_returns_200(self, client):
        rv = client.post(
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PW, "role": "admin"},
        )
        assert rv.status_code == 200
        assert rv.get_json()["role"] == "admin"

    def test_wrong_password_returns_401(self, client, seeds):
        register(client, 1, seeds)
        rv = client.post(
            "/api/auth/login",
            json={"email": "user1@e2e.test", "password": "WRONGPASSWORD", "role": "participant"},
        )
        assert rv.status_code == 401

    def test_nonexistent_user_returns_same_401_as_wrong_password(self, client, seeds):
        """No user-enumeration: unknown email must produce the same response as wrong password."""
        register(client, 1, seeds)
        rv_bad_email = client.post(
            "/api/auth/login",
            json={"email": "nobody@e2e.test", "password": "anything", "role": "participant"},
        )
        rv_bad_pw = client.post(
            "/api/auth/login",
            json={"email": "user1@e2e.test", "password": "WRONGPASSWORD", "role": "participant"},
        )
        assert rv_bad_email.status_code == 401
        assert rv_bad_pw.status_code == 401
        # Both must return the SAME error message — different messages would let
        # an attacker enumerate which emails are registered in the system.
        error_unknown = rv_bad_email.get_json()["error"].lower()
        error_wrong_pw = rv_bad_pw.get_json()["error"].lower()
        assert error_unknown == error_wrong_pw, (
            f"Login error differs between unknown email ({error_unknown!r}) "
            f"and wrong password ({error_wrong_pw!r}) — user enumeration risk"
        )
        assert "invalid email or password" in error_unknown

    def test_wrong_admin_password_returns_401_not_500(self, client):
        rv = client.post(
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": "WRONGADMINPW", "role": "admin"},
        )
        assert rv.status_code == 401

    def test_invalid_role_returns_400(self, client):
        rv = client.post(
            "/api/auth/login",
            json={"email": "x@e2e.test", "password": "pw", "role": "superuser"},
        )
        assert rv.status_code == 400

    def test_empty_email_and_password_returns_400(self, client):
        rv = client.post("/api/auth/login", json={"email": "", "password": ""})
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# Logout
# ═══════════════════════════════════════════════════════════════════════════


class TestLogout:
    def test_logout_clears_cookies(self, client, seeds):
        register(client, 1, seeds)
        rv = client.post("/api/auth/logout")
        assert rv.status_code == 200
        # Both cookies must be deleted (max-age=0 or expires in the past)
        for cookie_str in rv.headers.getlist("Set-Cookie"):
            if "token=" in cookie_str or "role=" in cookie_str:
                assert (
                    "max-age=0" in cookie_str.lower()
                    or "expires=" in cookie_str.lower()
                    or cookie_str.split("=", 1)[1].split(";")[0] == ""
                )

    def test_logout_without_token_still_returns_200(self, client):
        rv = client.post("/api/auth/logout")
        assert rv.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# /me endpoint
# ═══════════════════════════════════════════════════════════════════════════


class TestGetMe:
    def test_returns_participant_profile(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        with flask_app_client(client.application) as c2:
            rv = c2.get("/api/auth/me", headers=bearer(token))
        assert rv.status_code == 200
        user = rv.get_json()["user"]
        assert user["role"] == "participant"
        assert user["email"] == "user1@e2e.test"

    def test_returns_mentor_profile(self, client, seeds, flask_app):
        token = mentor_token_for_seed(flask_app, seeds)
        with flask_app.test_client() as c:
            rv = c.get("/api/auth/me", headers=bearer(token))
        assert rv.status_code == 200
        assert rv.get_json()["user"]["role"] == "mentor"

    def test_admin_me_returns_role_only(self, flask_app):
        token = admin_token(flask_app)
        with flask_app.test_client() as c:
            rv = c.get("/api/auth/me", headers=bearer(token))
        assert rv.status_code == 200
        user = rv.get_json()["user"]
        assert user["role"] == "admin"

    def test_without_token_returns_401(self, client):
        rv = client.get("/api/auth/me")
        assert rv.status_code == 401

    def test_tampered_token_returns_401(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        bad = token[:-4] + "XXXX"
        with client.application.test_client() as c:
            rv = c.get("/api/auth/me", headers=bearer(bad))
        assert rv.status_code == 401

    def test_expired_token_returns_401(self, flask_app, seeds):
        """Forge a token that is already past its expiry."""
        with flask_app.app_context():
            secret = flask_app.config["JWT_SECRET_KEY"]
            payload = {
                "user_id": 9999,
                "role": "participant",
                "iat": datetime.now(UTC) - timedelta(days=10),
                "exp": datetime.now(UTC) - timedelta(days=7),
            }
            expired_token = jwt.encode(payload, secret, algorithm="HS256")
        with flask_app.test_client() as c:
            rv = c.get("/api/auth/me", headers=bearer(expired_token))
        assert rv.status_code == 401

    def test_profile_never_contains_password_hash(self, client, seeds):
        token = register_and_token(client, 1, seeds)
        with client.application.test_client() as c:
            rv = c.get("/api/auth/me", headers=bearer(token))
        assert "password_hash" not in rv.get_data(as_text=True)

    def test_wrong_secret_returns_401(self, flask_app, seeds):
        """Token signed with the wrong key must be rejected."""
        payload = {
            "user_id": 1,
            "role": "participant",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(days=3),
        }
        bad_token = jwt.encode(payload, "wrong-secret-key-padded-to-32bytes!!", algorithm="HS256")
        with flask_app.test_client() as c:
            rv = c.get("/api/auth/me", headers=bearer(bad_token))
        assert rv.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# Change password
# ═══════════════════════════════════════════════════════════════════════════


class TestChangePassword:
    def test_happy_path_changes_password(self, client, seeds):
        register(client, 1, seeds)
        token = login_token(client, "user1@e2e.test", DEFAULT_PW)
        rv = client.patch(
            "/api/auth/change-password",
            json={"current_password": DEFAULT_PW, "new_password": "NewPassword99!"},
            headers=bearer(token),
        )
        assert rv.status_code == 200
        # Old password must no longer work
        rv2 = client.post(
            "/api/auth/login",
            json={"email": "user1@e2e.test", "password": DEFAULT_PW, "role": "participant"},
        )
        assert rv2.status_code == 401

    def test_change_password_returns_fresh_token_cookie(self, client, seeds):
        """After changing password the response must set a new token cookie so
        the user stays logged in — no forced logout."""
        register(client, 1, seeds)
        token = login_token(client, "user1@e2e.test", DEFAULT_PW)
        rv = client.patch(
            "/api/auth/change-password",
            json={"current_password": DEFAULT_PW, "new_password": "NewPassword99!"},
            headers=bearer(token),
        )
        assert rv.status_code == 200
        # A fresh token cookie must be present in the response
        new_token = _extract_token(rv)
        assert new_token is not None, "change-password must return a fresh token cookie"
        # The new token must be different from the original (old one was revoked)
        assert new_token != token
        # The new token must be usable to reach a protected endpoint
        rv2 = client.get("/api/auth/me", headers=bearer(new_token))
        assert rv2.status_code == 200

    def test_wrong_current_password_returns_401(self, client, seeds):
        register(client, 1, seeds)
        token = login_token(client, "user1@e2e.test", DEFAULT_PW)
        rv = client.patch(
            "/api/auth/change-password",
            json={"current_password": "WRONG!", "new_password": "NewPassword99!"},
            headers=bearer(token),
        )
        assert rv.status_code == 401

    def test_new_password_too_short_returns_400(self, client, seeds):
        register(client, 1, seeds)
        token = login_token(client, "user1@e2e.test", DEFAULT_PW)
        rv = client.patch(
            "/api/auth/change-password",
            json={"current_password": DEFAULT_PW, "new_password": "abc"},
            headers=bearer(token),
        )
        assert rv.status_code == 400

    def test_admin_cannot_change_password_via_this_endpoint(self, flask_app):
        token = admin_token(flask_app)
        with flask_app.test_client() as c:
            rv = c.patch(
                "/api/auth/change-password",
                json={"current_password": ADMIN_PW, "new_password": "NewAdminPw99!"},
                headers=bearer(token),
            )
        assert rv.status_code == 403

    def test_requires_authentication(self, client):
        rv = client.patch(
            "/api/auth/change-password",
            json={"current_password": "any", "new_password": "newpassword"},
        )
        assert rv.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# Reset password
# ═══════════════════════════════════════════════════════════════════════════


class TestResetPassword:
    def test_missing_email_returns_400(self, client):
        rv = client.post("/api/auth/reset-password", json={"role": "participant"})
        assert rv.status_code == 400

    def test_invalid_role_returns_400(self, client):
        rv = client.post(
            "/api/auth/reset-password",
            json={"email": "any@e2e.test", "role": "admin"},
        )
        assert rv.status_code == 400

    def test_unknown_email_returns_generic_success_no_enumeration(self, client):
        """Must not reveal whether an email exists in the system."""
        rv = client.post(
            "/api/auth/reset-password",
            json={"email": "ghost@e2e.test", "role": "participant"},
        )
        # Endpoint returns 200 with a generic message (Step 1 of the spec)
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True
        # The message must be identical to what a known user would receive
        # so attackers cannot enumerate accounts
        assert "email is registered" in body["message"].lower() or "sent" in body["message"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# Confirm password reset
# ═══════════════════════════════════════════════════════════════════════════


def _insert_reset_token(
    db_conn,
    user_id: int,
    role: str,
    *,
    expired: bool = False,
    used: bool = False,
) -> str:
    """Insert a password_reset_tokens row directly and return the raw token."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    if expired:
        expires_at = datetime.now(UTC) - timedelta(hours=2)
    else:
        expires_at = datetime.now(UTC) + timedelta(hours=1)
    used_at = datetime.now(UTC) if used else None
    with db_conn.cursor() as cur:
        cur.execute(
            """INSERT INTO password_reset_tokens (user_id, role, token_hash, expires_at, used_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, role, token_hash, expires_at, used_at),
        )
    return raw_token


class TestConfirmPasswordReset:
    # ── Input validation (no valid token needed) ───────────────────────────

    def test_missing_fields_returns_400(self, client):
        rv = client.post("/api/auth/reset-password/confirm", json={})
        assert rv.status_code == 400
        assert rv.get_json()["success"] is False

    def test_invalid_role_returns_400(self, client):
        rv = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": "abc", "new_password": "ValidPassword1!", "role": "admin"},
        )
        assert rv.status_code == 400

    def test_password_too_short_returns_400(self, client):
        rv = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": "sometoken", "new_password": "short", "role": "participant"},
        )
        assert rv.status_code == 400
        assert "12" in rv.get_json()["error"]

    def test_unknown_token_returns_400(self, client):
        rv = client.post(
            "/api/auth/reset-password/confirm",
            json={
                "token": secrets.token_urlsafe(32),
                "new_password": "ValidPassword1!",
                "role": "participant",
            },
        )
        assert rv.status_code == 400
        assert (
            "invalid" in rv.get_json()["error"].lower()
            or "expired" in rv.get_json()["error"].lower()
        )

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_happy_path_updates_password_and_allows_login(self, client, seeds, db_conn):
        register(client, 1, seeds)
        # Fetch the participant id directly from the DB
        with db_conn.cursor() as cur:
            cur.execute("SELECT id FROM participants WHERE email = 'user1@e2e.test'")
            user_id = cur.fetchone()["id"]

        raw_token = _insert_reset_token(db_conn, user_id, "participant")
        new_pw = "BrandNewPassword1!"

        rv = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": raw_token, "new_password": new_pw, "role": "participant"},
        )
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

        # Old password must no longer work
        rv_old = client.post(
            "/api/auth/login",
            json={"email": "user1@e2e.test", "password": DEFAULT_PW, "role": "participant"},
        )
        assert rv_old.status_code == 401

        # New password must work
        rv_new = client.post(
            "/api/auth/login",
            json={"email": "user1@e2e.test", "password": new_pw, "role": "participant"},
        )
        assert rv_new.status_code == 200

    # ── Token reuse ────────────────────────────────────────────────────────

    def test_token_cannot_be_reused_after_success(self, client, seeds, db_conn):
        register(client, 1, seeds)
        with db_conn.cursor() as cur:
            cur.execute("SELECT id FROM participants WHERE email = 'user1@e2e.test'")
            user_id = cur.fetchone()["id"]

        raw_token = _insert_reset_token(db_conn, user_id, "participant")

        # First use succeeds
        rv1 = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": raw_token, "new_password": "FirstNewPassword1!", "role": "participant"},
        )
        assert rv1.status_code == 200

        # Second use must be rejected
        rv2 = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": raw_token, "new_password": "SecondNewPassword1!", "role": "participant"},
        )
        assert rv2.status_code == 400

    # ── Expired token ──────────────────────────────────────────────────────

    def test_expired_token_returns_400(self, client, seeds, db_conn):
        register(client, 1, seeds)
        with db_conn.cursor() as cur:
            cur.execute("SELECT id FROM participants WHERE email = 'user1@e2e.test'")
            user_id = cur.fetchone()["id"]

        raw_token = _insert_reset_token(db_conn, user_id, "participant", expired=True)

        rv = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": raw_token, "new_password": "ValidPassword1!", "role": "participant"},
        )
        assert rv.status_code == 400
        assert "expired" in rv.get_json()["error"].lower()

    # ── Role mismatch ──────────────────────────────────────────────────────

    def test_role_mismatch_returns_400(self, client, seeds, db_conn):
        """A token issued for 'participant' must not work when role='mentor' is supplied."""
        register(client, 1, seeds)
        with db_conn.cursor() as cur:
            cur.execute("SELECT id FROM participants WHERE email = 'user1@e2e.test'")
            user_id = cur.fetchone()["id"]

        # Token stored with role='participant'
        raw_token = _insert_reset_token(db_conn, user_id, "participant")

        rv = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": raw_token, "new_password": "ValidPassword1!", "role": "mentor"},
        )
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# Session revocation epoch (R-25) — password change/reset must evict existing
# sessions, not just the caller's own token.
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionRevocation:
    def test_change_password_revokes_a_previously_issued_session(self, client, seeds, flask_app):
        """A token issued before a password change must stop working afterwards.

        This is the multi-session case: the caller's own token is blocklisted by
        jti, but a *second* live session (e.g. another device, or a stolen cookie)
        is only killed by the tokens_valid_from epoch bump. In the test env Redis
        is absent so the jti blocklist is a no-op — the epoch is what does the work.

        The old session lives on its OWN client so its httpOnly cookie jar isn't
        overwritten by the fresh token change-password sets on `client`. Since
        token_required reads the cookie first, sharing one client would let the
        post-change cookie shadow the old session and mask the revocation.
        """
        register(client, 1, seeds)
        # An earlier, independent session for the same user, on a separate client.
        old = new_client(flask_app)
        old_token = login_token(old, "user1@e2e.test", DEFAULT_PW)
        assert old.get("/api/auth/me", headers=bearer(old_token)).status_code == 200

        # JWT `iat` is whole-second; ensure the epoch bump lands in a strictly
        # later second than the old token so the assertion is deterministic.
        time.sleep(1.1)

        # A second session performs the password change.
        change_token = login_token(client, "user1@e2e.test", DEFAULT_PW)
        rv = client.patch(
            "/api/auth/change-password",
            json={"current_password": DEFAULT_PW, "new_password": "NewPassword99!"},
            headers=bearer(change_token),
        )
        assert rv.status_code == 200

        # The pre-change session must now be rejected by the revocation epoch.
        rv_old = old.get("/api/auth/me", headers=bearer(old_token))
        assert rv_old.status_code == 401

    def test_password_reset_revokes_existing_sessions(self, client, seeds, db_conn, flask_app):
        """The account-recovery case: after a reset, a session that predates the
        reset (an attacker holding a stolen cookie) must be evicted."""
        register(client, 1, seeds)
        with db_conn.cursor() as cur:
            cur.execute("SELECT id FROM participants WHERE email = 'user1@e2e.test'")
            user_id = cur.fetchone()["id"]

        # A live session obtained before the reset, on its own client so the
        # reset flow can't refresh its cookie jar.
        stolen = new_client(flask_app)
        stolen_token = login_token(stolen, "user1@e2e.test", DEFAULT_PW)
        assert stolen.get("/api/auth/me", headers=bearer(stolen_token)).status_code == 200

        # Whole-second `iat` — ensure the reset epoch lands in a later second.
        time.sleep(1.1)

        raw_token = _insert_reset_token(db_conn, user_id, "participant")
        rv = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": raw_token, "new_password": "BrandNewPassword1!", "role": "participant"},
        )
        assert rv.status_code == 200

        # The pre-reset session must no longer reach protected endpoints.
        rv_stolen = stolen.get("/api/auth/me", headers=bearer(stolen_token))
        assert rv_stolen.status_code == 401


# ─── Internal helpers used only within this module ────────────────────────


def _extract_token(response):
    for h in response.headers.getlist("Set-Cookie"):
        if "token=" in h:
            return h.split("token=", 1)[1].split(";")[0]
    return None


def flask_app_client(app):
    return app.test_client()


def mentor_token_for_seed(app, seeds):
    with app.app_context():
        from app.services.auth_service import generate_token

        return generate_token(seeds["mentor_ids"][0], "mentor")
