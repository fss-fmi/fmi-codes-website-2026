"""Postgres connections fail in seconds when the peer goes silent, on both ends (#280).

Without these options a connection whose peer stops answering (packets dropped, no reset)
hangs every query on it for the kernel's retransmit timeout, minutes, and Postgres keeps a
silently vanished client's locks until its own keepalive notices, about 2 h on OS defaults.
The real behaviour on Linux sockets is checked in tests/e2e/test_connection_timeouts_e2e.py.
"""

import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app import database
from database import migrate
from psycopg2.extensions import TRANSACTION_STATUS_IDLE

from tests.k8s_manifests import K8S, ROOT

EXPECTED = {
    "connect_timeout": 5,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
    "tcp_user_timeout": 10_000,
}
POSTGRES_VALUES = {
    "prod": K8S / "helm-values" / "postgresql-values.yaml",
    "staging": K8S / "overlays" / "staging" / "postgresql-values.yaml",
}
SERVER_SETTINGS = {
    "tcp_keepalives_idle": "keepalives_idle",
    "tcp_keepalives_interval": "keepalives_interval",
    "tcp_keepalives_count": "keepalives_count",
    "tcp_user_timeout": "tcp_user_timeout",
}
MIGRATE_JOB = K8S / "templates" / "db-migrate-job.yaml"


class FakeCursor:
    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return {"exists": True}

    def close(self):
        pass


class FakeConnection:
    closed = 0

    def __init__(self):
        self.info = SimpleNamespace(transaction_status=TRANSACTION_STATUS_IDLE)

    def cursor(self):
        return FakeCursor()

    def close(self):
        pass


def test_every_pool_connection_gets_the_options(monkeypatch):
    monkeypatch.setattr(database, "_pool", None)
    monkeypatch.setattr(database, "_pool_timeout", 5)
    connects = []

    def fake_connect(*args, **kwargs):
        connects.append(kwargs)
        return FakeConnection()

    app = SimpleNamespace(
        config={"DATABASE_URL": "postgresql://unused", "DB_POOL_MIN": 1, "DB_POOL_MAX": 3}
    )
    with patch("psycopg2.pool.psycopg2.connect", side_effect=fake_connect):
        database.init_database(app)
        # The idle one, then one the pool opens on demand.
        held = [database.get_db_connection(), database.get_db_connection()]

    assert len(connects) == 2
    for kwargs in connects:
        assert {k: kwargs.get(k) for k in EXPECTED} == EXPECTED
    for conn in held:
        database.return_db_connection(conn)


def test_the_migration_runner_uses_the_same_options():
    assert migrate.CONNECT_OPTIONS == database.CONNECT_OPTIONS == EXPECTED


def _server_settings(path):
    block = re.search(
        r"^  extendedConfiguration: \|\n((?:    .*\n)+)", path.read_text(encoding="utf-8"), re.M
    )
    assert block, f"extendedConfiguration not found in {path.relative_to(ROOT)}"
    return dict(re.findall(r"^    (\w+) = (\S+)$", block[1], re.M))


@pytest.mark.parametrize("env", ["prod", "staging"])
def test_postgres_mirrors_the_tcp_options(env):
    """The server side frees a dead client's locks (advisory lock 1 included) as fast as the
    backend notices a dead server."""
    settings = _server_settings(POSTGRES_VALUES[env])
    for server, client in SERVER_SETTINGS.items():
        assert settings.get(server) == str(EXPECTED[client]), f"{env}: {server}"


def test_the_backup_dump_opts_out_of_the_user_timeout():
    """pg_dump stops reading while gzip writes fall behind, and the server's tcp_user_timeout
    ends a session whose reader stalls longer than it."""
    backup = re.search(
        r"^        - name: backup\n((?:          .*\n|\s*\n)+)",
        MIGRATE_JOB.read_text(encoding="utf-8"),
        re.M,
    )
    assert backup, "backup initContainer not found"
    assert re.search(
        r'^            - name: PGOPTIONS\n              value: "-c tcp_user_timeout=0"$',
        backup[1],
        re.M,
    )
