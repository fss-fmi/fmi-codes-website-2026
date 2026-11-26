"""Gale-Shapley + Greedy Fill Matching Service

Phase 1 — Extended Gale-Shapley (mentor-proposing, MENTOR_CAPACITY=3, TEAM_CAPACITY=3):
  Each mentor proposes down their ranked preference list, accumulating up to 3 team
  assignments. Teams hold the best TEAM_CAPACITY proposals by their own preference
  ranking; displaced mentors re-queue to propose to their next choice.

Phase 2 — Greedy fill:
  Even fill: one mentor at a time goes to the team with the fewest mentors, taken
  from the least-loaded mentors with spare capacity, until no team under
  TEAM_CAPACITY can take one. Then rebalance: while a team holds fewer than
  TEAM_FLOOR mentors and another holds TEAM_CAPACITY, a full team hands its
  least-preferred mentor to the shortest team, and the even fill runs again so the
  donor can take a mentor who still has room. Every team reaches TEAM_FLOOR
  whenever there are at least 2 mentors and 3 x mentors >= 2 x teams.
"""

import logging
from collections import deque

from flask import current_app

from app.database import execute_query, get_db_cursor
from app.services import event_notifier, feature_flag_service, matching_events
from app.utils.service_errors import ServiceFailureError

logger = logging.getLogger(__name__)

TEAM_CAPACITY = 3  # mentors per team
TEAM_FLOOR = 2  # mentors every team should get when supply allows
MENTOR_CAPACITY = 3  # teams per mentor

TEAM_NOT_FOUND = "Team not found"


def run_gale_shapley():
    """Run the matching algorithm.

    Returns:
        (success, message, assignments, warnings, team_count) where assignments is
        a list of (team_id, mentor_id) tuples, warnings is a list of advisory
        strings and team_count is how many teams the run matched, those left
        without a mentor included.

    Always attempts to run — incomplete preference submissions produce warnings
    rather than an outright failure. Phase 2 greedy fill covers the gaps, evenly.
    Teams and mentors are read in id order, which fixes the phase 1 queue and
    every tie-break, so the same data always gives the same matching.
    """
    warnings = []

    all_team_rows = (
        execute_query(
            current_app,
            "SELECT id FROM teams WHERE status = 'active' AND is_registered = TRUE ORDER BY id",
            fetch_all=True,
        )
        or []
    )
    all_teams = [r["id"] for r in all_team_rows]

    all_mentor_rows = (
        execute_query(
            current_app,
            "SELECT id FROM mentors WHERE status = 'active' ORDER BY id",
            fetch_all=True,
        )
        or []
    )
    all_mentors = [r["id"] for r in all_mentor_rows]

    if not all_teams:
        return False, "No active registered teams found", [], [], 0
    if not all_mentors:
        return False, "No active mentors found", [], [], 0

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

    # Soft warnings for incomplete submissions (do not block). A mentor whose picks
    # have all lost their slot has nothing left to propose to.
    teams_without_prefs = [t for t in all_teams if t not in team_pref_ranks]
    team_set = set(all_teams)
    mentors_without_prefs = [
        m for m in all_mentors if not team_set.intersection(mentor_pref_lists.get(m, []))
    ]
    if teams_without_prefs:
        warnings.append(f"{len(teams_without_prefs)} team(s) have not submitted mentor preferences")
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
    return True, msg, assignments, warnings, len(all_teams)


def _run_algorithm(all_teams, all_mentors, mentor_pref_lists, team_pref_ranks, warnings=None):
    """Pure Gale-Shapley (mentor-proposing) + greedy fill (even fill, then rebalance).

    This is intentionally free of Flask/DB dependencies so it can be unit-tested
    with arbitrary in-memory data. Ties go by position in all_teams and
    all_mentors.

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
    mentor_proposal_idx = dict.fromkeys(all_mentors, 0)
    mentor_assignments = {m: [] for m in all_mentors}  # mentor -> [team_ids]
    team_assignments = {t: [] for t in all_teams}  # team   -> [mentor_ids]

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
            worst_held = max(current_holders, key=lambda m: team_ranking.get(m, float("inf")))
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
    team_order = {t: i for i, t in enumerate(all_teams)}
    mentor_order = {m: i for i, m in enumerate(all_mentors)}

    def _even_fill():
        # One mentor per step to the team with the fewest mentors. A team with no
        # eligible mentor is skipped rather than ending the fill, or a team that
        # already holds the only mentor with room left would starve every other team.
        while True:
            target, eligible = None, []
            for team_id in all_teams:
                held = len(team_assignments[team_id])
                if held >= TEAM_CAPACITY or (
                    target is not None and held >= len(team_assignments[target])
                ):
                    continue
                free = [
                    m
                    for m in all_mentors
                    if len(mentor_assignments[m]) < MENTOR_CAPACITY
                    and team_id not in mentor_assignments[m]
                ]
                if free:
                    target, eligible = team_id, free
            if target is None:
                return
            mentor_id = min(eligible, key=lambda m: len(mentor_assignments[m]))
            team_assignments[target].append(mentor_id)
            mentor_assignments[mentor_id].append(target)

    def _how_unwanted(donor, mentor_id):
        # Smallest first: unranked by the donor (inf), then the largest rank, then
        # a mentor who didn't rank the donor.
        return (
            -team_pref_ranks.get(donor, {}).get(mentor_id, float("inf")),
            donor in mentor_pref_lists.get(mentor_id, []),
        )

    def _rebalance_once():
        # A full team gives the team furthest under the floor the mentor it wants
        # least. Returns False when no team is under the floor or none is full.
        short = [t for t in all_teams if len(team_assignments[t]) < TEAM_FLOOR]
        donors = [t for t in all_teams if len(team_assignments[t]) >= TEAM_CAPACITY]
        if not short or not donors:
            return False
        recipient = min(short, key=lambda t: len(team_assignments[t]))
        offers = []
        for donor in donors:
            spare = [m for m in team_assignments[donor] if m not in team_assignments[recipient]]
            mentor_id = min(spare, key=lambda m, d=donor: (*_how_unwanted(d, m), mentor_order[m]))
            offers.append((*_how_unwanted(donor, mentor_id), team_order[donor], donor, mentor_id))
        *_, donor, mentor_id = min(offers)
        team_assignments[donor].remove(mentor_id)
        mentor_assignments[mentor_id].remove(donor)
        team_assignments[recipient].append(mentor_id)
        mentor_assignments[mentor_id].append(recipient)
        return True

    # After each move the donor is at 2 and may take a mentor who still has room,
    # so fill again. This ends because fill steps only add assignments, never more
    # than 3 per mentor in all, and with no fill in between each move leaves one
    # fewer full team. A fill that could remove assignments would break that.
    _even_fill()
    while _rebalance_once():
        _even_fill()

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
    teams_under_floor = sum(1 for t in all_teams if len(team_assignments[t]) < TEAM_FLOOR)
    if teams_under_floor:
        warnings.append(
            f"{teams_under_floor} team(s) received fewer than {TEAM_FLOOR} mentors"
            f": not enough mentors to give every team {TEAM_FLOOR}"
        )

    return assignments, warnings


def frozen_locked(cursor) -> bool:
    """Whether matching is confirmed, read in the caller's transaction with a share lock.

    Every transaction that takes pg_advisory_xact_lock(1) calls this as its next
    statement, before any row lock, and the preference saves call it first. The
    writers of team_mentors (a matching save, an admin mentor edit) lock this row
    FOR UPDATE before touching that table, so all of them queue on one row and a
    team-row lock can't deadlock against the foreign-key locks their inserts take.
    """
    cursor.execute("SELECT is_confirmed FROM matching_state WHERE id = 1 FOR SHARE")
    row = cursor.fetchone()
    return bool(row and row.get("is_confirmed"))


def save_matching_results(assignments, warnings, team_count):
    """Clear existing team_mentors and write new assignments. Returns how many were written.

    Also resets the admin confirmation flag so teams/mentors continue seeing
    preferences until the admin explicitly re-confirms the new results. After
    the commit the run is posted to the event feed.

    The run read its teams outside any transaction, so a pair whose team lost its
    slot since then is skipped here, under the lock.

    Args:
        assignments: list of (team_id, mentor_id) tuples
        warnings: the run's advisory strings, posted with it
        team_count: teams in the run, from run_gale_shapley(); counting the
            teams in *assignments* would miss any left without a mentor
    """
    try:
        with get_db_cursor(current_app) as cursor:
            # Lock 2 serialises the writers of team_mentors; matching_state FOR UPDATE
            # comes next, before the table is touched (see frozen_locked).
            cursor.execute("SELECT pg_advisory_xact_lock(2)")
            cursor.execute("SELECT is_confirmed FROM matching_state WHERE id = 1 FOR UPDATE")
            state = cursor.fetchone()
            cursor.execute("DELETE FROM team_mentors")
            cursor.execute(
                """
                INSERT INTO team_mentors (team_id, mentor_id, is_active)
                SELECT p.team_id, p.mentor_id, TRUE
                FROM unnest(%s::bigint[], %s::bigint[]) AS p(team_id, mentor_id)
                JOIN teams t ON t.id = p.team_id AND t.status = 'active' AND t.is_registered
                """,
                ([t for t, _ in assignments], [m for _, m in assignments]),
            )
            saved = cursor.rowcount
            # Reset confirmation — admin must re-confirm after every new run
            cursor.execute(
                "UPDATE matching_state SET is_confirmed = FALSE, confirmed_at = NULL WHERE id = 1"
            )
        logger.info(f"Saved {saved} of {len(assignments)} matching results")
    except Exception as e:
        logger.error(f"Error saving matching results: {e}")
        raise
    cleared = bool(state and state["is_confirmed"])
    if cleared:
        feature_flag_service.invalidate_cache()
    _announce_matching_run(saved, team_count, warnings, cleared)
    return saved


def _announce_matching_run(
    assignment_count: int, team_count: int, warnings, confirmation_cleared: bool
) -> None:
    """Post a saved matching run to the event feed: counts only, never the pairs."""
    try:
        event_notifier.notify(
            matching_events.matching_run_text(
                assignment_count, team_count, warnings, confirmation_cleared
            )
        )
    except Exception:
        logger.exception("Could not post the matching run event")


def get_matching_confirmed() -> bool:
    """Return whether the admin has confirmed the current matching results as final."""
    row = execute_query(
        current_app,
        "SELECT is_confirmed FROM matching_state WHERE id = 1",
        fetch_one=True,
    )
    return bool(row["is_confirmed"]) if row else False


def confirm_matching() -> bool:
    """Mark the current results final. Returns False when they already were.

    The event feed is posted only on a real change, so a double-click or a
    second confirm doesn't announce the same results twice.
    """
    with get_db_cursor(current_app) as cursor:
        cursor.execute(
            "UPDATE matching_state SET is_confirmed = TRUE, confirmed_at = NOW()"
            " WHERE id = 1 AND NOT is_confirmed"
        )
        changed = cursor.rowcount == 1
    if changed:
        feature_flag_service.invalidate_cache()
        try:
            event_notifier.notify(matching_events.matching_confirmed_text())
        except Exception:
            logger.exception("Could not post the matching confirmed event")
    return changed


def _assignment_warnings(cursor, team_name, mentor_ids):
    """Limits a hand edit broke, read after the write over registered teams."""
    warnings = []
    if len(mentor_ids) > TEAM_CAPACITY:
        warnings.append(f"Team {team_name} has {len(mentor_ids)} mentors (max {TEAM_CAPACITY})")
    elif len(mentor_ids) < TEAM_FLOOR:
        warnings.append(f"Team {team_name} has {len(mentor_ids)} mentors (fewer than {TEAM_FLOOR})")
    if mentor_ids:
        cursor.execute(
            """
            SELECT m.first_name || ' ' || m.last_name AS name, COUNT(*) AS teams
            FROM team_mentors tm
            JOIN teams t ON t.id = tm.team_id AND t.is_registered
            JOIN mentors m ON m.id = tm.mentor_id
            WHERE tm.is_active AND tm.mentor_id = ANY(%s)
            GROUP BY m.id
            HAVING COUNT(*) > %s
            ORDER BY m.last_name, m.first_name
            """,
            (list(mentor_ids), MENTOR_CAPACITY),
        )
        for row in cursor.fetchall():
            warnings.append(
                f"Mentor {row['name']} is assigned to {row['teams']} teams (max {MENTOR_CAPACITY})"
            )
    return warnings


def admin_set_team_mentors(team_id, mentor_ids):
    """Replace one registered team's assignments by hand. Leaves the confirmation as it is.

    Returns (success, error, result) where result is {changed, mentor_count, warnings}.
    The limits of 3 per team and 3 teams per mentor are only warned about: the admin
    may need to go past them on the day.
    """
    try:
        with get_db_cursor(current_app) as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(2)")
            cursor.execute("SELECT is_confirmed FROM matching_state WHERE id = 1 FOR UPDATE")
            cursor.execute(
                "SELECT team_name, status = 'active' AND is_registered AS eligible"
                " FROM teams WHERE id = %s",
                (team_id,),
            )
            team = cursor.fetchone()
            if not team:
                return False, TEAM_NOT_FOUND, None
            if not team["eligible"]:
                return False, "Only registered teams can be assigned mentors", None

            cursor.execute(
                "SELECT id FROM mentors WHERE id = ANY(%s) AND status = 'active'",
                (list(mentor_ids),),
            )
            active = {r["id"] for r in cursor.fetchall()}
            for mid in mentor_ids:
                if mid not in active:
                    return False, f"Mentor {mid} not found or inactive", None

            cursor.execute(
                "SELECT mentor_id FROM team_mentors WHERE team_id = %s AND is_active", (team_id,)
            )
            changed = {r["mentor_id"] for r in cursor.fetchall()} != set(mentor_ids)
            if changed:
                cursor.execute("DELETE FROM team_mentors WHERE team_id = %s", (team_id,))
                cursor.execute(
                    "INSERT INTO team_mentors (team_id, mentor_id, is_active)"
                    " SELECT %s, m, TRUE FROM unnest(%s::bigint[]) AS m",
                    (team_id, list(mentor_ids)),
                )
            warnings = _assignment_warnings(cursor, team["team_name"], mentor_ids)
    except Exception as e:
        logger.error(f"Error setting team {team_id} mentors: {e}")
        raise ServiceFailureError("Could not save the mentors. Try again.") from e

    if changed:
        logger.info(f"Admin set team {team_id} mentors to {len(mentor_ids)}")
        try:
            event_notifier.notify(
                matching_events.admin_mentors_changed_text(team["team_name"], len(mentor_ids))
            )
        except Exception:
            logger.exception("Could not post the admin mentor change event")
    return True, None, {"changed": changed, "mentor_count": len(mentor_ids), "warnings": warnings}


def get_assigned_teams_for_mentor(mentor_id):
    """Teams the confirmed matching assigned to a mentor; none until the admin confirms.

    The flag is read in the same statement, so a run saved in between can't slip through.
    Only registered teams count, so an assignment left behind by an unregister never shows.
    """
    query = """
        SELECT tm.team_id, t.team_name,
               COUNT(DISTINCT p.id) AS participant_count
        FROM team_mentors tm
        JOIN teams t ON tm.team_id = t.id
        JOIN matching_state ms ON ms.id = 1 AND ms.is_confirmed
        LEFT JOIN participants p ON t.id = p.team_id AND p.status = 'active'
        WHERE tm.mentor_id = %s AND tm.is_active = TRUE AND t.is_registered
        GROUP BY tm.team_id, t.team_name
        ORDER BY t.team_name
    """
    return execute_query(current_app, query, (mentor_id,), fetch_all=True) or []


def get_matching_results():
    """Get current mentor–team assignments, for registered teams only."""
    query = """
        SELECT tm.team_id, t.team_name,
               tm.mentor_id, m.first_name || ' ' || m.last_name AS mentor_name,
               m.company_name, tm.assigned_at
        FROM team_mentors tm
        JOIN teams t ON tm.team_id = t.id
        JOIN mentors m ON tm.mentor_id = m.id
        WHERE tm.is_active = TRUE AND t.is_registered
        ORDER BY t.team_name, m.last_name
    """
    return execute_query(current_app, query, fetch_all=True) or []
