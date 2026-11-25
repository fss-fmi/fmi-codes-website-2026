"""Mentor photo paths.

Migration 019 moves seeded paths to the frontend's WebP files, and a team's page returns each
assigned mentor's path, since the backend serves no pictures itself.
"""

from pathlib import Path

import pytest

from tests.e2e.conftest import bearer, register_and_token

pytestmark = pytest.mark.e2e

PHOTO = "/mentorPictures/Alpha_Mentor.webp"

MIGRATION_019 = (
    Path(__file__).parent.parent.parent
    / "backend"
    / "database"
    / "migrations"
    / "019_mentor_pictures_webp.sql"
)

ROWS = [
    ("m019-jpg@example.test", "/static/mentorPictures/Alice_Example.jpg", "Alice_Example.jpg"),
    ("m019-jpeg@example.test", "/static/mentorPictures/Боби_Пример.jpeg", "Боби_Пример.jpeg"),
    ("m019-png@example.test", "/static/mentorPictures/Carol_Example.PNG", "Carol_Example.PNG"),
    ("m019-done@example.test", "/mentorPictures/Done.webp", "Done.webp"),
    ("m019-url@example.test", "https://example.test/photo.jpg", "photo.jpg"),
    ("m019-none@example.test", None, None),
]

EXPECTED = {
    "m019-jpg@example.test": ("/mentorPictures/Alice_Example.webp", "Alice_Example.webp"),
    "m019-jpeg@example.test": ("/mentorPictures/Боби_Пример.webp", "Боби_Пример.webp"),
    "m019-png@example.test": ("/mentorPictures/Carol_Example.webp", "Carol_Example.webp"),
    "m019-done@example.test": ("/mentorPictures/Done.webp", "Done.webp"),
    "m019-url@example.test": ("https://example.test/photo.jpg", "photo.jpg"),
    "m019-none@example.test": (None, None),
}


class TestMigration019:
    def test_seeded_paths_move_to_webp_and_others_are_untouched(self, db_conn, seeds):
        sql = MIGRATION_019.read_text(encoding="utf-8")
        emails = [r[0] for r in ROWS]
        with db_conn.cursor() as cur:
            try:
                for i, (email, url, filename) in enumerate(ROWS):
                    cur.execute(
                        """INSERT INTO mentors (first_name, last_name, email, phone_number,
                                                company_name, picture_url, picture_filename)
                           VALUES (%s, %s, %s, '0888000000', 'M019', %s, %s)""",
                        ("M019", f"Row{i}", email, url, filename),
                    )
                cur.execute(sql)
                cur.execute(sql)  # must be safe to re-run
                cur.execute(
                    "SELECT email, picture_url, picture_filename FROM mentors "
                    "WHERE email = ANY(%s)",
                    (emails,),
                )
                got = {
                    r["email"]: (r["picture_url"], r["picture_filename"]) for r in cur.fetchall()
                }
            finally:
                cur.execute("DELETE FROM mentors WHERE email = ANY(%s)", (emails,))
        assert got == EXPECTED


@pytest.fixture
def mentor_with_photo(db_conn, seeds):
    """The first seeded mentor with a photo path. Seeded mentors outlive clean_db, so reset it."""
    mentor_id = seeds["mentor_ids"][0]
    with db_conn.cursor() as cur:
        cur.execute("UPDATE mentors SET picture_url = %s WHERE id = %s", (PHOTO, mentor_id))
    try:
        yield mentor_id
    finally:
        with db_conn.cursor() as cur:
            cur.execute("UPDATE mentors SET picture_url = NULL WHERE id = %s", (mentor_id,))


class TestTeamMentorPhotos:
    def test_team_shows_each_assigned_mentors_photo(
        self, client, db_conn, seeds, mentor_with_photo
    ):
        token = register_and_token(client, 1, seeds)
        rv = client.post("/api/teams", json={"team_name": "Photo Team"}, headers=bearer(token))
        assert rv.status_code == 201, rv.get_json()
        team_id = rv.get_json()["team"]["id"]
        other_id = seeds["mentor_ids"][1]
        with db_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO team_mentors (team_id, mentor_id, is_active) "
                "VALUES (%s, %s, TRUE), (%s, %s, TRUE)",
                (team_id, mentor_with_photo, team_id, other_id),
            )

        rv = client.get(f"/api/teams/{team_id}", headers=bearer(token))

        assert rv.status_code == 200, rv.get_json()
        # Every seeded mentor's last name is "Mentor", so the order isn't fixed.
        mentors = {m["mentor_id"]: m for m in rv.get_json()["team"]["mentors"]}
        assert set(mentors) == {mentor_with_photo, other_id}
        assert mentors[mentor_with_photo]["picture_url"] == PHOTO
        assert mentors[other_id]["picture_url"] is None
        for m in mentors.values():
            assert set(m) == {"mentor_id", "mentor_name", "company_name", "picture_url"}

    def test_picture_endpoint_is_gone(self, client, mentor_with_photo):
        # A mentor with a photo, since the old handler answered 404 only when there was none.
        assert client.get(f"/api/mentors/{mentor_with_photo}/picture").status_code == 404
