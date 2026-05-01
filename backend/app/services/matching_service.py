"""Gale-Shapley + Greedy Fill Matching Service

Phase 1 — Extended Gale-Shapley (mentor-proposing, MENTOR_CAPACITY=3, TEAM_CAPACITY=3):
  Each mentor proposes down their ranked preference list, accumulating up to 3 team
  assignments. Teams hold the best TEAM_CAPACITY proposals by their own preference
  ranking; displaced mentors re-queue to propose to their next choice.

Phase 2 — Greedy fill:
  Any team still below TEAM_CAPACITY gets the most-available unassigned mentors
  appended to it. Ensures every registered+active team reaches capacity even when
  preference coverage is sparse (e.g. not all preferences submitted).
"""

import logging
from collections import deque

from flask import current_app

from app.database import execute_query, get_db_cursor
from app.services.mentor_selection_service import get_preference_submission_status

logger = logging.getLogger(__name__)

TEAM_CAPACITY = 3    # mentors per team
MENTOR_CAPACITY = 3  # teams per mentor


def run_gale_shapley():
    """Run the matching algorithm.

    Returns:
        (success, message, assignments, warnings) where assignments is a list of
        (team_id, mentor_id) tuples and warnings is a list of advisory strings.

    Always attempts to run — incomplete preference submissions produce warnings
    rather than an outright failure. Phase 2 greedy fill covers the gaps.
    """
    warnings = []

    # Load all active+registered teams and all active mentors
    all_team_rows = (
        execute_query(
            current_app,
            "SELECT id FROM teams WHERE status = 'active' AND is_registered = TRUE",
            fetch_all=True,
        )
        or []
    )
    all_teams = [r["id"] for r in all_team_rows]

    all_mentor_rows = (
        execute_query(
            current_app,
            "SELECT id FROM mentors WHERE status = 'active'",
            fetch_all=True,
        )
        or []
    )
    all_mentors = [r["id"] for r in all_mentor_rows]

    if not all_teams:
        return False, "No active registered teams found", [], []
    if not all_mentors:
        return False, "No active mentors found", [], []

    # Load mentor preferences: mentor_id -> [team_id ordered by rank]
    mentor_prefs_rows = (
        execute_query(
            current_app,
            "SELECT mentor_id, team_id FROM mentor_team_preferences ORDER BY mentor_id, rank",
            fetch_all=True,
        )
        or []
    )
    mentor_pref_lists = {}
    for row in mentor_prefs_rows:
        mentor_pref_lists.setdefault(row["mentor_id"], []).append(row["team_id"])

    # Load team preferences: team_id -> {mentor_id: rank}
    team_prefs_rows = (
        execute_query(
            current_app,
            "SELECT team_id, mentor_id, rank FROM team_mentor_preferences ORDER BY team_id, rank",
            fetch_all=True,
        )
        or []
    )
    team_pref_ranks = {}
    for row in team_prefs_rows:
        team_pref_ranks.setdefault(row["team_id"], {})[row["mentor_id"]] = row["rank"]

    # Soft warnings for incomplete submissions (do not block)
    teams_without_prefs = [t for t in all_teams if t not in team_pref_ranks]
    mentors_without_prefs = [m for m in all_mentors if m not in mentor_pref_lists]
    if teams_without_prefs:
        warnings.append(
            f"{len(teams_without_prefs)} team(s) have not submitted mentor preferences"
        )
    if mentors_without_prefs:
        warnings.append(
            f"{len(mentors_without_prefs)} mentor(s) have not submitted team preferences"
        )

    assignments, warnings = _run_algorithm(
        all_teams, all_mentors, mentor_pref_lists, team_pref_ranks, warnings
    )

    msg = (
        f"Matching complete: {len(assignments)} assignments"
        f" across {len(all_teams)} teams and {len(all_mentors)} mentors"
    )
    logger.info(msg)
    return True, msg, assignments, warnings


def _run_algorithm(all_teams, all_mentors, mentor_pref_lists, team_pref_ranks, warnings=None):
    """Pure Gale-Shapley (mentor-proposing) + greedy fill.

    This is intentionally free of Flask/DB dependencies so it can be unit-tested
    with arbitrary in-memory data.

    Args:
        all_teams:        list of team IDs eligible for matching
        all_mentors:      list of mentor IDs participating in matching
        mentor_pref_lists: dict mapping mentor_id -> [team_id, ...] ordered by preference
        team_pref_ranks:  dict mapping team_id -> {mentor_id: rank} (1 = most preferred)
        warnings:         optional list to accumulate advisory strings (mutated in-place)

    Returns:
        (assignments, warnings) where assignments is a sorted list of (team_id, mentor_id)
        tuples and warnings is the (possibly empty) advisory list.
    """
    if warnings is None:
        warnings = []

    # ── Phase 1: Extended Gale-Shapley ───────────────────────────────────────
    mentor_proposal_idx = {m: 0 for m in all_mentors}
    mentor_assignments = {m: [] for m in all_mentors}   # mentor -> [team_ids]
    team_assignments   = {t: [] for t in all_teams}     # team   -> [mentor_ids]

    queue = deque(all_mentors)
    in_queue = set(all_mentors)

    while queue:
        mentor_id = queue.popleft()
        in_queue.discard(mentor_id)

        if len(mentor_assignments[mentor_id]) >= MENTOR_CAPACITY:
            continue  # already full

        pref_list = mentor_pref_lists.get(mentor_id, [])
        idx = mentor_proposal_idx[mentor_id]

        if idx >= len(pref_list):
            continue  # exhausted all preferences

        team_id = pref_list[idx]
        mentor_proposal_idx[mentor_id] = idx + 1

        if team_id not in team_assignments:
            # Proposed to a team not in the eligible set — skip, try next
            if (
                len(mentor_assignments[mentor_id]) < MENTOR_CAPACITY
                and mentor_proposal_idx[mentor_id] < len(pref_list)
                and mentor_id not in in_queue
            ):
                queue.append(mentor_id)
                in_queue.add(mentor_id)
            continue

        team_ranking = team_pref_ranks.get(team_id, {})
        current_holders = team_assignments[team_id]

        if len(current_holders) < TEAM_CAPACITY:
            # Space available — accept
            current_holders.append(mentor_id)
            mentor_assignments[mentor_id].append(team_id)
        else:
            # Team is full — displace the worst holder if this mentor is preferred
            mentor_rank = team_ranking.get(mentor_id, float("inf"))
            worst_held = max(
                current_holders, key=lambda m: team_ranking.get(m, float("inf"))
            )
            worst_rank = team_ranking.get(worst_held, float("inf"))

            if mentor_rank < worst_rank:
                current_holders.remove(worst_held)
                mentor_assignments[worst_held].remove(team_id)
                # Displaced mentor re-enters the queue
                if worst_held not in in_queue:
                    queue.append(worst_held)
                    in_queue.add(worst_held)

                current_holders.append(mentor_id)
                mentor_assignments[mentor_id].append(team_id)
            # else rejected — fall through to re-queue below

        # Re-queue if mentor still has capacity and unproposed teams left
        if (
            len(mentor_assignments[mentor_id]) < MENTOR_CAPACITY
            and mentor_proposal_idx[mentor_id] < len(pref_list)
            and mentor_id not in in_queue
        ):
            queue.append(mentor_id)
            in_queue.add(mentor_id)

    # ── Phase 2: Greedy fill ─────────────────────────────────────────────────
    # Fill teams that are still below capacity using mentors that still have room.
    # Process teams with fewest mentors first; prefer mentors with fewest assignments
    # (spreads load evenly instead of piling onto already-busy mentors).
    def _mentor_load(m):
        return len(mentor_assignments.get(m, []))

    for team_id in sorted(all_teams, key=lambda t: len(team_assignments[t])):
        if len(team_assignments[team_id]) >= TEAM_CAPACITY:
            continue
        candidates = sorted(
            [
                m
                for m in all_mentors
                if len(mentor_assignments[m]) < MENTOR_CAPACITY
                and team_id not in mentor_assignments[m]
            ],
            key=_mentor_load,
        )
        for mentor_id in candidates:
            if len(team_assignments[team_id]) >= TEAM_CAPACITY:
                break
            team_assignments[team_id].append(mentor_id)
            mentor_assignments[mentor_id].append(team_id)

    # Collect and sort final assignments
    assignments = [
        (team_id, mentor_id)
        for team_id, mentor_list in team_assignments.items()
        for mentor_id in mentor_list
    ]
    assignments.sort(key=lambda x: (x[0], x[1]))

    teams_underfilled = sum(1 for t in all_teams if len(team_assignments[t]) < TEAM_CAPACITY)
    if teams_underfilled:
        warnings.append(
            f"{teams_underfilled} team(s) received fewer than {TEAM_CAPACITY} mentors"
            " — not enough mentors available to fill all slots"
        )

    return assignments, warnings



def save_matching_results(assignments):
    """Clear existing team_mentors and write new assignments.

    Also resets the admin confirmation flag so teams/mentors continue seeing
    preferences until the admin explicitly re-confirms the new results.

    Args:
        assignments: list of (team_id, mentor_id) tuples
    """
    try:
        with get_db_cursor(current_app) as cursor:
            # Serialize concurrent saves with a dedicated advisory lock.
            # Key 2 is distinct from the team-mutation lock (key 1) to avoid
            # accidental deadlocks.  Two simultaneous admin "run matching" calls
            # will now queue up here rather than racing on DELETE FROM team_mentors.
            cursor.execute("SELECT pg_advisory_xact_lock(2)")
            cursor.execute("DELETE FROM team_mentors")
            for team_id, mentor_id in assignments:
                cursor.execute(
                    "INSERT INTO team_mentors (team_id, mentor_id, is_active) VALUES (%s, %s, TRUE)",
                    (team_id, mentor_id),
                )
            # Reset confirmation — admin must re-confirm after every new run
            cursor.execute(
                "UPDATE matching_state SET is_confirmed = FALSE, confirmed_at = NULL WHERE id = 1"
            )
        logger.info(f"Saved {len(assignments)} matching results")
    except Exception as e:
        logger.error(f"Error saving matching results: {e}")
        raise


def get_matching_confirmed() -> bool:
    """Return whether the admin has confirmed the current matching results as final."""
    row = execute_query(
        current_app,
        "SELECT is_confirmed FROM matching_state WHERE id = 1",
        fetch_one=True,
    )
    return bool(row["is_confirmed"]) if row else False


def set_matching_confirmed(confirmed: bool) -> None:
    """Set (or clear) the admin confirmation flag."""
    with get_db_cursor(current_app) as cursor:
        if confirmed:
            cursor.execute(
                "UPDATE matching_state SET is_confirmed = TRUE, confirmed_at = NOW() WHERE id = 1"
            )
        else:
            cursor.execute(
                "UPDATE matching_state SET is_confirmed = FALSE, confirmed_at = NULL WHERE id = 1"
            )


def get_assigned_teams_for_mentor(mentor_id):
    """Get teams assigned to a mentor by the algorithm."""
    query = """
        SELECT tm.team_id, t.team_name,
               COUNT(DISTINCT p.id) AS participant_count
        FROM team_mentors tm
        JOIN teams t ON tm.team_id = t.id
        LEFT JOIN participants p ON t.id = p.team_id AND p.status = 'active'
        WHERE tm.mentor_id = %s AND tm.is_active = TRUE
        GROUP BY tm.team_id, t.team_name
        ORDER BY t.team_name
    """
    return execute_query(current_app, query, (mentor_id,), fetch_all=True) or []


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
