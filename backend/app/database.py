"""PostgreSQL Database initialization and utilities — connection-pooled"""

import logging
import time
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)

# Module-level pool — one per worker process (safe with gunicorn prefork)
_pool = None
# How long to wait for a pooled connection before giving up (seconds)
_pool_timeout = 5


def init_database(app):
    """Initialize a ThreadedConnectionPool and verify the schema exists."""
    global _pool, _pool_timeout

    min_conn = app.config.get("DB_POOL_MIN", 2)
    max_conn = app.config.get("DB_POOL_MAX", 20)
    _pool_timeout = app.config.get("DB_POOL_TIMEOUT", 5)

    max_retries = 10
    retry_delay = 3

    for attempt in range(1, max_retries + 1):
        try:
            _pool = ThreadedConnectionPool(
                min_conn,
                max_conn,
                app.config["DATABASE_URL"],
                cursor_factory=RealDictCursor,
            )

            # Quick schema check using a pooled connection
            conn = _pool.getconn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT EXISTS(
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'teams'
                    );
                """)
                tables_exist = cursor.fetchone()["exists"]
                if not tables_exist:
                    logger.warning("Database schema not found. Please run schema.sql manually.")
                    logger.warning(
                        "Execute: psql -U postgres -d fmi_hackathon_2026 -f database/schema.sql"
                    )
                cursor.close()
            finally:
                _pool.putconn(conn)

            logger.info(f"✓ PostgreSQL connection pool ready (min={min_conn}, max={max_conn})")
            return  # Exit the initialization function entirely on success

        except psycopg2.OperationalError as e:
            logger.warning(f"Database connection attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("Make sure PostgreSQL is running and credentials are correct.")
                raise  # Exhausted retries, crash the worker
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise


def close_pool():
    """Shut down the connection pool (call on app teardown)."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("Connection pool closed")


def get_db_connection(app=None):
    """Get a connection from the pool with a timeout.

    Raises psycopg2.pool.PoolError if no connection is available within the timeout.
    """
    if _pool is None:
        raise RuntimeError("Connection pool not initialized — call init_database first")

    deadline = time.monotonic() + _pool_timeout
    while True:
        try:
            return _pool.getconn()
        except psycopg2.pool.PoolError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


def return_db_connection(conn):
    """Return a connection to the pool."""
    if _pool is not None and conn is not None:
        _pool.putconn(conn)


@contextmanager
def get_db_cursor(app=None, commit=True):
    """Context manager for database operations using pooled connections.

    Usage:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM participants")
            results = cursor.fetchall()
    """
    conn = get_db_connection()
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
        return_db_connection(conn)


def execute_query(app, query, params=None, fetch_one=False, fetch_all=False):
    """Execute a query and optionally fetch results"""
    with get_db_cursor(app) as cursor:
        cursor.execute(query, params or ())

        if fetch_one:
            return cursor.fetchone()
        elif fetch_all:
            return cursor.fetchall()
        return None


def execute_insert(app, query, params):
    """Execute INSERT and return generated ID"""
    try:
        with get_db_cursor(app) as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result["id"] if result else None
    except psycopg2.IntegrityError as e:
        logger.error(f"Integrity error during insert: {e}")
        raise
    except Exception as e:
        logger.error(f"Insert error: {e}")
        raise


def execute_update(app, query, params):
    """Execute UPDATE/DELETE and return number of affected rows"""
    try:
        with get_db_cursor(app) as cursor:
            cursor.execute(query, params)
            return cursor.rowcount
    except Exception as e:
        logger.error(f"Update error: {e}")
        raise


def execute_batch(app, query, params_list):
    """Execute batch INSERT operations efficiently"""
    try:
        with get_db_cursor(app) as cursor:
            if "RETURNING" in query.upper():
                execute_values(cursor, query, params_list, fetch=True)
                return [row[0] for row in cursor.fetchall()]
            else:
                execute_values(cursor, query, params_list)
                return cursor.rowcount
    except Exception as e:
        logger.error(f"Batch execution error: {e}")
        raise
