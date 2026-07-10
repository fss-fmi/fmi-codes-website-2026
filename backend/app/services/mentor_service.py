"""Mentor management business logic - PostgreSQL version"""

import base64
import json
import logging
import threading
import time
from pathlib import Path

import psycopg2
from flask import current_app

from app.database import execute_insert, execute_query, execute_update, get_db_cursor

logger = logging.getLogger(__name__)

# ── In-memory cache for get_all_mentors (mirrors regulations_service pattern) ──
_mentor_cache_lock = threading.Lock()
_mentor_cache = None
_mentor_cache_ts = 0
_MENTOR_CACHE_TTL = 60  # seconds


def mentor_exists(first_name: str, last_name: str, company_name: str, email: str = None) -> bool:
    """Check if a mentor already exists. Prefers email lookup when available."""
    if email:
        result = execute_query(
            current_app,
            "SELECT 1 FROM mentors WHERE email = %s",
            (email,),
            fetch_one=True,
        )
        if result is not None:
            return True
    query = """
        SELECT 1 FROM mentors
        WHERE first_name = %s AND last_name = %s AND company_name = %s
    """
    result = execute_query(
        current_app, query, (first_name, last_name, company_name), fetch_one=True
    )
    return result is not None


def register_mentor(
    first_name: str, last_name: str, company_name: str, picture_data=None, picture_filename=None
) -> tuple:
    """Register a new mentor

    Returns:
        Tuple of (success: bool, message: str, mentor_id: int or None)
    """
    if not first_name or not last_name or not company_name:
        return False, "All fields are required", None

    if not picture_data:
        return False, "Picture is required", None

    query = """
        INSERT INTO mentors (first_name, last_name, company_name, picture_url, picture_filename)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """

    try:
        mentor_id = execute_insert(
            current_app,
            query,
            (first_name, last_name, company_name, picture_data, picture_filename),
        )
        logger.info(f"✓ Mentor registered: {first_name} {last_name} (ID: {mentor_id})")
        _invalidate_mentor_cache()
        return True, f'Mentor "{first_name} {last_name}" registered successfully', mentor_id

    except psycopg2.IntegrityError as e:
        logger.error(f"Integrity error registering mentor: {e}")
        return False, "Mentor already exists or constraint violated", None
    except Exception as e:
        logger.error(f"Error registering mentor: {e}")
        return False, str(e), None


def get_all_mentors() -> list:
    """Get all registered mentors (cached for 60s to handle high concurrency)"""
    global _mentor_cache, _mentor_cache_ts

    # Capture the reference into a local variable first so that a concurrent
    # _invalidate_mentor_cache() call cannot set the global to None between the
    # "is not None" check and the actual return, which would hand callers None.
    cached = _mentor_cache
    now = time.monotonic()
    if cached is not None and (now - _mentor_cache_ts) < _MENTOR_CACHE_TTL:
        return cached

    with _mentor_cache_lock:
        # Double-check after acquiring lock (same safe capture pattern)
        cached = _mentor_cache
        if cached is not None and (time.monotonic() - _mentor_cache_ts) < _MENTOR_CACHE_TTL:
            return cached

        query = """
            SELECT id AS mentor_id,
                   first_name || ' ' || last_name AS name,
                   first_name, last_name, email, phone_number, company_name,
                   bio, status, technologies, picture_url, picture_filename,
                   availability_text, created_at
            FROM mentors
            WHERE status = 'active'
            ORDER BY created_at DESC
        """
        try:
            result = execute_query(current_app, query, fetch_all=True) or []
            _mentor_cache = result
            _mentor_cache_ts = time.monotonic()
            return result
        except Exception as e:
            raise Exception(f"Failed to get mentors: {str(e)}") from e


def _invalidate_mentor_cache():
    """Clear cached mentor list so the next read fetches fresh data."""
    global _mentor_cache, _mentor_cache_ts
    # Hold the lock so the two-field clear is atomic with respect to readers
    # that use the lock path, and so local-ref capture in get_all_mentors is safe.
    with _mentor_cache_lock:
        _mentor_cache = None
        _mentor_cache_ts = 0


def get_mentor_picture(mentor_id: int) -> tuple:
    """Get mentor picture and filename by ID

    Returns:
        Tuple of (picture_data, filename) or (None, None)
    """
    query = "SELECT picture_url, picture_filename FROM mentors WHERE id = %s"
    try:
        result = execute_query(current_app, query, (mentor_id,), fetch_one=True)
        if result and result["picture_url"]:
            return result["picture_url"], result["picture_filename"]
        return None, None
    except Exception as e:
        raise Exception(f"Failed to get mentor picture: {str(e)}") from e


def delete_mentor(mentor_id: int) -> tuple:
    """Delete a mentor

    Returns:
        Tuple of (success: bool, message: str)
    """
    query = "DELETE FROM mentors WHERE id = %s"
    try:
        rows = execute_update(current_app, query, (mentor_id,))
        if rows == 0:
            return False, "Mentor not found"
        logger.info(f"✓ Mentor {mentor_id} deleted")
        _invalidate_mentor_cache()
        return True, "Mentor deleted successfully"
    except Exception as e:
        logger.error(f"Error deleting mentor: {e}")
        return False, str(e)


def load_mentors_from_file(json_path: Path) -> int:
    """Load mentors from a JSON file into the database if not already present

    Returns:
        Number of mentors inserted
    """
    if not json_path.exists():
        return 0

    with open(json_path, encoding="utf-8") as f:
        mentors = json.load(f)

    if not isinstance(mentors, list):
        return 0

    inserted = 0

    from app.services.auth_service import hash_password as _hash_pw

    for mentor in mentors:
        first_name = str(mentor.get("first_name", "")).strip()
        last_name = str(mentor.get("last_name", "")).strip()
        company_name = str(mentor.get("company_name", "")).strip()
        picture_path = mentor.get("picture_url")
        email = str(mentor.get("email", "")).strip() or None

        if not first_name or not last_name or not company_name:
            continue

        if mentor_exists(first_name, last_name, company_name, email=email):
            continue

        # picture_url is stored as a URL string (e.g. /static/mentorPictures/alice.jpg)
        # If the value is a bare filename, normalise it to the expected static path.
        picture_data = None
        picture_filename = None
        if picture_path:
            p = str(picture_path).strip()
            if p.startswith(("http://", "https://", "/")):
                picture_data = p  # already a full URL or absolute path
            else:
                picture_data = f"/static/mentorPictures/{p}"
            picture_filename = Path(p).name

        phone_number = str(mentor.get("phone_number", "")).strip() or None
        bio = str(mentor.get("bio", "")).strip() or None
        status = str(mentor.get("status", "active")).strip()
        technologies = mentor.get("technologies", [])
        if not isinstance(technologies, list):
            technologies = []
        availability_text = str(mentor.get("availability_text", "")).strip() or None
        raw_password = mentor.get("password", "mentor123")
        pw_hash = _hash_pw(raw_password)

        query = """
            INSERT INTO mentors (first_name, last_name, company_name, email, phone_number,
                                 bio, status, picture_url, picture_filename, password_hash,
                                 technologies, availability_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uidx_mentors_identity DO NOTHING
        """

        try:
            with get_db_cursor(current_app) as cursor:
                cursor.execute(
                    query,
                    (
                        first_name,
                        last_name,
                        company_name,
                        email,
                        phone_number,
                        bio,
                        status,
                        picture_data,
                        picture_filename,
                        pw_hash,
                        technologies,
                        availability_text,
                    ),
                )
                if cursor.rowcount:
                    inserted += 1
        except psycopg2.IntegrityError:
            continue
        except Exception as e:
            logger.error(f"Error inserting mentor {first_name} {last_name}: {e}")
            continue

    logger.info(f"✓ Loaded {inserted} mentors from {json_path}")
    return inserted


def load_specialties_from_file(json_path: Path) -> int:
    """Load specialties from a JSON file into the database if not already present

    Returns:
        Number of specialties inserted
    """
    if not json_path.exists():
        return 0

    with open(json_path, encoding="utf-8") as f:
        specialties = json.load(f)

    if not isinstance(specialties, list):
        return 0

    inserted = 0

    for item in specialties:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        description = item.get("description") or None

        query = """
            INSERT INTO specialties (name, description, is_seed)
            VALUES (%s, %s, TRUE)
            ON CONFLICT (name) DO NOTHING
        """
        try:
            with get_db_cursor(current_app) as cursor:
                cursor.execute(query, (name, description))
                if cursor.rowcount:
                    inserted += 1
        except Exception as e:
            logger.error(f"Error inserting specialty '{name}': {e}")
            continue

    logger.info(f"✓ Loaded {inserted} specialties from {json_path}")
    return inserted


def load_universities_from_file(json_path: Path) -> int:
    """Load universities from a JSON file into the database if not already present

    Returns:
        Number of universities inserted
    """
    if not json_path.exists():
        return 0

    with open(json_path, encoding="utf-8") as f:
        universities = json.load(f)

    if not isinstance(universities, list):
        return 0

    inserted = 0

    for item in universities:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        city = str(item.get("city", "")).strip() or None
        country = str(item.get("country", "")).strip() or None

        query = """
            INSERT INTO universities (name, city, country, is_seed)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (name) DO NOTHING
        """
        try:
            with get_db_cursor(current_app) as cursor:
                cursor.execute(query, (name, city, country))
                if cursor.rowcount:
                    inserted += 1
        except Exception as e:
            logger.error(f"Error inserting university '{name}': {e}")
            continue

    logger.info(f"✓ Loaded {inserted} universities from {json_path}")
    return inserted


def serialize_mentor_row(row, selection_count=0) -> dict:
    """Serialize mentor row with optional picture and selection count"""
    data = {
        "id": row["id"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "company_name": row["company_name"],
        "picture_filename": row.get("picture_filename"),
        "technologies": row.get("technologies") or [],
        "selection_count": selection_count,
    }
    picture_blob = row.get("picture_url")
    if picture_blob:
        data["picture_data"] = base64.b64encode(picture_blob).decode("utf-8")
    else:
        data["picture_data"] = None
    return data
