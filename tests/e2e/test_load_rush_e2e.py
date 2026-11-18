"""The registration rush load test (tests/load/) against the real app and schema.

A small run proves the script's scenario works end to end, check.sql finds every kind of
inconsistency it names and cleanup.sql leaves nothing behind, or refuses and changes nothing.
"""

import subprocess
import sys
import threading
import uuid
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor
from werkzeug.serving import make_server

pytestmark = pytest.mark.e2e

LOAD_DIR = Path(__file__).parent.parent / "load"
CHECK_SQL = (LOAD_DIR / "check.sql").read_text(encoding="utf-8")
CLEANUP_SQL = (LOAD_DIR / "cleanup.sql").read_text(encoding="utf-8")


@pytest.fixture()
def live_server(flask_app):
    server = make_server("127.0.0.1", 0, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()


def run_rush(base_url, *args):
    return subprocess.run(
        [sys.executable, str(LOAD_DIR / "registration_rush.py"), f"--base-url={base_url}", *args],
        capture_output=True,
        text=True,
        timeout=300,
    )


def problems(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(CHECK_SQL)
        return sorted(row["problem"] for row in cur.fetchall())


def cleanup(db_url):
    # Its own connection: a refused cleanup leaves the session in an aborted transaction.
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(CLEANUP_SQL)
    finally:
        conn.close()


def counts(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT COUNT(*) FROM participants) AS participants,"
            " (SELECT COUNT(*) FROM teams) AS teams,"
            " (SELECT COUNT(*) FROM teams WHERE is_registered) AS registered,"
            " (SELECT COUNT(*) FROM teams WHERE queue_position IS NOT NULL) AS queued"
        )
        return dict(cur.fetchone())


def test_a_small_rush_passes_checks_and_cleans_up(live_server, db_conn, db_url):
    # 60 users in teams of 3 make 20 active teams: 18 registered and 2 queued.
    run = run_rush(
        live_server,
        "--users=60",
        "--arrival-seconds=5",
        "--team-size=3",
        "--relogin-share=0.2",
        "--linger-seconds=1.5",
        "--config-poll-seconds=0.5",
        "--team-reloads=1",
        "--seat-wait-seconds=60",
        "--register-p95=120",
        "--register-p99=120",
        # A busy CI runner can start a thread late; the 1 s default is for the cluster run.
        "--max-start-lag=10",
        "--seed=7",
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "RESULT: PASS" in run.stdout
    for name in ("register", "create_team", "join_team", "login", "logout", "config", "team"):
        assert f"\n{name} " in run.stdout, name

    assert counts(db_conn) == {"participants": 60, "teams": 20, "registered": 18, "queued": 2}
    assert problems(db_conn) == []

    cleanup(db_url)
    assert counts(db_conn) == {"participants": 0, "teams": 0, "registered": 0, "queued": 0}
    assert problems(db_conn) == []


def test_preflight_refuses_while_registration_is_closed(live_server, db_conn, set_flag):
    set_flag("registration_open", False)
    run = run_rush(live_server, "--users=3", "--arrival-seconds=0")
    assert run.returncode == 2
    assert "registration_open is off" in run.stderr
    assert counts(db_conn)["participants"] == 0


def test_preflight_refuses_when_teams_are_registered(live_server, db_conn, seeds):
    _team(db_conn, seeds, members=3, registered=True)
    run = run_rush(live_server, "--users=3", "--arrival-seconds=0")
    assert run.returncode == 2
    assert "already registered" in run.stderr


# ── check.sql and cleanup.sql on hand-built states ─────────────────────────


def _team(
    db_conn,
    seeds,
    members,
    status=None,
    registered=False,
    queue=None,
    domain="loadtest.invalid",
    captain_last=False,
):
    """A team with `members` participants written straight to the DB.

    The captain is the first member inserted, or the last with `captain_last`, as when
    friends register before the captain does.
    """
    tag = uuid.uuid4().hex[:8]
    captain = members - 1 if captain_last else 0
    status = status or ("active" if members >= 3 else "pending")
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO teams (team_name, password_hash, join_code, status, is_registered,"
            " queue_position) VALUES (%s, '', %s, %s, %s, %s) RETURNING id",
            (f"T {tag}", tag.upper(), status, registered, queue),
        )
        team_id = cur.fetchone()["id"]
        for n in range(members):
            cur.execute(
                "INSERT INTO participants (first_name, last_name, email, phone_number,"
                " faculty_number, course, specialty_id, university_id, password_hash,"
                " team_id, is_captain) VALUES ('Load', 'Tester', %s, '0888000000', %s,"
                " 'Bachelor 1st Year', %s, %s, 'x', %s, %s) RETURNING id",
                (
                    f"{tag}-{n}@{domain}",
                    f"F{tag}{n}",
                    seeds["spec_id"],
                    seeds["univ_id"],
                    team_id,
                    n == captain,
                ),
            )
            if n == captain:
                cur.execute(
                    "UPDATE teams SET captain_id = %s WHERE id = %s",
                    (cur.fetchone()["id"], team_id),
                )
    return team_id


def _sql(db_conn, statement, *params):
    with db_conn.cursor() as cur:
        cur.execute(statement, params)


def _full_event(db_conn, seeds, queued=2):
    for _ in range(18):
        _team(db_conn, seeds, members=3, registered=True)
    queued_ids = [_team(db_conn, seeds, members=3, queue=n) for n in range(1, queued + 1)]
    _team(db_conn, seeds, members=1)
    return queued_ids


def test_check_passes_a_consistent_event(db_conn, seeds):
    _full_event(db_conn, seeds)
    assert problems(db_conn) == []


def test_check_counts_an_inactive_member_as_the_trigger_and_the_app_do(db_conn, seeds):
    # participant_count counts every row on the team; size and activation only active ones.
    queued_ids = _full_event(db_conn, seeds)
    _sql(
        db_conn,
        "UPDATE participants SET status = 'inactive'"
        " WHERE team_id = %s AND NOT is_captain AND id = ("
        "  SELECT MAX(id) FROM participants WHERE team_id = %s)",
        queued_ids[0],
        queued_ids[0],
    )
    assert problems(db_conn) == ["status vs members"]


def _gap_in_queue(c, s, q):
    _sql(c, "UPDATE teams SET queue_position = 3 WHERE id = %s", q[1])


def _nineteenth_registered(c, s, q):
    _sql(c, "UPDATE teams SET queue_position = NULL, is_registered = TRUE WHERE id = %s", q[0])


def _active_team_dropped_from_queue(c, s, q):
    _sql(c, "UPDATE teams SET queue_position = NULL WHERE id = %s", q[0])
    _sql(c, "UPDATE teams SET queue_position = 1 WHERE id = %s", q[1])


def _queued_team_also_registered(c, s, q):
    _sql(c, "UPDATE teams SET is_registered = TRUE WHERE id = %s", q[1])


def _seven_members(c, s, q):
    _team(c, s, members=7, queue=3)


def _active_with_two(c, s, q):
    _team(c, s, members=2, status="active", queue=3)


def _pending_in_queue(c, s, q):
    _team(c, s, members=1, queue=3)


def _wrong_participant_count(c, s, q):
    _sql(c, "UPDATE teams SET participant_count = 9 WHERE id = %s", q[0])


def _captain_of_another_team(c, s, q):
    _sql(
        c,
        "UPDATE teams SET captain_id = (SELECT captain_id FROM teams WHERE id = %s) WHERE id = %s",
        q[0],
        q[1],
    )


@pytest.mark.parametrize(
    ("break_it", "expected"),
    [
        (_gap_in_queue, ["queue position"]),
        (_nineteenth_registered, ["queue position", "registered teams"]),
        (_active_team_dropped_from_queue, ["active team neither registered nor queued"]),
        (_queued_team_also_registered, ["registered and queued", "registered teams"]),
        (_seven_members, ["over 6 members"]),
        (_active_with_two, ["status vs members"]),
        (_pending_in_queue, ["pending team registered or queued"]),
        (_wrong_participant_count, ["participant_count"]),
        (_captain_of_another_team, ["captain not in the team", "captain of no team"]),
    ],
)
def test_check_finds_each_inconsistency(db_conn, seeds, break_it, expected):
    queued_ids = _full_event(db_conn, seeds)
    break_it(db_conn, seeds, queued_ids)
    assert problems(db_conn) == sorted(expected)


def test_cleanup_refuses_a_team_with_a_real_member(db_conn, db_url, seeds):
    team_id = _team(db_conn, seeds, members=3, registered=True)
    _team(db_conn, seeds, members=1, domain="example.com")
    _sql(
        db_conn,
        "UPDATE participants SET team_id = %s WHERE email LIKE '%%@example.com'",
        team_id,
    )
    before = counts(db_conn)
    with pytest.raises(psycopg2.errors.RaiseException, match="member outside"):
        cleanup(db_url)
    assert counts(db_conn) == before


def test_cleanup_refuses_to_leave_another_teams_queue_position_gapped(db_conn, db_url, seeds):
    _team(db_conn, seeds, members=3, queue=1)
    _team(db_conn, seeds, members=3, queue=2, domain="example.com")
    before = counts(db_conn)
    with pytest.raises(psycopg2.errors.RaiseException, match="queued"):
        cleanup(db_url)
    assert counts(db_conn) == before


@pytest.mark.parametrize("captain_last", [False, True])
def test_cleanup_keeps_real_accounts_and_teams(db_conn, db_url, seeds, captain_last):
    _team(db_conn, seeds, members=3, registered=True, captain_last=captain_last)
    _team(db_conn, seeds, members=2, domain="example.com")
    cleanup(db_url)
    assert counts(db_conn) == {"participants": 2, "teams": 1, "registered": 0, "queued": 0}
