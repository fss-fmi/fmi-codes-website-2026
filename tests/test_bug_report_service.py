"""Unit tests for app/services/bug_report_service.py (no network, no database)."""

import json

import pytest
from app.services import bug_report_service as svc

REPORT = {
    "reporter_name": "Ana Petrova",
    "reporter_email": "ana@example.test",
    "reporter_role": "participant",
    "page_url": "/team",
    "what_did": "clicked APPLY",
    "what_happened": "nothing happened",
}


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def sent(monkeypatch):
    requests = []

    def fake_urlopen(req, timeout):
        requests.append(req)
        return Response()

    monkeypatch.setattr(svc.urllib.request, "urlopen", fake_urlopen)
    return requests


def _blocks_text(payload):
    parts = [payload["text"]]
    for block in payload["blocks"]:
        if "text" in block:
            parts.append(block["text"]["text"])
        parts += [f["text"] for f in block.get("fields", [])]
        parts += [e["text"] for e in block.get("elements", [])]
    return "\n".join(parts)


class TestSlackText:
    def test_escapes_control_characters(self):
        assert svc._slack_text("<!channel> & <b>") == "&lt;!channel&gt; &amp; &lt;b&gt;"

    def test_short_text_is_untouched(self):
        assert svc._slack_text("hello", 10) == "hello"

    def test_truncates_to_limit(self):
        out = svc._slack_text("x" * 50, 20)
        assert out == "x" * 17 + "..."

    def test_truncation_never_splits_an_entity(self):
        out = svc._slack_text("x" * 15 + "<<<", 20)
        assert out == "x" * 15 + "..."
        assert len(out) <= 20


class TestSendSlack:
    def test_posts_block_kit_message(self, sent):
        assert svc.send_slack_bug_report("https://hooks.slack.test/bugs", **REPORT) is True
        req = sent[0]
        assert req.full_url == "https://hooks.slack.test/bugs"
        assert req.get_header("Content-type") == "application/json"
        payload = json.loads(req.data)
        text = _blocks_text(payload)
        for value in REPORT.values():
            assert value in text
        assert payload["blocks"][0]["type"] == "header"

    def test_user_input_cannot_mention_the_channel(self, sent):
        report = {**REPORT, "what_happened": "<!channel> <!here> <@U123>"}
        svc.send_slack_bug_report("https://hooks.slack.test/bugs", **report)
        text = _blocks_text(json.loads(sent[0].data))
        assert "<!" not in text
        assert "<@" not in text
        assert "&lt;!channel&gt;" in text

    def test_long_descriptions_fit_slack_limits(self, sent):
        report = {**REPORT, "what_did": "<" * 2000, "what_happened": "&" * 2000}
        svc.send_slack_bug_report("https://hooks.slack.test/bugs", **report)
        payload = json.loads(sent[0].data)
        for block in payload["blocks"]:
            if block["type"] == "section" and "text" in block:
                assert len(block["text"]["text"]) <= 3000
            for field in block.get("fields", []):
                assert len(field["text"]) <= 2000

    def test_no_webhook_does_not_post(self, monkeypatch):
        monkeypatch.setattr(
            svc.urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not post")
        )
        assert svc.send_slack_bug_report("", **REPORT) is False

    def test_post_failure_never_raises(self, monkeypatch):
        def broken(*args, **kwargs):
            raise OSError("network down")

        monkeypatch.setattr(svc.urllib.request, "urlopen", broken)
        assert svc.send_slack_bug_report("https://hooks.slack.test/bugs", **REPORT) is False


class TestSendDiscord:
    def test_still_posts_embed_with_bot_user_agent(self, sent):
        assert svc.send_discord_bug_report("https://discord.test/hook", **REPORT) is True
        req = sent[0]
        assert req.get_header("User-agent").startswith("DiscordBot")
        payload = json.loads(req.data)
        assert payload["embeds"][0]["fields"][0]["value"] == "Ana Petrova"


class TestSubmitAsync:
    @pytest.fixture()
    def queued(self, monkeypatch):
        jobs = []

        class InlineExecutor:
            def submit(self, fn, *args):
                jobs.append((fn, args))

        monkeypatch.setattr(svc, "_executor", InlineExecutor())
        return jobs

    def _submit(self, discord, slack):
        svc.submit_bug_report_async(discord, slack, **REPORT)

    def test_both_webhooks_get_the_report(self, queued):
        self._submit("https://discord.test/hook", "https://hooks.slack.test/bugs")
        assert [(fn, args[0]) for fn, args in queued] == [
            (svc.send_discord_bug_report, "https://discord.test/hook"),
            (svc.send_slack_bug_report, "https://hooks.slack.test/bugs"),
        ]
        assert queued[0][1][1:] == queued[1][1][1:] == tuple(REPORT.values())

    def test_only_discord(self, queued):
        self._submit("https://discord.test/hook", "")
        assert [fn for fn, _ in queued] == [svc.send_discord_bug_report]

    def test_only_slack(self, queued):
        self._submit("", "https://hooks.slack.test/bugs")
        assert [fn for fn, _ in queued] == [svc.send_slack_bug_report]

    def test_none_configured_drops_with_warning(self, queued, caplog):
        self._submit("", "")
        assert queued == []
        assert "No bug-report webhook configured" in caplog.text
