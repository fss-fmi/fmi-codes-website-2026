"""Mentor management routes — JWT-protected"""

import logging

from flask import g, jsonify

from app.routes import mentors_bp
from app.services import feature_flag_service, mentor_selection_service, mentor_service
from app.utils.auth_decorators import (
    captain_required,
    mentor_required,
)
from app.utils.request_json import json_object

logger = logging.getLogger(__name__)

# ── Public mentor API ──────────────────────────────────────────────


@mentors_bp.route("/api/mentors", methods=["GET"])
def get_mentors():
    """Get all registered mentors (public)"""
    try:
        mentors = mentor_service.get_all_mentors()
        return jsonify({"success": True, "mentors": [dict(m) for m in mentors]}), 200
    except Exception as e:
        logger.error(f"Error fetching mentors: {e}")
        return jsonify({"success": False, "error": "Failed to fetch mentors"}), 500


# ── Team mentor preferences (captain) ─────────────────────────────


def _preferences_closed():
    """403 once matching is confirmed or while submission is switched off, else None.

    Cached fast paths that answer before the body is read; the save itself
    re-checks both under row locks, which is what holds at the deadline. The
    confirmed check goes first: the admin closes submissions before the final
    run, so the closed text would otherwise be the only one anyone sees.
    """
    if feature_flag_service.get_matching_confirmed_cached():
        return _save_refused(mentor_selection_service.PREFERENCES_CONFIRMED)
    if feature_flag_service.is_enabled("preferences_open"):
        return None
    return _save_refused(mentor_selection_service.PREFERENCES_CLOSED)


_FORBIDDEN_SAVES = (
    mentor_selection_service.PREFERENCES_CLOSED,
    mentor_selection_service.PREFERENCES_CONFIRMED,
)


def _save_refused(message):
    status = 403 if message in _FORBIDDEN_SAVES else 400
    return jsonify({"success": False, "error": message}), status


@mentors_bp.route("/api/teams/<int:team_id>/available-mentors", methods=["GET"])
@captain_required
def get_available_mentors(team_id):
    """List all active mentors for captain to rank"""
    if g.current_user.get("team_id") != team_id:
        return jsonify({"success": False, "error": "Not your team"}), 403
    mentors = mentor_selection_service.get_available_mentors_for_ranking(team_id)
    return jsonify({"success": True, "mentors": [dict(m) for m in mentors]}), 200


@mentors_bp.route("/api/teams/<int:team_id>/mentor-preferences", methods=["POST"])
@captain_required
def set_team_preferences(team_id):
    """Captain sets ranked mentor preferences for the team"""
    if g.current_user.get("team_id") != team_id:
        return jsonify({"success": False, "error": "Not your team"}), 403
    if (closed := _preferences_closed()) is not None:
        return closed

    preferences = json_object().get("preferences", [])

    success, message = mentor_selection_service.set_team_mentor_preferences(team_id, preferences)
    if success:
        return jsonify({"success": True, "message": message}), 200
    return _save_refused(message)


@mentors_bp.route("/api/teams/<int:team_id>/mentor-preferences", methods=["GET"])
@captain_required
def get_team_preferences(team_id):
    """Get team's current mentor preferences"""
    if g.current_user.get("team_id") != team_id:
        return jsonify({"success": False, "error": "Not your team"}), 403

    prefs = mentor_selection_service.get_team_mentor_preferences(team_id)
    return jsonify({"success": True, "preferences": [dict(p) for p in prefs]}), 200


# ── Mentor team preferences (mentor) ──────────────────────────────


@mentors_bp.route("/api/mentors/available-teams", methods=["GET"])
@mentor_required
def get_available_teams():
    """List all active teams for mentor to rank"""
    teams = mentor_selection_service.get_active_teams_for_ranking()
    return jsonify({"success": True, "teams": [dict(t) for t in teams]}), 200


@mentors_bp.route("/api/mentors/team-preferences", methods=["POST"])
@mentor_required
def set_mentor_preferences():
    """Mentor sets ranked team preferences"""
    if (closed := _preferences_closed()) is not None:
        return closed
    preferences = json_object().get("preferences", [])

    success, message = mentor_selection_service.set_mentor_team_preferences(
        g.current_user["user_id"], preferences
    )
    if success:
        return jsonify({"success": True, "message": message}), 200
    return _save_refused(message)


@mentors_bp.route("/api/mentors/team-preferences", methods=["GET"])
@mentor_required
def get_mentor_preferences():
    """Get mentor's current team preferences"""
    prefs = mentor_selection_service.get_mentor_team_preferences(g.current_user["user_id"])
    return jsonify({"success": True, "preferences": [dict(p) for p in prefs]}), 200


@mentors_bp.route("/api/mentors/assigned-teams", methods=["GET"])
@mentor_required
def get_assigned_teams():
    """The teams the confirmed matching assigned to this mentor; empty until the admin confirms."""
    from app.services import matching_service

    teams = matching_service.get_assigned_teams_for_mentor(g.current_user["user_id"])
    return jsonify({"success": True, "teams": [dict(t) for t in teams]}), 200
