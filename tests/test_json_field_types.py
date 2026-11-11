"""Wrongly typed JSON bodies and fields are client errors: 400, never 500 (issue #224).

Every request here is malformed, so a route must refuse it before any query of its own.
Only the auth decorators read the database, through a patched execute_query; there is no
pool behind anything else. Each case asserts the validator's own message, because some
services turn a failed query into a 400 too and a bare status would pass without the fix.
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
    (5, "count"),
    ("abc", "count"),
    ({"a": 1}, "count"),
    (None, "count"),
    ([1, 2, 3], "shape"),
    (["a", "b", "c"], "shape"),
    (lambda k: _prefs(k, ids=("1", "2", "3")), "shape"),
    (lambda k: _prefs(k, ids=([1], [2], [3])), "shape"),
    (lambda k: _prefs(k, ids=(1.0, 2.0, 3.0)), "shape"),
    (lambda k: _prefs(k, ids=(True, 2, 3)), "shape"),
    (lambda k: _prefs(k, ids=(2**31, 2, 3)), "shape"),
    (lambda k: _prefs(k, ranks=("1", 2, 3)), "shape"),
    (lambda k: _prefs(k, ranks=(True, 2, 3)), "shape"),
    (lambda k: _prefs(k, ranks=(1, 2, None)), "shape"),
    (lambda k: [{"rank": 1}, {"rank": 2}, {"rank": 3}], "shape"),
    (lambda k: _prefs(k, ranks=(1, 1, 2)), "ranks"),
    (lambda k: _prefs(k, ids=(1, 1, 2)), "distinct"),
]


@pytest.mark.parametrize(
    ("route", "id_key", "noun"),
    [("team_preferences", "mentor_id", "mentors"), ("mentor_preferences", "team_id", "teams")],
)
@pytest.mark.parametrize(("preferences", "kind"), BAD_PREFERENCES)
def test_malformed_preferences_are_400(call, route, id_key, noun, preferences, kind):
    if callable(preferences):
        preferences = preferences(id_key)
    error = {
        "count": f"You must rank exactly 3 {noun}",
        "shape": f"Each preference needs a whole-number {id_key} and rank",
        "ranks": "Ranks must be exactly 1, 2, and 3",
        "distinct": f"All three {noun} must be different",
    }[kind]
    _expect_400(call(route, {"preferences": preferences}), error)


@pytest.mark.parametrize("value", [v for v in WRONG_TYPES if v is not True] + ["true"])
def test_flag_switch_of_wrong_type_is_400(call, value):
    _expect_400(call("set_flag", {"enabled": value}), "enabled must be true or false")


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"value": "true", "at": "2026-12-01T10:00:00+02:00"}, "value must be true or false"),
        ({"value": True, "at": 5}, "at must be an ISO 8601 time with a UTC offset"),
        ({"value": True, "at": ["2026-12-01"]}, "at must be an ISO 8601 time with a UTC offset"),
    ],
)
def test_flag_schedule_of_wrong_type_is_400(call, body, error):
    _expect_400(call("schedule_flag", body), error)


@pytest.mark.parametrize("score", [["x"], {"a": 1}, "abc", True])
def test_score_of_wrong_type_is_400(call, score):
    _expect_400(call("score", {"score": score}), "Score must be a number")


# A lone surrogate is valid JSON but can't be encoded to UTF-8; Postgres can't store a NUL.
INVALID_TEXT = ["\ud800", "a\udfffb", "a\x00b"]


@pytest.mark.parametrize(("route", "field"), STRING_FIELDS)
@pytest.mark.parametrize("value", INVALID_TEXT)
def test_text_that_cannot_be_stored_is_400(call, route, field, value):
    body = {**ROUTES[route][3], field: value}
    _expect_400(call(route, body), f"{field} contains an invalid character")


@pytest.mark.parametrize(
    ("route", "field", "size"),
    [
        ("register", "first_name", 100),
        ("register", "last_name", 100),
        ("register", "email", 255),
        ("register", "phone_number", 20),
        ("register", "faculty_number", 20),
        ("create_team", "team_name", 100),
    ],
)
def test_text_longer_than_its_column_is_400(call, route, field, size):
    body = {**ROUTES[route][3], field: "a" * (size + 1)}
    _expect_400(call(route, body), f"{field} must be at most {size} characters")


@pytest.mark.parametrize("value", [5, ["x"], {"a": "b"}, "\ud800", "a\x00b"])
def test_other_university_field_of_wrong_type_or_text_is_400(call, value):
    body = {
        **ROUTES["register"][3],
        "university_id": "other",
        "university_other": {"name": value, "city": "Sofia", "country": "Bulgaria"},
    }
    response = call("register", body)
    _expect_400(response)
    assert response.get_json()["error"].startswith("university_other.name ")
