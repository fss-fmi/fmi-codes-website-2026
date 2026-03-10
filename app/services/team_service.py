"""Teams management business logic - PostgreSQL version

All mutating operations run inside a single transaction with row-level locks
(SELECT ... FOR UPDATE) to prevent race conditions under concurrent access.
"""

import logging
import secrets
import string

import psycopg2
from flask import current_app

from app.database import execute_query, get_db_cursor

logger = logging.getLogger(__name__)

MAX_TEAM_MEMBERS = 6
MAX_TEAMS = 18
ACTIVE_THRESHOLD = 3  # members required to activate a team


class TeamService:
    """Service for managing hackathon teams"""

    @staticmethod
    def generate_join_code(length=8):
        """Generate a random alphanumeric join code"""
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def get_team_by_id(team_id):
        """Get a team by ID with participant count and mentor info"""
        query = """
            SELECT t.*,
                   COUNT(DISTINCT p.id) as participant_count,
                   COUNT(DISTINCT tm.mentor_id) as mentor_count
            FROM teams t
            LEFT JOIN participants p ON t.id = p.team_id AND p.status = 'active'
            LEFT JOIN team_mentors tm ON t.id = tm.team_id AND tm.is_active = TRUE
            WHERE t.id = %s
            GROUP BY t.id
        """
        return execute_query(current_app, query, (team_id,), fetch_one=True)

    @staticmethod
    def get_team_by_name(team_name):
        """Get a team by name"""
        query = """
            SELECT t.*,
                   COUNT(DISTINCT p.id) as participant_count,
                   COUNT(DISTINCT tm.mentor_id) as mentor_count
            FROM teams t
            LEFT JOIN participants p ON t.id = p.team_id AND p.status = 'active'
            LEFT JOIN team_mentors tm ON t.id = tm.team_id AND tm.is_active = TRUE
            WHERE t.team_name = %s
            GROUP BY t.id
        """
        return execute_query(current_app, query, (team_name,), fetch_one=True)

    @staticmethod
    def get_team_by_join_code(join_code):
        """Get a team by its join code"""
        return execute_query(
            current_app, "SELECT * FROM teams WHERE join_code = %s", (join_code,), fetch_one=True
        )

    @staticmethod
    def get_all_teams(active_only=False, order_by="created_at"):
        """Get all teams with participant and mentor counts"""
        query = """
            SELECT t.*,
                   COUNT(DISTINCT p.id) as participant_count,
                   COUNT(DISTINCT tm.mentor_id) as mentor_count
            FROM teams t
            LEFT JOIN participants p ON t.id = p.team_id AND p.status = 'active'
            LEFT JOIN team_mentors tm ON t.id = tm.team_id AND tm.is_active = TRUE
        """
        if active_only:
            query += " WHERE t.status = 'active'"
        valid_order_fields = ["created_at", "team_name", "status"]
        order_field = order_by if order_by in valid_order_fields else "created_at"
        query += f" GROUP BY t.id ORDER BY t.{order_field} DESC"
        return execute_query(current_app, query, fetch_all=True) or []

    @staticmethod
    def get_team_count(active_only=True):
        """Get total number of teams"""
        query = "SELECT COUNT(*) as count FROM teams"
        if active_only:
            query += " WHERE status IN ('active', 'pending')"
        result = execute_query(current_app, query, fetch_one=True)
        return result["count"] if result else 0

    @staticmethod
    def can_create_team():
        """Check if a new team can be created (max 18 teams)"""
        team_count = TeamService.get_team_count(active_only=True)
        if team_count >= MAX_TEAMS:
            return False, f"Maximum number of teams ({MAX_TEAMS}) already reached"
        return True, "Team creation allowed"

    # ── Atomic mutating operations ─────────────────────────────────

    @staticmethod
    def create_team_with_captain(team_name, captain_id):
        """Create a new team and assign the participant as captain.

        Entire operation runs in ONE transaction with an advisory lock on the
        team-count to prevent two concurrent creates from exceeding MAX_TEAMS.
        """
        if not team_name or not team_name.strip():
            return False, "Team name is required", None

        team_name = team_name.strip()

        try:
            with get_db_cursor() as cursor:
                # Advisory lock so concurrent creates serialize on the count check.
                # Key 1 = arbitrary namespace for "team creation".
                cursor.execute("SELECT pg_advisory_xact_lock(1)")

                # Count check inside the lock
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM teams WHERE status IN ('active', 'pending')"
                )
                if cursor.fetchone()["cnt"] >= MAX_TEAMS:
                    return False, f"Maximum number of teams ({MAX_TEAMS}) already reached", None

                # Name uniqueness (DB UNIQUE will also catch races)
                cursor.execute("SELECT 1 FROM teams WHERE team_name = %s", (team_name,))
                if cursor.fetchone():
                    return False, f'Team name "{team_name}" is already taken', None

                # Lock the participant row to prevent double-team assignment
                cursor.execute(
                    "SELECT id, team_id, is_captain FROM participants "
                    "WHERE id = %s AND status = 'active' FOR UPDATE",
                    (captain_id,),
                )
                participant = cursor.fetchone()
                if not participant:
                    return False, "Participant not found", None
                if participant["team_id"]:
                    return False, "You are already in a team. Leave it first.", None

                # Generate a unique join code inside the same txn
                for _ in range(10):
                    join_code = TeamService.generate_join_code()
                    cursor.execute("SELECT 1 FROM teams WHERE join_code = %s", (join_code,))
                    if not cursor.fetchone():
                        break
                else:
                    return False, "Could not generate unique join code, try again", None

                # Insert team
                cursor.execute(
                    """INSERT INTO teams (team_name, password_hash, join_code, status)
                       VALUES (%s, '', %s, 'pending') RETURNING id""",
                    (team_name, join_code),
                )
                team_id = cursor.fetchone()["id"]

                # Mark participant as captain
                cursor.execute(
                    "UPDATE participants SET team_id = %s, is_captain = TRUE WHERE id = %s",
                    (team_id, captain_id),
                )
                cursor.execute(
                    "UPDATE teams SET captain_id = %s WHERE id = %s",
                    (captain_id, team_id),
                )

            # Fetch full team info outside the lock
            team = TeamService.get_team_by_id(team_id)
            logger.info(f"Team '{team_name}' created by captain {captain_id}")
            return (
                True,
                "Team created successfully",
                dict(team) if team else {"id": team_id, "join_code": join_code},
            )

        except psycopg2.IntegrityError:
            return False, "Team name already taken", None
        except Exception as e:
            logger.error(f"Error creating team: {e}")
            return False, str(e), None

    @staticmethod
    def join_team(participant_id, join_code):
        """Join a team via invite code.

        Single transaction with FOR UPDATE on the team row so concurrent
        joins correctly serialize and never exceed MAX_TEAM_MEMBERS.
        """
        try:
            with get_db_cursor() as cursor:
                # Lock the team row and get current info
                cursor.execute(
                    "SELECT * FROM teams WHERE join_code = %s FOR UPDATE",
                    (join_code.strip().upper(),),
                )
                team = cursor.fetchone()
                if not team:
                    return False, "Invalid join code", None

                if team["status"] == "disqualified":
                    return False, "This team has been disqualified", None

                # Count inside the same txn (row lock guarantees no one else is changing it)
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM participants "
                    "WHERE team_id = %s AND status = 'active'",
                    (team["id"],),
                )
                member_count = cursor.fetchone()["cnt"]
                if member_count >= MAX_TEAM_MEMBERS:
                    return False, f"Team is full (max {MAX_TEAM_MEMBERS} members)", None

                # Lock the participant row
                cursor.execute(
                    "SELECT id, team_id FROM participants "
                    "WHERE id = %s AND status = 'active' FOR UPDATE",
                    (participant_id,),
                )
                participant = cursor.fetchone()
                if not participant:
                    return False, "Participant not found", None
                if participant["team_id"]:
                    return False, "You are already in a team. Leave it first.", None

                # Assign to team
                cursor.execute(
                    "UPDATE participants SET team_id = %s WHERE id = %s",
                    (team["id"], participant_id),
                )

                # Auto-activate at threshold
                new_count = member_count + 1
                if new_count >= ACTIVE_THRESHOLD and team["status"] == "pending":
                    cursor.execute(
                        "UPDATE teams SET status = 'active' WHERE id = %s",
                        (team["id"],),
                    )

            updated_team = TeamService.get_team_by_id(team["id"])
            logger.info(f"Participant {participant_id} joined team {team['id']}")
            return True, "Joined team successfully", dict(updated_team) if updated_team else None

        except Exception as e:
            logger.error(f"Error joining team: {e}")
            return False, str(e), None

    @staticmethod
    def leave_team(participant_id):
        """Participant leaves their team.  If captain leaves, team is disbanded.

        Single transaction with FOR UPDATE to prevent stale member-count reads.
        """
        try:
            with get_db_cursor() as cursor:
                # Lock participant row
                cursor.execute(
                    "SELECT id, team_id, is_captain FROM participants "
                    "WHERE id = %s AND status = 'active' FOR UPDATE",
                    (participant_id,),
                )
                participant = cursor.fetchone()
                if not participant or not participant["team_id"]:
                    return False, "You are not in a team"

                team_id = participant["team_id"]

                if participant["is_captain"]:
                    # Captain leaving → disband (inside same txn)
                    return TeamService._disband_team_in_cursor(cursor, team_id)

                # Regular member — detach
                cursor.execute(
                    "UPDATE participants SET team_id = NULL WHERE id = %s",
                    (participant_id,),
                )

                # Recount inside the same txn
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM participants "
                    "WHERE team_id = %s AND status = 'active'",
                    (team_id,),
                )
                remaining = cursor.fetchone()["cnt"]
                if remaining < ACTIVE_THRESHOLD:
                    cursor.execute(
                        "UPDATE teams SET status = 'pending' WHERE id = %s AND status = 'active'",
                        (team_id,),
                    )

            logger.info(f"Participant {participant_id} left team {team_id}")
            return True, "Left team successfully"

        except Exception as e:
            logger.error(f"Error leaving team: {e}")
            return False, str(e)

    @staticmethod
    def remove_member(team_id, member_id, captain_id):
        """Captain removes a member. Single transaction with row locks."""
        try:
            with get_db_cursor() as cursor:
                # Lock team row
                cursor.execute(
                    "SELECT * FROM teams WHERE id = %s FOR UPDATE",
                    (team_id,),
                )
                team = cursor.fetchone()
                if not team or team["captain_id"] != captain_id:
                    return False, "Only the captain can remove members"

                # Lock member row
                cursor.execute(
                    "SELECT id, team_id, is_captain FROM participants WHERE id = %s FOR UPDATE",
                    (member_id,),
                )
                member = cursor.fetchone()
                if not member or member["team_id"] != team_id:
                    return False, "Member not found in this team"
                if member["is_captain"]:
                    return False, "Captain cannot remove themselves. Use disband instead."

                cursor.execute(
                    "UPDATE participants SET team_id = NULL WHERE id = %s",
                    (member_id,),
                )

                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM participants "
                    "WHERE team_id = %s AND status = 'active'",
                    (team_id,),
                )
                remaining = cursor.fetchone()["cnt"]
                if remaining < ACTIVE_THRESHOLD:
                    cursor.execute(
                        "UPDATE teams SET status = 'pending' WHERE id = %s AND status = 'active'",
                        (team_id,),
                    )

            logger.info(f"Member {member_id} removed from team {team_id}")
            return True, "Member removed successfully"

        except Exception as e:
            logger.error(f"Error removing member: {e}")
            return False, str(e)

    @staticmethod
    def disband_team(team_id):
        """Disband a team — clear members and delete. Single transaction."""
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM teams WHERE id = %s FOR UPDATE",
                    (team_id,),
                )
                team = cursor.fetchone()
                if not team:
                    return False, "Team not found"

                return TeamService._disband_team_in_cursor(cursor, team_id)

        except Exception as e:
            logger.error(f"Error disbanding team: {e}")
            return False, str(e)

    @staticmethod
    def _disband_team_in_cursor(cursor, team_id):
        """Internal helper — disbands inside an already-open cursor/transaction."""
        cursor.execute(
            "UPDATE participants SET team_id = NULL, is_captain = FALSE WHERE team_id = %s",
            (team_id,),
        )
        cursor.execute("DELETE FROM team_mentor_preferences WHERE team_id = %s", (team_id,))
        cursor.execute("DELETE FROM mentor_team_preferences WHERE team_id = %s", (team_id,))
        cursor.execute("DELETE FROM team_mentors WHERE team_id = %s", (team_id,))
        cursor.execute("DELETE FROM teams WHERE id = %s", (team_id,))
        logger.info(f"Team {team_id} disbanded")
        return True, "Team disbanded successfully"

    @staticmethod
    def get_team_members(team_id):
        """Get all active members of a team"""
        query = """
            SELECT p.id, p.first_name, p.last_name, p.email, p.is_captain,
                   s.name as specialty, u.name as university
            FROM participants p
            LEFT JOIN specialties s ON p.specialty_id = s.id
            LEFT JOIN universities u ON p.university_id = u.id
            WHERE p.team_id = %s AND p.status = 'active'
            ORDER BY p.is_captain DESC, p.created_at
        """
        return execute_query(current_app, query, (team_id,), fetch_all=True) or []


# Module-level convenience instance
team_service = TeamService()
