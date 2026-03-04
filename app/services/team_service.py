"""Teams management business logic - PostgreSQL version"""
import logging
from flask import current_app
from app.database import get_db_cursor, execute_query, execute_insert, execute_update
import psycopg2
import bcrypt

logger = logging.getLogger(__name__)


class TeamService:
    """Service for managing hackathon teams"""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode(), salt).decode()

    @staticmethod
    def verify_password(password: str, hash_value: str) -> bool:
        """Verify a password against its hash"""
        return bcrypt.checkpw(password.encode(), hash_value.encode())

    @staticmethod
    def get_team_by_id(team_id: int) -> dict:
        """Get a team by ID with participant count and mentor info"""
        query = """
            SELECT
                t.*,
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
    def get_team_by_name(team_name: str) -> dict:
        """Get a team by name with participant count and mentor info"""
        query = """
            SELECT
                t.*,
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
    def get_all_teams(active_only=True, order_by='created_at') -> list:
        """Get all teams with participant and mentor counts

        Args:
            active_only: If True, only return active teams
            order_by: Field to order by (created_at, team_name, status)

        Returns:
            List of team dictionaries
        """
        query = """
            SELECT
                t.*,
                COUNT(DISTINCT p.id) as participant_count,
                COUNT(DISTINCT tm.mentor_id) as mentor_count
            FROM teams t
            LEFT JOIN participants p ON t.id = p.team_id AND p.status = 'active'
            LEFT JOIN team_mentors tm ON t.id = tm.team_id AND tm.is_active = TRUE
        """

        if active_only:
            query += " WHERE t.status = 'active'"

        valid_order_fields = ['created_at', 'team_name', 'status']
        order_field = order_by if order_by in valid_order_fields else 'created_at'

        query += f" GROUP BY t.id ORDER BY t.{order_field} DESC"

        return execute_query(current_app, query, fetch_all=True) or []

    @staticmethod
    def get_team_count(active_only=True) -> int:
        """Get total number of teams

        Args:
            active_only: If True, only count active teams

        Returns:
            Number of teams
        """
        query = "SELECT COUNT(*) FROM teams"

        if active_only:
            query += " WHERE status = 'active'"

        try:
            result = execute_query(current_app, query, fetch_one=True)
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error counting teams: {e}")
            return 0

    @staticmethod
    def can_create_team() -> tuple:
        """Check if a new team can be created (max 18 teams)

        Returns:
            Tuple (allowed: bool, message: str)
        """
        team_count = TeamService.get_team_count(active_only=True)
        if team_count >= 18:
            return False, "Maximum number of teams (18) already reached"
        return True, "Team creation allowed"

    @staticmethod
    def create_team(team_name: str, password: str) -> tuple:
        """Create a new team

        Args:
            team_name: Unique team name
            password: Team password (will be hashed)

        Returns:
            Tuple (success: bool, message: str, team_id: int or None)
        """
        # Validation
        if not team_name or not team_name.strip():
            return False, "Team name is required", None

        if not password or len(password) < 4:
            return False, "Password must be at least 4 characters", None

        # Check if team already exists
        if TeamService.get_team_by_name(team_name):
            return False, f'Team name "{team_name}" is already taken', None

        # Check if we can create more teams
        allowed, message = TeamService.can_create_team()
        if not allowed:
            return False, message, None

        # Hash password
        try:
            password_hash = TeamService.hash_password(password)
        except Exception as e:
            logger.error(f"Error hashing password: {e}")
            return False, "Password hashing failed", None

        # Insert team
        query = """
            INSERT INTO teams (team_name, password_hash, status)
            VALUES (%s, %s, 'pending')
            RETURNING id
        """

        try:
            team_id = execute_insert(current_app, query, (team_name.strip(), password_hash))
            logger.info(f"✓ Team created: {team_name} (ID: {team_id})")
            return True, f"Team '{team_name}' created successfully", team_id

        except psycopg2.IntegrityError as e:
            logger.error(f"Integrity error creating team: {e}")
            return False, "Database constraint violation", None
        except Exception as e:
            logger.error(f"Error creating team: {e}")
            return False, str(e), None

    @staticmethod
    def activate_team(team_id: int) -> tuple:
        """Activate a team (change status from pending to active)

        Args:
            team_id: Team ID

        Returns:
            Tuple (success: bool, message: str)
        """
        team = TeamService.get_team_by_id(team_id)
        if not team:
            return False, f"Team {team_id} not found"

        # Verify team has 3-6 participants
        if team['participant_count'] < 3:
            return False, f"Team must have at least 3 participants (currently {team['participant_count']})"

        if team['participant_count'] > 6:
            return False, f"Team cannot have more than 6 participants (currently {team['participant_count']})"

        # Update status to active
        query = "UPDATE teams SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = %s"

        try:
            rows = execute_update(current_app, query, (team_id,))
            if rows > 0:
                logger.info(f"✓ Team {team_id} activated")
                return True, "Team activated successfully"
            else:
                return False, "Failed to activate team"

        except Exception as e:
            logger.error(f"Error activating team: {e}")
            return False, str(e)

    @staticmethod
    def update_team_status(team_id: int, new_status: str) -> tuple:
        """Update team status

        Args:
            team_id: Team ID
            new_status: New status (pending, active, completed, disqualified)

        Returns:
            Tuple (success: bool, message: str)
        """
        valid_statuses = ['pending', 'active', 'completed', 'disqualified']
        if new_status not in valid_statuses:
            return False, f"Invalid status. Must be one of: {', '.join(valid_statuses)}"

        team = TeamService.get_team_by_id(team_id)
        if not team:
            return False, f"Team {team_id} not found"

        query = "UPDATE teams SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s"

        try:
            rows = execute_update(current_app, query, (new_status, team_id))
            if rows > 0:
                logger.info(f"✓ Team {team_id} status updated to '{new_status}'")
                return True, f"Team status updated to '{new_status}'"
            else:
                return False, "Failed to update team status"

        except Exception as e:
            logger.error(f"Error updating team status: {e}")
            return False, str(e)

    @staticmethod
    def verify_team_credentials(team_name: str, password: str) -> tuple:
        """Verify team login credentials

        Args:
            team_name: Team name
            password: Password to verify

        Returns:
            Tuple (success: bool, team_id: int or None, message: str)
        """
        team = TeamService.get_team_by_name(team_name)
        if not team:
            return False, None, f"Team '{team_name}' not found"

        try:
            if TeamService.verify_password(password, team['password_hash']):
                logger.info(f"✓ Team '{team_name}' login successful")
                return True, team['id'], "Login successful"
            else:
                logger.warning(f"✗ Failed login attempt for team '{team_name}'")
                return False, None, "Invalid password"

        except Exception as e:
            logger.error(f"Error verifying credentials: {e}")
            return False, None, "Credential verification failed"

    @staticmethod
    def update_team_password(team_id: int, new_password: str) -> tuple:
        """Update team password

        Args:
            team_id: Team ID
            new_password: New password

        Returns:
            Tuple (success: bool, message: str)
        """
        if not new_password or len(new_password) < 4:
            return False, "Password must be at least 4 characters"

        team = TeamService.get_team_by_id(team_id)
        if not team:
            return False, f"Team {team_id} not found"

        try:
            password_hash = TeamService.hash_password(new_password)
            query = "UPDATE teams SET password_hash = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
            rows = execute_update(current_app, query, (password_hash, team_id))

            if rows > 0:
                logger.info(f"✓ Team {team_id} password updated")
                return True, "Password updated successfully"
            else:
                return False, "Failed to update password"

        except Exception as e:
            logger.error(f"Error updating password: {e}")
            return False, str(e)

    @staticmethod
    def delete_team(team_id: int, force=False) -> tuple:
        """Delete a team

        Args:
            team_id: Team ID
            force: If True, delete even if team has participants (will remove them)

        Returns:
            Tuple (success: bool, message: str)
        """
        team = TeamService.get_team_by_id(team_id)
        if not team:
            return False, f"Team {team_id} not found"

        # Check if team has participants
        if team['participant_count'] > 0 and not force:
            return False, f"Team has {team['participant_count']} participants. Use force=True to delete with participants."

        try:
            with get_db_cursor(current_app) as cursor:
                # If force delete, remove participants first
                if force:
                    cursor.execute("DELETE FROM participants WHERE team_id = %s", (team_id,))

                # Delete team_mentors
                cursor.execute("DELETE FROM team_mentors WHERE team_id = %s", (team_id,))

                # Delete team
                cursor.execute("DELETE FROM teams WHERE id = %s", (team_id,))

            logger.info(f"✓ Team {team_id} deleted")
            return True, "Team deleted successfully"

        except Exception as e:
            logger.error(f"Error deleting team: {e}")
            return False, str(e)

    @staticmethod
    def get_team_statistics() -> dict:
        """Get aggregate statistics about teams"""
        try:
            with get_db_cursor(current_app) as cursor:
                # Total teams
                cursor.execute("SELECT COUNT(*) FROM teams WHERE status = 'active'")
                total_teams = cursor.fetchone()[0]

                # Teams by status
                cursor.execute("""
                    SELECT status, COUNT(*) as count FROM teams
                    GROUP BY status
                """)
                by_status = dict(cursor.fetchall())

                # Participant distribution
                cursor.execute("""
                    SELECT
                        COUNT(DISTINCT t.id) as teams,
                        COUNT(p.id) as total_participants,
                        MIN(COUNT(p.id) OVER (PARTITION BY t.id)) as min_per_team,
                        MAX(COUNT(p.id) OVER (PARTITION BY t.id)) as max_per_team,
                        AVG(COUNT(p.id) OVER (PARTITION BY t.id))::NUMERIC(5,2) as avg_per_team
                    FROM teams t
                    LEFT JOIN participants p ON t.id = p.team_id AND p.status = 'active'
                    WHERE t.status = 'active'
                """)
                dist = cursor.fetchone()
                participant_stats = {
                    'total_teams': dist[0],
                    'total_participants': dist[1],
                    'min_per_team': dist[2],
                    'max_per_team': dist[3],
                    'avg_per_team': dist[4]
                }

                return {
                    'total_active_teams': total_teams,
                    'by_status': by_status,
                    'participant_distribution': participant_stats
                }

        except Exception as e:
            logger.error(f"Error getting team statistics: {e}")
            return {}
