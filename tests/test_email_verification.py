"""Unit tests for email verification: the email sender and the team-action gate.

The end-to-end token flow is covered in tests/e2e/test_email_verification_e2e.py.
"""

import email

import pytest
from app.services import email_service
from app.utils.auth_decorators import verified_email_required
from flask import g

VERIFY_URL = "https://fmicodes.test/verify-email?token=abc123"


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, username, password):
        pass

    def sendmail(self, from_addr, to_addrs, message):
        FakeSMTP.sent.append((from_addr, to_addrs, message))


@pytest.fixture()
def fake_smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def test_verification_email_contains_link(fake_smtp):
    config = {"MAIL_USERNAME": "sender@test", "MAIL_PASSWORD": "pw"}
    assert email_service.send_verification_email(config, "student@test", VERIFY_URL) is True
    ((_, to_addrs, raw),) = fake_smtp.sent
    assert to_addrs == ["student@test"]
    parts = email.message_from_string(raw).get_payload()
    assert all(VERIFY_URL in p.get_payload(decode=True).decode() for p in parts)


def test_verification_email_without_credentials_fails_cleanly(fake_smtp):
    assert email_service.send_verification_email({}, "student@test", VERIFY_URL) is False
    assert fake_smtp.sent == []


def test_verification_email_smtp_error_returns_false(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(email_service.smtplib, "SMTP", broken)
    config = {"MAIL_USERNAME": "sender@test", "MAIL_PASSWORD": "pw"}
    assert email_service.send_verification_email(config, "student@test", VERIFY_URL) is False


@verified_email_required
def _team_action():
    return "allowed"


@pytest.fixture()
def participant(app_ctx):
    with app_ctx.test_request_context():
        g.current_user = {"user_id": 7, "role": "participant"}
        yield app_ctx


def test_gate_is_a_no_op_when_flag_off(participant, monkeypatch):
    monkeypatch.setitem(participant.config, "REQUIRE_EMAIL_VERIFICATION", False)
    monkeypatch.setattr(
        "app.database.execute_query",
        lambda *a, **k: pytest.fail("flag off must not query the DB"),
    )
    assert _team_action() == "allowed"


@pytest.mark.parametrize("row", [{"email_verified": False}, None])
def test_gate_blocks_unverified_when_flag_on(participant, monkeypatch, row):
    monkeypatch.setitem(participant.config, "REQUIRE_EMAIL_VERIFICATION", True)
    monkeypatch.setattr("app.database.execute_query", lambda *a, **k: row)
    response, status = _team_action()
    assert status == 403
    assert response.get_json()["code"] == "email_unverified"


def test_gate_allows_verified_when_flag_on(participant, monkeypatch):
    monkeypatch.setitem(participant.config, "REQUIRE_EMAIL_VERIFICATION", True)
    monkeypatch.setattr("app.database.execute_query", lambda *a, **k: {"email_verified": True})
    assert _team_action() == "allowed"
