"""Participants management business logic - PostgreSQL version"""
import logging
from flask import current_app
from app.database import get_db_cursor, execute_query, execute_insert, execute_update
import psycopg2

logger = logging.getLogger(__name__)


class ParticipantService:
    """Service for managing hackathon participants"""

    @staticmethod
    def get_participant_by_id(participant_id: int) -> dict:
        """Get a participant by ID with all details"""
        query = """
            SELECT p.*, s.name as specialty, u.name as university, u.country,
                   t.team_name, t.id as team_id
            FROM participants p
            LEFT JOIN specialties s ON p.specialty_id = s.id
            LEFT JOIN universities u ON p.university_id = u.id
            LEFT JOIN teams t ON p.team_id = t.id
            WHERE p.id = %s
        """
        return execute_query(current_app, query, (participant_id,), fetch_one=True)

    @staticmethod
    def get_participant_by_email(email: str) -> dict:
        """Get a participant by email (unique lookup)"""
        query = """
            SELECT p.*, s.name as specialty, u.name as university,
                   t.team_name, t.id as team_id
            FROM participants p
            LEFT JOIN specialties s ON p.specialty_id = s.id
            LEFT JOIN universities u ON p.university_id = u.id
            LEFT JOIN teams t ON p.team_id = t.id
            WHERE p.email = %s
        """
        return execute_query(current_app, query, (email,), fetch_one=True)

    @staticmethod
    def get_participant_by_faculty_number(faculty_number: str) -> dict:
        """Get a participant by faculty number (unique lookup)"""
        query = """
            SELECT p.*, s.name as specialty, u.name as university,
                   t.team_name, t.id as team_id
            FROM participants p
            LEFT JOIN specialties s ON p.specialty_id = s.id
            LEFT JOIN universities u ON p.university_id = u.id
            LEFT JOIN teams t ON p.team_id = t.id
            WHERE p.faculty_number = %s
        """
        return execute_query(current_app, query, (faculty_number,), fetch_one=True)

    @staticmethod
    def get_team_participants(team_id: int, active_only=True) -> list:
        """Get all participants for a team

        Args:
            team_id: Team ID
            active_only: If True, only return active participants

        Returns:
            List of participant dictionaries
        """
        query = """
            SELECT p.*, s.name as specialty, u.name as university, u.country
            FROM participants p
            LEFT JOIN specialties s ON p.specialty_id = s.id
            LEFT JOIN universities u ON p.university_id = u.id
            WHERE p.team_id = %s
        """

        if active_only:
            query += " AND p.status = 'active'"

        query += " ORDER BY p.created_at"

        return execute_query(current_app, query, (team_id,), fetch_all=True) or []

    @staticmethod
    def get_participants_by_course(course: int) -> list:
        """Get all participants in a specific course year

        Args:
            course: Course number (1-4)

        Returns:
            List of participant dictionaries
        """
        if not 1 <= course <= 4:
            logger.error(f"Invalid course number: {course}")
            return []

        query = """
            SELECT p.*, s.name as specialty, u.name as university,
                   t.team_name, t.id as team_id
            FROM participants p
            LEFT JOIN specialties s ON p.specialty_id = s.id
            LEFT JOIN universities u ON p.university_id = u.id
            LEFT JOIN teams t ON p.team_id = t.id
            WHERE p.course = %s AND p.status = 'active'
            ORDER BY u.name, p.last_name
        """
        return execute_query(current_app, query, (course,), fetch_all=True) or []

    @staticmethod
    def get_participants_by_specialty(specialty_id: int) -> list:
        """Get all participants in a specific specialty"""
        query = """
            SELECT p.*, s.name as specialty, u.name as university,
                   t.team_name, t.id as team_id
            FROM participants p
            LEFT JOIN specialties s ON p.specialty_id = s.id
            LEFT JOIN universities u ON p.university_id = u.id
            LEFT JOIN teams t ON p.team_id = t.id
            WHERE p.specialty_id = %s AND p.status = 'active'
            ORDER BY t.team_name
        """
        return execute_query(current_app, query, (specialty_id,), fetch_all=True) or []

    @staticmethod
    def get_participants_by_university(university_id: int) -> list:
        """Get all participants from a specific university"""
        query = """
            SELECT p.*, s.name as specialty, u.name as university,
                   t.team_name, t.id as team_id
            FROM participants p
            LEFT JOIN specialties s ON p.specialty_id = s.id
            LEFT JOIN universities u ON p.university_id = u.id
            LEFT JOIN teams t ON p.team_id = t.id
            WHERE p.university_id = %s AND p.status = 'active'
            ORDER BY t.team_name, p.last_name
        """
        return execute_query(current_app, query, (university_id,), fetch_all=True) or []

    @staticmethod
    def create_participant(team_id: int, first_name: str, last_name: str,
                          email: str, phone_number: str, faculty_number: str,
                          course: int, specialty_id: int, university_id: int) -> tuple:
        """Create a new participant

        Args:
            team_id: Team ID to assign to
            first_name: First name
            last_name: Last name
            email: Email (must be unique)
            phone_number: Phone number
            faculty_number: Faculty number (must be unique)
            course: Course year (1-4)
            specialty_id: Specialty ID
            university_id: University ID

        Returns:
            Tuple (success: bool, message: str, participant_id: int or None)
        """
        # Validation
        if not all([first_name, last_name, email, phone_number, faculty_number]):
            return False, "All fields are required", None

        if not 1 <= course <= 4:
            return False, f"Course must be between 1 and 4, got {course}", None

        # Check if email already exists
        if ParticipantService.get_participant_by_email(email):
            return False, f"Email '{email}' is already in use", None

        # Check if faculty number already exists
        if ParticipantService.get_participant_by_faculty_number(faculty_number):
            return False, f"Faculty number '{faculty_number}' is already in use", None

        # Check team exists and has room
        from app.services.team_service import TeamService
        team = TeamService.get_team_by_id(team_id)
        if not team:
            return False, f"Team with ID {team_id} not found", None

        if team['participant_count'] >= 6:
            return False, "Team is already full (max 6 participants)", None

        # Insert participant
        query = """
            INSERT INTO participants
            (team_id, first_name, last_name, email, phone_number,
             faculty_number, course, specialty_id, university_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
            RETURNING id
        """

        try:
            participant_id = execute_insert(current_app, query, (
                team_id, first_name.strip(), last_name.strip(),
                email.strip(), phone_number.strip(), faculty_number.strip(),
                course, specialty_id, university_id
            ))

            logger.info(f"✓ Participant created: {first_name} {last_name} (ID: {participant_id})")
            return True, "Participant registered successfully", participant_id

        except psycopg2.IntegrityError as e:
            logger.error(f"Integrity error creating participant: {e}")
            return False, "Database constraint violation", None
        except Exception as e:
            logger.error(f"Error creating participant: {e}")
            return False, str(e), None

    @staticmethod
    def update_participant(participant_id: int, **kwargs) -> tuple:
        """Update participant information

        Args:
            participant_id: Participant ID
            **kwargs: Fields to update (email, phone_number, course, specialty_id, etc.)

        Returns:
            Tuple (success: bool, message: str)
        """
        # Get current participant
        participant = ParticipantService.get_participant_by_id(participant_id)
        if not participant:
            return False, f"Participant {participant_id} not found"

        # Build update query
        update_fields = []
        params = []
        param_count = 1

        for field, value in kwargs.items():
            if field not in ['team_id']:  # Don't allow changing team via this method
                update_fields.append(f"{field} = %s")
                params.append(value)
                param_count += 1

        if not update_fields:
            return False, "No fields to update"

        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(participant_id)

        query = f"UPDATE participants SET {', '.join(update_fields)} WHERE id = %s"

        try:
            rows = execute_update(current_app, query, tuple(params))
            if rows > 0:
                logger.info(f"✓ Participant {participant_id} updated")
                return True, "Participant updated successfully"
            else:
                return False, "No changes made"

        except psycopg2.IntegrityError as e:
            logger.error(f"Integrity error updating participant: {e}")
            return False, "Database constraint violation"
        except Exception as e:
            logger.error(f"Error updating participant: {e}")
            return False, str(e)

    @staticmethod
    def remove_participant(participant_id: int) -> tuple:
        """Remove a participant from a team (soft delete)

        Args:
            participant_id: Participant ID

        Returns:
            Tuple (success: bool, message: str)
        """
        participant = ParticipantService.get_participant_by_id(participant_id)
        if not participant:
            return False, f"Participant {participant_id} not found"

        query = "UPDATE participants SET status = 'removed', updated_at = CURRENT_TIMESTAMP WHERE id = %s"

        try:
            rows = execute_update(current_app, query, (participant_id,))
            if rows > 0:
                logger.info(f"✓ Participant {participant_id} removed")
                return True, "Participant removed successfully"
            else:
                return False, "Failed to remove participant"

        except Exception as e:
            logger.error(f"Error removing participant: {e}")
            return False, str(e)

    @staticmethod
    def delete_participant(participant_id: int) -> tuple:
        """Permanently delete a participant (hard delete)

        Args:
            participant_id: Participant ID

        Returns:
            Tuple (success: bool, message: str)
        """
        query = "DELETE FROM participants WHERE id = %s"

        try:
            rows = execute_update(current_app, query, (participant_id,))
            if rows > 0:
                logger.info(f"✓ Participant {participant_id} permanently deleted")
                return True, "Participant deleted permanently"
            else:
                return False, "Participant not found"

        except Exception as e:
            logger.error(f"Error deleting participant: {e}")
            return False, str(e)

    @staticmethod
    def get_participant_statistics() -> dict:
        """Get aggregate statistics about participants"""
        try:
            with get_db_cursor(current_app) as cursor:
                # Total counts
                cursor.execute("SELECT COUNT(*) FROM participants WHERE status = 'active'")
                total_active = cursor.fetchone()[0]

                # By course
                cursor.execute("""
                    SELECT course, COUNT(*) as count
                    FROM participants WHERE status = 'active'
                    GROUP BY course ORDER BY course
                """)
                by_course = {str(row[0]): row[1] for row in cursor.fetchall()}

                # By specialty
                cursor.execute("""
                    SELECT s.name, COUNT(*) as count
                    FROM participants p
                    LEFT JOIN specialties s ON p.specialty_id = s.id
                    WHERE p.status = 'active'
                    GROUP BY s.name ORDER BY count DESC
                """)
                by_specialty = dict(cursor.fetchall())

                # By university
                cursor.execute("""
                    SELECT u.name, COUNT(*) as count
                    FROM participants p
                    LEFT JOIN universities u ON p.university_id = u.id
                    WHERE p.status = 'active'
                    GROUP BY u.name ORDER BY count DESC
                """)
                by_university = dict(cursor.fetchall())

                return {
                    'total_active': total_active,
                    'by_course': by_course,
                    'by_specialty': by_specialty,
                    'by_university': by_university
                }

        except Exception as e:
            logger.error(f"Error getting participant statistics: {e}")
            return {}
