"""API routes — rankings, regulations, admin matching, lookup data, and bug reports"""

import logging
from datetime import UTC

from flask import current_app, jsonify, request

from app import limiter
from app.database import execute_query
from app.routes import api_bp
from app.services import (
    matching_service,
    mentor_selection_service,
    mentor_service,
    ranking_service,
    regulations_service,
)
from app.services.redis_client import get_redis_client
from app.services.team_service import TeamService
from app.utils.auth_decorators import admin_required, get_optional_user

logger = logging.getLogger(__name__)


@api_bp.route("/health", methods=["GET"])
@limiter.exempt
def health():
    """Liveness probe — 200 as long as the process can serve a request.

    Deliberately touches no dependencies so a transient Postgres/Redis outage
    never kills an otherwise-healthy pod (that's readiness' job, below).
    """
    return jsonify({"status": "ok"}), 200


@api_bp.route("/health/ready", methods=["GET"])
@limiter.exempt
def health_ready():
    """Readiness probe — 200 only when the pod can actually serve traffic.

    Postgres is the hard dependency: if a pooled `SELECT 1` fails, the pod is
    pulled from the Service (503) until the DB comes back. Redis is fail-open by
    design, so its state is reported but never gates readiness.
    """
    try:
        row = execute_query(current_app, "SELECT 1 AS ok", fetch_one=True)
        if not row or row.get("ok") != 1:
            logger.warning(f"Readiness DB check returned unexpected result: {row!r}")
            return jsonify({"db": "down", "redis": "unknown"}), 503
        db_status = "ok"
    except Exception as e:
        logger.warning(f"Readiness DB check failed: {e}")
        return jsonify({"db": "down", "redis": "unknown"}), 503

    redis_status = "disabled"
    client = get_redis_client()
    if client is not None:
        try:
            client.ping()
            redis_status = "ok"
        except Exception as e:
            logger.warning(f"Readiness Redis check failed: {e}")
            redis_status = "down"

    return jsonify({"db": db_status, "redis": redis_status}), 200


# ── Feature-flag config (no auth required) ──────────────────────────


@api_bp.route("/config", methods=["GET"])
def get_config():
    """Return feature flags for the frontend SPA.

    No auth required — flags are read by the Navbar, Hero, Rankings routing, etc.
    SameSite=Lax cookies mean this endpoint is safe to call without CSRF tokens.
    """
    return jsonify(
        {
            "REGISTRATION_OPEN": bool(current_app.config.get("REGISTRATION_OPEN")),
            "MENTORS_STAY_TUNED": bool(current_app.config.get("MENTORS_STAY_TUNED")),
            "RANKINGS_LIVE": bool(current_app.config.get("RANKINGS_LIVE")),
        }
    ), 200


# ── Lookup-data endpoints (universities & specialties) ─────────────


@api_bp.route("/universities", methods=["GET"])
def get_universities():
    """Return seed universities only (curated list)"""
    try:
        rows = mentor_service.get_seed_universities()
        return jsonify({"success": True, "universities": rows}), 200
    except Exception as e:
        logger.error(f"Error fetching universities: {e}")
        return jsonify({"success": False, "error": "Failed to fetch universities"}), 500


@api_bp.route("/specialties", methods=["GET"])
def get_specialties():
    """Return seed specialties only (curated list)"""
    try:
        rows = mentor_service.get_seed_specialties()
        return jsonify({"success": True, "specialties": rows}), 200
    except Exception as e:
        logger.error(f"Error fetching specialties: {e}")
        return jsonify({"success": False, "error": "Failed to fetch specialties"}), 500


# ── Rankings & Regulations ─────────────────────────────────────────


@api_bp.route("/ranking", methods=["GET"])
def get_ranking():
    """Get rankings sorted by points"""
    try:
        rankings = ranking_service.get_rankings()
        return jsonify({"success": True, "rankings": rankings}), 200
    except Exception as e:
        logger.error(f"Error fetching ranking: {e}")
        return jsonify({"success": False, "error": "Failed to fetch rankings"}), 500


@api_bp.route("/regulations", methods=["GET"])
def get_regulations():
    """Get regulations"""
    try:
        regulations = regulations_service.get_regulations()
        return jsonify({"success": True, "regulations": regulations}), 200
    except Exception as e:
        logger.error(f"Error fetching regulations: {e}")
        return jsonify({"success": False, "error": "Failed to fetch regulations"}), 500


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
        logger.error(f"Failed to save matching results: {e}")
        return jsonify({"success": False, "error": "Failed to save matching results"}), 500

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
        return jsonify({"success": False, "error": "Failed to confirm matching"}), 500


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
    from datetime import datetime

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
        entry = mentor_teams.setdefault(mid, {"mentor_name": r["mentor_name"], "teams": []})
        entry["teams"].append(r["team_name"])

    violations = []
    for t in teams.values():
        if len(t["mentors"]) > 3:
            violations.append(f"Team '{t['team_name']}' has {len(t['mentors'])} mentors (max 3)")
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
            "generated_at": datetime.now(UTC).isoformat(),
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

    Auth is optional — if a valid session cookie or Bearer token is present the
    reporter's name/email are looked up from the DB and included in the Discord
    embed.  Anonymous submissions are accepted too (e.g. from the registration
    page, before an account exists).

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

    reporter_name = "Anonymous"
    reporter_email = "(not provided)"
    reporter_role = "unknown"

    payload = get_optional_user()
    if payload:
        try:
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
                    "SELECT first_name || ' ' || last_name AS name, email FROM mentors WHERE id = %s",
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

    logger.info("Bug report queued for delivery (page=%s)", page_url)
    return jsonify({"success": True, "message": "Bug report submitted — thank you!"}), 202


# ── Team Score Rankings ────────────────────────────────────────────


@api_bp.route("/teams/rankings", methods=["GET"])
def get_team_rankings():
    """Public once RANKINGS_LIVE is on: DB-backed team rankings sorted by score descending.

    The flag is enforced here and not only in the SPA, so scores entered before
    the reveal can't be read by calling the API directly.
    """
    if not current_app.config.get("RANKINGS_LIVE"):
        return jsonify({"success": False, "error": "Rankings are not live yet"}), 403
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
