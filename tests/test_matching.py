"""Unit tests for the pure Gale-Shapley + greedy-fill matching algorithm.

All tests call `_run_algorithm` directly with in-memory data — no Flask app
context or database connection required.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.matching_service import MENTOR_CAPACITY, TEAM_CAPACITY, _run_algorithm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assignments_for_team(assignments, team_id):
    return [m for (t, m) in assignments if t == team_id]


def assignments_for_mentor(assignments, mentor_id):
    return [t for (t, m) in assignments if m == mentor_id]


# ---------------------------------------------------------------------------
# Basic correctness
# ---------------------------------------------------------------------------

class TestPerfectMatch:
    """Single team + single mentor, mutual #1 preference."""

    def test_one_team_one_mentor_matched(self):
        teams   = [1]
        mentors = [10]
        mentor_prefs = {10: [1]}
        team_prefs   = {1: {10: 1}}

        assignments, warnings = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        assert (1, 10) in assignments

    def test_underfill_warning_when_not_enough_mentors(self):
        """1 team needs 3 mentors but only 1 mentor exists → underfill warning."""
        teams   = [1]
        mentors = [10]
        mentor_prefs = {10: [1]}
        team_prefs   = {1: {10: 1}}

        _, warnings = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        assert any("fewer than" in w for w in warnings)


class TestCapacityLimits:
    """Verify TEAM_CAPACITY and MENTOR_CAPACITY are respected."""

    def test_team_receives_at_most_team_capacity_mentors(self):
        # 6 mentors all prefer the same single team
        teams   = [1]
        mentors = list(range(10, 16))  # 10..15
        mentor_prefs = {m: [1] for m in mentors}
        team_prefs   = {1: {m: i + 1 for i, m in enumerate(mentors)}}

        assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        assert len(assignments_for_team(assignments, 1)) == TEAM_CAPACITY

    def test_mentor_assigned_to_at_most_mentor_capacity_teams(self):
        # 1 mentor, 6 teams — all prefer that mentor
        teams   = list(range(1, 7))
        mentors = [10]
        mentor_prefs = {10: list(range(1, 7))}
        team_prefs   = {t: {10: 1} for t in teams}

        assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        assert len(assignments_for_mentor(assignments, 10)) <= MENTOR_CAPACITY


# ---------------------------------------------------------------------------
# Preference satisfaction
# ---------------------------------------------------------------------------

class TestPreferenceSatisfaction:
    """Algorithm should honour mutual preferences over greedy fill."""

    def test_top_preference_accepted_when_space_available(self):
        teams   = [1, 2, 3]
        mentors = [10, 11, 12]
        # Each mentor's #1 pick is a distinct team — perfect match
        mentor_prefs = {10: [1, 2, 3], 11: [2, 1, 3], 12: [3, 1, 2]}
        team_prefs   = {1: {10: 1, 11: 2, 12: 3},
                        2: {11: 1, 10: 2, 12: 3},
                        3: {12: 1, 10: 2, 11: 3}}

        assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        assert (1, 10) in assignments
        assert (2, 11) in assignments
        assert (3, 12) in assignments

    def test_displacement_gives_slot_to_higher_ranked_mentor(self):
        """Mentor 11 (rank 1 for team 1) displaces mentor 10 (rank 2)."""
        teams   = [1]
        mentors = [10, 11]
        # Team capacity = 3; only 2 mentors so neither gets displaced by capacity.
        # Use capacity=1 scenario by making team_prefs only rank one mentor.
        # Actually let's make a 2-mentor, 1-slot scenario: set TEAM_CAPACITY
        # artificially by having exactly 3 mentors, 2 of which compete for the
        # one remaining slot after the first two fill it.
        teams   = [1]
        mentors = [10, 11, 12, 13]
        # Team 1 ranks: 11 > 10 > 12 > 13 (lower number = better rank)
        team_prefs = {1: {11: 1, 10: 2, 12: 3, 13: 4}}
        # Mentor 10 proposes first (by queue order); mentor 11 proposes second
        mentor_prefs = {10: [1], 11: [1], 12: [1], 13: [1]}

        assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        # Team capacity = 3: top-3 ranked mentors for team 1 should be 11, 10, 12
        team_mentors = set(assignments_for_team(assignments, 1))
        assert 11 in team_mentors   # rank-1 must be present
        assert 13 not in team_mentors  # rank-4 should be displaced


# ---------------------------------------------------------------------------
# Greedy fill
# ---------------------------------------------------------------------------

class TestGreedyFill:
    """Phase 2 should fill teams that preference coverage left short."""

    def test_team_with_no_preferences_still_gets_mentors(self):
        teams   = [1]
        mentors = [10, 11, 12]
        # No preferences submitted by anyone
        mentor_prefs = {}
        team_prefs   = {}

        assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        # Greedy fill should assign all 3 mentors to the single team
        assert len(assignments_for_team(assignments, 1)) == TEAM_CAPACITY

    def test_greedy_fill_spreads_load_evenly(self):
        """With 2 teams and 6 mentors (no prefs) each team should get 3."""
        teams   = [1, 2]
        mentors = list(range(10, 16))
        mentor_prefs = {}
        team_prefs   = {}

        assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        assert len(assignments_for_team(assignments, 1)) == TEAM_CAPACITY
        assert len(assignments_for_team(assignments, 2)) == TEAM_CAPACITY

    def test_mentor_not_double_assigned_to_same_team(self):
        teams   = [1]
        mentors = [10]
        mentor_prefs = {}
        team_prefs   = {}

        assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        mentor_ids = assignments_for_team(assignments, 1)
        assert len(mentor_ids) == len(set(mentor_ids))


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Empty inputs, ineligible teams in preferences, etc."""

    def test_mentor_prefers_ineligible_team_is_skipped(self):
        """Mentor lists a team not in all_teams — should skip and move on."""
        teams   = [1]
        mentors = [10]
        mentor_prefs = {10: [999, 1]}   # 999 is not eligible
        team_prefs   = {1: {10: 1}}

        assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        assert (1, 10) in assignments

    def test_no_assignments_when_no_mentors(self):
        assignments, warnings = _run_algorithm([1, 2], [], {}, {})
        assert assignments == []
        assert any("fewer than" in w for w in warnings)

    def test_no_assignments_when_no_teams(self):
        assignments, warnings = _run_algorithm([], [10, 11], {10: [], 11: []}, {})
        assert assignments == []

    def test_result_is_sorted(self):
        teams   = [3, 1, 2]
        mentors = [30, 10, 20]
        mentor_prefs = {10: [1, 2, 3], 20: [2, 1, 3], 30: [3, 1, 2]}
        team_prefs   = {
            1: {10: 1, 20: 2, 30: 3},
            2: {20: 1, 10: 2, 30: 3},
            3: {30: 1, 10: 2, 20: 3},
        }

        assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)

        assert assignments == sorted(assignments, key=lambda x: (x[0], x[1]))

    def test_warnings_not_none_when_not_passed(self):
        assignments, warnings = _run_algorithm([1], [10], {10: [1]}, {1: {10: 1}})
        assert isinstance(warnings, list)

    def test_warnings_accumulated_into_passed_list(self):
        existing_warnings = ["pre-existing warning"]
        teams   = [1]
        mentors = [10]  # Only 1 mentor for a 3-mentor-capacity team → underfill
        _, warnings = _run_algorithm([1], [10], {10: [1]}, {1: {10: 1}}, existing_warnings)
        assert existing_warnings[0] in warnings


# ---------------------------------------------------------------------------
# Stability property (Gale-Shapley guarantee)
# ---------------------------------------------------------------------------

class TestStabilityProperty:
    """A mentor-optimal stable matching has no blocking pair (t, m) where both
    t prefers m over one of its current mentors AND m prefers t over one of its
    current teams."""

    def _is_stable(self, assignments, all_teams, all_mentors, mentor_pref_lists, team_pref_ranks):
        team_to_mentors  = {t: [] for t in all_teams}
        mentor_to_teams  = {m: [] for m in all_mentors}
        for (t, m) in assignments:
            team_to_mentors[t].append(m)
            mentor_to_teams[m].append(t)

        for team_id in all_teams:
            t_ranks = team_pref_ranks.get(team_id, {})
            for mentor_id in all_mentors:
                if mentor_id in team_to_mentors[team_id]:
                    continue  # already matched

                # Would this team prefer this mentor over one of its current mentors?
                current_worst_rank = max(
                    (t_ranks.get(m, float("inf")) for m in team_to_mentors[team_id]),
                    default=float("inf"),
                )
                m_rank_for_t = t_ranks.get(mentor_id, float("inf"))
                if m_rank_for_t >= current_worst_rank:
                    continue  # team doesn't prefer this mentor

                # Would this mentor prefer this team over one of its current teams?
                m_prefs = mentor_pref_lists.get(mentor_id, [])
                m_team_ranks = {t: i for i, t in enumerate(m_prefs)}
                current_worst_m = max(
                    (m_team_ranks.get(t, float("inf")) for t in mentor_to_teams[mentor_id]),
                    default=float("inf"),
                )
                t_rank_for_m = m_team_ranks.get(team_id, float("inf"))
                if t_rank_for_m < current_worst_m:
                    return False  # blocking pair found
        return True

    def test_stable_matching_3x3(self):
        teams   = [1, 2, 3]
        mentors = [10, 11, 12]
        mentor_prefs = {10: [1, 2, 3], 11: [2, 1, 3], 12: [3, 2, 1]}
        team_prefs   = {
            1: {10: 1, 11: 2, 12: 3},
            2: {11: 1, 10: 2, 12: 3},
            3: {12: 1, 11: 2, 10: 3},
        }
        assignments, _ = _run_algorithm(teams, mentors, mentor_prefs, team_prefs)
        assert self._is_stable(assignments, teams, mentors, mentor_prefs, team_prefs)
