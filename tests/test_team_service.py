"""Unit tests for app.services.team_service.

Covers pure-logic portions that don't require a real database:
- join code generation
- constant guard values (MAX_TEAM_MEMBERS, MAX_REGISTERED_TEAMS, ACTIVE_THRESHOLD)
"""

import re
import string
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.team_service import (
    ACTIVE_THRESHOLD,
    MAX_REGISTERED_TEAMS,
    MAX_TEAM_MEMBERS,
    TeamService,
)


# ---------------------------------------------------------------------------
# generate_join_code
# ---------------------------------------------------------------------------

class TestGenerateJoinCode:
    VALID_CHARS = set(string.ascii_uppercase + string.digits)

    def test_default_length_is_8(self):
        code = TeamService.generate_join_code()
        assert len(code) == 8

    def test_custom_length(self):
        for length in (4, 6, 12, 20):
            code = TeamService.generate_join_code(length=length)
            assert len(code) == length

    def test_only_uppercase_alphanumeric(self):
        for _ in range(20):
            code = TeamService.generate_join_code()
            assert all(c in self.VALID_CHARS for c in code)

    def test_no_lowercase(self):
        for _ in range(20):
            code = TeamService.generate_join_code()
            assert code == code.upper()

    def test_codes_are_random(self):
        """Generate 50 codes and verify they're not all the same."""
        codes = {TeamService.generate_join_code() for _ in range(50)}
        # Statistically, all 50 being identical is astronomically unlikely
        assert len(codes) > 1

    def test_codes_match_expected_pattern(self):
        pattern = re.compile(r"^[A-Z0-9]{8}$")
        for _ in range(20):
            assert pattern.match(TeamService.generate_join_code())


# ---------------------------------------------------------------------------
# Module-level business constants
# ---------------------------------------------------------------------------

class TestBusinessConstants:
    """Guard rails — if someone accidentally changes these thresholds the tests
    will catch it immediately."""

    def test_max_team_members_is_6(self):
        assert MAX_TEAM_MEMBERS == 6

    def test_max_registered_teams_is_18(self):
        assert MAX_REGISTERED_TEAMS == 18

    def test_active_threshold_is_3(self):
        assert ACTIVE_THRESHOLD == 3
