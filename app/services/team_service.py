"""Team management business logic"""
import sqlite3
from flask import current_app
from app.database import get_db_connection


def get_team_by_name(team_name: str) -> dict:
    """Get team details and participants by team name"""
    conn = get_db_connection(current_app)
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM teams WHERE team_name = ?', (team_name,))
    team = cursor.fetchone()

    if team:
        cursor.execute('SELECT * FROM participants WHERE team_id = ?', (team['id'],))
        participants = [dict(row) for row in cursor.fetchall()]
        team_dict = dict(team)
        team_dict['participants'] = participants
    else:
        team_dict = None

    conn.close()
    return team_dict


def get_all_teams() -> list:
    """Get all teams with their participants"""
    conn = get_db_connection(current_app)
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM teams ORDER BY created_at DESC')
    teams = [dict(row) for row in cursor.fetchall()]

    for team in teams:
        cursor.execute('SELECT * FROM participants WHERE team_id = ?', (team['id'],))
        team['participants'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return teams


def register_team(team_name: str, password: str, participants: list) -> tuple:
    """Register a new team with participants
    
    Returns:
        Tuple of (success: bool, message: str, team_id: int or None)
    """
    # Validation
    if not team_name:
        return False, 'Team name is required', None

    if not password:
        return False, 'Password is required', None

    if len(participants) < 3 or len(participants) > 6:
        return False, 'Team must have 3-6 participants', None

    # Check if team already exists
    if get_team_by_name(team_name):
        return False, f'Team name "{team_name}" is already taken. Please choose a different name.', None

    # Insert into database
    conn = get_db_connection(current_app)
    cursor = conn.cursor()

    try:
        # Insert team
        cursor.execute(
            'INSERT INTO teams (team_name, password, participant_count) VALUES (?, ?, ?)',
            (team_name, password, len(participants))
        )
        team_id = cursor.lastrowid

        # Insert participants
        for participant in participants:
            cursor.execute(
                '''INSERT INTO participants
                   (team_id, first_name, last_name, faculty_number, discord)
                   VALUES (?, ?, ?, ?, ?)''',
                (
                    team_id,
                    participant.get('firstName', '').strip(),
                    participant.get('lastName', '').strip(),
                    participant.get('facultyNumber', '').strip(),
                    participant.get('discord', '').strip()
                )
            )

        conn.commit()
        message = f'Team "{team_name}" registered successfully with {len(participants)} participants'
        return True, message, team_id

    except sqlite3.IntegrityError as e:
        conn.rollback()
        return False, f'Database error: {str(e)}', None
    finally:
        conn.close()


def delete_team(team_name: str) -> tuple:
    """Delete a team and its participants
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    conn = get_db_connection(current_app)
    cursor = conn.cursor()

    try:
        # Get team
        cursor.execute('SELECT id FROM teams WHERE team_name = ?', (team_name,))
        team = cursor.fetchone()

        if not team:
            return False, 'Team not found'

        team_id = team[0]

        # Delete participants
        cursor.execute('DELETE FROM participants WHERE team_id = ?', (team_id,))

        # Delete team mentors
        cursor.execute('DELETE FROM team_mentors WHERE team_id = ?', (team_id,))

        # Delete team
        cursor.execute('DELETE FROM teams WHERE id = ?', (team_id,))

        conn.commit()
        return True, f'Team "{team_name}" deleted successfully'

    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def verify_team_credentials(team_name: str, password: str) -> tuple:
    """Verify team login credentials
    
    Returns:
        Tuple of (success: bool, team_id: int or None)
    """
    conn = get_db_connection(current_app)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM teams WHERE team_name = ? AND password = ?', (team_name, password))
    team = cursor.fetchone()
    conn.close()

    if team:
        return True, team['id']
    else:
        return False, None
