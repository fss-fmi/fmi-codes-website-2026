"""Ranking data management — file-based + DB-backed team score rankings"""

import json
import logging
import math
import threading
import time
from pathlib import Path

from flask import current_app

from app.database import execute_query, get_db_cursor

logger = logging.getLogger(__name__)

# ── File-based rankings cache (legacy, used by /api/ranking) ───────

_cache_lock = threading.Lock()
_cached_rankings = None
_cache_ts = 0
_CACHE_TTL = 60  # seconds


def get_rankings() -> list:
    """Get rankings from rankings.json sorted by points descending.

    Results are cached in memory for up to 60 seconds so 500 concurrent
    requests don't each open + parse the file independently.
    """
    global _cached_rankings, _cache_ts

    now = time.monotonic()
    if _cached_rankings is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cached_rankings

    with _cache_lock:
        # Double-check inside the lock
        if _cached_rankings is not None and (time.monotonic() - _cache_ts) < _CACHE_TTL:
            return _cached_rankings

        result = _load_rankings()
        _cached_rankings = result
        _cache_ts = time.monotonic()
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


# ── DB-backed team score rankings ──────────────────────────────────

_team_rankings_lock = threading.Lock()
_team_rankings_cache = None
_team_rankings_cache_ts = 0


def get_team_rankings() -> list:
    """Get team rankings from DB sorted by score descending.

    Uses RANK() window function so ties get the same rank.
    Cached for 60s with double-checked locking.
    """
    global _team_rankings_cache, _team_rankings_cache_ts

    now = time.monotonic()
    if _team_rankings_cache is not None and (now - _team_rankings_cache_ts) < _CACHE_TTL:
        return _team_rankings_cache

    with _team_rankings_lock:
        if (
            _team_rankings_cache is not None
            and (time.monotonic() - _team_rankings_cache_ts) < _CACHE_TTL
        ):
            return _team_rankings_cache

        result = _load_team_rankings()
        _team_rankings_cache = result
        _team_rankings_cache_ts = time.monotonic()
        return result


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
    global _team_rankings_cache, _team_rankings_cache_ts
    with _team_rankings_lock:
        _team_rankings_cache = None
        _team_rankings_cache_ts = 0


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
