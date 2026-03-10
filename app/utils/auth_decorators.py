"""Authentication decorators for route protection"""

import functools
import logging

import jwt
from flask import g, jsonify, request

from app.services.auth_service import decode_token

logger = logging.getLogger(__name__)


def token_required(f):
    """Decorator that extracts and validates JWT from Authorization header.

    Sets g.current_user = {'user_id': int, 'role': str} on success.
    """

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify(
                {"success": False, "error": "Missing or invalid Authorization header"}
            ), 401

        token = auth_header[7:]
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"success": False, "error": "Invalid token"}), 401

        g.current_user = {
            "user_id": payload["user_id"],
            "role": payload["role"],
        }
        return f(*args, **kwargs)

    return decorated


def participant_required(f):
    """Requires a valid JWT with role == 'participant'."""

    @functools.wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        if g.current_user["role"] != "participant":
            return jsonify({"success": False, "error": "Participant access required"}), 403
        return f(*args, **kwargs)

    return decorated


def mentor_required(f):
    """Requires a valid JWT with role == 'mentor'."""

    @functools.wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        if g.current_user["role"] != "mentor":
            return jsonify({"success": False, "error": "Mentor access required"}), 403
        return f(*args, **kwargs)

    return decorated


def captain_required(f):
    """Requires a valid JWT participant who is a captain of the team in the route."""

    @functools.wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        if g.current_user["role"] != "participant":
            return jsonify({"success": False, "error": "Participant access required"}), 403

        from flask import current_app

        from app.database import execute_query

        participant = execute_query(
            current_app,
            "SELECT id, team_id, is_captain FROM participants WHERE id = %s",
            (g.current_user["user_id"],),
            fetch_one=True,
        )
        if not participant or not participant["is_captain"]:
            return jsonify({"success": False, "error": "Captain access required"}), 403

        g.current_user["team_id"] = participant["team_id"]
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    """Requires a valid JWT with role == 'admin'."""

    @functools.wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        if g.current_user["role"] != "admin":
            return jsonify({"success": False, "error": "Admin access required"}), 403
        return f(*args, **kwargs)

    return decorated
