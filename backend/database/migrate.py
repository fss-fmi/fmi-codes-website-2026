"""Apply pending SQL migrations from backend/database/migrations/, in order.

Usage (from backend/, or /app in the image):
    python -m database.migrate [--notify always|changes|never]

Each file runs in its own transaction together with its schema_migrations row,
so a failing file leaves no trace and stops the run. A session-level advisory
lock serialises concurrent runners (the manual Job and every backend pod's
initContainer). Migration files must be safe to re-run and must not contain
their own BEGIN/COMMIT.

Connection: DATABASE_URL if set, otherwise DB_HOST/DB_PORT/DB_NAME/DB_USER/
DB_PASSWORD (the backend's own variables). Results go to the Slack incoming
webhook in SLACK_MIGRATIONS_WEBHOOK_URL when set, labelled with MIGRATION_ENV.
"""

import argparse
import json
import logging
import os
import re
import sys
import urllib.request
from pathlib import Path

import psycopg2

logger = logging.getLogger("migrate")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
FILENAME_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
# Session-level lock; distinct from the transaction-level locks 1 and 2 the app takes.
LOCK_ID = 727_001

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        filename   VARCHAR(255) PRIMARY KEY,
        applied_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
"""


class MigrationError(Exception):
    def __init__(self, filename: str, applied: list[str], cause: Exception):
        super().__init__(f"{filename}: {cause}")
        self.filename = filename
        self.applied = applied


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """Every migration file, sorted by its numeric prefix. Rejects stray names."""
    files = []
    for path in directory.glob("*.sql"):
        if not FILENAME_RE.match(path.name):
            raise ValueError(f"Migration file name must look like 016_some_change.sql: {path.name}")
        files.append(path)
    numbers = [p.name[:3] for p in files]
    duplicates = {n for n in numbers if numbers.count(n) > 1}
    if duplicates:
        raise ValueError(f"Duplicate migration numbers: {', '.join(sorted(duplicates))}")
    return sorted(files, key=lambda p: p.name)


def _connection_params() -> str | dict:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
        "dbname": os.environ.get("DB_NAME", "fmi_hackathon_2026_dev"),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }


def apply_pending(params: str | dict, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every unrecorded migration and return the filenames applied.

    *params* is a DSN/URL string or psycopg2.connect keyword arguments.
    """
    files = migration_files(directory)
    applied: list[str] = []
    conn = psycopg2.connect(params) if isinstance(params, str) else psycopg2.connect(**params)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
            cur.execute(_CREATE_TABLE)
            conn.commit()

            cur.execute("SELECT filename FROM schema_migrations")
            done = {row[0] for row in cur.fetchall()}

            for path in files:
                if path.name in done:
                    continue
                logger.info("Applying %s", path.name)
                try:
                    cur.execute(path.read_text(encoding="utf-8"))
                    cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
                    )
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    raise MigrationError(path.name, applied, e) from e
                applied.append(path.name)
    finally:
        conn.close()  # also releases the advisory lock
    return applied


def _slack_escape(text: str) -> str:
    # Slack reads <...> as links/mentions; Postgres errors can contain all three.
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def notify(text: str) -> None:
    """Post *text* (Slack mrkdwn) to Slack. Never raises; a missing webhook is a no-op."""
    url = os.environ.get("SLACK_MIGRATIONS_WEBHOOK_URL", "")
    if not url:
        return
    req = urllib.request.Request(
        url,
        # Truncate before escaping so an entity is never cut in half.
        data=json.dumps({"text": _slack_escape(text[:3000])}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        logger.error("Could not post migration result to Slack: %s", e)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--notify",
        choices=("always", "changes", "never"),
        default="changes",
        help="When to post to Slack: every run, only when something applied or failed, or never",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    env = os.environ.get("MIGRATION_ENV", "unknown")
    backup = os.environ.get("MIGRATION_BACKUP_FILE", "")
    backup_note = f"\nBackup: `{backup}`" if backup else ""

    try:
        applied = apply_pending(_connection_params())
    except MigrationError as e:
        logger.error("Migration failed: %s", e)
        done = ", ".join(e.applied) or "none"
        if args.notify != "never":
            notify(
                f"❌ *DB migration failed* on `{env}` at `{e.filename}` (rolled back).\n"
                f"Applied before the failure: {done}.\nError: {e.__cause__}{backup_note}"
            )
        return 1
    except Exception as e:
        logger.error("Migration run failed: %s", e)
        if args.notify != "never":
            notify(f"❌ *DB migration run failed* on `{env}` before applying anything: {e}")
        return 1

    if applied:
        logger.info("Applied %d migration(s): %s", len(applied), ", ".join(applied))
    else:
        logger.info("No pending migrations")

    if args.notify == "always" or (args.notify == "changes" and applied):
        summary = ", ".join(f"`{name}`" for name in applied) or "nothing pending"
        notify(f"✅ *DB migration* on `{env}`: {summary}.{backup_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
