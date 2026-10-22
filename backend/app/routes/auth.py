"""Authentication routes — JWT-based individual auth for participants, mentors, and admin"""

import hashlib
import hmac
import logging
import os
import secrets
import threading
from datetime import UTC, datetime, timedelta

import psycopg2
from flask import current_app, g, jsonify, make_response, request

from app import limiter
from app.database import execute_query, get_db_cursor
from app.routes import auth_bp
from app.services.auth_service import generate_token, hash_password, verify_password
from app.services.redis_client import redis_del
from app.utils.auth_decorators import participant_required, token_required

logger = logging.getLogger(__name__)

_COOKIE_MAX_AGE = 3 * 24 * 60 * 60  # 3 days, matches JWT expiry
# Bcrypt hash generated once at startup and used as a timing equaliser when
# no account exists, so response time is indistinguishable from a wrong-password attempt.
_DUMMY_HASH: str = hash_password("__timing_dummy__")
_VERIFICATION_TTL = timedelta(hours=24)


def _fetch_user_profile(app, user_id: int, role: str, strict: bool = False) -> dict | None:
    """Return a user dict suitable for embedding in API responses.

    Mirrors the query used by /api/auth/me so the frontend receives the same
    shape whether it calls login/register or refreshes the page.

    When *strict* is True, a missing profile row yields None so the caller can
    404 (used by /api/auth/me). When False (default, used by register/login),
    a missing row falls back to {"role": role}.
    """
    if role == "admin":
        return {"role": "admin"}
    if role == "participant":
        row = execute_query(
            app,
            """SELECT p.id, p.first_name, p.last_name, p.email, p.phone_number,
                      p.faculty_number, p.course, p.is_captain, p.team_id, p.status,
                      p.email_verified,
                      s.name AS specialty, u.name AS university, t.team_name, t.join_code
               FROM participants p
               LEFT JOIN specialties s ON p.specialty_id = s.id
               LEFT JOIN universities u ON p.university_id = u.id
               LEFT JOIN teams t ON p.team_id = t.id
               WHERE p.id = %s""",
            (user_id,),
            fetch_one=True,
        )
    else:
        row = execute_query(
            app,
            """SELECT id, first_name, last_name, email, phone_number,
                      company_name, bio, status
               FROM mentors WHERE id = %s""",
            (user_id,),
            fetch_one=True,
        )
    if not row:
        return None if strict else {"role": role}
    result = dict(row)
    result["role"] = role
    return result


def _issue_verification_link(participant_id: int) -> str:
    """Replace the participant's unused verification tokens with a fresh one.

    Only the SHA-256 hash is stored; the returned link carries the raw token.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    with get_db_cursor() as cursor:
        cursor.execute(
            "DELETE FROM email_verification_tokens WHERE participant_id = %s AND used_at IS NULL",
            (participant_id,),
        )
        cursor.execute(
            """INSERT INTO email_verification_tokens (participant_id, token_hash, expires_at)
               VALUES (%s, %s, %s)""",
            (participant_id, token_hash, datetime.now(UTC) + _VERIFICATION_TTL),
        )
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
    return f"{frontend_origin}/verify-email?token={raw_token}"


def _is_secure() -> bool:
    """Return True when the cookie Secure flag should be set (production only)."""
    return os.environ.get("FLASK_ENV", "development") == "production"


def _set_auth_cookies(response, token: str) -> None:
    """Attach httpOnly token cookie to *response* in-place.

    M7: The role cookie has been removed.  Role is derived exclusively from
    /api/auth/me so JavaScript can never read or manipulate it.
    """
    secure = _is_secure()
    response.set_cookie(
        "token",
        token,
        httponly=True,
        samesite="Lax",
        path="/",
        max_age=_COOKIE_MAX_AGE,
        secure=secure,
    )


@auth_bp.route("/api/auth/register", methods=["POST"])
@limiter.limit("10 per minute")
def register_participant():
    """Register a new participant and return JWT.

    Optimised for concurrent load:
    - bcrypt hash runs BEFORE any DB connection is acquired
    - uniqueness checks + insert happen in a single pooled transaction
    - DB UNIQUE constraints are the real guard against races
    """
    if not current_app.config.get("REGISTRATION_OPEN"):
        return jsonify({"success": False, "error": "Registration is closed"}), 403
    data = request.get_json(silent=True) or {}
    required = [
        "first_name",
        "last_name",
        "email",
        "password",
        "phone_number",
        "faculty_number",
        "course",
        "specialty_id",
        "university_id",
    ]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"success": False, "error": f"Missing fields: {', '.join(missing)}"}), 400

    # C7: Reject HTML injection characters in name fields at the backend boundary
    from app.utils import validate_email, validate_name_field

    for field_key, label in (("first_name", "First name"), ("last_name", "Last name")):
        ok, result = validate_name_field(data[field_key], label)
        if not ok:
            return jsonify({"success": False, "error": result}), 400

    email = data["email"].strip().lower()
    if not validate_email(email):
        return jsonify({"success": False, "error": "Invalid email address"}), 400
    fac = data["faculty_number"].strip()

    course = data["course"].strip()
    valid_courses = {
        "Bachelor 1st Year",
        "Bachelor 2nd Year",
        "Bachelor 3rd Year",
        "Bachelor 4th Year",
        "Masters 1st Year",
        "Masters 2nd Year",
        "Masters 3rd Year",
        "Masters 4th Year",
        "Masters 5th Year",
        "Masters 6th Year",
    }
    if course not in valid_courses:
        return jsonify({"success": False, "error": "Invalid course selection"}), 400

    # M4: Enforce minimum password length
    if len(data["password"]) < 12:
        return jsonify({"success": False, "error": "Password must be at least 12 characters"}), 400

    # CPU-heavy work first — no DB connection held, doesn't block the pool
    pw_hash = hash_password(data["password"])

    try:
        with get_db_cursor() as cursor:
            # Single query checks both uniqueness constraints at once
            cursor.execute(
                """SELECT
                       EXISTS(SELECT 1 FROM participants WHERE email = %s)          AS email_taken,
                       EXISTS(SELECT 1 FROM participants WHERE faculty_number = %s) AS fac_taken""",
                (email, fac),
            )
            check = cursor.fetchone()
            if check["email_taken"] or check["fac_taken"]:
                # M2: Single generic message — don't reveal which field is taken
                return jsonify(
                    {"success": False, "error": "An account with these details already exists."}
                ), 409

            # Insert in the same transaction — DB UNIQUE constraints guard against races
            cursor.execute(
                """INSERT INTO participants
                       (first_name, last_name, email, phone_number, faculty_number,
                        course, specialty_id, university_id, password_hash, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
                   RETURNING id""",
                (
                    data["first_name"].strip(),
                    data["last_name"].strip(),
                    email,
                    data["phone_number"].strip(),
                    fac,
                    course,
                    int(data["specialty_id"]),
                    int(data["university_id"]),
                    pw_hash,
                ),
            )
            pid = cursor.fetchone()["id"]

    except psycopg2.IntegrityError:
        # M2: Generic message regardless of which field caused the conflict
        return jsonify(
            {"success": False, "error": "An account with these details already exists."}
        ), 409
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({"success": False, "error": "Registration failed"}), 500

    # The account exists either way; a failed send is recoverable via
    # /api/auth/resend-verification, so it must never fail registration.
    try:
        from app.services.email_service import send_verification_email

        verify_url = _issue_verification_link(pid)
        threading.Thread(
            target=send_verification_email,
            args=(dict(current_app.config), email, verify_url),
            daemon=True,
        ).start()
    except Exception as e:
        logger.error("Could not issue verification email for participant %s: %s", pid, e)

    token = generate_token(pid, "participant")
    user_profile = _fetch_user_profile(current_app, pid, "participant")
    resp = make_response(
        jsonify({"success": True, "user_id": pid, "role": "participant", "user": user_profile}),
        201,
    )
    _set_auth_cookies(resp, token)
    return resp


@auth_bp.route("/api/auth/login", methods=["POST"])
@limiter.limit("15 per minute")
def login():
    """Login for participants, mentors, or admin. Returns JWT.

    Optimised: DB connection is released BEFORE bcrypt.checkpw runs (~300ms CPU).
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")
    role = (data.get("role") or "participant").strip().lower()

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required"}), 400

    # Admin login — C1: compare against bcrypt hash, never plaintext
    if role == "admin":
        admin_email = current_app.config.get("ADMIN_EMAIL", "")
        admin_password_hash = current_app.config.get("ADMIN_PASSWORD_HASH") or ""
        if not admin_password_hash:
            logger.error("ADMIN_PASSWORD_HASH is not configured — admin login disabled")
            return jsonify({"success": False, "error": "Admin login not configured"}), 503
        # Timing-safe email comparison, then bcrypt verify for password
        if hmac.compare_digest(email.encode(), admin_email.encode()) and verify_password(
            password, admin_password_hash
        ):
            token = generate_token(0, "admin")
            resp = make_response(
                jsonify(
                    {"success": True, "user_id": 0, "role": "admin", "user": {"role": "admin"}}
                ),
                200,
            )
            _set_auth_cookies(resp, token)
            return resp
        return jsonify({"success": False, "error": "Invalid admin credentials"}), 401

    if role not in ("participant", "mentor"):
        return jsonify({"success": False, "error": "Invalid role"}), 400

    # Fetch hash from DB then RELEASE the connection before the expensive bcrypt check
    # Use explicit branches instead of f-string table interpolation to prevent SQL injection.
    if role == "participant":
        _login_query = (
            "SELECT id, password_hash FROM participants WHERE email = %s AND status = 'active'"
        )
    else:
        _login_query = (
            "SELECT id, password_hash FROM mentors WHERE email = %s AND status = 'active'"
        )
    user = execute_query(
        current_app,
        _login_query,
        (email,),
        fetch_one=True,
    )

    # M8: Run bcrypt even when no user found to prevent timing-based enumeration
    stored_hash = user["password_hash"] if (user and user.get("password_hash")) else _DUMMY_HASH
    password_valid = verify_password(password, stored_hash)

    if not user or not user.get("password_hash") or not password_valid:
        return jsonify({"success": False, "error": "Invalid email or password"}), 401

    token = generate_token(user["id"], role)
    user_profile = _fetch_user_profile(current_app, user["id"], role)
    resp = make_response(
        jsonify({"success": True, "user_id": user["id"], "role": role, "user": user_profile}),
        200,
    )
    _set_auth_cookies(resp, token)
    return resp


@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    """Clear auth cookies and revoke the JWT so it can't be replayed (H1)."""
    # H1: Read and revoke the token before clearing the cookie
    token = request.cookies.get("token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if token:
        try:
            from app.services.auth_service import decode_token as _decode

            payload = _decode(token)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                remaining = int(exp - datetime.now(UTC).timestamp())
                if remaining > 0:
                    from app.services.token_blocklist import revoke_token

                    revoke_token(jti, remaining)
        except Exception:
            pass  # Expired / invalid token — nothing to revoke

    resp = make_response(jsonify({"success": True}), 200)
    resp.delete_cookie("token", path="/", samesite="Lax")
    return resp


@auth_bp.route("/api/auth/me", methods=["GET"])
@token_required
def get_me():
    """Return current user profile from JWT."""
    user = g.current_user
    if user["role"] == "admin":
        return jsonify({"success": True, "user": {"role": "admin"}}), 200

    profile = _fetch_user_profile(current_app, user["user_id"], user["role"], strict=True)
    if profile is None:
        return jsonify({"success": False, "error": "User not found"}), 404

    return jsonify({"success": True, "user": profile}), 200


@auth_bp.route("/api/auth/change-password", methods=["PATCH"])
@limiter.limit("10 per minute")
@token_required
def change_password():
    """Change the current user's password. Requires current password verification."""
    user = g.current_user
    if user["role"] == "admin":
        return jsonify({"success": False, "error": "Admin password cannot be changed here"}), 403

    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")

    if not current_password or not new_password:
        return jsonify(
            {"success": False, "error": "Current password and new password are required"}
        ), 400

    if len(new_password) < 12:
        return jsonify(
            {"success": False, "error": "New password must be at least 12 characters"}
        ), 400

    if user["role"] == "participant":
        _hash_select_query = "SELECT password_hash FROM participants WHERE id = %s"
        _hash_update_query = (
            "UPDATE participants SET password_hash = %s, tokens_valid_from = %s WHERE id = %s"
        )
    else:
        _hash_select_query = "SELECT password_hash FROM mentors WHERE id = %s"
        _hash_update_query = (
            "UPDATE mentors SET password_hash = %s, tokens_valid_from = %s WHERE id = %s"
        )
    row = execute_query(
        current_app,
        _hash_select_query,
        (user["user_id"],),
        fetch_one=True,
    )

    if not row or not verify_password(current_password, row["password_hash"]):
        return jsonify({"success": False, "error": "Current password is incorrect"}), 401

    new_hash = hash_password(new_password)
    # R-25: Bump the revocation epoch so every OTHER active session for this user
    # is invalidated (the fresh token issued below is minted after this, so its
    # `iat` is >= the epoch and it survives). The epoch is stamped with the app
    # clock — the SAME source as the JWT `iat` — so token_required's comparison is
    # immune to app/DB clock skew (a NOW() DB clock could disagree by seconds).
    # The per-jti blocklist below still covers the caller's current token.
    execute_query(
        current_app,
        _hash_update_query,
        (new_hash, datetime.now(UTC), user["user_id"]),
    )

    # R-25: Drop the cached epoch so the bumped tokens_valid_from takes effect on
    # the very next request rather than after the cache TTL lapses.
    redis_del(f"cache:epoch:{user['role']}:{user['user_id']}")

    # H1: Revoke the current token so it can't be replayed after a password change
    jti = g.current_user.get("jti")
    exp = g.current_user.get("exp")
    if jti and exp:
        remaining = int(exp - datetime.now(UTC).timestamp())
        if remaining > 0:
            from app.services.token_blocklist import revoke_token

            revoke_token(jti, remaining)

    # Issue a fresh token so the user stays logged in after the password change.
    # The old token is already blocklisted above — the new one takes its place.
    new_token = generate_token(user["user_id"], user["role"])
    resp = make_response(
        jsonify({"success": True, "message": "Password changed successfully"}), 200
    )
    _set_auth_cookies(resp, new_token)
    return resp


@auth_bp.route("/api/auth/reset-password", methods=["POST"])
@limiter.limit("5 per hour")
def reset_password():
    """C4: Initiate a secure password reset.

    Generates a cryptographically random token, stores its SHA-256 hash in DB,
    and emails ONLY a reset link to the user.  The plaintext token never touches
    the database — only the hash is stored, so a DB breach doesn't hand out
    working reset tokens.

    Returns the same generic success message whether or not the email exists
    to prevent account enumeration.
    """
    from app.services.email_service import send_password_reset_link_email

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    role = (data.get("role") or "").strip().lower()

    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400
    if role not in ("participant", "mentor"):
        return jsonify({"success": False, "error": "Role must be participant or mentor"}), 400

    generic_msg = "If this email is registered, a password reset link has been sent to it."

    # Look up user — same generic response on miss so email existence is never revealed
    if role == "participant":
        _user_query = "SELECT id FROM participants WHERE email = %s AND status = 'active'"
    else:
        _user_query = "SELECT id FROM mentors WHERE email = %s AND status = 'active'"
    user = execute_query(current_app, _user_query, (email,), fetch_one=True)
    if not user:
        return jsonify({"success": True, "message": generic_msg}), 200

    user_id = user["id"]

    # Generate a 32-byte URL-safe token (256-bit entropy — safe with SHA-256 storage)
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    # Invalidate any existing unused tokens for this user before inserting a new one
    with get_db_cursor() as cursor:
        cursor.execute(
            """DELETE FROM password_reset_tokens
               WHERE user_id = %s AND role = %s AND used_at IS NULL""",
            (user_id, role),
        )
        cursor.execute(
            """INSERT INTO password_reset_tokens (user_id, role, token_hash, expires_at)
               VALUES (%s, %s, %s, %s)""",
            (user_id, role, token_hash, expires_at),
        )

    # Build reset URL using FRONTEND_ORIGIN env var
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
    reset_url = f"{frontend_origin}/reset-password?token={raw_token}&role={role}"

    sent = send_password_reset_link_email(dict(current_app.config), email, reset_url, role)
    if not sent:
        # Clean up the token so the user can retry immediately.
        # Return the same generic 200 to avoid leaking whether the account exists.
        execute_query(
            current_app,
            "DELETE FROM password_reset_tokens WHERE token_hash = %s",
            (token_hash,),
        )
        logger.error("Failed to send password reset email to %s (role=%s)", email, role)
        return jsonify({"success": True, "message": generic_msg}), 200

    logger.info("Password reset link sent to %s (role=%s, id=%s)", email, role, user_id)
    return jsonify({"success": True, "message": generic_msg}), 200


@auth_bp.route("/api/auth/reset-password/confirm", methods=["POST"])
@limiter.limit("10 per hour")
def confirm_password_reset():
    """C4: Verify the reset token and set a new password.

    The raw token from the email link is hashed with SHA-256 and looked up in DB.
    On success, the token is marked used and the user's password is updated.
    """
    data = request.get_json(silent=True) or {}
    raw_token = (data.get("token") or "").strip()
    new_password = data.get("new_password", "")
    role = (data.get("role") or "").strip().lower()

    if not raw_token or not new_password or role not in ("participant", "mentor"):
        return jsonify(
            {"success": False, "error": "Token, new_password, and role are required"}
        ), 400

    # M4: enforce minimum password length
    if len(new_password) < 12:
        return jsonify({"success": False, "error": "Password must be at least 12 characters"}), 400

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    # Step 1: Validate token quickly (no lock) — avoid bcrypt cost on invalid tokens.
    with get_db_cursor() as cursor:
        cursor.execute(
            """SELECT id, user_id, expires_at FROM password_reset_tokens
               WHERE token_hash = %s AND role = %s AND used_at IS NULL""",
            (token_hash, role),
        )
        token_row = cursor.fetchone()

    if not token_row:
        return jsonify({"success": False, "error": "Invalid or expired reset token"}), 400

    expires_at = token_row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires_at:
        return jsonify({"success": False, "error": "Reset token has expired"}), 400

    # Step 2: Token is valid — compute bcrypt hash outside any DB transaction.
    new_hash = hash_password(new_password)

    # Step 3: Re-lock and apply updates (re-verify token still unused in case of race).
    with get_db_cursor() as cursor:
        cursor.execute(
            """SELECT id, user_id FROM password_reset_tokens
               WHERE token_hash = %s AND role = %s AND used_at IS NULL
               FOR UPDATE""",
            (token_hash, role),
        )
        token_row = cursor.fetchone()

        if not token_row:
            return jsonify({"success": False, "error": "Invalid or expired reset token"}), 400

        user_id = token_row["user_id"]

        # R-25: stamp the revocation epoch with the app clock (same source as the
        # JWT `iat`) so token_required's comparison is immune to app/DB clock skew.
        epoch = datetime.now(UTC)
        if role == "participant":
            cursor.execute(
                "UPDATE participants SET password_hash = %s, tokens_valid_from = %s WHERE id = %s",
                (new_hash, epoch, user_id),
            )
        else:
            cursor.execute(
                "UPDATE mentors SET password_hash = %s, tokens_valid_from = %s WHERE id = %s",
                (new_hash, epoch, user_id),
            )

        cursor.execute(
            "UPDATE password_reset_tokens SET used_at = NOW() WHERE id = %s",
            (token_row["id"],),
        )

    # R-25: Drop the cached epoch so the bumped tokens_valid_from takes effect on
    # the very next request rather than after the cache TTL lapses.
    redis_del(f"cache:epoch:{role}:{user_id}")

    logger.info("Password reset confirmed for user_id=%s role=%s", user_id, role)
    return jsonify(
        {"success": True, "message": "Password has been reset. You can now log in."}
    ), 200


@auth_bp.route("/api/auth/verify-email", methods=["POST"])
@limiter.limit("20 per hour")
def verify_email():
    """Mark a participant's email verified from the emailed link's token.

    No login needed, so the link works on any device. Tokens are single-use
    and expire after 24 hours.
    """
    data = request.get_json(silent=True) or {}
    raw_token = (data.get("token") or "").strip()
    if not raw_token:
        return jsonify({"success": False, "error": "Verification token is required"}), 400

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    with get_db_cursor() as cursor:
        cursor.execute(
            """SELECT id, participant_id, expires_at FROM email_verification_tokens
               WHERE token_hash = %s AND used_at IS NULL
               FOR UPDATE""",
            (token_hash,),
        )
        token_row = cursor.fetchone()
        if not token_row:
            return jsonify(
                {
                    "success": False,
                    "error": "This verification link is invalid or was already used.",
                }
            ), 400

        expires_at = token_row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if datetime.now(UTC) > expires_at:
            return jsonify({"success": False, "error": "This verification link has expired."}), 400

        cursor.execute(
            "UPDATE participants SET email_verified = TRUE WHERE id = %s",
            (token_row["participant_id"],),
        )
        cursor.execute(
            "UPDATE email_verification_tokens SET used_at = NOW() WHERE id = %s",
            (token_row["id"],),
        )

    logger.info("Email verified for participant %s", token_row["participant_id"])
    return jsonify({"success": True, "message": "Your email address is verified."}), 200


@auth_bp.route("/api/auth/resend-verification", methods=["POST"])
@limiter.limit("3 per hour")
@participant_required
def resend_verification():
    """Send a fresh verification link to the logged-in participant."""
    from app.services.email_service import send_verification_email

    participant_id = g.current_user["user_id"]
    row = execute_query(
        current_app,
        "SELECT email, email_verified FROM participants WHERE id = %s",
        (participant_id,),
        fetch_one=True,
    )
    if not row:
        return jsonify({"success": False, "error": "User not found"}), 404
    if row["email_verified"]:
        return jsonify({"success": False, "error": "Your email address is already verified."}), 400

    verify_url = _issue_verification_link(participant_id)
    if not send_verification_email(dict(current_app.config), row["email"], verify_url):
        return jsonify(
            {"success": False, "error": "Could not send the verification email. Try again later."}
        ), 503

    return jsonify({"success": True, "message": f"Verification link sent to {row['email']}."}), 200
