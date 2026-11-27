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
from app.utils.service_errors import ServiceFailureError

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

    def fetchall(self):
        return self._last or []


def _save_cursor(was_confirmed, written):
    """A save's statements in order: lock 2, the state row, DELETE, INSERT ... RETURNING."""
    rows = [{"team_id": t, "mentor_id": m} for t, m in written]
    return FakeCursor([None, {"is_confirmed": was_confirmed}, None, rows])


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


def _team_cursor(*, eligible=True, had_rows=False, name="Night Owls", open_=True, confirmed=False):
    return FakeCursor(
        [
            {"is_confirmed": confirmed},
            {"value": open_},
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
    with pytest.raises(ServiceFailureError):
        mentor_selection_service.set_team_mentor_preferences(
            TEAM_IDS[0], _ranking("mentor_id", MENTOR_IDS)
        )
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


def _mentor_cursor(*, active=True, had_rows=False, open_=True, confirmed=False):
    return FakeCursor(
        [
            {"is_confirmed": confirmed},
            {"value": open_},
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


# ── Submissions closed under the lock ───────────────────────────────


@pytest.mark.parametrize(
    ("save", "make_cursor", "ranking"),
    [
        (
            mentor_selection_service.set_team_mentor_preferences,
            _team_cursor,
            _ranking("mentor_id", MENTOR_IDS),
        ),
        (
            mentor_selection_service.set_mentor_team_preferences,
            _mentor_cursor,
            _ranking("team_id", TEAM_IDS),
        ),
    ],
)
def test_save_rechecks_the_flag_under_a_lock_before_writing(
    app_ctx, cursor_for, notices, save, make_cursor, ranking
):
    cursor = make_cursor(open_=False)
    cursor_for(mentor_selection_service, cursor)
    assert save(4101, ranking) == (False, mentor_selection_service.PREFERENCES_CLOSED)
    flag_sql, params = cursor.executed[1]
    assert flag_sql.endswith("FROM feature_flags WHERE name = %s FOR SHARE")
    assert "scheduled_at <= NOW()" in flag_sql
    assert params == ("preferences_open",)
    assert len(cursor.executed) == 2
    assert notices == []


@pytest.mark.parametrize(
    ("save", "make_cursor", "ranking"),
    [
        (
            mentor_selection_service.set_team_mentor_preferences,
            _team_cursor,
            _ranking("mentor_id", MENTOR_IDS),
        ),
        (
            mentor_selection_service.set_mentor_team_preferences,
            _mentor_cursor,
            _ranking("team_id", TEAM_IDS),
        ),
    ],
)
def test_save_checks_the_confirmation_first_and_refuses_while_frozen(
    app_ctx, cursor_for, notices, save, make_cursor, ranking
):
    """Before the flag and before any team or mentor row lock: the lock order."""
    cursor = make_cursor(confirmed=True, open_=False)
    cursor_for(mentor_selection_service, cursor)
    assert save(4101, ranking) == (False, mentor_selection_service.PREFERENCES_CONFIRMED)
    assert cursor.executed == [
        ("SELECT is_confirmed FROM matching_state WHERE id = 1 FOR SHARE", None)
    ]
    assert notices == []


# ── Matching run and confirmation ───────────────────────────────────


ASSIGNMENTS = [(t, m) for t in TEAM_IDS for m in MENTOR_IDS]


@pytest.fixture()
def bumps(monkeypatch):
    """Record feature_flag_service.invalidate_cache() calls made by the matching service."""
    calls = []
    monkeypatch.setattr(
        matching_service.feature_flag_service, "invalidate_cache", lambda: calls.append(1)
    )
    return calls


@pytest.mark.parametrize("was_confirmed", [False, True])
def test_saved_run_posts_counts_only(app_ctx, cursor_for, notices, bumps, was_confirmed):
    cursor_for(matching_service, _save_cursor(was_confirmed, ASSIGNMENTS))
    saved = matching_service.save_matching_results(
        ASSIGNMENTS, ["1 mentor(s) have not submitted"], 3
    )
    assert saved == ASSIGNMENTS
    assert len(notices) == 1
    text = notices[0]
    assert "*9* assignments for *3* teams" in text
    assert "• 1 mentor(s) have not submitted" in text
    assert ("The earlier confirmation was cleared." in text) is was_confirmed
    _assert_no_choice(text, TEAM_IDS + MENTOR_IDS)
    # A cleared confirmation lifts the freeze, so /api/config must not serve the old bit.
    assert len(bumps) == (1 if was_confirmed else 0)


def test_save_writes_only_pairs_of_teams_still_registered(app_ctx, cursor_for, notices, bumps):
    """The run read its teams outside the lock: one that lost its slot since is skipped,
    and the feed and the answer count the rows written, not the pairs the run produced."""
    written = ASSIGNMENTS[3:]
    cursor = _save_cursor(False, written)
    cursor_for(matching_service, cursor)
    assert matching_service.save_matching_results(ASSIGNMENTS, [], 3) == written
    [(insert_sql, params)] = [(s, p) for s, p in cursor.executed if s.startswith("INSERT")]
    assert "JOIN teams t ON t.id = p.team_id AND t.status = 'active' AND t.is_registered" in (
        insert_sql
    )
    assert insert_sql.endswith("RETURNING team_id, mentor_id")
    assert params == ([t for t, _ in ASSIGNMENTS], [m for _, m in ASSIGNMENTS])
    assert "*6* assignments for *3* teams" in notices[0]


def test_failed_save_raises_and_posts_nothing(app_ctx, cursor_for, notices):
    cursor_for(matching_service, FakeCursor([None, {"is_confirmed": False}]), fail_at_commit=True)
    with pytest.raises(RuntimeError):
        matching_service.save_matching_results(ASSIGNMENTS, [], 3)
    assert notices == []


def test_run_counts_teams_left_without_a_mentor(app_ctx, cursor_for, notices, monkeypatch):
    """One mentor covers at most 3 teams, so the fourth team gets none. The run
    still matched 4 teams, and the feed must say 4, not the 3 in the pairs."""
    teams = [{"id": t} for t in (*TEAM_IDS, 7104)]
    rows = iter([teams, [{"id": MENTOR_IDS[0]}], [], []])
    monkeypatch.setattr(matching_service, "execute_query", lambda *a, **k: next(rows))
    ok, _, assignments, warnings, team_count = matching_service.run_gale_shapley()
    assert ok
    assert len({t for t, _ in assignments}) == 3
    assert team_count == 4

    cursor_for(matching_service, _save_cursor(False, assignments))
    matching_service.save_matching_results(assignments, warnings, team_count)
    assert "*3* assignments for *4* teams" in notices[0]
    assert "• 4 team(s) received fewer than 3 mentors" in notices[0]


def test_a_mentor_whose_picks_all_lost_their_slot_counts_as_not_submitted(app_ctx, monkeypatch):
    rows = iter(
        [
            [{"id": TEAM_IDS[0]}],
            [{"id": MENTOR_IDS[0]}],
            [{"mentor_id": MENTOR_IDS[0], "team_id": 9999}],
            [],
        ]
    )
    monkeypatch.setattr(matching_service, "execute_query", lambda *a, **k: next(rows))
    *_, warnings, _ = matching_service.run_gale_shapley()
    assert "1 mentor(s) have not submitted team preferences" in warnings


@pytest.mark.parametrize(("rowcount", "posted"), [(1, True), (0, False)])
def test_confirm_posts_only_on_a_real_change(app_ctx, cursor_for, notices, bumps, rowcount, posted):
    cursor_for(matching_service, FakeCursor(rowcount=rowcount))
    assert matching_service.confirm_matching() is posted
    assert notices == ([matching_events.matching_confirmed_text()] if posted else [])
    assert len(bumps) == (1 if posted else 0)


# ── Admin hand edits ────────────────────────────────────────────────


def test_admin_edit_texts_name_the_team_and_a_count():
    assert matching_events.admin_mentors_changed_text("Night Owls", 4) == (
        "🛠️ Admin changed team *Night Owls*'s mentors (now 4)."
    )
    assert matching_events.admin_member_added_text("Night Owls", 3) == (
        "🛠️ Admin added a member to team *Night Owls* (now 3)."
    )
    assert matching_events.admin_member_removed_text("Night Owls", 2) == (
        "🛠️ Admin removed a member from team *Night Owls* (now 2)."
    )
    assert matching_events.admin_unregistered_text("Night Owls") == (
        "🛠️ Admin unregistered team *Night Owls*; its mentors were released."
    )


@pytest.mark.parametrize(
    "text",
    [
        lambda name: matching_events.admin_mentors_changed_text(name, 1),
        lambda name: matching_events.admin_member_added_text(name, 1),
        lambda name: matching_events.admin_member_removed_text(name, 1),
        matching_events.admin_unregistered_text,
    ],
)
def test_admin_edit_texts_escape_the_team_name(text):
    out = text("<!channel> & <https://evil.example|click>")
    assert "<" not in out and ">" not in out
    assert "&lt;!channel&gt; &amp; &lt;https://evil.example|click&gt;" in out
