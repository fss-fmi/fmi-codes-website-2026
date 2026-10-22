"""Ranking data management — file-based + DB-backed team score rankings"""

import json
import logging
import math
from pathlib import Path

from flask import current_app

from app.database import execute_query, get_db_cursor
from app.services.redis_client import jittered_ttl, redis_del, redis_get, redis_set

logger = logging.getLogger(__name__)

_RANKINGS_CACHE_KEY = "cache:rankings:legacy"
_TEAM_RANKINGS_CACHE_KEY = "cache:rankings:teams"


def get_rankings() -> list:
    """Get rankings from rankings.json sorted by points descending.

    Results are cached in Redis for ~60s so concurrent requests don't each
    open + parse the file independently.
    """
    cached = redis_get(_RANKINGS_CACHE_KEY)
    if cached is not None:
        try:
            return json.loads(cached)
        except (ValueError, TypeError):
            pass  # corrupt cache entry — fall through to reload

    result = _load_rankings()
    redis_set(_RANKINGS_CACHE_KEY, json.dumps(result, default=str), jittered_ttl(60, 10))
    return result


def _load_rankings() -> list:
    try:
        possible_paths = [
            Path(current_app.root_path).parent / "rankings.json",
            Path(current_app.root_path).parent / "database" / "seeds" / "rankings.json",
        ]

        path = None
        for p in possible_paths:
            if p.exists():
                path = p
                break

        if not path:
            return []

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            data = []

        normalized = []
        for item in data:
            team = str(item.get("team", "")).strip()
            pts = item.get("points", 0)
            img = item.get("image")
            if team:
                try:
                    pts = int(pts)
                except Exception:
                    pts = 0
                normalized.append({"team": team, "points": pts, "image": img})

        normalized.sort(key=lambda x: x["points"], reverse=True)
        return normalized

    except Exception as e:
        raise Exception(f"Failed to load rankings: {str(e)}") from e


def get_team_rankings() -> list:
    """Get team rankings from DB sorted by score descending.

    Uses RANK() window function so ties get the same rank.
    Cached in Redis for ~60s.
    """
    cached = redis_get(_TEAM_RANKINGS_CACHE_KEY)
    if cached is not None:
        try:
            return json.loads(cached)
        except (ValueError, TypeError):
            pass  # corrupt cache entry — fall through to reload

    # The app JSON provider keeps score_updated_at in the same format on a hit and a miss.
    payload = current_app.json.dumps(_load_team_rankings())
    redis_set(_TEAM_RANKINGS_CACHE_KEY, payload, jittered_ttl(60, 10))
    return json.loads(payload)


def _load_team_rankings() -> list:
    query = """
        SELECT t.id          AS team_id,
               t.team_name,
               t.score,
               t.score_updated_at,
               t.participant_count,
               RANK() OVER (ORDER BY t.score DESC NULLS LAST) AS rank
        FROM teams t
        WHERE t.is_registered = TRUE
        ORDER BY t.score DESC NULLS LAST, t.team_name ASC
    """
    rows = execute_query(current_app, query, fetch_all=True) or []
    return [dict(r) for r in rows]


def invalidate_team_rankings_cache():
    """Force cache refresh on next read. Called after admin score updates."""
    redis_del(_TEAM_RANKINGS_CACHE_KEY)


def update_team_score(team_id: int, score: float) -> bool:
    """Atomically update a single team's score with row-level locking.

    M9: Validation runs inside the service so internal callers can't bypass it.
    """
    valid, result = validate_score(score)
    if not valid:
        logger.error("update_team_score called with invalid score: %s", result)
        return False
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id FROM teams WHERE id = %s FOR UPDATE", (team_id,))
        row = cursor.fetchone()
        if not row:
            return False
        cursor.execute(
            "UPDATE teams SET score = %s, score_updated_at = NOW() WHERE id = %s",
            (result, team_id),
        )
    invalidate_team_rankings_cache()
    return True


def get_registered_teams_for_scoring() -> list:
    """Return registered teams with current scores for the admin UI."""
    query = """
        SELECT t.id AS team_id, t.team_name, t.score, t.score_updated_at, t.participant_count
        FROM teams t
        WHERE t.is_registered = TRUE
        ORDER BY t.team_name ASC
    """
    rows = execute_query(current_app, query, fetch_all=True) or []
    return [dict(r) for r in rows]


def validate_score(value) -> tuple:
    """Validate a score value. Returns (is_valid, parsed_float_or_error_msg)."""
    if value is None:
        return False, "Score is required"
    try:
        score = float(value)
    except (TypeError, ValueError):
        return False, "Score must be a number"
    if math.isnan(score) or math.isinf(score):
        return False, "Score must be a finite number"
    if score < 0 or score > 100:
        return False, "Score must be between 0 and 100"
    return True, score
