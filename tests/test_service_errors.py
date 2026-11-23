"""A failing query is logged and answered with a 500 and a fixed message, never the
exception text.

The exception can carry database details (a host name, a constraint, a statement), and
the SPA shows a response's `error` to the user as is. A 500, not a 400, so the 5xx alert
sees a database outage during a rush of team actions.
"""

from unittest.mock import MagicMock

import psycopg2
import pytest
from app.routes import teams as teams_routes
from app.services import mentor_selection_service, mentor_service
from app.services.auth_service import generate_token
from app.services.team_service import TeamService
from app.utils.service_errors import ServiceFailureError

DETAIL = "could not connect to server db-internal-7.cluster.local"

TEAM_CALLS = [
    ("create_team_with_captain", ("Knights", 1), "Could not create the team. Try again."),
    ("join_team", (1, "ABCD1234"), "Could not join the team. Try again."),
    ("leave_team", (1,), "Could not leave the team. Try again."),
    ("remove_member", (1, 2, 1), "Could not remove the member. Try again."),
    ("disband_team", (1,), "Could not disband the team. Try again."),
    ("admin_register_team", (1,), "Could not register the team. Try again."),
    ("admin_unregister_team", (1,), "Could not unregister the team. Try again."),
    ("apply_to_team", (1, 1), "Could not submit the application. Try again."),
    ("accept_join_request", (1, 1), "Could not accept the request. Try again."),
    ("decline_join_request", (1, 1), "Could not decline the request. Try again."),
    ("cancel_join_request", (1, 1), "Could not withdraw the application. Try again."),
]


def _failing_cursor(*args, **kwargs):
    raise psycopg2.OperationalError(DETAIL)


@pytest.mark.parametrize(("method", "args", "message"), TEAM_CALLS)
def test_team_service_hides_the_exception(monkeypatch, method, args, message):
    monkeypatch.setattr("app.services.team_service.get_db_cursor", _failing_cursor)
    with pytest.raises(ServiceFailureError) as failure:
        getattr(TeamService, method)(*args)
    assert str(failure.value) == message


@pytest.mark.parametrize(
    ("save", "id_key"),
    [
        (mentor_selection_service.set_team_mentor_preferences, "mentor_id"),
        (mentor_selection_service.set_mentor_team_preferences, "team_id"),
    ],
)
def test_ranking_save_hides_the_exception(app_ctx, monkeypatch, save, id_key):
    monkeypatch.setattr(mentor_selection_service, "get_db_cursor", _failing_cursor)
    preferences = [{id_key: i, "rank": i} for i in (1, 2, 3)]
    with pytest.raises(ServiceFailureError) as failure:
        save(1, preferences)
    assert str(failure.value) == "Could not save the ranking. Try again."


def test_admin_team_action_failure_is_a_500(app, client, monkeypatch):
    monkeypatch.setattr("app.services.team_service.get_db_cursor", _failing_cursor)
    with app.app_context():
        token = generate_token(0, "admin")

    response = client.post(
        "/api/admin/teams/1/register", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 500
    assert response.get_json() == {
        "success": False,
        "error": "Could not register the team. Try again.",
    }


def test_participant_team_action_failure_is_a_500(app, client, monkeypatch):
    monkeypatch.setattr("app.services.team_service.get_db_cursor", _failing_cursor)
    monkeypatch.setattr(
        "app.database.execute_query",
        lambda *a, **k: {"id": 7, "tokens_valid_from": None, "email_verified": True},
    )
    with app.app_context():
        token = generate_token(7, "participant")

    response = client.post(
        "/api/teams/join",
        json={"join_code": "ABCD1234"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500
    assert response.get_json() == {"success": False, "error": "Could not join the team. Try again."}


def test_mentor_list_hides_the_exception(client, monkeypatch):
    def broken():
        raise Exception(f"Failed to get mentors: {DETAIL}")

    monkeypatch.setattr(mentor_service, "get_all_mentors", broken)
    response = client.get("/api/mentors")
    assert response.status_code == 500
    assert response.get_json() == {"success": False, "error": "Failed to fetch mentors"}


def test_mentor_picture_hides_the_exception(client, monkeypatch):
    # The seeder stores a path, which send_file can't stream (a known bug): the 500 stays.
    monkeypatch.setattr(
        mentor_service, "get_mentor_picture", lambda _id: ("/mentorPictures/a.webp", "a.webp")
    )
    response = client.get("/api/mentors/1/picture")
    assert response.status_code == 500
    assert response.get_json() == {"success": False, "error": "Failed to fetch the picture"}


def test_join_request_mail_goes_through_the_bounded_pool(app, client, monkeypatch):
    assert teams_routes._join_request_mail._max_workers == 4
    pool = MagicMock()
    monkeypatch.setattr(teams_routes, "_join_request_mail", pool)
    monkeypatch.setattr(
        "app.database.execute_query",
        lambda *a, **k: {"id": 7, "tokens_valid_from": None, "email_verified": True},
    )
    service = MagicMock()
    service.apply_to_team.return_value = (True, "Application submitted")
    monkeypatch.setattr(teams_routes, "TeamService", service)
    row = {
        "captain_email": "captain@example.com",
        "captain_first_name": "Ana",
        "team_name": "Knights",
        "app_first_name": "Ivan",
        "app_last_name": "Ivanov",
    }
    monkeypatch.setattr(teams_routes, "execute_query", lambda *a, **k: row)
    with app.app_context():
        token = generate_token(7, "participant")

    response = client.post("/api/teams/3/apply", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 201
    pool.submit.assert_called_once()
    fn, *args = pool.submit.call_args.args
    assert fn is teams_routes.send_join_request_notification
    assert args[1:] == ["captain@example.com", "Ana", "Knights", "Ivan", "Ivanov"]
