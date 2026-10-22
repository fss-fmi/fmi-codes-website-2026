"""E2E tests for the migration runner against a real PostgreSQL database.

Covers:
 - Every committed migration applies cleanly on a schema.sql database and is recorded
 - A second run applies nothing
 - A failing file rolls back on its own and stops the run
 - The advisory lock serialises concurrent runners
"""

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from database import migrate

pytestmark = pytest.mark.e2e

PROBE_TABLES = ("migrate_probe_ok", "migrate_probe_bad", "migrate_probe_never")


@pytest.fixture()
def fresh_history(db_conn):
    """Start and end every test with no schema_migrations table and no probe tables."""

    def reset():
        with db_conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS schema_migrations")
            for table in PROBE_TABLES:
                cur.execute(f"DROP TABLE IF EXISTS {table}")

    reset()
    yield
    reset()


def _recorded(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
        return [r["filename"] for r in cur.fetchall()]


def _table_exists(db_conn, name):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS present", (name,))
        return cur.fetchone()["present"]


def test_repository_migrations_apply_and_rerun_as_noop(db_url, db_conn, fresh_history):
    expected = [p.name for p in migrate.migration_files()]

    assert migrate.apply_pending(db_url) == expected
    assert _recorded(db_conn) == expected
    assert migrate.apply_pending(db_url) == []


def test_only_new_files_are_applied(db_url, db_conn, fresh_history, tmp_path):
    (tmp_path / "001_ok.sql").write_text("CREATE TABLE migrate_probe_ok (id int);")
    assert migrate.apply_pending(db_url, tmp_path) == ["001_ok.sql"]

    (tmp_path / "002_never.sql").write_text("CREATE TABLE migrate_probe_never (id int);")
    assert migrate.apply_pending(db_url, tmp_path) == ["002_never.sql"]
    assert _recorded(db_conn) == ["001_ok.sql", "002_never.sql"]


def test_failing_file_rolls_back_and_stops(db_url, db_conn, fresh_history, tmp_path):
    (tmp_path / "001_ok.sql").write_text("CREATE TABLE migrate_probe_ok (id int);")
    (tmp_path / "002_bad.sql").write_text("CREATE TABLE migrate_probe_bad (id int);\nSELECT 1 / 0;")
    (tmp_path / "003_never.sql").write_text("CREATE TABLE migrate_probe_never (id int);")

    with pytest.raises(migrate.MigrationError) as excinfo:
        migrate.apply_pending(db_url, tmp_path)

    assert excinfo.value.filename == "002_bad.sql"
    assert excinfo.value.applied == ["001_ok.sql"]
    assert _recorded(db_conn) == ["001_ok.sql"]
    assert _table_exists(db_conn, "migrate_probe_ok")
    assert not _table_exists(db_conn, "migrate_probe_bad")
    assert not _table_exists(db_conn, "migrate_probe_never")


def test_concurrent_runner_waits_for_the_lock(db_url, db_conn, fresh_history, tmp_path):
    (tmp_path / "001_ok.sql").write_text("CREATE TABLE migrate_probe_ok (id int);")
    result = {}

    with db_conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", (migrate.LOCK_ID,))
    try:
        runner = threading.Thread(
            target=lambda: result.setdefault("applied", migrate.apply_pending(db_url, tmp_path))
        )
        runner.start()
        time.sleep(1)
        assert runner.is_alive(), "runner must block while another session holds the lock"
        assert not _table_exists(db_conn, "migrate_probe_ok")
    finally:
        with db_conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (migrate.LOCK_ID,))

    runner.join(timeout=10)
    assert not runner.is_alive()
    assert result["applied"] == ["001_ok.sql"]
