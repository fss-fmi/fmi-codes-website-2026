"""The connect options reach the kernel on real connections to Postgres (#280).

libpq applies keepalives and tcp_user_timeout as socket options, so the test reads them back
from the connection's own socket. Linux only: the option names differ elsewhere, and CI is
Linux. The unit side is tests/test_connection_timeouts.py.
"""

import os
import socket
import sys
from pathlib import Path

import psycopg2
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from database import migrate

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(sys.platform != "linux", reason="reads Linux TCP socket options"),
]

EXPECTED = {
    "SO_KEEPALIVE": 1,
    "TCP_KEEPIDLE": 30,
    "TCP_KEEPINTVL": 10,
    "TCP_KEEPCNT": 3,
    "TCP_USER_TIMEOUT": 10_000,
}


def _socket_options(conn):
    if conn.info.host.startswith("/"):
        pytest.skip("connected over a Unix socket, where libpq sets no TCP options")
    sock = socket.socket(fileno=os.dup(conn.fileno()))
    try:
        return {
            name: sock.getsockopt(
                socket.SOL_SOCKET if name.startswith("SO_") else socket.IPPROTO_TCP,
                getattr(socket, name),
            )
            for name in EXPECTED
        }
    finally:
        sock.close()


def test_pooled_connections_carry_the_tcp_options(flask_app):
    from app import database

    conn = database.get_db_connection()
    try:
        assert _socket_options(conn) == EXPECTED
    finally:
        database.return_db_connection(conn)


@pytest.mark.parametrize("form", ["url", "params"])
def test_migration_runner_connections_carry_the_tcp_options(db_url, form):
    params = db_url if form == "url" else psycopg2.extensions.parse_dsn(db_url)
    conn = migrate._connect(params)
    try:
        assert _socket_options(conn) == EXPECTED
    finally:
        conn.close()
