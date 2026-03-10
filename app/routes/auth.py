"""Authentication routes — JWT-based individual auth for participants, mentors, and admin"""

import logging
import secrets
import string

import psycopg2
from flask import current_app, g, jsonify, render_template, request

from app import limiter
from app.database import execute_query, get_db_cursor
from app.routes import auth_bp
from app.services.auth_service import generate_token, hash_password, verify_password
from app.services.email_service import send_password_reset_email
from app.utils.auth_decorators import token_required

logger = logging.getLogger(__name__)


@auth_bp.route("/login", methods=["GET"])
def login_page():
    """Serve the login page"""
    return render_template("auth/login.html")


@auth_bp.route("/registration", methods=["GET"])
def registration_page():
    """Serve the participant registration form"""
    return render_template("auth/registration.html")


@auth_bp.route("/api/auth/register", methods=["POST"])
@limiter.limit("10 per minute")
def register_participant():
    """Register a new participant and return JWT.

    Optimised for concurrent load:
    - bcrypt hash runs BEFORE any DB connection is acquired
    - uniqueness checks + insert happen in a single pooled transaction
    - DB UNIQUE constraints are the real guard against races
    """
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

    email = data["email"].strip().lower()
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
            if check["email_taken"]:
                return jsonify({"success": False, "error": "Email already registered"}), 409
            if check["fac_taken"]:
                return jsonify(
                    {"success": False, "error": "Faculty number already registered"}
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

    except psycopg2.IntegrityError as e:
        err = str(e).lower()
        if "email" in err:
            return jsonify({"success": False, "error": "Email already registered"}), 409
        if "faculty_number" in err:
            return jsonify({"success": False, "error": "Faculty number already registered"}), 409
        return jsonify({"success": False, "error": "Registration failed (duplicate data)"}), 409
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({"success": False, "error": "Registration failed"}), 500

    token = generate_token(pid, "participant")
    return jsonify({"success": True, "token": token, "user_id": pid, "role": "participant"}), 201


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

    # Admin login — no DB needed
    if role == "admin":
        admin_email = current_app.config.get("ADMIN_EMAIL", "")
        admin_password = current_app.config.get("ADMIN_PASSWORD", "")
        if email == admin_email and password == admin_password:
            token = generate_token(0, "admin")
            return jsonify({"success": True, "token": token, "user_id": 0, "role": "admin"}), 200
        return jsonify({"success": False, "error": "Invalid admin credentials"}), 401

    if role not in ("participant", "mentor"):
        return jsonify({"success": False, "error": "Invalid role"}), 400

    # Fetch hash from DB then RELEASE the connection before the expensive bcrypt check
    table = "participants" if role == "participant" else "mentors"
    user = execute_query(
        current_app,
        f"SELECT id, password_hash FROM {table} WHERE email = %s AND status = 'active'",
        (email,),
        fetch_one=True,
    )

    if not user or not user.get("password_hash"):
        return jsonify({"success": False, "error": "Invalid credentials"}), 401

    # CPU-heavy — no DB connection held
    if not verify_password(password, user["password_hash"]):
        return jsonify({"success": False, "error": "Invalid credentials"}), 401

    token = generate_token(user["id"], role)
    return jsonify({"success": True, "token": token, "user_id": user["id"], "role": role}), 200


@auth_bp.route("/api/auth/me", methods=["GET"])
@token_required
def get_me():
    """Return current user profile from JWT."""
    user = g.current_user
    if user["role"] == "admin":
        return jsonify({"success": True, "user": {"role": "admin"}}), 200

    if user["role"] == "participant":
        profile = execute_query(
            current_app,
            """SELECT p.id, p.first_name, p.last_name, p.email, p.phone_number,
                      p.faculty_number, p.course, p.is_captain, p.team_id, p.status,
                      s.name as specialty, u.name as university, t.team_name, t.join_code
               FROM participants p
               LEFT JOIN specialties s ON p.specialty_id = s.id
               LEFT JOIN universities u ON p.university_id = u.id
               LEFT JOIN teams t ON p.team_id = t.id
               WHERE p.id = %s""",
            (user["user_id"],),
            fetch_one=True,
        )
    else:
        profile = execute_query(
            current_app,
            """SELECT id, first_name, last_name, email, phone_number,
                      company_name, bio, status
               FROM mentors WHERE id = %s""",
            (user["user_id"],),
            fetch_one=True,
        )

    if not profile:
        return jsonify({"success": False, "error": "User not found"}), 404

    profile_dict = dict(profile)
    profile_dict["role"] = user["role"]
    return jsonify({"success": True, "user": profile_dict}), 200


@auth_bp.route("/api/auth/change-password", methods=["PATCH"])
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

    if len(new_password) < 6:
        return jsonify(
            {"success": False, "error": "New password must be at least 6 characters"}
        ), 400

    table = "participants" if user["role"] == "participant" else "mentors"
    row = execute_query(
        current_app,
        f"SELECT password_hash FROM {table} WHERE id = %s",
        (user["user_id"],),
        fetch_one=True,
    )

    if not row or not verify_password(current_password, row["password_hash"]):
        return jsonify({"success": False, "error": "Current password is incorrect"}), 401

    new_hash = hash_password(new_password)
    # Also clear any in-flight password reset for this user.
    # If a reset email is currently mid-send (SMTP window), its final conditional
    # UPDATE checks `password_reset_requested_at IS NOT NULL` — clearing it here
    # makes that UPDATE a no-op, so this manual change is never silently overwritten.
    execute_query(
        current_app,
        f"UPDATE {table} SET password_hash = %s, password_reset_requested_at = NULL WHERE id = %s",
        (new_hash, user["user_id"]),
    )

    return jsonify({"success": True, "message": "Password changed successfully"}), 200


@auth_bp.route("/api/auth/reset-password", methods=["POST"])
@limiter.limit("5 per hour")
def reset_password():
    """Generate a new random password and email it to the user.

    Concurrency model (safe for 500 concurrent users across all Gunicorn workers):

    Step 1 — Atomic claim:
      A single UPDATE atomically marks the user row as "reset in progress" and
      returns the user id. The WHERE clause enforces:
        (a) user exists and is active
        (b) no reset is already in progress (NULL), OR the last claim expired
            (> 60 s ago — handles worker crashes and SMTP hangs)
      Because this is one atomic SQL statement, all workers share a single source
      of truth via PostgreSQL. No application-level locks needed.
      If 0 rows updated: user not found, inactive, or cooldown active — return
      the same generic success message so no email existence is revealed.

    Step 2 — SMTP (no DB connection held):
      Password generation and the SMTP call happen while no DB connection is held,
      keeping the connection pool free for the rest of the app.

    Step 3 — Conditional write:
      The final hash update checks `password_reset_requested_at IS NOT NULL`.
      If the user changed their password manually (via change_password, which
      clears the column), this UPDATE matches 0 rows — the manual change wins
      and is never silently overwritten by a stale in-flight reset.

    Step 4 — SMTP failure release:
      If the email send fails, the claim is released immediately (set to NULL)
      so the user can retry without waiting for the 60-second expiry.
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    role = (data.get("role") or "").strip().lower()

    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400

    if role not in ("participant", "mentor"):
        return jsonify({"success": False, "error": "Role must be participant or mentor"}), 400

    table = "participants" if role == "participant" else "mentors"
    generic_msg = "If this email is registered, a new password has been sent to it."

    # Step 1 — atomically claim the reset slot.
    # Returns the user id only if the claim succeeded (user active + slot free/expired).
    with get_db_cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {table}
               SET password_reset_requested_at = NOW()
             WHERE email = %s
               AND status = 'active'
               AND (
                     password_reset_requested_at IS NULL
                  OR password_reset_requested_at < NOW() - INTERVAL '60 seconds'
               )
             RETURNING id
            """,
            (email,),
        )
        row = cursor.fetchone()

    if not row:
        # User doesn't exist, is inactive, or a reset is already in progress —
        # return generic success so no information is leaked about account existence.
        logger.debug(
            "Reset claim failed for %s/%s (not found, inactive, or cooldown active)", role, email
        )
        return jsonify({"success": True, "message": generic_msg}), 200

    user_id = row["id"]

    # Step 2 — generate outside the DB transaction; no connection is held.
    alphabet = string.ascii_letters + string.digits + string.punctuation
    new_password = "".join(secrets.choice(alphabet) for _ in range(16))
    new_hash = hash_password(new_password)  # CPU-heavy, ~300ms, no connection held

    # Step 3 — send email (SMTP, ~1–10 s, no DB connection held).
    sent = send_password_reset_email(dict(current_app.config), email, new_password, role)

    if not sent:
        # Release the claim so the user can retry immediately instead of waiting 60 s.
        execute_query(
            current_app,
            f"UPDATE {table} SET password_reset_requested_at = NULL WHERE id = %s",
            (user_id,),
        )
        return jsonify(
            {"success": False, "error": "Could not send email. Please try again later."}
        ), 502

    # Step 4 — write the new hash only if we still own the slot.
    # If change_password() ran during the SMTP window it cleared the column to NULL,
    # which causes this UPDATE to match 0 rows — the manual change is preserved.
    with get_db_cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {table}
               SET password_hash = %s,
                   password_reset_requested_at = NULL
             WHERE id = %s
               AND password_reset_requested_at IS NOT NULL
            """,
            (new_hash, user_id),
        )
        updated = cursor.rowcount

    if updated == 0:
        # The user changed their password manually during the SMTP window.
        # Their chosen password is intact; the emailed password is now stale but harmless.
        logger.info(
            "Reset hash NOT written for %s (id=%s, role=%s): manual change took precedence",
            email,
            user_id,
            role,
        )
    else:
        logger.info("Password reset completed for %s (role=%s, id=%s)", email, role, user_id)

    return jsonify({"success": True, "message": generic_msg}), 200
