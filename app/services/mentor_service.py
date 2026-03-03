"""Mentor management business logic"""
import sqlite3
import base64
import json
from pathlib import Path
from flask import current_app
from app.database import get_db_connection


def mentor_exists(name: str, surname: str, workplace: str) -> bool:
    """Check if a mentor already exists by identity fields"""
    conn = get_db_connection(current_app)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT 1 FROM mentors WHERE name = ? AND surname = ? AND workplace = ?',
        (name, surname, workplace)
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def register_mentor(name: str, surname: str, workplace: str, picture_data=None, picture_filename=None) -> tuple:
    """Register a new mentor
    
    Returns:
        Tuple of (success: bool, message: str, mentor_id: int or None)
    """
    # Validation
    if not name or not surname or not workplace:
        return False, 'All fields are required', None

    if not picture_data:
        return False, 'Picture is required', None

    # Insert into database
    conn = get_db_connection(current_app)
    cursor = conn.cursor()

    try:
        cursor.execute(
            '''INSERT INTO mentors (name, surname, workplace, picture, picture_filename)
               VALUES (?, ?, ?, ?, ?)''',
            (name, surname, workplace, picture_data, picture_filename)
        )
        conn.commit()
        mentor_id = cursor.lastrowid
        message = f'Mentor "{name} {surname}" registered successfully'
        return True, message, mentor_id

    except sqlite3.IntegrityError as e:
        conn.rollback()
        return False, str(e), None
    finally:
        conn.close()


def get_all_mentors() -> list:
    """Get all registered mentors"""
    try:
        conn = get_db_connection(current_app)
        cursor = conn.cursor()

        cursor.execute('SELECT id, name, surname, workplace, picture_filename, created_at FROM mentors ORDER BY created_at DESC')
        mentors = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return mentors

    except Exception as e:
        raise Exception(f'Failed to get mentors: {str(e)}')


def get_mentor_picture(mentor_id: int) -> tuple:
    """Get mentor picture and filename by ID
    
    Returns:
        Tuple of (picture_data, filename) or (None, None)
    """
    try:
        conn = get_db_connection(current_app)
        cursor = conn.cursor()

        cursor.execute('SELECT picture, picture_filename FROM mentors WHERE id = ?', (mentor_id,))
        result = cursor.fetchone()
        conn.close()

        if result and result[0]:
            return result[0], result[1]
        return None, None

    except Exception as e:
        raise Exception(f'Failed to get mentor picture: {str(e)}')


def delete_mentor(mentor_id: int) -> tuple:
    """Delete a mentor
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        conn = get_db_connection(current_app)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM mentors WHERE id = ?', (mentor_id,))

        if cursor.rowcount == 0:
            return False, 'Mentor not found'

        conn.commit()
        conn.close()

        return True, 'Mentor deleted successfully'

    except Exception as e:
        return False, str(e)


def load_mentors_from_file(json_path: Path) -> int:
    """Load mentors from a JSON file into the database if not already present
    
    Returns:
        Number of mentors inserted
    """
    if not json_path.exists():
        return 0

    with open(json_path, 'r', encoding='utf-8') as f:
        mentors = json.load(f)

    if not isinstance(mentors, list):
        return 0

    conn = get_db_connection(current_app)
    cursor = conn.cursor()
    inserted = 0

    for mentor in mentors:
        name = str(mentor.get('name', '')).strip()
        surname = str(mentor.get('surname', '')).strip()
        workplace = str(mentor.get('workplace', '')).strip()
        picture_path = mentor.get('picturePath')

        if not name or not surname or not workplace:
            continue

        if mentor_exists(name, surname, workplace):
            continue

        picture_data = None
        picture_filename = None
        if picture_path:
            resolved_path = (json_path.parent / picture_path).resolve()
            if resolved_path.exists():
                with open(resolved_path, 'rb') as img_file:
                    picture_data = img_file.read()
                picture_filename = resolved_path.name

        try:
            cursor.execute(
                '''INSERT OR IGNORE INTO mentors (name, surname, workplace, picture, picture_filename)
                   VALUES (?, ?, ?, ?, ?)''',
                (name, surname, workplace, picture_data, picture_filename)
            )
            if cursor.rowcount:
                inserted += 1
        except sqlite3.IntegrityError:
            continue

    conn.commit()
    conn.close()
    return inserted


def serialize_mentor_row(row, selection_count=0) -> dict:
    """Serialize mentor row with optional picture and selection count"""
    data = {
        'id': row['id'],
        'name': row['name'],
        'surname': row['surname'],
        'workplace': row['workplace'],
        'picture_filename': row.get('picture_filename'),
        'selection_count': selection_count
    }
    picture_blob = row.get('picture')
    if picture_blob:
        data['picture_data'] = base64.b64encode(picture_blob).decode('utf-8')
    else:
        data['picture_data'] = None
    return data
