"""Dead pooled connections after a Postgres restart (#277).

The real ThreadedConnectionPool runs with psycopg2.connect patched to hand out fake
connections that fail the way psycopg2's do once the server is gone: the next query or
rollback raises OperationalError and sets `closed` to 2, and a closed connection raises
InterfaceError on rollback and on cursor(). Every test also checks that no connection
is left checked out, since a leaked one shrinks the worker's pool for good.
"""

import logging
from types import SimpleNamespace
from unittest.mock import patch

import psycopg2
import pytest
from app import database
from psycopg2.extensions import TRANSACTION_STATUS_IDLE, TRANSACTION_STATUS_INTRANS
from psycopg2.pool import ThreadedConnectionPool

MINCONN = 2
MAXCONN = 8


class Interrupted(BaseException):
    pass


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        if self.conn.ping_error is not None and sql == "SELECT 1":
            raise self.conn.ping_error
        if self.conn.dead:
            self.conn.closed = 2
            if self.conn.on_failure is not None:
                self.conn.on_failure()
            raise psycopg2.OperationalError("terminating connection due to administrator command")
        self.conn.executed.append(sql)
        self.conn.info.transaction_status = TRANSACTION_STATUS_INTRANS
        if self.conn.lost_after_ping and sql == "SELECT 1":
            self.conn.closed = 2

    def close(self):
        pass


class FakeConnection:
    def __init__(self, dead=False):
        self.dead = dead
        self.closed = 0
        self.executed = []
        self.ping_error = None
        self.rollback_error = None
        self.on_failure = None
        self.lost_after_ping = False
        self.info = SimpleNamespace(transaction_status=TRANSACTION_STATUS_IDLE)

    def cursor(self):
        if self.closed:
            raise psycopg2.InterfaceError("connection already closed")
        return FakeCursor(self)

    def commit(self):
        if self.closed:
            raise psycopg2.InterfaceError("connection already closed")
        self.info.transaction_status = TRANSACTION_STATUS_IDLE

    def rollback(self):
        if self.closed:
            raise psycopg2.InterfaceError("connection already closed")
        if self.dead:
            self.closed = 2
            raise psycopg2.OperationalError("server closed the connection unexpectedly")
        if self.rollback_error is not None:
            raise self.rollback_error
        self.info.transaction_status = TRANSACTION_STATUS_IDLE

    def close(self):
        if not self.closed:
            self.closed = 1


@pytest.fixture()
def make_pool(monkeypatch):
    """Build a real pool whose connects return the given fakes (or raise them) in order."""

    def _make(*connects):
        queue = list(connects)

        def fake_connect(*args, **kwargs):
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with patch("psycopg2.pool.psycopg2.connect", side_effect=fake_connect):
            pool = ThreadedConnectionPool(MINCONN, MAXCONN, "postgresql://unused")
        monkeypatch.setattr(database, "_pool", pool)
        monkeypatch.setattr(database, "_pool_timeout", 0.2)
        return pool, fake_connect

    return _make


def checkout(fake_connect):
    with patch("psycopg2.pool.psycopg2.connect", side_effect=fake_connect):
        return database.get_db_connection()


def test_checkout_replaces_dead_idle_connections(make_pool, caplog):
    dead_a, dead_b, fresh = FakeConnection(), FakeConnection(), FakeConnection()
    pool, fake_connect = make_pool(dead_a, dead_b, fresh)
    dead_a.dead = dead_b.dead = True  # Postgres restarted after the pool filled

    with caplog.at_level(logging.WARNING, logger="app.database"):
        conn = checkout(fake_connect)

    assert conn is fresh
    assert dead_a.closed and dead_b.closed
    assert "Discarded a pooled database connection whose ping failed" in caplog.text
    database.return_db_connection(conn)
    assert pool._used == {}


def test_dead_connections_returned_by_other_threads_are_replaced_too(make_pool):
    """Requests that committed just before the restart hand back dead connections that
    still look idle, so one checkout can meet more dead ones than the pool keeps idle."""
    dead = [FakeConnection(dead=True) for _ in range(4)]
    fresh = FakeConnection()
    pool, fake_connect = make_pool(*dead, fresh)
    with patch("psycopg2.pool.psycopg2.connect", side_effect=fake_connect):
        held = [pool.getconn() for _ in range(4)]  # the two idle ones, then two opened
    pool.putconn(held[0])
    pool.putconn(held[1])
    # Each failed ping lets another thread finish and return its connection.
    held[1].on_failure = lambda: pool.putconn(held[2])
    held[2].on_failure = lambda: pool.putconn(held[3])

    conn = checkout(fake_connect)

    assert conn is fresh
    assert all(c.closed for c in dead)
    database.return_db_connection(conn)
    assert pool._used == {}


def test_healthy_connection_is_pinged_inside_its_transaction(make_pool):
    first, second = FakeConnection(), FakeConnection()
    pool, fake_connect = make_pool(first, second)

    conn = checkout(fake_connect)

    assert conn is second  # getconn pops the newest idle connection
    assert conn.executed == ["SELECT 1"]
    assert conn.info.transaction_status == TRANSACTION_STATUS_INTRANS
    database.return_db_connection(conn)
    assert pool._used == {}


def test_connect_error_after_dead_connections_is_raised(make_pool):
    dead_a, dead_b = FakeConnection(), FakeConnection()
    pool, fake_connect = make_pool(
        dead_a, dead_b, psycopg2.OperationalError("could not connect to server")
    )
    dead_a.dead = dead_b.dead = True

    with pytest.raises(psycopg2.OperationalError, match="could not connect"):
        checkout(fake_connect)

    assert dead_a.closed and dead_b.closed
    assert pool._used == {}


def test_new_connection_failing_its_ping_is_raised_at_once(make_pool):
    """Postgres accepts connections but every query fails: after the dead idle ones the
    checkout opens one new connection, not one after another."""
    conns = [FakeConnection(dead=True) for _ in range(MINCONN + 2)]
    pool, fake_connect = make_pool(*conns)

    with pytest.raises(psycopg2.OperationalError, match="administrator command"):
        checkout(fake_connect)

    assert all(c.closed for c in conns[: MINCONN + 1])
    assert not conns[MINCONN + 1].closed  # never connected: the checkout stopped first
    assert pool._used == {}


def test_pooled_ping_failure_after_the_timeout_is_raised(make_pool, monkeypatch):
    first, second = FakeConnection(dead=True), FakeConnection(dead=True)
    pool, fake_connect = make_pool(first, second)
    monkeypatch.setattr(database, "_pool_timeout", 0)

    with pytest.raises(psycopg2.OperationalError, match="administrator command"):
        checkout(fake_connect)

    assert second.closed and not first.closed
    assert pool._used == {}


def test_cursor_error_after_the_ping_frees_the_slot(make_pool):
    pool, fake_connect = make_pool(FakeConnection(), FakeConnection())
    pool._pool[-1].lost_after_ping = True

    with pytest.raises(psycopg2.InterfaceError, match="connection already closed"):
        with patch("psycopg2.pool.psycopg2.connect", side_effect=fake_connect):
            with database.get_db_cursor():
                pass

    assert pool._used == {}


def test_any_psycopg2_error_on_the_ping_replaces_the_connection(make_pool):
    fresh, broken = FakeConnection(), FakeConnection()
    pool, fake_connect = make_pool(fresh, broken)
    broken.ping_error = psycopg2.DatabaseError("SSL error: decryption failed or bad record mac")

    conn = checkout(fake_connect)

    assert conn is fresh
    assert broken.closed
    database.return_db_connection(conn)
    assert pool._used == {}


def test_other_ping_error_returns_the_slot_and_is_raised(make_pool):
    first, second = FakeConnection(), FakeConnection()
    pool, fake_connect = make_pool(first, second)
    second.ping_error = RuntimeError("unexpected")

    with pytest.raises(RuntimeError, match="unexpected"):
        checkout(fake_connect)

    assert second.closed
    assert pool._used == {}


def test_query_error_on_a_dead_connection_raises_the_real_error(make_pool, caplog):
    pool, fake_connect = make_pool(FakeConnection(), FakeConnection())

    with caplog.at_level(logging.ERROR, logger="app.database"):
        with pytest.raises(psycopg2.OperationalError, match="administrator command"):
            with patch("psycopg2.pool.psycopg2.connect", side_effect=fake_connect):
                with database.get_db_cursor() as cursor:
                    cursor.conn.dead = True  # dies mid-request, after the ping
                    cursor.execute("SELECT * FROM teams")

    assert "Database transaction error: terminating connection" in caplog.text
    assert pool._used == {}
    assert all(not c.closed for c in pool._pool)


def test_failed_rollback_discards_the_connection_and_keeps_the_error(make_pool, caplog):
    pool, fake_connect = make_pool(FakeConnection(), FakeConnection())

    with caplog.at_level(logging.ERROR, logger="app.database"):
        with pytest.raises(ValueError, match="bad input"):
            with patch("psycopg2.pool.psycopg2.connect", side_effect=fake_connect):
                with database.get_db_cursor() as cursor:
                    conn = cursor.conn
                    conn.rollback_error = psycopg2.OperationalError("server closed the connection")
                    raise ValueError("bad input")

    assert conn.closed
    assert "Rollback failed, discarding the connection" in caplog.text
    assert pool._used == {}
    assert conn not in pool._pool


def test_interrupt_on_a_dead_connection_frees_the_slot(make_pool):
    """A BaseException skips the rollback branch, so putconn rolls back the ping's open
    transaction itself, which raises on a dead connection before it frees the slot."""
    pool, fake_connect = make_pool(FakeConnection(), FakeConnection())

    with pytest.raises(Interrupted):
        with patch("psycopg2.pool.psycopg2.connect", side_effect=fake_connect):
            with database.get_db_cursor() as cursor:
                conn = cursor.conn
                conn.dead = True
                raise Interrupted()

    assert conn.closed
    assert pool._used == {}
    assert conn not in pool._pool
