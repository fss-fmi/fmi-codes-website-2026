"""A Postgres restart costs no request once Postgres is back (#277).

The server ends the app pool's idle connections the way a restart does
(pg_terminate_backend on their pids, which leaves the session's own connections
alone). The next requests must all succeed, readiness and a registration included,
because every checkout pings its connection and replaces a dead one first.
"""

import logging
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from tests.e2e.conftest import register

pytestmark = pytest.mark.e2e


def _terminate(db_conn, pids):
    with db_conn.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(pid) FROM unnest(%s::int[]) AS pid", (pids,))
        # pg_terminate_backend only sends the signal.
        deadline = time.monotonic() + 5
        while True:
            cur.execute(
                "SELECT COUNT(*) AS n FROM pg_stat_activity WHERE pid = ANY(%s::int[])", (pids,)
            )
            if cur.fetchone()["n"] == 0:
                return
            assert time.monotonic() < deadline, "terminated backends still listed after 5 s"
            time.sleep(0.05)


def test_requests_succeed_after_the_pools_connections_are_killed(client, db_conn, seeds, caplog):
    from app import database

    assert client.get("/api/health/ready").status_code == 200
    idle = list(database._pool._pool)
    assert idle, "the pool holds no idle connection to kill"
    _terminate(db_conn, [c.get_backend_pid() for c in idle])

    with caplog.at_level(logging.WARNING, logger="app.database"):
        for _ in range(len(idle) + 1):
            resp = client.get("/api/health/ready")
            assert resp.status_code == 200, resp.get_json()
        assert register(client, 1, seeds).status_code == 201

    assert caplog.text.count("Discarded a dead pooled database connection") == len(idle)
    assert "Database transaction error" not in caplog.text
    assert all(c.closed for c in idle)
    assert database._pool._used == {}
