"""Unit tests for backend/database/migrate.py (no database needed).

The apply path against real Postgres is covered in tests/e2e/test_migrate_e2e.py.
"""

import json
import re

import pytest
from database import migrate


def _touch(directory, *names):
    for name in names:
        (directory / name).write_text("SELECT 1;", encoding="utf-8")


class TestMigrationFiles:
    def test_sorted_by_number(self, tmp_path):
        _touch(tmp_path, "013_b.sql", "002_a.sql", "120_c.sql")
        assert [p.name for p in migrate.migration_files(tmp_path)] == [
            "002_a.sql",
            "013_b.sql",
            "120_c.sql",
        ]

    @pytest.mark.parametrize("name", ["16_short.sql", "016-dash.sql", "016_Upper.sql", "x.sql"])
    def test_rejects_bad_names(self, tmp_path, name):
        _touch(tmp_path, name)
        with pytest.raises(ValueError, match="file name"):
            migrate.migration_files(tmp_path)

    def test_rejects_duplicate_numbers(self, tmp_path):
        _touch(tmp_path, "016_a.sql", "016_b.sql")
        with pytest.raises(ValueError, match="Duplicate migration numbers: 016"):
            migrate.migration_files(tmp_path)


class TestRepositoryMigrations:
    """Rules every committed migration must follow."""

    def test_all_names_valid(self):
        assert migrate.migration_files()

    @pytest.mark.parametrize("path", migrate.migration_files(), ids=lambda p: p.name)
    def test_no_transaction_control(self, path):
        # The runner wraps each file in its own transaction together with its
        # schema_migrations row; a COMMIT inside the file would break that.
        sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
        assert not re.search(r"^\s*(BEGIN|COMMIT|ROLLBACK|START\s+TRANSACTION)\b", sql, re.I | re.M)


class TestMain:
    @pytest.fixture()
    def posted(self, monkeypatch):
        messages = []
        monkeypatch.setattr(migrate, "notify", messages.append)
        monkeypatch.setenv("MIGRATION_ENV", "fmi-codes-staging")
        return messages

    def test_changes_mode_is_quiet_when_nothing_pending(self, monkeypatch, posted):
        monkeypatch.setattr(migrate, "apply_pending", lambda params: [])
        assert migrate.main(["--notify", "changes"]) == 0
        assert posted == []

    def test_changes_mode_reports_applied(self, monkeypatch, posted):
        monkeypatch.setattr(migrate, "apply_pending", lambda params: ["016_email_verification.sql"])
        assert migrate.main(["--notify", "changes"]) == 0
        assert "016_email_verification.sql" in posted[0]
        assert "fmi-codes-staging" in posted[0]

    def test_always_mode_reports_noop_with_backup(self, monkeypatch, posted):
        monkeypatch.setattr(migrate, "apply_pending", lambda params: [])
        monkeypatch.setenv("MIGRATION_BACKUP_FILE", "/backups/x.sql.gz")
        assert migrate.main(["--notify", "always"]) == 0
        assert "nothing pending" in posted[0]
        assert "/backups/x.sql.gz" in posted[0]

    def test_never_mode_stays_quiet_on_failure(self, monkeypatch, posted):
        def fail(params):
            raise migrate.MigrationError("017_bad.sql", [], RuntimeError("boom"))

        monkeypatch.setattr(migrate, "apply_pending", fail)
        assert migrate.main(["--notify", "never"]) == 1
        assert posted == []

    def test_failure_reports_file_and_earlier_successes(self, monkeypatch, posted):
        def fail(params):
            cause = RuntimeError("relation does not exist")
            raise migrate.MigrationError("018_bad.sql", ["017_ok.sql"], cause) from cause

        monkeypatch.setattr(migrate, "apply_pending", fail)
        assert migrate.main([]) == 1
        assert "018_bad.sql" in posted[0]
        assert "017_ok.sql" in posted[0]
        assert "relation does not exist" in posted[0]

    def test_connection_error_is_reported(self, monkeypatch, posted):
        def fail(params):
            raise OSError("could not connect")

        monkeypatch.setattr(migrate, "apply_pending", fail)
        assert migrate.main([]) == 1
        assert "could not connect" in posted[0]


class TestConnectionParams:
    def test_database_url_wins(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        assert migrate._connection_params() == "postgresql://u:p@h/db"

    def test_backend_variables(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        for key, value in {
            "DB_HOST": "postgres.fmi-codes.svc",
            "DB_PORT": "5432",
            "DB_NAME": "fmi",
            "DB_USER": "fmi_app",
            "DB_PASSWORD": "has spaces ' and quotes",
        }.items():
            monkeypatch.setenv(key, value)
        params = migrate._connection_params()
        assert params["host"] == "postgres.fmi-codes.svc"
        assert params["password"] == "has spaces ' and quotes"


class TestConnect:
    @pytest.fixture()
    def clock(self, monkeypatch):
        now = [0.0]

        def sleep(seconds):
            now[0] += seconds

        monkeypatch.setattr(migrate.time, "monotonic", lambda: now[0])
        monkeypatch.setattr(migrate.time, "sleep", sleep)
        return now

    def _refuse(self, monkeypatch, refusals):
        calls = []

        def connect(*args, **kwargs):
            calls.append((args, kwargs))
            if len(calls) <= refusals:
                raise migrate.psycopg2.OperationalError("connection refused")
            return "conn"

        monkeypatch.setattr(migrate.psycopg2, "connect", connect)
        return calls

    def test_connects_once_postgres_is_up(self, monkeypatch, clock):
        calls = self._refuse(monkeypatch, refusals=3)
        assert migrate._connect({"host": "postgres"}) == "conn"
        assert len(calls) == 4
        assert clock[0] == 3 * migrate.CONNECT_RETRY_SECONDS

    def test_gives_up_after_the_wait_window(self, monkeypatch, clock):
        self._refuse(monkeypatch, refusals=10_000)
        with pytest.raises(migrate.psycopg2.OperationalError):
            migrate._connect({"host": "postgres"})
        assert clock[0] <= migrate.CONNECT_WAIT_SECONDS

    def test_non_connection_errors_are_not_retried(self, monkeypatch, clock):
        calls = []

        def connect(*args, **kwargs):
            calls.append(args)
            raise migrate.psycopg2.ProgrammingError("invalid dsn")

        monkeypatch.setattr(migrate.psycopg2, "connect", connect)
        with pytest.raises(migrate.psycopg2.ProgrammingError):
            migrate._connect("bogus")
        assert len(calls) == 1

    def test_every_attempt_has_a_timeout(self, monkeypatch, clock):
        calls = self._refuse(monkeypatch, refusals=1)
        migrate._connect("postgresql://u:p@h/db")
        migrate._connect({"host": "postgres"})
        assert all(kw["connect_timeout"] == migrate.CONNECT_ATTEMPT_TIMEOUT for _, kw in calls)


class TestNotify:
    @pytest.fixture()
    def sent(self, monkeypatch):
        bodies = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout):
            bodies.append(json.loads(req.data))
            return Response()

        monkeypatch.setenv("SLACK_MIGRATIONS_WEBHOOK_URL", "https://hooks.slack.test/hook")
        monkeypatch.setattr(migrate.urllib.request, "urlopen", fake_urlopen)
        return bodies

    def test_no_webhook_is_a_noop(self, monkeypatch):
        monkeypatch.delenv("SLACK_MIGRATIONS_WEBHOOK_URL", raising=False)
        monkeypatch.setattr(
            migrate.urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not post")
        )
        migrate.notify("hello")

    def test_posts_truncated_text(self, sent):
        migrate.notify("x" * 5000)
        assert sent[0] == {"text": "x" * 3000}

    def test_escapes_slack_control_characters(self, sent):
        migrate.notify('syntax error at or near "<" & ">"')
        assert sent[0]["text"] == 'syntax error at or near "&lt;" &amp; "&gt;"'

    def test_truncation_never_splits_an_entity(self, sent):
        migrate.notify("x" * 2999 + "<<<")
        assert sent[0]["text"] == "x" * 2999 + "&lt;"

    def test_post_failure_never_raises(self, monkeypatch):
        def broken(*args, **kwargs):
            raise OSError("network down")

        monkeypatch.setenv("SLACK_MIGRATIONS_WEBHOOK_URL", "https://hooks.slack.test/hook")
        monkeypatch.setattr(migrate.urllib.request, "urlopen", broken)
        migrate.notify("hello")
