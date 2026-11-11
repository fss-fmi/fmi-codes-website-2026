"""Unit tests for the matching-phase event feed (issue #205).

Message builders, the submitted vs updated detection, the registered-team rule
and that a failing count or Slack hand-off never changes the outcome. The DB is
a FakeCursor on the service modules; real row locks and commits are covered in
tests/e2e/test_matching_events_e2e.py.
"""

import re
from contextlib import contextmanager

import pytest
from app.services import matching_events, matching_service, mentor_selection_service

# Distinctive ids, so a leaked id or rank can't hide among the counts.
MENTOR_IDS = (4101, 4102, 4103)
TEAM_IDS = (7101, 7102, 7103)


class FakeCursor:
    """Answers each execute() from *responses*: a list of fetch results in call order."""

    def __init__(self, responses=None, rowcount=1):
        self.responses = list(responses or [])
        self.executed = []
        self.rowcount = rowcount
        self._last = None

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        self._last = self.responses.pop(0) if self.responses else None

    def fetchone(self):
        return self._last


@pytest.fixture()
def notices(monkeypatch):
    posted = []
    monkeypatch.setattr("app.services.event_notifier.notify", posted.append)
    return posted


@pytest.fixture()
def cursor_for(monkeypatch):
    """Make the next get_db_cursor() in *module* yield *cursor*."""

    def _install(module, cursor, fail_at_commit=False):
        @contextmanager
        def fake_get_db_cursor(*args, **kwargs):
            yield cursor
            if fail_at_commit:
                raise RuntimeError("commit failed")

        monkeypatch.setattr(module, "get_db_cursor", fake_get_db_cursor)

    return _install


@pytest.fixture()
def status(monkeypatch):
    counts = {"teams_submitted": 7, "teams_total": 18, "mentors_submitted": 12, "mentors_total": 20}
    monkeypatch.setattr(
        mentor_selection_service, "get_preference_submission_status", lambda: counts
    )
    return counts


def _ranking(id_key, ids):
    return [{id_key: i, "rank": r} for r, i in zip((2, 3, 1), ids, strict=True)]


def _assert_no_choice(text, ids):
    for i in ids:
        assert str(i) not in text
    assert not re.search(r"\brank(ed)? \d|#\d|\b[123](st|nd|rd)\b", text, re.IGNORECASE)


# ── Message builders ────────────────────────────────────────────────


def test_team_submitted_names_the_team_and_the_progress():
    text = matching_events.team_ranking_text("Night Owls", False, (7, 18))
    assert text == "🗳️ Team *Night Owls* submitted its mentor ranking. Teams: 7 of 18 submitted."


def test_team_updated_has_no_progress():
    text = matching_events.team_ranking_text("Night Owls", True, (7, 18))
    assert text == "🔁 Team *Night Owls* updated its mentor ranking."


def test_mentor_submitted_and_updated():
    assert matching_events.mentor_ranking_text("Ana Petrova", False, (12, 20)) == (
        "🗳️ Mentor *Ana Petrova* submitted their team ranking. Mentors: 12 of 20 submitted."
    )
    assert matching_events.mentor_ranking_text("Ana Petrova", True, None) == (
        "🔁 Mentor *Ana Petrova* updated their team ranking."
    )


def test_submitted_without_a_count_still_posts():
    text = matching_events.team_ranking_text("Night Owls", False, None)
    assert text == "🗳️ Team *Night Owls* submitted its mentor ranking."


@pytest.mark.parametrize(
    "build", [matching_events.team_ranking_text, matching_events.mentor_ranking_text]
)
@pytest.mark.parametrize("updated", [False, True])
def test_names_are_escaped_for_slack(build, updated):
    text = build("<!channel> & <https://evil.example|click>", updated, (1, 2))
    assert "<" not in text and ">" not in text
    assert "&lt;!channel&gt; &amp; &lt;https://evil.example|click&gt;" in text


def test_matching_run_gives_counts_and_warnings():
    text = matching_events.matching_run_text(
        54, 18, ["2 team(s) have not submitted mentor preferences"], False
    )
    assert text == (
        "🧩 Mentor matching ran (Gale-Shapley, then greedy fill): *54* assignments for *18* teams.\n"
        "• 2 team(s) have not submitted mentor preferences"
    )


def test_matching_run_says_when_a_confirmation_was_cleared():
    text = matching_events.matching_run_text(3, 1, [], True)
    assert text.endswith("\nThe earlier confirmation was cleared.")


def test_matching_run_escapes_warnings():
    assert "&lt;b&gt;" in matching_events.matching_run_text(0, 0, ["<b>"], False)


def test_matching_confirmed_text():
    assert matching_events.matching_confirmed_text() == (
        "✅ Matching confirmed as final. Teams and mentors now see their assignments."
    )


# ── Team ranking ────────────────────────────────────────────────────


def _team_cursor(*, eligible=True, had_rows=False, name="Night Owls"):
    return FakeCursor(
        [
            {"team_name": name, "eligible": eligible},
            *({"id": m} for m in MENTOR_IDS),
            {"found": had_rows},
        ]
    )


def test_first_team_ranking_posts_submitted_with_progress(app_ctx, cursor_for, notices, status):
    cursor_for(mentor_selection_service, _team_cursor())
    ok, _ = mentor_selection_service.set_team_mentor_preferences(
        TEAM_IDS[0], _ranking("mentor_id", MENTOR_IDS)
    )
    assert ok
    assert notices == [
        "🗳️ Team *Night Owls* submitted its mentor ranking. Teams: 7 of 18 submitted."
    ]
    _assert_no_choice(notices[0], MENTOR_IDS)


def test_existing_rows_are_read_before_the_delete(app_ctx, cursor_for, notices, status):
    cursor = _team_cursor(had_rows=True)
    cursor_for(mentor_selection_service, cursor)
    mentor_selection_service.set_team_mentor_preferences(
        TEAM_IDS[0], _ranking("mentor_id", MENTOR_IDS)
    )
    sql = [s for s, _ in cursor.executed]
    exists_at = next(i for i, s in enumerate(sql) if s.startswith("SELECT EXISTS"))
    delete_at = next(i for i, s in enumerate(sql) if s.startswith("DELETE"))
    assert exists_at < delete_at
    assert notices == ["🔁 Team *Night Owls* updated its mentor ranking."]


def test_unregistered_team_is_refused_and_posts_nothing(app_ctx, cursor_for, notices):
    cursor = _team_cursor(eligible=False)
    cursor_for(mentor_selection_service, cursor)
    ok, message = mentor_selection_service.set_team_mentor_preferences(
        TEAM_IDS[0], _ranking("mentor_id", MENTOR_IDS)
    )
    assert (ok, message) == (False, "Only registered teams can rank mentors")
    assert notices == []
    assert not any(s.startswith(("DELETE", "INSERT")) for s, _ in cursor.executed)


def test_failed_commit_posts_nothing(app_ctx, cursor_for, notices, status):
    cursor_for(mentor_selection_service, _team_cursor(), fail_at_commit=True)
    ok, _ = mentor_selection_service.set_team_mentor_preferences(
        TEAM_IDS[0], _ranking("mentor_id", MENTOR_IDS)
    )
    assert not ok
    assert notices == []


def test_invalid_ranking_posts_nothing(app_ctx, notices):
    ok, _ = mentor_selection_service.set_team_mentor_preferences(TEAM_IDS[0], [])
    assert not ok
    assert notices == []


def test_count_failure_still_posts_without_progress(app_ctx, cursor_for, notices, monkeypatch):
    def broken():
        raise RuntimeError("db down")

    monkeypatch.setattr(mentor_selection_service, "get_preference_submission_status", broken)
    cursor_for(mentor_selection_service, _team_cursor())
    ok, _ = mentor_selection_service.set_team_mentor_preferences(
        TEAM_IDS[0], _ranking("mentor_id", MENTOR_IDS)
    )
    assert ok
    assert notices == ["🗳️ Team *Night Owls* submitted its mentor ranking."]


def test_notifier_failure_keeps_the_saved_ranking(app_ctx, cursor_for, status, monkeypatch):
    def broken(text):
        raise RuntimeError("pool shut down")

    monkeypatch.setattr("app.services.event_notifier.notify", broken)
    cursor_for(mentor_selection_service, _team_cursor())
    assert mentor_selection_service.set_team_mentor_preferences(
        TEAM_IDS[0], _ranking("mentor_id", MENTOR_IDS)
    ) == (True, "Mentor preferences saved successfully")


# ── Mentor ranking ──────────────────────────────────────────────────


def _mentor_cursor(*, active=True, had_rows=False):
    return FakeCursor(
        [
            {"name": "Ana Petrova"} if active else None,
            *({"id": t} for t in TEAM_IDS),
            {"found": had_rows},
        ]
    )


@pytest.mark.parametrize(
    ("had_rows", "expected"),
    [
        (
            False,
            "🗳️ Mentor *Ana Petrova* submitted their team ranking. Mentors: 12 of 20 submitted.",
        ),
        (True, "🔁 Mentor *Ana Petrova* updated their team ranking."),
    ],
)
def test_mentor_ranking_posts_submitted_or_updated(
    app_ctx, cursor_for, notices, status, had_rows, expected
):
    cursor_for(mentor_selection_service, _mentor_cursor(had_rows=had_rows))
    ok, _ = mentor_selection_service.set_mentor_team_preferences(
        MENTOR_IDS[0], _ranking("team_id", TEAM_IDS)
    )
    assert ok
    assert notices == [expected]
    _assert_no_choice(notices[0], TEAM_IDS)


def test_inactive_mentor_is_refused_and_posts_nothing(app_ctx, cursor_for, notices):
    cursor_for(mentor_selection_service, _mentor_cursor(active=False))
    ok, message = mentor_selection_service.set_mentor_team_preferences(
        MENTOR_IDS[0], _ranking("team_id", TEAM_IDS)
    )
    assert (ok, message) == (False, "Mentor not found or inactive")
    assert notices == []


# ── Matching run and confirmation ───────────────────────────────────


ASSIGNMENTS = [(t, m) for t in TEAM_IDS for m in MENTOR_IDS]


@pytest.mark.parametrize("was_confirmed", [False, True])
def test_saved_run_posts_counts_only(app_ctx, cursor_for, notices, was_confirmed):
    cursor_for(matching_service, FakeCursor([None, {"is_confirmed": was_confirmed}]))
    matching_service.save_matching_results(ASSIGNMENTS, ["1 mentor(s) have not submitted"])
    assert len(notices) == 1
    text = notices[0]
    assert "*9* assignments for *3* teams" in text
    assert "• 1 mentor(s) have not submitted" in text
    assert ("The earlier confirmation was cleared." in text) is was_confirmed
    _assert_no_choice(text, TEAM_IDS + MENTOR_IDS)


def test_failed_save_raises_and_posts_nothing(app_ctx, cursor_for, notices):
    cursor_for(matching_service, FakeCursor([None, {"is_confirmed": False}]), fail_at_commit=True)
    with pytest.raises(RuntimeError):
        matching_service.save_matching_results(ASSIGNMENTS, [])
    assert notices == []


@pytest.mark.parametrize(("rowcount", "posted"), [(1, True), (0, False)])
def test_confirm_posts_only_on_a_real_change(app_ctx, cursor_for, notices, rowcount, posted):
    cursor_for(matching_service, FakeCursor(rowcount=rowcount))
    assert matching_service.confirm_matching() is posted
    assert notices == ([matching_events.matching_confirmed_text()] if posted else [])
