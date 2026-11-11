"""Mentor preference selection service — PostgreSQL, ranked preferences"""

import logging

from flask import current_app

from app.database import execute_query, get_db_cursor
from app.services import event_notifier, matching_events
from app.utils.request_json import is_row_id

logger = logging.getLogger(__name__)


def _has_rows(cursor, table: str, column: str, owner_id: int) -> bool:
    """Whether *owner_id* already has a ranking, read before it is replaced."""
    cursor.execute(
        f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {column} = %s) AS found", (owner_id,)
    )
    return cursor.fetchone()["found"]


def _announce_ranking(build_text, name: str, updated: bool, side: str) -> None:
    """Post a committed ranking to the event feed. Never raises: the ranking is saved."""
    progress = None
    if not updated:
        try:
            status = get_preference_submission_status()
            progress = (status[f"{side}_submitted"], status[f"{side}_total"])
        except Exception:
            logger.exception("Could not count %s ranking submissions", side)
    try:
        event_notifier.notify(build_text(name, updated, progress))
    except Exception:
        logger.exception("Could not post the %s ranking event", side)


def _preferences_error(preferences, id_key: str, noun: str) -> str | None:
    """Why a submitted ranking of exactly 3 `noun` is malformed, or None."""
    if not isinstance(preferences, list) or len(preferences) != 3:
        return f"You must rank exactly 3 {noun}"
    if not all(
        isinstance(p, dict) and is_row_id(p.get(id_key)) and is_row_id(p.get("rank"))
        for p in preferences
    ):
        return f"Each preference needs a whole-number {id_key} and rank"
    if sorted(p["rank"] for p in preferences) != [1, 2, 3]:
        return "Ranks must be exactly 1, 2, and 3"
    if len({p[id_key] for p in preferences}) != 3:
        return f"All three {noun} must be different"
    return None


def set_team_mentor_preferences(team_id, preferences):
    """Set a team's ranked mentor preferences (exactly 3).

    Args:
        team_id: The team ID.
        preferences: List of dicts [{'mentor_id': int, 'rank': int}, ...] with ranks 1-3.

    Returns:
        (success, message)
    """
    if error := _preferences_error(preferences, "mentor_id", "mentors"):
        return False, error
    mentor_ids = [p["mentor_id"] for p in preferences]

    try:
        with get_db_cursor(current_app) as cursor:
            # Lock the team row for the duration of this transaction so that a
            # concurrent double-submit (network retry / double-click) from the
            # same captain cannot interleave their DELETE+INSERT sequences, and
            # registration can't change between this check and the commit.
            cursor.execute(
                "SELECT team_name, status = 'active' AND is_registered AS eligible"
                " FROM teams WHERE id = %s FOR UPDATE",
                (team_id,),
            )
            team = cursor.fetchone()
            if not team:
                return False, "Team not found"
            # Matching only takes registered teams, so a ranking from any other
            # team would never be used and would skew the submission count.
            if not team["eligible"]:
                return False, "Only registered teams can rank mentors"

            # Validate mentors inside the transaction to close the TOCTOU window
            # between the check and the INSERT (no FK enforces status='active').
            for mid in mentor_ids:
                cursor.execute(
                    "SELECT id FROM mentors WHERE id = %s AND status = 'active'",
                    (mid,),
                )
                if not cursor.fetchone():
                    return False, f"Mentor {mid} not found or inactive"

            updated = _has_rows(cursor, "team_mentor_preferences", "team_id", team_id)
            cursor.execute("DELETE FROM team_mentor_preferences WHERE team_id = %s", (team_id,))
            for pref in preferences:
                cursor.execute(
                    "INSERT INTO team_mentor_preferences (team_id, mentor_id, rank) VALUES (%s, %s, %s)",
                    (team_id, pref["mentor_id"], pref["rank"]),
                )
    except Exception as e:
        logger.error(f"Error setting team mentor preferences: {e}")
        return False, str(e)

    logger.info(f"Team {team_id} set mentor preferences")
    _announce_ranking(matching_events.team_ranking_text, team["team_name"], updated, "teams")
    return True, "Mentor preferences saved successfully"


def get_team_mentor_preferences(team_id):
    """Get a team's ranked mentor preferences."""
    query = """
        SELECT tmp.rank, tmp.mentor_id,
               m.first_name || ' ' || m.last_name AS mentor_name,
               m.company_name, m.picture_url
        FROM team_mentor_preferences tmp
        JOIN mentors m ON tmp.mentor_id = m.id
        WHERE tmp.team_id = %s
        ORDER BY tmp.rank
    """
    return execute_query(current_app, query, (team_id,), fetch_all=True) or []


def set_mentor_team_preferences(mentor_id, preferences):
    """Set a mentor's ranked team preferences (exactly 3).

    Args:
        mentor_id: The mentor ID.
        preferences: List of dicts [{'team_id': int, 'rank': int}, ...] with ranks 1-3.

    Returns:
        (success, message)
    """
    if error := _preferences_error(preferences, "team_id", "teams"):
        return False, error
    team_ids = [p["team_id"] for p in preferences]

    try:
        with get_db_cursor(current_app) as cursor:
            # Lock the mentor row for the duration of this transaction so that a
            # concurrent double-submit cannot interleave their DELETE+INSERT sequences.
            cursor.execute(
                "SELECT first_name || ' ' || last_name AS name FROM mentors"
                " WHERE id = %s AND status = 'active' FOR UPDATE",
                (mentor_id,),
            )
            mentor = cursor.fetchone()
            if not mentor:
                return False, "Mentor not found or inactive"

            # Validate teams inside the transaction to close the TOCTOU window.
            # Require active AND registered — matches the ranking UI filter so a
            # mentor cannot rank a team that isn't eligible for the algorithm.
            for tid in team_ids:
                cursor.execute(
                    "SELECT id FROM teams WHERE id = %s AND status = 'active' AND is_registered = TRUE",
                    (tid,),
                )
                if not cursor.fetchone():
                    return False, f"Team {tid} not found or not eligible"

            updated = _has_rows(cursor, "mentor_team_preferences", "mentor_id", mentor_id)
            cursor.execute("DELETE FROM mentor_team_preferences WHERE mentor_id = %s", (mentor_id,))
            for pref in preferences:
                cursor.execute(
                    "INSERT INTO mentor_team_preferences (mentor_id, team_id, rank) VALUES (%s, %s, %s)",
                    (mentor_id, pref["team_id"], pref["rank"]),
                )
    except Exception as e:
        logger.error(f"Error setting mentor team preferences: {e}")
        return False, str(e)

    logger.info(f"Mentor {mentor_id} set team preferences")
    _announce_ranking(matching_events.mentor_ranking_text, mentor["name"], updated, "mentors")
    return True, "Team preferences saved successfully"


def get_mentor_team_preferences(mentor_id):
    """Get a mentor's ranked team preferences."""
    query = """
        SELECT mtp.rank, mtp.team_id, t.team_name
        FROM mentor_team_preferences mtp
        JOIN teams t ON mtp.team_id = t.id
        WHERE mtp.mentor_id = %s
        ORDER BY mtp.rank
    """
    return execute_query(current_app, query, (mentor_id,), fetch_all=True) or []


def get_available_mentors_for_ranking(team_id):
    """Get all active mentors for the captain to choose from."""
    query = """
        SELECT m.id AS mentor_id, m.first_name || ' ' || m.last_name AS name,
               m.company_name, m.bio, m.picture_url, m.picture_filename, m.availability_text
        FROM mentors m
        WHERE m.status = 'active'
        ORDER BY m.last_name, m.first_name
    """
    return execute_query(current_app, query, fetch_all=True) or []


def get_active_teams_for_ranking():
    """Get all active teams for mentors to rank."""
    query = """
        SELECT t.id AS team_id, t.team_name,
               COUNT(DISTINCT p.id) as participant_count
        FROM teams t
        LEFT JOIN participants p ON t.id = p.team_id AND p.status = 'active'
        WHERE t.status = 'active'
          AND t.is_registered = TRUE
        GROUP BY t.id
        ORDER BY t.team_name
    """
    return execute_query(current_app, query, fetch_all=True) or []


def get_preference_submission_status():
    """Get which teams and mentors have/haven't submitted preferences.

    Returns:
        dict with 'teams' and 'mentors' lists, each entry having
        'id', 'name', 'submitted' boolean.
    """
    teams = (
        execute_query(
            current_app,
            """
        SELECT t.id, t.team_name,
               EXISTS(SELECT 1 FROM team_mentor_preferences tmp WHERE tmp.team_id = t.id) as submitted
        FROM teams t WHERE t.status = 'active' AND t.is_registered = TRUE
        ORDER BY t.team_name
    """,
            fetch_all=True,
        )
        or []
    )

    mentors = (
        execute_query(
            current_app,
            """
        SELECT m.id, m.first_name || ' ' || m.last_name as name, m.company_name,
               EXISTS(SELECT 1 FROM mentor_team_preferences mtp WHERE mtp.mentor_id = m.id) as submitted
        FROM mentors m WHERE m.status = 'active'
        ORDER BY m.last_name, m.first_name
    """,
            fetch_all=True,
        )
        or []
    )

    teams_submitted = sum(1 for t in teams if t["submitted"])
    mentors_submitted = sum(1 for m in mentors if m["submitted"])

    return {
        "teams": [dict(t) for t in teams],
        "mentors": [dict(m) for m in mentors],
        "teams_total": len(teams),
        "teams_submitted": teams_submitted,
        "mentors_total": len(mentors),
        "mentors_submitted": mentors_submitted,
        "all_submitted": teams_submitted == len(teams)
        and mentors_submitted == len(mentors)
        and len(teams) > 0
        and len(mentors) > 0,
    }
