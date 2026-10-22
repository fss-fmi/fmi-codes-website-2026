"""Authentication decorators for route protection"""

import functools
import logging
from datetime import UTC, datetime

import jwt
from flask import g, jsonify, request

from app.services.auth_service import decode_token
from app.services.redis_client import jittered_ttl, redis_get, redis_set

logger = logging.getLogger(__name__)


def extract_token():
    """Return the raw JWT string from the request, or None.

    Reads the httpOnly cookie first (React SPA), then falls back to the
    Authorization: Bearer header. This is the single source of truth for
    where a token lives on a request — optional-auth endpoints must use
    this rather than reading one source directly, or they silently ignore
    cookie-authenticated SPA callers.
    """
    token = request.cookies.get("token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token


def token_required(f):
    """Decorator that extracts and validates JWT from httpOnly cookie or Authorization header.

    Reads from request.cookies['token'] first (httpOnly cookie, XSS-safe).
    Falls back to Authorization: Bearer <token> header for internal/tooling use.
    Sets g.current_user = {'user_id': int, 'role': str, 'jti': str, 'exp': int} on success.
    H1: Checks the Redis revocation blocklist before accepting the token.
    """

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = extract_token()

        if not token:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"success": False, "error": "Invalid token"}), 401

        # H1: Check revocation blocklist before trusting the token
        jti = payload.get("jti")
        if not jti:
            return jsonify({"success": False, "error": "Token is missing required claims"}), 401

        from app.services.token_blocklist import is_revoked

        if is_revoked(jti):
            return jsonify({"success": False, "error": "Token has been revoked"}), 401

        # R-25: Reject tokens issued before the user's revocation epoch. A password
        # change/reset bumps tokens_valid_from, invalidating every session that
        # predates the new credential — the per-jti blocklist can't do "all sessions".
        if _token_predates_revocation_epoch(payload):
            return jsonify({"success": False, "error": "Token has been revoked"}), 401

        g.current_user = {
            "user_id": payload["user_id"],
            "role": payload["role"],
            "jti": jti,
            "exp": payload.get("exp"),
        }
        return f(*args, **kwargs)

    return decorated


def get_optional_user():
    """Return the decoded payload of a valid, unrevoked token, or None.

    For endpoints where auth is optional: applies every check token_required
    does, but an absent or rejected token means "anonymous" rather than a 401,
    so a logged-out or revoked token can never be used to act as its owner.
    """
    token = extract_token()
    if not token:
        return None

    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        return None

    jti = payload.get("jti")
    if not jti:
        return None

    from app.services.token_blocklist import is_revoked

    if is_revoked(jti) or _token_predates_revocation_epoch(payload):
        return None
    return payload


def _token_predates_revocation_epoch(payload):
    """Return True if the token was issued before the user's tokens_valid_from.

    Admins have no participant/mentor row (role is authoritative, id is unused),
    so there is no epoch to compare against — they are never revoked this way.
    A user with tokens_valid_from = NULL has no epoch set → all tokens valid.
    """
    role = payload.get("role")
    if role not in ("participant", "mentor"):
        return False

    iat = payload.get("iat")
    if iat is None:
        return False

    user_id = payload["user_id"]
    cache_key = f"cache:epoch:{role}:{user_id}"

    # Three-state cache so a user with NO epoch (NULL) doesn't re-hit the DB on
    # every request: "none" sentinel = no epoch set, an ISO string = the epoch,
    # a miss (None) = fall through to the DB. redis_get is fail-open, so a Redis
    # outage yields None → same DB-read behavior as before caching existed.
    cached = redis_get(cache_key)
    if cached == "none":
        return False
    if cached is not None:
        valid_from = datetime.fromisoformat(cached)
        return int(iat) < int(valid_from.timestamp())

    from flask import current_app

    from app.database import execute_query

    if role == "participant":
        query = "SELECT tokens_valid_from FROM participants WHERE id = %s"
    elif role == "mentor":
        query = "SELECT tokens_valid_from FROM mentors WHERE id = %s"
    else:
        return False
    row = execute_query(
        current_app,
        query,
        (user_id,),
        fetch_one=True,
    )
    if not row or row["tokens_valid_from"] is None:
        redis_set(cache_key, "none", ttl=jittered_ttl(45, 15))
        return False

    valid_from = row["tokens_valid_from"]
    if valid_from.tzinfo is None:
        valid_from = valid_from.replace(tzinfo=UTC)

    # Cache the tz-aware epoch as an ISO string (carries +00:00) so a subsequent
    # hit reconstructs the same instant before calling .timestamp().
    redis_set(cache_key, valid_from.isoformat(), ttl=jittered_ttl(45, 15))

    # JWT `iat` is whole-second (RFC 7518), while tokens_valid_from carries
    # sub-second precision. Compare at second granularity so the fresh token the
    # change-password endpoint mints in the same second as the epoch bump is NOT
    # revoked, while any session from a prior second is. Strict `<` on the
    # truncated epoch second gives exactly that.
    return int(iat) < int(valid_from.timestamp())


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
