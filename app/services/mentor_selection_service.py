"""Mentor selection business logic"""
import sqlite3
from flask import current_app
from app.database import get_db_connection
from app.services.mentor_service import serialize_mentor_row


def get_available_mentors_for_team(team_id: int) -> dict:
    """Get available mentors or current team's selection
    
    Returns specific team's selection if already chosen, otherwise mentors with capacity < 3
    
    Returns:
        Dict with 'selected' and 'available' lists
    """
    conn = get_db_connection(current_app)
    cursor = conn.cursor()

    # Current selection for this team
    cursor.execute('''
        SELECT m.*, tm.mentor_id
        FROM mentors m
        JOIN team_mentors tm ON tm.mentor_id = m.id
        WHERE tm.team_id = ?
    ''', (team_id,))
    selected_rows = cursor.fetchall()

    # Selection counts per mentor
    cursor.execute('SELECT mentor_id, COUNT(*) as cnt FROM team_mentors GROUP BY mentor_id')
    counts = {row['mentor_id']: row['cnt'] for row in cursor.fetchall()}

    result = {}

    if selected_rows:
        result['selected'] = [serialize_mentor_row(row, counts.get(row['id'], 0)) for row in selected_rows]
        result['available'] = []
    else:
        # If no selection yet, return mentors with capacity < 3
        cursor.execute('SELECT * FROM mentors')
        mentors = []
        for row in cursor.fetchall():
            selection_count = counts.get(row['id'], 0)
            if selection_count < 3:
                mentors.append(serialize_mentor_row(row, selection_count))
        result['selected'] = []
        result['available'] = mentors

    conn.close()
    return result


def select_mentors_for_team(team_id: int, mentor_ids: list) -> tuple:
    """Select mentors for a team (exactly 3)
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    if len(mentor_ids) != 3:
        return False, 'You must select exactly 3 mentors'

    conn = get_db_connection(current_app)
    cursor = conn.cursor()

    try:
        # Validate mentor existence and capacity (max 3 teams)
        cursor.execute('SELECT mentor_id, COUNT(*) as cnt FROM team_mentors GROUP BY mentor_id')
        counts = {row['mentor_id']: row['cnt'] for row in cursor.fetchall()}

        cursor.execute('SELECT mentor_id FROM team_mentors WHERE team_id = ?', (team_id,))
        existing_selection = {row['mentor_id'] for row in cursor.fetchall()}

        full_mentors = []
        for mentor_id in mentor_ids:
            cursor.execute('SELECT id FROM mentors WHERE id = ?', (mentor_id,))
            if cursor.fetchone() is None:
                conn.close()
                return False, f'Mentor with id {mentor_id} does not exist'

            current_count = counts.get(mentor_id, 0)
            # Allow keeping already selected mentors even if at capacity
            if mentor_id not in existing_selection and current_count >= 3:
                full_mentors.append(mentor_id)

        if full_mentors:
            conn.close()
            return False, 'One or more mentors are already at capacity (3 teams). Please pick others.'

        # Replace selection
        cursor.execute('DELETE FROM team_mentors WHERE team_id = ?', (team_id,))
        for mentor_id in mentor_ids:
            cursor.execute('INSERT INTO team_mentors (team_id, mentor_id) VALUES (?, ?)', (team_id, mentor_id))

        conn.commit()
        return True, 'Mentors selected successfully'

    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
