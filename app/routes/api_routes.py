"""API routes — rankings, regulations, admin matching, lookup data, and bug reports"""

import logging

from flask import current_app, jsonify, request

from app import limiter
from app.database import execute_insert, execute_query
from app.routes import api_bp
from app.services import (
    matching_service,
    mentor_selection_service,
    ranking_service,
    regulations_service,
)
from app.services.team_service import TeamService
from app.utils.auth_decorators import admin_required

logger = logging.getLogger(__name__)


# ── Lookup-data endpoints (universities & specialties) ─────────────


@api_bp.route("/universities", methods=["GET"])
def get_universities():
    """Return seed universities only (curated list)"""
    from flask import current_app

    try:
        rows = execute_query(
            current_app,
            "SELECT id, name, city, country FROM universities WHERE is_seed = TRUE ORDER BY id",
            fetch_all=True,
        )
        return jsonify({"success": True, "universities": [dict(r) for r in rows]}), 200
    except Exception as e:
        logger.error(f"Error fetching universities: {e}")
        return jsonify({"success": False, "error": "Failed to fetch universities"}), 500


@api_bp.route("/specialties", methods=["GET"])
def get_specialties():
    """Return seed specialties only (curated list)"""
    from flask import current_app

    try:
        rows = execute_query(
            current_app,
            "SELECT id, name FROM specialties WHERE is_seed = TRUE ORDER BY id",
            fetch_all=True,
        )
        return jsonify({"success": True, "specialties": [dict(r) for r in rows]}), 200
    except Exception as e:
        logger.error(f"Error fetching specialties: {e}")
        return jsonify({"success": False, "error": "Failed to fetch specialties"}), 500


@api_bp.route("/universities", methods=["POST"])
def create_university():
    """Create a user-submitted university (is_seed = FALSE). Returns existing ID if name already taken."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    city = (data.get("city") or "").strip()
    country = (data.get("country") or "").strip()

    if not name or not city or not country:
        return jsonify({"success": False, "error": "Name, city, and country are required"}), 400

    from flask import current_app

    # Check for existing university with the same name
    existing = execute_query(
        current_app,
        "SELECT id FROM universities WHERE name = %s",
        (name,),
        fetch_one=True,
    )
    if existing:
        return jsonify({"success": True, "id": existing["id"], "existing": True}), 200

    try:
        uid = execute_insert(
            current_app,
            "INSERT INTO universities (name, city, country, is_seed) VALUES (%s, %s, %s, FALSE) RETURNING id",
            (name, city, country),
        )
        return jsonify({"success": True, "id": uid}), 201
    except Exception as e:
        logger.error(f"Error creating university: {e}")
        return jsonify({"success": False, "error": "Failed to create university"}), 500


@api_bp.route("/specialties", methods=["POST"])
def create_specialty():
    """Create a user-submitted specialty (is_seed = FALSE). Returns existing ID if name already taken."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()

    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400

    from flask import current_app

    existing = execute_query(
        current_app,
        "SELECT id FROM specialties WHERE name = %s",
        (name,),
        fetch_one=True,
    )
    if existing:
        return jsonify({"success": True, "id": existing["id"], "existing": True}), 200

    try:
        sid = execute_insert(
            current_app,
            "INSERT INTO specialties (name, description, is_seed) VALUES (%s, NULL, FALSE) RETURNING id",
            (name,),
        )
        return jsonify({"success": True, "id": sid}), 201
    except Exception as e:
        logger.error(f"Error creating specialty: {e}")
        return jsonify({"success": False, "error": "Failed to create specialty"}), 500


# ── Rankings & Regulations ─────────────────────────────────────────


@api_bp.route("/ranking", methods=["GET"])
def get_ranking():
    """Get rankings sorted by points"""
    try:
        rankings = ranking_service.get_rankings()
        return jsonify({"success": True, "rankings": rankings}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/regulations", methods=["GET"])
def get_regulations():
    """Get regulations"""
    try:
        regulations = regulations_service.get_regulations()
        return jsonify({"success": True, "regulations": regulations}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Admin matching endpoints ───────────────────────────────────────


@api_bp.route("/admin/preference-status", methods=["GET"])
@admin_required
def preference_status():
    """Get which teams/mentors have submitted preferences"""
    status = mentor_selection_service.get_preference_submission_status()
    return jsonify({"success": True, **status}), 200


@api_bp.route("/admin/run-matching", methods=["POST"])
@admin_required
def run_matching():
    """Trigger Gale-Shapley matching algorithm"""
    success, message, assignments = matching_service.run_gale_shapley()
    if not success:
        return jsonify({"success": False, "error": message}), 400

    try:
        matching_service.save_matching_results(assignments)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save results: {e}"}), 500

    # Format results for response
    results = {}
    for team_id, mentor_id in assignments:
        results.setdefault(team_id, []).append(mentor_id)

    return jsonify(
        {
            "success": True,
            "message": message,
            "assignment_count": len(assignments),
            "assignments": results,
        }
    ), 200


@api_bp.route("/admin/matching-results", methods=["GET"])
@admin_required
def get_matching_results():
    """Get current matching results"""
    results = matching_service.get_matching_results()
    return jsonify({"success": True, "results": [dict(r) for r in results]}), 200


# ── Admin team registration endpoints ──────────────────────────────


@api_bp.route("/admin/teams/registration-status", methods=["GET"])
@admin_required
def team_registration_status():
    """Return all teams grouped by registration state"""
    from app.services.team_service import MAX_REGISTERED_TEAMS

    teams = TeamService.get_all_teams()
    teams_list = [dict(t) for t in teams]
    for t in teams_list:
        t.pop("password_hash", None)
        t.pop("join_code", None)

    registered = [t for t in teams_list if t.get("is_registered")]
    queued = sorted(
        [t for t in teams_list if t.get("queue_position") is not None],
        key=lambda t: t["queue_position"],
    )
    unregistered = [
        t
        for t in teams_list
        if not t.get("is_registered")
        and t.get("queue_position") is None
        and t.get("status") == "active"
    ]

    return jsonify(
        {
            "success": True,
            "registered_count": len(registered),
            "max_registered": MAX_REGISTERED_TEAMS,
            "queue_count": len(queued),
            "registered_teams": registered,
            "queued_teams": queued,
            "unregistered_teams": unregistered,
        }
    ), 200


@api_bp.route("/admin/teams/<int:team_id>/register", methods=["POST"])
@admin_required
def admin_register_team(team_id):
    """Admin manually registers a team"""
    success, message = TeamService.admin_register_team(team_id)
    if success:
        return jsonify({"success": True, "message": message}), 200
    return jsonify({"success": False, "error": message}), 400


@api_bp.route("/admin/teams/<int:team_id>/unregister", methods=["POST"])
@admin_required
def admin_unregister_team(team_id):
    """Admin manually unregisters a team"""
    success, message = TeamService.admin_unregister_team(team_id)
    if success:
        return jsonify({"success": True, "message": message}), 200
    return jsonify({"success": False, "error": message}), 400


# ── Bug Report ─────────────────────────────────────────────────────


@api_bp.route("/bug-report", methods=["POST"])
@limiter.limit("10 per minute")
def submit_bug_report():
    """Accept a bug report and post it to the Discord bug-report channel.

    Auth is optional — if a valid JWT is present the reporter's name/email are
    looked up from the DB and included in the Discord embed.  Anonymous
    submissions are accepted too.

    Returns 202 immediately; the webhook POST runs asynchronously from a
    bounded thread pool so the endpoint never blocks on the Discord call and
    can handle 500+ concurrent submissions without issue.
    """
    from app.services.bug_report_service import submit_bug_report_async

    data = request.get_json(silent=True) or {}

    # Clamp fields to reasonable lengths to prevent oversized payloads
    what_did = (data.get("what_did") or "").strip()[:2000]
    what_happened = (data.get("what_happened") or "").strip()[:2000]
    page_url = (data.get("page") or "").strip()[:500]

    if not what_did and not what_happened:
        return jsonify({"success": False, "error": "Please describe the issue."}), 400

    # Attempt to resolve reporter identity from an optional JWT
    reporter_name = "Anonymous"
    reporter_email = "(not provided)"
    reporter_role = "unknown"

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from app.services.auth_service import decode_token

            payload = decode_token(token)
            user_id = payload.get("user_id")
            role = payload.get("role", "unknown")
            reporter_role = role

            if role == "participant":
                row = execute_query(
                    current_app,
                    "SELECT first_name, last_name, email FROM participants WHERE id = %s",
                    (user_id,),
                    fetch_one=True,
                )
                if row:
                    reporter_name = f"{row['first_name']} {row['last_name']}"
                    reporter_email = row["email"]
            elif role == "mentor":
                row = execute_query(
                    current_app,
                    "SELECT name, email FROM mentors WHERE id = %s",
                    (user_id,),
                    fetch_one=True,
                )
                if row:
                    reporter_name = row["name"]
                    reporter_email = row["email"]
            elif role == "admin":
                reporter_name = "Admin"
                reporter_email = current_app.config.get("ADMIN_EMAIL", "admin")
        except Exception:
            pass  # Non-fatal — fall back to anonymous

    webhook_url = current_app.config.get("DISCORD_BUG_WEBHOOK_URL", "")

    submit_bug_report_async(
        webhook_url,
        reporter_name=reporter_name,
        reporter_email=reporter_email,
        reporter_role=reporter_role,
        page_url=page_url or "(unknown)",
        what_did=what_did or "(not specified)",
        what_happened=what_happened or "(not specified)",
    )

    logger.info(
        "Bug report queued for delivery (reporter=%s, page=%s)",
        reporter_email,
        page_url,
    )
    return jsonify({"success": True, "message": "Bug report submitted — thank you!"}), 202
