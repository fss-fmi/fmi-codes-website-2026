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
    """Trigger matching algorithm — always attempts to run, returns warnings for partial data"""
    success, message, assignments, warnings = matching_service.run_gale_shapley()
    if not success:
        return jsonify({"success": False, "error": message}), 400

    try:
        matching_service.save_matching_results(assignments)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save results: {e}"}), 500

    results = {}
    for team_id, mentor_id in assignments:
        results.setdefault(team_id, []).append(mentor_id)

    return jsonify(
        {
            "success": True,
            "message": message,
            "assignment_count": len(assignments),
            "assignments": results,
            "warnings": warnings,
        }
    ), 200


@api_bp.route("/matching-status", methods=["GET"])
def matching_status():
    """Return whether the admin has confirmed the current matching results.

    Accessible to any user (no auth required) so teams and mentors can poll it.
    """
    confirmed = matching_service.get_matching_confirmed()
    return jsonify({"success": True, "confirmed": confirmed}), 200


@api_bp.route("/admin/confirm-matching", methods=["POST"])
@admin_required
def confirm_matching():
    """Admin explicitly confirms that the current matching results are final.

    After this, teams see their assigned mentors and mentors see their assigned
    teams instead of their preferences.
    """
    try:
        matching_service.set_matching_confirmed(True)
        return jsonify({"success": True, "message": "Matching results confirmed as final"}), 200
    except Exception as e:
        logger.error(f"Error confirming matching: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/admin/matching-results", methods=["GET"])
@admin_required
def get_matching_results():
    """Get current matching results"""
    results = matching_service.get_matching_results()
    return jsonify({"success": True, "results": [dict(r) for r in results]}), 200


@api_bp.route("/admin/matching-export", methods=["GET"])
@admin_required
def matching_export():
    """Get matching results grouped by team, with constraint validation, for export"""
    from datetime import datetime, timezone

    rows = [dict(r) for r in matching_service.get_matching_results()]

    teams: dict = {}
    mentor_teams: dict = {}

    for r in rows:
        tid = r["team_id"]
        mid = r["mentor_id"]
        if tid not in teams:
            teams[tid] = {"team_name": r["team_name"], "mentors": []}
        teams[tid]["mentors"].append(
            {
                "mentor_name": r["mentor_name"],
                "company_name": r.get("company_name") or "",
            }
        )
        entry = mentor_teams.setdefault(
            mid, {"mentor_name": r["mentor_name"], "teams": []}
        )
        entry["teams"].append(r["team_name"])

    violations = []
    for t in teams.values():
        if len(t["mentors"]) > 3:
            violations.append(
                f"Team '{t['team_name']}' has {len(t['mentors'])} mentors (max 3)"
            )
    for m in mentor_teams.values():
        if len(m["teams"]) > 3:
            violations.append(
                f"Mentor '{m['mentor_name']}' is assigned to {len(m['teams'])} teams (max 3)"
            )

    return jsonify(
        {
            "success": True,
            "teams": list(teams.values()),
            "total_assignments": len(rows),
            "violations": violations,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    ), 200


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


# ── Team Score Rankings ────────────────────────────────────────────


@api_bp.route("/teams/rankings", methods=["GET"])
def get_team_rankings():
    """Public: get DB-backed team rankings sorted by score descending."""
    try:
        rankings = ranking_service.get_team_rankings()
        return jsonify({"success": True, "rankings": rankings}), 200
    except Exception as e:
        logger.error(f"Error fetching team rankings: {e}")
        return jsonify({"success": False, "error": "Failed to fetch rankings"}), 500


@api_bp.route("/admin/teams/<int:team_id>/score", methods=["PUT"])
@admin_required
def set_team_score(team_id):
    """Admin: set the score for a single team."""
    data = request.get_json(silent=True) or {}
    valid, result = ranking_service.validate_score(data.get("score"))
    if not valid:
        return jsonify({"success": False, "error": result}), 400

    try:
        updated = ranking_service.update_team_score(team_id, result)
        if not updated:
            return jsonify({"success": False, "error": "Team not found"}), 404
        return jsonify({"success": True, "message": "Score updated"}), 200
    except Exception as e:
        logger.error(f"Error updating team score: {e}")
        return jsonify({"success": False, "error": "Failed to update score"}), 500


@api_bp.route("/admin/teams/scores", methods=["GET"])
@admin_required
def get_teams_for_scoring():
    """Admin: get registered teams with current scores for the scoring UI."""
    try:
        teams = ranking_service.get_registered_teams_for_scoring()
        return jsonify({"success": True, "teams": teams}), 200
    except Exception as e:
        logger.error(f"Error fetching teams for scoring: {e}")
        return jsonify({"success": False, "error": "Failed to fetch teams"}), 500
