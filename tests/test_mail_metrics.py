"""mail_sent_total: every send counted once by kind and result, so a spent quota shows up."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from app.services import email_service
from prometheus_client import REGISTRY

BACKEND_DIR = Path(__file__).parent.parent / "backend"

CONFIG = {"MAIL_USERNAME": "sender@test", "MAIL_PASSWORD": "pw"}

SENDERS = {
    "verification": lambda config: email_service.send_verification_email(
        config, "student@test", "https://fmicodes.test/verify-email?token=t"
    ),
    "reset": lambda config: email_service.send_password_reset_link_email(
        config, "student@test", "https://fmicodes.test/reset-password?token=t", "participant"
    ),
    "join_request": lambda config: email_service.send_join_request_notification(
        config, "captain@test", "Cap", "Team A", "Ann", "Lee"
    ),
}


def _counts(kind):
    return {
        result: REGISTRY.get_sample_value("mail_sent_total", {"kind": kind, "result": result})
        or 0.0
        for result in ("sent", "failed", "skipped")
    }


class _SMTP:
    def __init__(self, host, port, timeout):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, username, password):
        pass

    def sendmail(self, from_addr, to_addrs, message):
        pass


class _QuotaSpentSMTP(_SMTP):
    def sendmail(self, from_addr, to_addrs, message):
        raise email_service.smtplib.SMTPDataError(550, b"5.4.5 Daily user sending limit exceeded.")


def _send(monkeypatch, kind, smtp, config):
    monkeypatch.setattr(email_service.smtplib, "SMTP", smtp)
    before = _counts(kind)
    returned = SENDERS[kind](config)
    after = _counts(kind)
    return returned, {result: after[result] - before[result] for result in after}


@pytest.mark.parametrize("kind", sorted(SENDERS))
def test_a_delivered_mail_counts_as_sent(monkeypatch, kind):
    returned, delta = _send(monkeypatch, kind, _SMTP, CONFIG)
    assert returned is True
    assert delta == {"sent": 1.0, "failed": 0.0, "skipped": 0.0}


@pytest.mark.parametrize("kind", sorted(SENDERS))
def test_a_refused_mail_counts_as_failed(monkeypatch, kind):
    returned, delta = _send(monkeypatch, kind, _QuotaSpentSMTP, CONFIG)
    assert returned is False
    assert delta == {"sent": 0.0, "failed": 1.0, "skipped": 0.0}


@pytest.mark.parametrize("kind", sorted(SENDERS))
def test_no_credentials_counts_as_skipped_not_failed(monkeypatch, kind):
    returned, delta = _send(monkeypatch, kind, _SMTP, {})
    assert returned is False
    assert delta == {"sent": 0.0, "failed": 0.0, "skipped": 1.0}


def test_every_series_is_exported_at_zero_before_any_send():
    """In a fresh process: the tests above have sent mail in this one, which creates the series.

    Without a 0 sample before its first failure, increase() misses that failure.
    """
    env = {k: v for k, v in os.environ.items() if k != "PROMETHEUS_MULTIPROC_DIR"}
    env["PYTHONPATH"] = str(BACKEND_DIR)
    code = (
        "from app.services import email_service\n"
        "from prometheus_client import generate_latest\n"
        "print(generate_latest().decode())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    for kind in SENDERS:
        for outcome in ("sent", "failed", "skipped"):
            assert f'mail_sent_total{{kind="{kind}",result="{outcome}"}} 0.0' in result.stdout


def test_the_app_exports_every_series(client):
    body = client.get("/metrics").get_data(as_text=True)
    for kind in SENDERS:
        for outcome in ("sent", "failed", "skipped"):
            assert f'mail_sent_total{{kind="{kind}",result="{outcome}"}}' in body
