"""PostgreSQL Database initialization and utilities"""
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def init_database(app):
    """Initialize PostgreSQL database connection and verify schema exists"""
    try:
        conn = get_db_connection(app)
        cursor = conn.cursor()

        # Verify that required tables exist
        cursor.execute("""
            SELECT EXISTS(
                SELECT FROM information_schema.tables
                WHERE table_name = 'teams'
            );
        """)
        tables_exist = cursor.fetchone()["exists"]

        if not tables_exist:
            logger.warning("Database schema not found. Please run schema.sql manually.")
            logger.warning("Execute: psql -U postgres -d fmi_hackathon_2026 -f database/schema.sql")

        cursor.close()
        conn.close()

        logger.info("✓ PostgreSQL database connection verified")

    except psycopg2.OperationalError as e:
        logger.error(f"Cannot connect to PostgreSQL: {e}")
        logger.error("Make sure PostgreSQL is running and credentials are correct")
        raise
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise


def get_db_connection(app):
    """Get a PostgreSQL database connection with RealDictCursor for dict-like row access"""
    try:
        conn = psycopg2.connect(app.config['DATABASE_URL'])
        # Set to return rows as dictionaries instead of tuples
        conn.cursor_factory = RealDictCursor
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise


@contextmanager
def get_db_cursor(app, commit=True):
    """Context manager for database operations

    Usage:
        with get_db_cursor(app) as cursor:
            cursor.execute("SELECT * FROM participants")
            results = cursor.fetchall()
    """
    conn = get_db_connection(app)
    cursor = conn.cursor()
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def execute_query(app, query, params=None, fetch_one=False, fetch_all=False):
    """Execute a query and optionally fetch results

    Args:
        app: Flask application instance
        query: SQL query string (use %s for parameters)
        params: Tuple or list of parameters
        fetch_one: If True, fetch single row
        fetch_all: If True, fetch all rows

    Returns:
        Query result or None
    """
    with get_db_cursor(app) as cursor:
        cursor.execute(query, params or ())

        if fetch_one:
            return cursor.fetchone()
        elif fetch_all:
            return cursor.fetchall()
        return None


def execute_insert(app, query, params):
    """Execute INSERT and return generated ID

    Args:
        app: Flask application instance
        query: SQL query string with RETURNING id clause
        params: Tuple or list of parameters

    Returns:
        Generated ID or None
    """
    try:
        with get_db_cursor(app) as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result['id'] if result else None
    except psycopg2.IntegrityError as e:
        logger.error(f"Integrity error during insert: {e}")
        raise
    except Exception as e:
        logger.error(f"Insert error: {e}")
        raise


def execute_update(app, query, params):
    """Execute UPDATE/DELETE and return number of affected rows

    Args:
        app: Flask application instance
        query: SQL query string
        params: Tuple or list of parameters

    Returns:
        Number of rows affected
    """
    try:
        with get_db_cursor(app) as cursor:
            cursor.execute(query, params)
            return cursor.rowcount
    except Exception as e:
        logger.error(f"Update error: {e}")
        raise


def execute_batch(app, query, params_list):
    """Execute batch INSERT operations efficiently

    Args:
        app: Flask application instance
        query: SQL query string
        params_list: List of parameter tuples

    Returns:
        List of generated IDs or None
    """
    try:
        with get_db_cursor(app) as cursor:
            if 'RETURNING' in query.upper():
                execute_values(cursor, query, params_list, fetch=True)
                return [row[0] for row in cursor.fetchall()]
            else:
                execute_values(cursor, query, params_list)
                return cursor.rowcount
    except Exception as e:
        logger.error(f"Batch operation error: {e}")
        raise

