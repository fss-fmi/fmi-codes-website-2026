"""Mentor preference selection service — PostgreSQL, ranked preferences"""

import logging

from flask import current_app

from app.database import execute_query, get_db_cursor

logger = logging.getLogger(__name__)


def set_team_mentor_preferences(team_id, preferences):
    """Set a team's ranked mentor preferences (exactly 3).

    Args:
        team_id: The team ID.
        preferences: List of dicts [{'mentor_id': int, 'rank': int}, ...] with ranks 1-3.

    Returns:
        (success, message)
    """
    if len(preferences) != 3:
        return False, "You must rank exactly 3 mentors"

    ranks = sorted([p["rank"] for p in preferences])
    if ranks != [1, 2, 3]:
        return False, "Ranks must be exactly 1, 2, and 3"

    mentor_ids = [p["mentor_id"] for p in preferences]
    if len(set(mentor_ids)) != 3:
        return False, "All three mentors must be different"

    # Verify all mentors exist and are active
    for mid in mentor_ids:
        m = execute_query(
            current_app,
            "SELECT id FROM mentors WHERE id = %s AND status = 'active'",
            (mid,),
            fetch_one=True,
        )
        if not m:
            return False, f"Mentor {mid} not found or inactive"

    try:
        with get_db_cursor(current_app) as cursor:
            cursor.execute("DELETE FROM team_mentor_preferences WHERE team_id = %s", (team_id,))
            for pref in preferences:
                cursor.execute(
                    "INSERT INTO team_mentor_preferences (team_id, mentor_id, rank) VALUES (%s, %s, %s)",
                    (team_id, pref["mentor_id"], pref["rank"]),
                )
        logger.info(f"Team {team_id} set mentor preferences")
        return True, "Mentor preferences saved successfully"
    except Exception as e:
        logger.error(f"Error setting team mentor preferences: {e}")
        return False, str(e)


def get_team_mentor_preferences(team_id):
    """Get a team's ranked mentor preferences."""
    query = """
        SELECT tmp.rank, tmp.mentor_id,
               m.first_name || ' ' || m.last_name AS mentor_name,
               m.company_name
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
    if len(preferences) != 3:
        return False, "You must rank exactly 3 teams"

    ranks = sorted([p["rank"] for p in preferences])
    if ranks != [1, 2, 3]:
        return False, "Ranks must be exactly 1, 2, and 3"

    team_ids = [p["team_id"] for p in preferences]
    if len(set(team_ids)) != 3:
        return False, "All three teams must be different"

    # Verify all teams exist and are active
    for tid in team_ids:
        t = execute_query(
            current_app,
            "SELECT id FROM teams WHERE id = %s AND status = 'active'",
            (tid,),
            fetch_one=True,
        )
        if not t:
            return False, f"Team {tid} not found or not active"

    try:
        with get_db_cursor(current_app) as cursor:
            cursor.execute("DELETE FROM mentor_team_preferences WHERE mentor_id = %s", (mentor_id,))
            for pref in preferences:
                cursor.execute(
                    "INSERT INTO mentor_team_preferences (mentor_id, team_id, rank) VALUES (%s, %s, %s)",
                    (mentor_id, pref["team_id"], pref["rank"]),
                )
        logger.info(f"Mentor {mentor_id} set team preferences")
        return True, "Team preferences saved successfully"
    except Exception as e:
        logger.error(f"Error setting mentor team preferences: {e}")
        return False, str(e)


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
               m.company_name, m.bio, m.picture_filename
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
    # Active teams
    teams = (
        execute_query(
            current_app,
            """
        SELECT t.id, t.team_name,
               EXISTS(SELECT 1 FROM team_mentor_preferences tmp WHERE tmp.team_id = t.id) as submitted
        FROM teams t WHERE t.status = 'active'
        ORDER BY t.team_name
    """,
            fetch_all=True,
        )
        or []
    )

    # Active mentors
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
