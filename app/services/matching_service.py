"""Gale-Shapley Matching Service — Hospital-Resident Variant

Each team (hospital) has capacity 3, each mentor (resident) has capacity 1.
Uses mentor-proposing algorithm:
  1. Each unmatched mentor proposes to their highest-ranked team not yet rejected by.
  2. Each team tentatively holds the best 3 proposers (per team's preference) and rejects the rest.
  3. Rejected mentors propose to their next choice.
  4. Repeat until no unmatched mentor has remaining teams to propose to.
"""
import logging
from flask import current_app
from app.database import execute_query, get_db_cursor
from app.services.mentor_selection_service import get_preference_submission_status

logger = logging.getLogger(__name__)

TEAM_CAPACITY = 3


def run_gale_shapley():
    """Run the Hospital-Resident Gale-Shapley matching algorithm.

    Returns:
        (success, message, assignments) where assignments is a list of
        (team_id, mentor_id) tuples.
    """
    # Check all preferences are submitted
    status = get_preference_submission_status()
    if not status['all_submitted']:
        return False, "Not all preferences have been submitted yet", []

    # Load mentor preferences: mentor_id -> [team_id ordered by rank]
    mentor_prefs_rows = execute_query(current_app, """
        SELECT mentor_id, team_id FROM mentor_team_preferences
        ORDER BY mentor_id, rank
    """, fetch_all=True) or []

    mentor_pref_lists = {}
    for row in mentor_prefs_rows:
        mentor_pref_lists.setdefault(row['mentor_id'], []).append(row['team_id'])

    # Load team preferences: team_id -> {mentor_id: rank}
    team_prefs_rows = execute_query(current_app, """
        SELECT team_id, mentor_id, rank FROM team_mentor_preferences
        ORDER BY team_id, rank
    """, fetch_all=True) or []

    team_pref_ranks = {}
    for row in team_prefs_rows:
        team_pref_ranks.setdefault(row['team_id'], {})[row['mentor_id']] = row['rank']

    all_mentors = list(mentor_pref_lists.keys())
    all_teams = list(team_pref_ranks.keys())

    # Initialize
    # mentor_proposal_index: which preference index mentor proposes to next
    mentor_proposal_index = {m: 0 for m in all_mentors}
    # mentor_match: mentor_id -> team_id or None
    mentor_match = {m: None for m in all_mentors}
    # team_matches: team_id -> list of mentor_ids currently held
    team_matches = {t: [] for t in all_teams}

    # Free mentors queue
    free_mentors = list(all_mentors)

    while free_mentors:
        mentor_id = free_mentors.pop(0)
        pref_list = mentor_pref_lists.get(mentor_id, [])
        idx = mentor_proposal_index[mentor_id]

        if idx >= len(pref_list):
            # Mentor has exhausted all preferences — remains unmatched
            continue

        team_id = pref_list[idx]
        mentor_proposal_index[mentor_id] = idx + 1

        team_ranking = team_pref_ranks.get(team_id, {})
        current_holders = team_matches[team_id]

        if len(current_holders) < TEAM_CAPACITY:
            # Team has room — accept
            current_holders.append(mentor_id)
            mentor_match[mentor_id] = team_id
        else:
            # Team is full — check if this mentor is preferred over the worst held
            # "Worst" = the held mentor with the highest rank number (least preferred)
            # If mentor is not in team's preference list, treat as rank infinity
            mentor_rank = team_ranking.get(mentor_id, float('inf'))
            worst_held = max(current_holders, key=lambda m: team_ranking.get(m, float('inf')))
            worst_rank = team_ranking.get(worst_held, float('inf'))

            if mentor_rank < worst_rank:
                # Replace worst with this mentor
                current_holders.remove(worst_held)
                mentor_match[worst_held] = None
                free_mentors.append(worst_held)

                current_holders.append(mentor_id)
                mentor_match[mentor_id] = team_id
            else:
                # Rejected — mentor proposes to next
                free_mentors.append(mentor_id)

    # Collect assignments
    assignments = []
    for mentor_id, team_id in mentor_match.items():
        if team_id is not None:
            assignments.append((team_id, mentor_id))

    assignments.sort(key=lambda x: (x[0], x[1]))
    return True, f"Matching complete: {len(assignments)} assignments made", assignments


def save_matching_results(assignments):
    """Clear existing team_mentors and write new assignments.

    Args:
        assignments: list of (team_id, mentor_id) tuples
    """
    try:
        with get_db_cursor(current_app) as cursor:
            cursor.execute("DELETE FROM team_mentors")
            for team_id, mentor_id in assignments:
                cursor.execute(
                    "INSERT INTO team_mentors (team_id, mentor_id, is_active) VALUES (%s, %s, TRUE)",
                    (team_id, mentor_id)
                )
        logger.info(f"Saved {len(assignments)} matching results")
    except Exception as e:
        logger.error(f"Error saving matching results: {e}")
        raise


def get_matching_results():
    """Get current mentor–team assignments."""
    query = """
        SELECT tm.team_id, t.team_name,
               tm.mentor_id, m.first_name || ' ' || m.last_name AS mentor_name,
               m.company_name, tm.assigned_at
        FROM team_mentors tm
        JOIN teams t ON tm.team_id = t.id
        JOIN mentors m ON tm.mentor_id = m.id
        WHERE tm.is_active = TRUE
        ORDER BY t.team_name, m.last_name
    """
    return execute_query(current_app, query, fetch_all=True) or []
