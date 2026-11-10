"""Migration 019 moves seeded mentor photo paths to the frontend's WebP files."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

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
