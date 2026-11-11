"""Wrongly typed JSON bodies and fields are client errors: 400, never 500 (issue #224).

Every request here is malformed, so a route must refuse it before any query of its own.
Only the auth decorators read the database, through a patched execute_query; a route that
reached a real query would fail on the missing pool and answer 500.
"""

import pytest
from app.services import feature_flag_service
from app.services.auth_service import generate_token

WRONG_TYPES = [5, 1.5, True, ["x"], {"a": "b"}]
PASSWORD = "p" * 12

ROUTES = {
    "register": (
        "POST",
        "/api/auth/register",
        None,
        {
            "first_name": "Ana",
            "last_name": "Petrova",
            "email": "ana@example.com",
            "password": PASSWORD,
            "phone_number": "0700123456",
            "faculty_number": "1MI0700123",
            "course": "Bachelor 1st Year",
            "specialty_id": "1",
            "university_id": "1",
        },
    ),
    "login": (
        "POST",
        "/api/auth/login",
        None,
        {"email": "a@example.com", "password": "pw", "role": "participant"},
    ),
    "change_password": (
        "PATCH",
        "/api/auth/change-password",
        "participant",
        {"current_password": PASSWORD, "new_password": PASSWORD},
    ),
    "reset": (
        "POST",
        "/api/auth/reset-password",
        None,
        {"email": "a@example.com", "role": "participant"},
    ),
    "reset_confirm": (
        "POST",
        "/api/auth/reset-password/confirm",
        None,
        {"token": "abc", "new_password": PASSWORD, "role": "participant"},
    ),
    "verify_email": ("POST", "/api/auth/verify-email", None, {"token": "abc"}),
    "create_team": ("POST", "/api/teams", "participant", {"team_name": "Knights"}),
    "join_team": ("POST", "/api/teams/join", "participant", {"join_code": "ABCD1234"}),
    "team_preferences": (
        "POST",
        "/api/teams/1/mentor-preferences",
        "participant",
        {"preferences": []},
    ),
    "mentor_preferences": (
        "POST",
        "/api/mentors/team-preferences",
        "mentor",
        {"preferences": []},
    ),
    "set_flag": ("PUT", "/api/admin/flags/registration_open", "admin", {"enabled": True}),
    "schedule_flag": (
        "PUT",
        "/api/admin/flags/registration_open/schedule",
        "admin",
        {"value": True, "at": "2026-12-01T10:00:00+02:00"},
    ),
    "bug_report": (
        "POST",
        "/api/bug-report",
        None,
        {"what_did": "clicked", "what_happened": "broke", "page": "/team"},
    ),
    "score": ("PUT", "/api/admin/teams/1/score", "admin", {"score": 50}),
}

STRING_FIELDS = [
    (route, field)
    for route, fields in {
        "register": [
            "first_name",
            "last_name",
            "email",
            "password",
            "phone_number",
            "faculty_number",
            "course",
        ],
        "login": ["email", "password", "role"],
        "change_password": ["current_password", "new_password"],
        "reset": ["email", "role"],
        "reset_confirm": ["token", "new_password", "role"],
        "verify_email": ["token"],
        "create_team": ["team_name"],
        "join_team": ["join_code"],
        "bug_report": ["what_did", "what_happened", "page"],
    }.items()
    for field in fields
]

# Pass the auth decorators: a verified captain of team 1 with no revocation epoch.
_USER_ROW = {
    "id": 1,
    "team_id": 1,
    "is_captain": True,
    "email_verified": True,
    "tokens_valid_from": None,
}


@pytest.fixture()
def call(app, client, monkeypatch):
    monkeypatch.setattr("app.database.execute_query", lambda *a, **k: _USER_ROW)
    monkeypatch.setattr(feature_flag_service, "is_enabled", lambda name: True)

    def send(route, body):
        method, path, role, _ = ROUTES[route]
        headers = {}
        if role:
            with app.app_context():
                headers["Authorization"] = f"Bearer {generate_token(1, role)}"
        return client.open(path, method=method, json=body, headers=headers)

    return send


def _expect_400(response, error=None):
    assert response.status_code == 400, response.get_data(as_text=True)
    body = response.get_json()
    assert body["success"] is False
    if error is not None:
        assert body["error"] == error


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("body", [["not", "an", "object"], "text", 5])
def test_non_object_body_is_400(call, route, body):
    _expect_400(call(route, body), "Request body must be a JSON object")


@pytest.mark.parametrize(("route", "field"), STRING_FIELDS)
@pytest.mark.parametrize("value", WRONG_TYPES)
def test_non_string_field_is_400(call, route, field, value):
    body = {**ROUTES[route][3], field: value}
    _expect_400(call(route, body), f"{field} must be a string")


@pytest.mark.parametrize("field", ["specialty_id", "university_id"])
@pytest.mark.parametrize("value", [1.5, True, ["1"], {"id": 1}, "abc", "0", -1, 2**31, "9" * 40])
def test_register_lookup_id_of_wrong_type_or_range_is_400(call, field, value):
    body = {**ROUTES["register"][3], field: value}
    _expect_400(call("register", body), f"Invalid {field}")


def _prefs(id_key, ids=(1, 2, 3), ranks=(1, 2, 3)):
    return [{id_key: i, "rank": r} for i, r in zip(ids, ranks, strict=True)]


BAD_PREFERENCES = [
    5,
    "abc",
    {"a": 1},
    [1, 2, 3],
    ["a", "b", "c"],
    lambda k: _prefs(k, ids=("1", "2", "3")),
    lambda k: _prefs(k, ids=([1], [2], [3])),
    lambda k: _prefs(k, ids=(1.0, 2.0, 3.0)),
    lambda k: _prefs(k, ids=(True, 2, 3)),
    lambda k: _prefs(k, ids=(2**31, 2, 3)),
    lambda k: _prefs(k, ranks=("1", 2, 3)),
    lambda k: _prefs(k, ranks=(True, 2, 3)),
    lambda k: _prefs(k, ranks=(1, 2, None)),
    lambda k: [{"rank": 1}, {"rank": 2}, {"rank": 3}],
    lambda k: _prefs(k, ranks=(1, 1, 2)),
    lambda k: _prefs(k, ids=(1, 1, 2)),
]


@pytest.mark.parametrize(
    ("route", "id_key"),
    [("team_preferences", "mentor_id"), ("mentor_preferences", "team_id")],
)
@pytest.mark.parametrize("preferences", BAD_PREFERENCES)
def test_malformed_preferences_are_400(call, route, id_key, preferences):
    if callable(preferences):
        preferences = preferences(id_key)
    _expect_400(call(route, {"preferences": preferences}))


@pytest.mark.parametrize("value", [v for v in WRONG_TYPES if v is not True] + ["true"])
def test_flag_switch_of_wrong_type_is_400(call, value):
    _expect_400(call("set_flag", {"enabled": value}), "enabled must be true or false")


@pytest.mark.parametrize(
    "body",
    [
        {"value": "true", "at": "2026-12-01T10:00:00+02:00"},
        {"value": True, "at": 5},
        {"value": True, "at": ["2026-12-01T10:00:00+02:00"]},
    ],
)
def test_flag_schedule_of_wrong_type_is_400(call, body):
    _expect_400(call("schedule_flag", body))


@pytest.mark.parametrize("score", [["x"], {"a": 1}, "abc"])
def test_score_of_wrong_type_is_400(call, score):
    _expect_400(call("score", {"score": score}))
