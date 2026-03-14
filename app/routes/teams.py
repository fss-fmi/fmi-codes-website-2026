"""Team management routes — JWT-protected"""

import threading

from flask import current_app, g, jsonify, render_template, request

from app.database import execute_query
from app.routes import teams_bp
from app.services.email_service import send_join_request_notification
from app.services.team_service import MAX_TEAM_MEMBERS, TeamService
from app.utils.auth_decorators import captain_required, participant_required, token_required


@teams_bp.route("/team", methods=["GET"])
def team_page():
    """Serve the team dashboard page"""
    return render_template("teams/team.html")


@teams_bp.route("/createTeam", methods=["GET"])
def create_team_page():
    """Serve the create team page"""
    return render_template("teams/createTeam.html")


@teams_bp.route("/joinTeam", methods=["GET"])
def join_team_page():
    """Serve the join team page"""
    return render_template("teams/joinTeam.html")


@teams_bp.route("/registeredTeams", methods=["GET"])
def registered_teams_page():
    """Serve the registered teams showcase page"""
    return render_template("teams/registeredTeams.html")


@teams_bp.route("/api/teams/registered", methods=["GET"])
def get_registered_teams():
    """Public endpoint: return all registered teams with optional auth enrichment.

    If the caller provides a valid participant JWT and has no team,
    each team entry includes an `already_applied` flag and `can_apply` is True
    in the response so the UI can show Apply buttons.
    """
    query = """
        SELECT t.id          AS team_id,
               t.team_name,
               t.status,
               t.participant_count,
               t.registered_at
        FROM teams t
        WHERE t.is_registered = TRUE
        ORDER BY t.registered_at ASC
    """
    teams = execute_query(current_app, query, fetch_all=True) or []
    teams_list = [dict(t) for t in teams]

    can_apply = False
    participant_id = None

    # Optional auth: try to read JWT but don't fail if absent/invalid
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.services.auth_service import decode_token
            payload = decode_token(auth_header[7:])
            if payload.get("role") == "participant":
                participant_id = payload["user_id"]
                # Check if participant already has a team
                p = execute_query(
                    current_app,
                    "SELECT team_id FROM participants WHERE id = %s AND status = 'active'",
                    (participant_id,),
                    fetch_one=True,
                )
                if p and not p["team_id"]:
                    can_apply = True
        except Exception:
            pass  # Invalid/expired token — just show read-only view

    if can_apply and participant_id:
        # Enrich with already_applied flag
        applied_query = """
            SELECT team_id FROM team_join_requests
            WHERE participant_id = %s AND status = 'pending'
        """
        applied_rows = execute_query(
            current_app, applied_query, (participant_id,), fetch_all=True
        ) or []
        applied_set = {r["team_id"] for r in applied_rows}
        for t in teams_list:
            t["already_applied"] = t["team_id"] in applied_set
            t["is_full"] = t["participant_count"] >= MAX_TEAM_MEMBERS

    return jsonify({
        "success": True,
        "teams": teams_list,
        "can_apply": can_apply,
        "max_registered": 18,
    }), 200


@teams_bp.route("/api/teams/<int:team_id>/members/public", methods=["GET"])
def get_team_members_public(team_id):
    """Public read-only endpoint: first+last names of active members in a registered team.

    Read-only SELECT under PostgreSQL MVCC — no locking needed.
    Only registered teams are exposed (privacy guard for unregistered teams).
    """
    team = execute_query(
        current_app,
        "SELECT id FROM teams WHERE id = %s AND is_registered = TRUE",
        (team_id,),
        fetch_one=True,
    )
    if not team:
        return jsonify({"success": False, "error": "Team not found"}), 404

    members = execute_query(
        current_app,
        """
        SELECT first_name, last_name
        FROM participants
        WHERE team_id = %s AND status = 'active'
        ORDER BY is_captain DESC, created_at
        """,
        (team_id,),
        fetch_all=True,
    ) or []

    return jsonify({
        "success": True,
        "members": [{"first_name": m["first_name"], "last_name": m["last_name"]} for m in members],
    }), 200

@teams_bp.route("/api/teams", methods=["POST"])
@participant_required
def create_team():
    """Create a new team. The authenticated participant becomes captain."""
    data = request.get_json(silent=True) or {}
    team_name = (data.get("team_name") or "").strip()
    if not team_name:
        return jsonify({"success": False, "error": "Team name is required"}), 400

    success, message, team = TeamService.create_team_with_captain(
        team_name, g.current_user["user_id"]
    )
    if success:
        return jsonify({"success": True, "message": message, "team": team}), 201
    return jsonify({"success": False, "error": message}), 400


@teams_bp.route("/api/teams/join", methods=["POST"])
@participant_required
def join_team():
    """Join a team via invite code."""
    data = request.get_json(silent=True) or {}
    join_code = (data.get("join_code") or "").strip()
    if not join_code:
        return jsonify({"success": False, "error": "Join code is required"}), 400

    success, message, team = TeamService.join_team(g.current_user["user_id"], join_code)
    if success:
        return jsonify({"success": True, "message": message, "team": team}), 200
    return jsonify({"success": False, "error": message}), 400


@teams_bp.route("/api/teams", methods=["GET"])
def get_teams():
    """Get all teams"""
    teams = TeamService.get_all_teams()
    teams_list = [dict(t) for t in teams]
    # Remove sensitive fields
    for t in teams_list:
        t.pop("password_hash", None)
        t.pop("join_code", None)
    return jsonify({"success": True, "teams": teams_list}), 200


@teams_bp.route("/api/teams/<int:team_id>", methods=["GET"])
@token_required
def get_team(team_id):
    """Get a specific team with members"""
    team = TeamService.get_team_by_id(team_id)
    if not team:
        return jsonify({"success": False, "error": "Team not found"}), 404

    team_dict = dict(team)
    members = TeamService.get_team_members(team_id)
    team_dict["members"] = [dict(m) for m in members]

    # Fetch assigned mentors
    mentors = (
        execute_query(
            current_app,
            """
        SELECT tm.mentor_id, m.first_name || ' ' || m.last_name AS mentor_name,
               m.company_name
        FROM team_mentors tm
        JOIN mentors m ON tm.mentor_id = m.id
        WHERE tm.team_id = %s AND tm.is_active = TRUE
        ORDER BY m.last_name
    """,
            (team_id,),
            fetch_all=True,
        )
        or []
    )
    team_dict["mentors"] = [dict(mt) for mt in mentors]

    # Only show join_code to team members
    user = g.current_user
    is_member = (
        any(m["id"] == user["user_id"] for m in members) if user["role"] == "participant" else False
    )
    if not is_member and user["role"] != "admin":
        team_dict.pop("join_code", None)
    team_dict.pop("password_hash", None)

    return jsonify({"success": True, "team": team_dict}), 200


@teams_bp.route("/api/teams/<int:team_id>/leave", methods=["POST"])
@participant_required
def leave_team(team_id):
    """Leave the current team"""
    success, message = TeamService.leave_team(g.current_user["user_id"])
    if success:
        return jsonify({"success": True, "message": message}), 200
    return jsonify({"success": False, "error": message}), 400


@teams_bp.route("/api/teams/<int:team_id>", methods=["DELETE"])
@captain_required
def disband_team(team_id):
    """Disband a team (captain only)"""
    if g.current_user.get("team_id") != team_id:
        return jsonify({"success": False, "error": "You can only disband your own team"}), 403

    success, message = TeamService.disband_team(team_id)
    if success:
        return jsonify({"success": True, "message": message}), 200
    return jsonify({"success": False, "error": message}), 400


@teams_bp.route("/api/teams/<int:team_id>/members/<int:member_id>", methods=["DELETE"])
@captain_required
def remove_member(team_id, member_id):
    """Remove a member from the team (captain only)"""
    if g.current_user.get("team_id") != team_id:
        return jsonify({"success": False, "error": "You can only manage your own team"}), 403

    success, message = TeamService.remove_member(team_id, member_id, g.current_user["user_id"])
    if success:
        return jsonify({"success": True, "message": message}), 200
    return jsonify({"success": False, "error": message}), 400


# ── Browse / Join Request flow ─────────────────────────────────


@teams_bp.route("/browseTeams", methods=["GET"])
def browse_teams_page():
    """Serve the browse available teams page"""
    return render_template("teams/browseTeams.html")


@teams_bp.route("/api/teams/available", methods=["GET"])
@participant_required
def get_available_teams():
    """List teams with fewer than 6 members for a teamless participant."""
    teams = TeamService.get_available_teams(g.current_user["user_id"])
    return jsonify({"success": True, "teams": [dict(t) for t in teams]}), 200


@teams_bp.route("/api/teams/my-applications", methods=["GET"])
@participant_required
def get_my_applications():
    """List the current participant's join requests."""
    apps = TeamService.get_my_applications(g.current_user["user_id"])
    return jsonify({"success": True, "applications": [dict(a) for a in apps]}), 200


@teams_bp.route("/api/teams/<int:team_id>/apply", methods=["POST"])
@participant_required
def apply_to_team(team_id):
    """Submit a join request to a team."""
    participant_id = g.current_user["user_id"]
    success, message = TeamService.apply_to_team(participant_id, team_id)
    if not success:
        return jsonify({"success": False, "error": message}), 400

    # Fire join-request notification email to the team captain in the background.
    # A failed email must never roll back a successful application.
    try:
        row = execute_query(
            current_app,
            """
            SELECT p_cap.email        AS captain_email,
                   p_cap.first_name   AS captain_first_name,
                   t.team_name,
                   p_app.first_name   AS app_first_name,
                   p_app.last_name    AS app_last_name
            FROM teams t
            JOIN participants p_cap ON t.captain_id = p_cap.id
            JOIN participants p_app ON p_app.id = %s
            WHERE t.id = %s
            """,
            (participant_id, team_id),
            fetch_one=True,
        )
        if row:
            app_config = dict(current_app.config)
            threading.Thread(
                target=send_join_request_notification,
                args=(
                    app_config,
                    row["captain_email"],
                    row["captain_first_name"],
                    row["team_name"],
                    row["app_first_name"],
                    row["app_last_name"],
                ),
                daemon=True,
            ).start()
    except Exception:
        pass  # Notification failure must not affect the response

    return jsonify({"success": True, "message": message}), 201


@teams_bp.route("/api/teams/<int:team_id>/requests", methods=["GET"])
@captain_required
def get_team_requests(team_id):
    """List pending join requests for the captain's team."""
    if g.current_user.get("team_id") != team_id:
        return jsonify({"success": False, "error": "You can only view your own team's requests"}), 403

    requests = TeamService.get_pending_requests_for_team(team_id)
    return jsonify({"success": True, "requests": [dict(r) for r in requests]}), 200


@teams_bp.route("/api/teams/requests/<int:request_id>/accept", methods=["POST"])
@captain_required
def accept_request(request_id):
    """Accept a pending join request (captain only)."""
    success, message = TeamService.accept_join_request(request_id, g.current_user["user_id"])
    if success:
        return jsonify({"success": True, "message": message}), 200
    return jsonify({"success": False, "error": message}), 400


@teams_bp.route("/api/teams/requests/<int:request_id>/decline", methods=["POST"])
@captain_required
def decline_request(request_id):
    """Decline a pending join request (captain only)."""
    success, message = TeamService.decline_join_request(request_id, g.current_user["user_id"])
    if success:
        return jsonify({"success": True, "message": message}), 200
    return jsonify({"success": False, "error": message}), 400


@teams_bp.route("/api/teams/requests/<int:request_id>/cancel", methods=["POST"])
@participant_required
def cancel_request(request_id):
    """Withdraw own pending join request."""
    success, message = TeamService.cancel_join_request(request_id, g.current_user["user_id"])
    if success:
        return jsonify({"success": True, "message": message}), 200
    return jsonify({"success": False, "error": message}), 400
