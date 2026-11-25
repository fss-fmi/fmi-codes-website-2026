"""The mentor seed loader against a real database.

A mentor seeded without a password can't log in until they set one through reset (#274): the
loader stores a NULL password_hash for an entry with no password, and these pin the login and
reset paths that make that safe. Every worker seeds while it boots, so a worker that loses the
race to insert a mentor must not log a database error (#191). clean_db keeps mentor rows, so
each test deletes its own.
"""

import json
import logging

import pytest

from tests.e2e.test_auth_e2e import _insert_reset_token

pytestmark = pytest.mark.e2e


def _insert_mentor(cur, email: str, password_hash) -> int:
    cur.execute(
        """INSERT INTO mentors (first_name, last_name, email, phone_number, company_name,
                                password_hash)
           VALUES ('No', %s, %s, '0888000000', 'No Password Co', %s)
           RETURNING id""",
        (email, email, password_hash),
    )
    return cur.fetchone()["id"]


@pytest.mark.parametrize("password_hash", [None, ""], ids=["null", "empty"])
def test_a_mentor_with_no_password_hash_cannot_log_in(client, seeds, db_conn, password_hash):
    email = f"no-hash-{'null' if password_hash is None else 'empty'}@mentor.test"
    with db_conn.cursor() as cur:
        try:
            _insert_mentor(cur, email, password_hash)
            rv = client.post(
                "/api/auth/login",
                json={"email": email, "password": "mentor123", "role": "mentor"},
            )
            assert rv.status_code == 401
            assert rv.get_json()["success"] is False
        finally:
            cur.execute("DELETE FROM mentors WHERE email = %s", (email,))


def test_a_mentor_with_no_password_sets_one_through_reset(client, seeds, db_conn):
    email = "no-hash-reset@mentor.test"
    new_pw = "MentorFirstPassword1!"
    mentor_id = None
    with db_conn.cursor() as cur:
        try:
            mentor_id = _insert_mentor(cur, email, None)
            token = _insert_reset_token(db_conn, mentor_id, "mentor")
            rv = client.post(
                "/api/auth/reset-password/confirm",
                json={"token": token, "new_password": new_pw, "role": "mentor"},
            )
            assert rv.status_code == 200
            rv = client.post(
                "/api/auth/login",
                json={"email": email, "password": new_pw, "role": "mentor"},
            )
            assert rv.status_code == 200
            assert rv.get_json()["role"] == "mentor"
        finally:
            if mentor_id is not None:
                cur.execute(
                    "DELETE FROM password_reset_tokens WHERE user_id = %s AND role = 'mentor'",
                    (mentor_id,),
                )
            cur.execute("DELETE FROM mentors WHERE email = %s", (email,))


def test_a_worker_that_loses_the_seed_race_logs_no_error(
    flask_app, seeds, db_conn, monkeypatch, tmp_path, caplog
):
    """The losing worker checked before the winner committed, so its INSERT meets the new row.

    That row is Alpha's: the entry reuses Alpha's email under another name and company, so only
    the email key conflicts, which is what two workers inserting the same mentor hit.
    """
    from app.services import mentor_service

    loser = ("Race", "Loser", "Race Co")
    entry = {
        "first_name": loser[0],
        "last_name": loser[1],
        "company_name": loser[2],
        "email": "alpha@mentor.test",
        "phone_number": "0000000001",
    }
    seed = tmp_path / "mentors.json"
    seed.write_text(json.dumps([entry]), encoding="utf-8")
    monkeypatch.setattr(mentor_service, "find_existing_mentor", lambda *a, **k: None)

    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM mentors WHERE email = %s", (entry["email"],))
        alpha = cur.fetchone()
        try:
            with flask_app.app_context(), caplog.at_level(logging.ERROR):
                assert mentor_service.load_mentors_from_file(seed) == 0
        finally:
            cur.execute(
                "DELETE FROM mentors WHERE first_name = %s AND last_name = %s"
                " AND company_name = %s",
                loser,
            )
        cur.execute("SELECT * FROM mentors WHERE email = %s", (entry["email"],))
        assert cur.fetchone() == alpha

    assert "Database transaction error" not in caplog.text
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_an_entry_with_another_mentors_email_is_skipped_with_a_warning(
    flask_app, seeds, db_conn, tmp_path, caplog
):
    """The lookup lowercases the email, as login does, so a capitalised copy still matches."""
    from app.services import mentor_service

    copy = ("Copy", "Paste", "Copy Co")
    entry = {
        "first_name": copy[0],
        "last_name": copy[1],
        "company_name": copy[2],
        "email": "ALPHA@mentor.test",
        "phone_number": "0000000002",
    }
    seed = tmp_path / "mentors.json"
    seed.write_text(json.dumps([entry]), encoding="utf-8")

    with db_conn.cursor() as cur:
        try:
            with flask_app.app_context(), caplog.at_level(logging.WARNING):
                assert mentor_service.load_mentors_from_file(seed) == 0
        finally:
            cur.execute(
                "DELETE FROM mentors WHERE first_name = %s AND last_name = %s"
                " AND company_name = %s",
                copy,
            )

    assert "its email belongs to the stored mentor Alpha Mentor (AlphaCorp)" in caplog.text
    assert "alpha@mentor.test" not in caplog.text.lower()
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_a_mentor_stored_with_capitals_is_not_seeded_twice(flask_app, seeds, db_conn, tmp_path):
    """Mentors seeded before the loader lowercased emails keep their capitals.

    With the company edited in the seed, only the email can still match the stored row, and
    the unique key is case-sensitive, so a lookup that missed it would insert a second row.
    """
    from app.services import mentor_service

    email = "Mixed.Case@Mentor.test"
    entry = {
        "first_name": "Mixed",
        "last_name": "Case",
        "company_name": "Mixed Co Ltd",
        "email": email,
        "phone_number": "0000000003",
    }
    seed = tmp_path / "mentors.json"
    seed.write_text(json.dumps([entry]), encoding="utf-8")

    with db_conn.cursor() as cur:
        try:
            cur.execute(
                """INSERT INTO mentors (first_name, last_name, email, phone_number, company_name)
                   VALUES ('Mixed', 'Case', %s, '0000000003', 'Mixed Co')""",
                (email,),
            )
            with flask_app.app_context():
                assert mentor_service.load_mentors_from_file(seed) == 0
            cur.execute(
                "SELECT company_name FROM mentors WHERE LOWER(email) = %s", (email.lower(),)
            )
            assert [r["company_name"] for r in cur.fetchall()] == ["Mixed Co"]
        finally:
            cur.execute("DELETE FROM mentors WHERE LOWER(email) = %s", (email.lower(),))
