"""Unit tests for feature_flag_service, event_notifier and the flag routes.

The DB helpers, Redis helpers and the Slack sender are replaced on the service
modules, so nothing here needs Postgres, Redis or the network. The concurrent
schedule race needs real row locks and is covered in tests/e2e/test_feature_flags_e2e.py.
"""

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from app.services import event_notifier, feature_flag_service
from app.services.auth_service import generate_token

NOW = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)


def _row(name, enabled=False, scheduled_value=None, scheduled_at=None):
    return {
        "name": name,
        "enabled": enabled,
        "scheduled_value": scheduled_value,
        "scheduled_at": scheduled_at,
        "updated_at": NOW - timedelta(days=1),
        "now": NOW,
    }


def _rows(**overrides):
    rows = {name: _row(name) for name in feature_flag_service.FLAG_NAMES}
    for name, row in overrides.items():
        rows[name] = row
    return list(rows.values())


class FakeRedis:
    def __init__(self, store=None):
        self.store = dict(store or {})
        self.set_calls = []
        self.bumps = 0

    def get(self, key, default=None):
        return self.store.get(key, default)

    def set(self, key, value, ttl=None):
        self.set_calls.append((key, value, ttl))
        self.store[key] = value
        return True

    def incr(self, key):
        self.bumps += 1
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return True


class FakeCursor:
    """Answers each execute() from *responses*: a list of fetch results in call order."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.executed = []
        self._last = None

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        self._last = self.responses.pop(0) if self.responses else None

    def fetchall(self):
        return self._last or []

    def fetchone(self):
        return self._last


@pytest.fixture()
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(feature_flag_service, "redis_get", fake.get)
    monkeypatch.setattr(feature_flag_service, "redis_set", fake.set)
    monkeypatch.setattr(feature_flag_service, "redis_incr", fake.incr)
    return fake


@pytest.fixture()
def notices(monkeypatch):
    posted = []
    monkeypatch.setattr(feature_flag_service.event_notifier, "notify", posted.append)
    return posted


@pytest.fixture()
def cursors(monkeypatch):
    """Queue FakeCursors for successive get_db_cursor() transactions."""
    queue = []
    used = []

    @contextmanager
    def fake_get_db_cursor(*args, **kwargs):
        cursor = queue.pop(0) if queue else FakeCursor()
        used.append(cursor)
        yield cursor

    monkeypatch.setattr(feature_flag_service, "get_db_cursor", fake_get_db_cursor)
    return queue, used


def _db_rows(monkeypatch, *row_sets):
    """Make successive _read_rows() calls return each row set in turn."""
    calls = list(row_sets)
    monkeypatch.setattr(feature_flag_service, "execute_query", lambda *a, **k: calls.pop(0))


# ── get_flags ───────────────────────────────────────────────────────


def test_get_flags_cache_hit_skips_db(app_ctx, fake_redis, monkeypatch):
    cached = {"registration_open": True, "rankings_live": False, "mentors_stay_tuned": False}
    fake_redis.store["cache:feature_flags:v0"] = json.dumps(cached)
    monkeypatch.setattr(
        feature_flag_service, "execute_query", lambda *a, **k: pytest.fail("DB hit on cache hit")
    )
    assert feature_flag_service.get_flags() == cached


def test_get_flags_miss_reads_db_and_caches(app_ctx, fake_redis, monkeypatch):
    _db_rows(monkeypatch, _rows(registration_open=_row("registration_open", enabled=True)))
    flags = feature_flag_service.get_flags()
    assert flags == {"registration_open": True, "rankings_live": False, "mentors_stay_tuned": False}
    assert fake_redis.set_calls == [("cache:feature_flags:v0", json.dumps(flags), 10)]


@pytest.mark.parametrize("bad", ["not json", json.dumps({"registration_open": True}), "[]"])
def test_get_flags_ignores_bad_cache_entry(app_ctx, fake_redis, monkeypatch, bad):
    fake_redis.store["cache:feature_flags:v0"] = bad
    _db_rows(monkeypatch, _rows())
    assert feature_flag_service.get_flags()["registration_open"] is False


def test_pending_schedule_caps_cache_ttl(app_ctx, fake_redis, monkeypatch):
    soon = NOW + timedelta(seconds=4, milliseconds=500)
    _db_rows(monkeypatch, _rows(rankings_live=_row("rankings_live", False, True, soon)))
    feature_flag_service.get_flags()
    assert fake_redis.set_calls[0][2] == 4


def test_schedule_under_a_second_away_is_not_cached(app_ctx, fake_redis, monkeypatch):
    soon = NOW + timedelta(milliseconds=300)
    _db_rows(monkeypatch, _rows(rankings_live=_row("rankings_live", False, True, soon)))
    feature_flag_service.get_flags()
    assert fake_redis.set_calls == []


def test_due_schedule_is_applied_then_reread(app_ctx, fake_redis, notices, cursors, monkeypatch):
    past = NOW - timedelta(seconds=1)
    queue, used = cursors
    queue.append(
        FakeCursor(
            [
                [
                    {
                        "name": "registration_open",
                        "enabled": False,
                        "scheduled_value": True,
                        "scheduled_at": past,
                    }
                ],
                None,
            ]
        )
    )
    _db_rows(
        monkeypatch,
        _rows(registration_open=_row("registration_open", False, True, past)),
        _rows(registration_open=_row("registration_open", True)),
    )

    assert feature_flag_service.get_flags()["registration_open"] is True
    update_sql, params = used[0].executed[1]
    assert update_sql.startswith("UPDATE feature_flags SET enabled = %s")
    assert params == (True, "registration_open")
    assert len(notices) == 1
    assert "Participant registration" in notices[0]
    assert "OFF → *ON*" in notices[0]
    assert f"<!date^{int(past.timestamp())}^" in notices[0]


def test_a_switch_during_a_read_cannot_leave_the_old_value_cached(app_ctx, fake_redis, monkeypatch):
    old = {"registration_open": False, "rankings_live": False, "mentors_stay_tuned": False}
    new = {**old, "registration_open": True}

    def read_old_while_a_switch_commits():
        feature_flag_service.invalidate_cache()
        return dict(old), 10

    monkeypatch.setattr(feature_flag_service, "_load", read_old_while_a_switch_commits)
    assert feature_flag_service.get_flags() == old

    monkeypatch.setattr(feature_flag_service, "_load", lambda: (dict(new), 10))
    assert feature_flag_service.get_flags() == new


def test_get_flags_raises_when_db_fails(app_ctx, fake_redis, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(feature_flag_service, "execute_query", boom)
    with pytest.raises(RuntimeError):
        feature_flag_service.get_flags()


# ── _apply_due ──────────────────────────────────────────────────────


def test_apply_due_with_nothing_due_leaves_cache_and_posts_nothing(
    app_ctx, fake_redis, notices, cursors
):
    queue, used = cursors
    queue.append(FakeCursor([[]]))
    feature_flag_service._apply_due()
    assert len(used[0].executed) == 1
    assert "FOR UPDATE" in used[0].executed[0][0]
    assert fake_redis.bumps == 0
    assert notices == []


def test_apply_due_same_value_clears_schedule_quietly(app_ctx, fake_redis, notices, cursors):
    queue, used = cursors
    queue.append(
        FakeCursor(
            [
                [
                    {
                        "name": "rankings_live",
                        "enabled": True,
                        "scheduled_value": True,
                        "scheduled_at": NOW,
                    }
                ],
                None,
            ]
        )
    )
    feature_flag_service._apply_due()
    sql, params = used[0].executed[1]
    assert sql == (
        "UPDATE feature_flags SET scheduled_value = NULL, scheduled_at = NULL WHERE name = %s"
    )
    assert params == ("rankings_live",)
    assert fake_redis.bumps == 1
    assert notices == []


# ── set_flag / schedule_flag / cancel_schedule ──────────────────────


def test_set_flag_changes_value_and_announces(app_ctx, fake_redis, notices, cursors):
    queue, used = cursors
    queue += [FakeCursor([[]]), FakeCursor([{"enabled": False}, None])]
    assert feature_flag_service.set_flag("rankings_live", True) is True
    assert used[1].executed[1] == (
        "UPDATE feature_flags SET enabled = %s, updated_at = NOW() WHERE name = %s",
        (True, "rankings_live"),
    )
    assert fake_redis.bumps == 1
    assert notices == ["🚦 *Live rankings*: OFF → *ON* (switched by the admin)"]


def test_set_flag_same_value_is_a_quiet_no_op(app_ctx, fake_redis, notices, cursors):
    queue, used = cursors
    queue += [FakeCursor([[]]), FakeCursor([{"enabled": True}])]
    assert feature_flag_service.set_flag("rankings_live", True) is False
    assert len(used[1].executed) == 1
    assert fake_redis.bumps == 0
    assert notices == []


def test_set_flag_unknown_row_raises(app_ctx, fake_redis, cursors):
    queue, _ = cursors
    queue += [FakeCursor([[]]), FakeCursor([None])]
    with pytest.raises(LookupError):
        feature_flag_service.set_flag("rankings_live", True)


def test_schedule_flag_rejects_past_time(app_ctx, fake_redis, cursors):
    queue, used = cursors
    queue += [FakeCursor([[]]), FakeCursor([{"enabled": False, "is_past": True}])]
    error = feature_flag_service.schedule_flag("registration_open", True, NOW)
    assert error == "Scheduled time must be in the future"
    assert len(used[1].executed) == 1


def test_schedule_flag_rejects_current_value(app_ctx, fake_redis, cursors):
    queue, _ = cursors
    queue += [
        FakeCursor([[]]),
        FakeCursor([{"enabled": True, "is_past": False, "has_schedule": False}]),
    ]
    error = feature_flag_service.schedule_flag("registration_open", True, NOW)
    assert error == "The flag is already on"


def test_schedule_flag_current_value_with_a_pending_schedule_points_to_cancel(
    app_ctx, fake_redis, cursors
):
    queue, _ = cursors
    queue += [
        FakeCursor([[]]),
        FakeCursor([{"enabled": False, "is_past": False, "has_schedule": True}]),
    ]
    error = feature_flag_service.schedule_flag("registration_open", False, NOW)
    assert error == "The flag is already off; cancel the pending schedule to keep it that way"


def test_schedule_flag_stores_schedule(app_ctx, fake_redis, notices, cursors):
    queue, used = cursors
    queue += [
        FakeCursor([[]]),
        FakeCursor([{"enabled": False, "is_past": False, "has_schedule": False}, None]),
    ]
    at = NOW + timedelta(hours=1)
    assert feature_flag_service.schedule_flag("registration_open", True, at) is None
    assert used[1].executed[1] == (
        "UPDATE feature_flags SET scheduled_value = %s, scheduled_at = %s WHERE name = %s",
        (True, at, "registration_open"),
    )
    assert fake_redis.bumps == 1
    assert notices == []


def test_cancel_schedule(app_ctx, fake_redis, cursors):
    queue, _ = cursors
    queue += [FakeCursor([[]]), FakeCursor([{"name": "rankings_live"}])]
    assert feature_flag_service.cancel_schedule("rankings_live") is True


def test_cancel_schedule_without_one_is_idempotent(app_ctx, fake_redis, cursors):
    queue, _ = cursors
    queue += [FakeCursor([[]]), FakeCursor([None, {"?column?": 1}])]
    assert feature_flag_service.cancel_schedule("rankings_live") is False


def test_list_flags_serialises_times(app_ctx, monkeypatch):
    at = NOW + timedelta(hours=2)
    _db_rows(monkeypatch, _rows(rankings_live=_row("rankings_live", False, True, at)))
    flags = {f["name"]: f for f in feature_flag_service.list_flags()}
    assert list(flags) == list(feature_flag_service.FLAG_NAMES)
    assert flags["rankings_live"]["scheduled_at"] == at.isoformat()
    assert flags["rankings_live"]["scheduled_value"] is True
    assert flags["registration_open"]["scheduled_at"] is None


# ── event_notifier ──────────────────────────────────────────────────


def test_notifier_without_webhook_only_logs(app_ctx, monkeypatch):
    app_ctx.config["SLACK_EVENTS_WEBHOOK_URL"] = ""
    monkeypatch.setattr(event_notifier._executor, "submit", lambda *a: pytest.fail("must not post"))
    event_notifier.notify("hello")


def test_notifier_posts_off_the_request_thread(app_ctx, monkeypatch):
    submitted = []
    app_ctx.config["SLACK_EVENTS_WEBHOOK_URL"] = "https://hooks.example/x"
    monkeypatch.setattr(event_notifier._executor, "submit", lambda *a: submitted.append(a))
    try:
        event_notifier.notify("hello")
    finally:
        app_ctx.config["SLACK_EVENTS_WEBHOOK_URL"] = ""
    assert submitted == [(event_notifier._post, "https://hooks.example/x", "hello")]


def test_notifier_post_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(event_notifier.urllib.request, "urlopen", boom)
    assert event_notifier._post("https://hooks.example/x", "hello") is False


# ── Routes ──────────────────────────────────────────────────────────


@pytest.fixture()
def admin_headers(app_ctx):
    return {"Authorization": f"Bearer {generate_token(0, 'admin')}"}


@pytest.fixture()
def participant_headers(app_ctx):
    return {"Authorization": f"Bearer {generate_token(7, 'participant')}"}


def test_config_route_keeps_its_shape(client, monkeypatch):
    monkeypatch.setattr(
        feature_flag_service,
        "get_flags",
        lambda: {"registration_open": True, "rankings_live": False, "mentors_stay_tuned": True},
    )
    rv = client.get("/api/config")
    assert rv.status_code == 200
    assert rv.get_json() == {
        "REGISTRATION_OPEN": True,
        "MENTORS_STAY_TUNED": True,
        "RANKINGS_LIVE": False,
        "REQUIRE_EMAIL_VERIFICATION": False,
    }


def test_config_route_is_not_rate_limited(monkeypatch):
    """Behind the ingress every visitor shares one limiter key, and the SPA polls."""
    for var in ("REDIS_SENTINELS", "REDIS_MASTER_NAME", "REDIS_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "y" * 40)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$" + "a" * 22)
    with patch("app.database.init_database"):
        from app import create_app

        limited_app = create_app("production")
    monkeypatch.setattr(
        feature_flag_service,
        "get_flags",
        lambda: dict.fromkeys(feature_flag_service.FLAG_NAMES, False),
    )
    c = limited_app.test_client()
    assert {c.get("/api/config").status_code for _ in range(210)} == {200}


def test_config_route_503_when_flags_unreadable(client, monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(feature_flag_service, "get_flags", boom)
    assert client.get("/api/config").status_code == 503


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/admin/flags"),
        ("put", "/api/admin/flags/registration_open"),
        ("put", "/api/admin/flags/registration_open/schedule"),
        ("delete", "/api/admin/flags/registration_open/schedule"),
    ],
)
def test_flag_admin_routes_need_admin(client, participant_headers, monkeypatch, method, path):
    monkeypatch.setattr(
        "app.utils.auth_decorators._token_predates_revocation_epoch", lambda payload: False
    )
    assert getattr(client, method)(path).status_code == 401
    assert getattr(client, method)(path, headers=participant_headers).status_code == 403


def test_set_flag_route(client, admin_headers, monkeypatch):
    calls = []
    monkeypatch.setattr(
        feature_flag_service, "set_flag", lambda name, value: calls.append((name, value)) or True
    )
    rv = client.put("/api/admin/flags/rankings_live", json={"enabled": True}, headers=admin_headers)
    assert rv.status_code == 200
    assert rv.get_json() == {"success": True, "changed": True}
    assert calls == [("rankings_live", True)]


@pytest.mark.parametrize("body", [{}, {"enabled": "true"}, {"enabled": 1}, {"enabled": None}])
def test_set_flag_route_rejects_non_boolean(client, admin_headers, body):
    rv = client.put("/api/admin/flags/rankings_live", json=body, headers=admin_headers)
    assert rv.status_code == 400


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("put", "/api/admin/flags/require_email_verification"),
        ("put", "/api/admin/flags/nope/schedule"),
        ("delete", "/api/admin/flags/nope/schedule"),
    ],
)
def test_unknown_flag_is_404(client, admin_headers, method, path):
    rv = getattr(client, method)(path, json={"enabled": True}, headers=admin_headers)
    assert rv.status_code == 404


def test_schedule_route_parses_offset_time(client, admin_headers, monkeypatch):
    calls = []
    monkeypatch.setattr(
        feature_flag_service,
        "schedule_flag",
        lambda name, value, at: calls.append((name, value, at)),
    )
    rv = client.put(
        "/api/admin/flags/registration_open/schedule",
        json={"value": True, "at": "2026-11-20T10:00:00+02:00"},
        headers=admin_headers,
    )
    assert rv.status_code == 200
    name, value, at = calls[0]
    assert (name, value) == ("registration_open", True)
    assert at == datetime(2026, 11, 20, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "body",
    [
        {"value": True},
        {"value": True, "at": "2026-11-20T10:00:00"},
        {"value": True, "at": "tomorrow"},
        {"value": True, "at": 1700000000},
        {"value": "yes", "at": "2026-11-20T10:00:00Z"},
    ],
)
def test_schedule_route_rejects_bad_input(client, admin_headers, body):
    rv = client.put("/api/admin/flags/registration_open/schedule", json=body, headers=admin_headers)
    assert rv.status_code == 400


def test_schedule_route_passes_service_error_as_400(client, admin_headers, monkeypatch):
    monkeypatch.setattr(
        feature_flag_service,
        "schedule_flag",
        lambda *a: "Scheduled time must be in the future",
    )
    rv = client.put(
        "/api/admin/flags/registration_open/schedule",
        json={"value": True, "at": "2020-01-01T00:00:00Z"},
        headers=admin_headers,
    )
    assert rv.status_code == 400
    assert rv.get_json()["error"] == "Scheduled time must be in the future"


def test_cancel_schedule_route(client, admin_headers, monkeypatch):
    monkeypatch.setattr(feature_flag_service, "cancel_schedule", lambda name: False)
    rv = client.delete("/api/admin/flags/registration_open/schedule", headers=admin_headers)
    assert rv.status_code == 200
    assert rv.get_json() == {"success": True, "cancelled": False}
