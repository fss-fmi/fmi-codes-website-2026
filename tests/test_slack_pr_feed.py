"""Unit tests for .github/scripts/slack_notify.py and pr_feed.py (no network)."""

import io
import json
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".github" / "scripts"))

import pr_feed  # noqa: E402
import slack_notify  # noqa: E402

REPO = "fss-fmi/fmi-codes-website-2026"
CHANNEL = "C0PRFEED"


class FakeSlack:
    """In-memory channel with the same surface Feed uses."""

    def __init__(self):
        self.messages = []
        self.updates = 0

    def post(self, channel, text, thread_ts=None, metadata=None):
        ts = f"{len(self.messages) + 1}.000"
        self.messages.append({"ts": ts, "text": text, "thread_ts": thread_ts, "metadata": metadata})
        return ts

    def update(self, channel, ts, text, metadata=None):
        message = next(m for m in self.messages if m["ts"] == ts)
        message["text"] = text
        message["metadata"] = metadata
        self.updates += 1

    def find_pr_message(self, channel, repo, pr_number, oldest=0):
        for m in self.messages:
            payload = (m["metadata"] or {}).get("event_payload", {})
            if m["thread_ts"] is None and (payload.get("repo"), payload.get("pr_number")) == (
                repo,
                pr_number,
            ):
                return m
        return None

    @property
    def parents(self):
        return [m for m in self.messages if m["thread_ts"] is None]

    @property
    def replies(self):
        return [m for m in self.messages if m["thread_ts"] is not None]


def make_pr(number=7, draft=False, state="open", merged=False, head="feature/x", **extra):
    pr = {
        "number": number,
        "title": "feat: add things",
        "html_url": f"https://github.com/{REPO}/pull/{number}",
        "user": {"login": "alice"},
        "draft": draft,
        "state": state,
        "merged": merged,
        "merged_by": {"login": "bob"} if merged else None,
        "created_at": "2026-11-03T00:00:00Z",
        "base": {"ref": "main"},
        "head": {"ref": head, "label": f"alice:{head}", "repo": {"full_name": REPO}},
    }
    pr.update(extra)
    return pr


def pr_event(action, pr, sender="alice", **extra):
    return {"action": action, "pull_request": pr, "sender": {"login": sender}, **extra}


def review_event(pr, state, reviewer="carol"):
    return {
        "action": "submitted",
        "pull_request": pr,
        "sender": {"login": reviewer},
        "review": {
            "state": state,
            "user": {"login": reviewer},
            "html_url": f"{pr['html_url']}#pullrequestreview-1",
        },
    }


@pytest.fixture()
def slack():
    return FakeSlack()


@pytest.fixture()
def feed(slack):
    return pr_feed.Feed(slack, CHANNEL, REPO)


def target(feed, action, pr, **extra):
    feed.handle("pull_request_target", pr_event(action, pr, **extra))


class TestDrafts:
    def test_draft_posts_nothing_until_ready(self, feed, slack):
        target(feed, "opened", make_pr(draft=True))
        feed.handle("pull_request_review", review_event(make_pr(draft=True), "approved"))
        target(feed, "edited", make_pr(draft=True), changes={"title": {"from": "x"}})
        assert slack.messages == []

        target(feed, "ready_for_review", make_pr())
        assert len(slack.parents) == 1
        assert slack.replies == []
        assert slack.parents[0]["text"].startswith("🟢")

    def test_converted_to_draft_pauses_updates(self, feed, slack):
        target(feed, "opened", make_pr())
        target(feed, "converted_to_draft", make_pr(draft=True), sender="bob")
        assert slack.parents[0]["text"].startswith("📝")
        assert "converted to draft by bob" in slack.replies[-1]["text"]

        feed.handle("pull_request_review", review_event(make_pr(draft=True), "approved"))
        assert len(slack.replies) == 1

        target(feed, "ready_for_review", make_pr())
        assert slack.parents[0]["text"].startswith("🟢")
        assert "ready for review again" in slack.replies[-1]["text"]
        assert len(slack.parents) == 1


class TestThread:
    def test_one_parent_and_every_later_event_in_its_thread(self, feed, slack):
        target(feed, "opened", make_pr())
        feed.handle("pull_request_review", review_event(make_pr(), "changes_requested"))
        feed.handle("pull_request_review", review_event(make_pr(), "commented"))
        feed.handle("pull_request_review", review_event(make_pr(), "approved"))
        target(feed, "closed", make_pr(state="closed", merged=True))

        assert len(slack.parents) == 1
        parent_ts = slack.parents[0]["ts"]
        assert all(r["thread_ts"] == parent_ts for r in slack.replies)
        texts = [r["text"] for r in slack.replies]
        assert "changes requested" in texts[0] and "carol" in texts[0]
        assert "approved" in texts[1]
        assert texts[2] == "🟣 merged into `main` by bob"
        assert len(texts) == 3

    def test_parent_shows_merged_state(self, feed, slack):
        target(feed, "opened", make_pr())
        target(feed, "closed", make_pr(state="closed", merged=True))
        assert slack.parents[0]["text"].startswith("🟣")
        assert slack.parents[0]["metadata"]["event_payload"]["state"] == "merged"

    def test_closed_without_merge_then_reopened(self, feed, slack):
        target(feed, "opened", make_pr())
        target(feed, "closed", make_pr(state="closed"), sender="dave")
        assert slack.parents[0]["text"].startswith("🔴")
        assert slack.replies[-1]["text"] == "🔴 closed without merging by dave"

        target(feed, "reopened", make_pr(), sender="dave")
        assert slack.parents[0]["text"].startswith("🟢")
        assert slack.replies[-1]["text"] == "🟢 reopened by dave"

    def test_reopened_as_draft_says_so(self, feed, slack):
        target(feed, "opened", make_pr())
        target(feed, "closed", make_pr(state="closed"))
        target(feed, "reopened", make_pr(draft=True))
        assert slack.parents[0]["text"].startswith("📝")
        assert "reopened by alice as a draft" in slack.replies[-1]["text"]

    def test_parent_text(self, feed, slack):
        target(feed, "opened", make_pr(head="feat/x"))
        text = slack.parents[0]["text"]
        assert f"<https://github.com/{REPO}/pull/7|feat: add things>" in text
        assert "#7" in text and "alice" in text
        assert "`main` ← `feat/x`" in text

    def test_fork_head_shows_owner(self, feed, slack):
        pr = make_pr(head="patch-1")
        pr["head"]["repo"] = {"full_name": "mallory/fork"}
        target(feed, "opened", pr)
        assert "← `alice:patch-1`" in slack.parents[0]["text"]

    def test_title_is_escaped(self, feed, slack):
        target(feed, "opened", make_pr(title="<!channel> & <@U1>"))
        text = slack.parents[0]["text"]
        assert "&lt;!channel&gt; &amp; &lt;@U1&gt;" in text
        assert "<!channel>" not in text

    def test_title_edit_updates_parent_without_reply(self, feed, slack):
        target(feed, "opened", make_pr())
        target(feed, "edited", make_pr(title="feat: renamed"), changes={"title": {"from": "x"}})
        assert "feat: renamed" in slack.parents[0]["text"]
        assert slack.replies == []

    def test_body_edit_changes_nothing(self, feed, slack):
        target(feed, "opened", make_pr())
        updates = slack.updates
        target(feed, "edited", make_pr(), changes={"body": {"from": "x"}})
        assert slack.updates == updates
        assert slack.replies == []

    def test_events_for_unposted_prs_create_nothing(self, feed, slack):
        target(feed, "closed", make_pr(state="closed", merged=True))
        target(feed, "edited", make_pr(), changes={"title": {"from": "x"}})
        feed.handle("pull_request_review", review_event(make_pr(), "approved"))
        assert slack.messages == []


class TestIdempotency:
    def test_reruns_never_create_a_second_parent(self, feed, slack):
        for _ in range(3):
            target(feed, "opened", make_pr())
            target(feed, "ready_for_review", make_pr())
            target(feed, "reopened", make_pr())
        assert len(slack.parents) == 1
        assert slack.replies == []

    def test_duplicate_close_replies_once(self, feed, slack):
        target(feed, "opened", make_pr())
        for _ in range(2):
            target(feed, "closed", make_pr(state="closed", merged=True))
        assert len(slack.replies) == 1


class TestFluxBumps:
    FILES = [
        {
            "filename": "infra/k8s/overlays/staging/kustomization.yaml",
            "patch": (
                "@@ -16,7 +16,7 @@ images:\n"
                "   - name: fssfmi/fmi-codes-backend\n"
                '-    newTag: 1792976992-d6162fc # {"$imagepolicy": "flux-system:fmi-codes-backend-staging:tag"}\n'
                '+    newTag: 1793041510-85d3415 # {"$imagepolicy": "flux-system:fmi-codes-backend-staging:tag"}\n'
                "   - name: fssfmi/fmi-codes-frontend\n"
                '-    newTag: 1792976992-d6162fc # {"$imagepolicy": "flux-system:fmi-codes-frontend-staging:tag"}\n'
                '+    newTag: 1793041510-85d3415 # {"$imagepolicy": "flux-system:fmi-codes-frontend-staging:tag"}'
            ),
        }
    ]

    @staticmethod
    def bump(**kw):
        return make_pr(
            number=152,
            head=pr_feed.FLUX_BRANCH,
            title="deploy: bump 1792976992-d6162fc -> 1793041510-85d3415 1792976992-d6162fc -> 1793041510-85d3415 ",
            **kw,
        )

    @pytest.fixture()
    def flux_feed(self, slack):
        return pr_feed.Feed(slack, CHANNEL, REPO, github=lambda path: self.FILES)

    def test_single_one_liner_from_the_diff(self, flux_feed, slack):
        target(flux_feed, "opened", self.bump(), sender="fmi-codes-bot[bot]")
        assert len(slack.messages) == 1
        assert slack.messages[0]["text"] == (
            "⬆️ fmi-codes-backend, fmi-codes-frontend bumped `1792976992-d6162fc` → "
            f"`1793041510-85d3415` · <https://github.com/{REPO}/pull/152|#152>"
        )
        assert slack.messages[0]["metadata"]["event_payload"]["kind"] == "flux"

    def test_merge_edits_in_place_without_a_thread(self, flux_feed, slack):
        target(flux_feed, "opened", self.bump())
        flux_feed.handle("pull_request_review", review_event(self.bump(), "approved"))
        target(flux_feed, "closed", self.bump(state="closed", merged=True))
        target(flux_feed, "closed", self.bump(state="closed", merged=True))
        assert len(slack.messages) == 1
        assert slack.messages[0]["text"].endswith(" · merged ✅")

    def test_closed_without_merge(self, flux_feed, slack):
        target(flux_feed, "opened", self.bump())
        target(flux_feed, "closed", self.bump(state="closed"))
        assert slack.messages[0]["text"].endswith(" · closed without merging")

    def test_falls_back_to_the_title_when_the_diff_is_unreadable(self, slack):
        def broken(path):
            raise OSError("api down")

        target(pr_feed.Feed(slack, CHANNEL, REPO, github=broken), "opened", self.bump())
        assert slack.messages[0]["text"].startswith(
            "⬆️ staging images bumped `1792976992-d6162fc` → `1793041510-85d3415` · "
        )

    def test_branch_named_like_flux_on_a_fork_is_a_normal_pr(self, flux_feed, slack):
        pr = self.bump()
        pr["head"]["repo"] = {"full_name": "mallory/fork"}
        target(flux_feed, "opened", pr)
        assert slack.messages[0]["text"].startswith("🟢")


class TestMain:
    def test_skips_quietly_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        monkeypatch.setenv("SLACK_PR_CHANNEL_ID", CHANNEL)
        monkeypatch.setattr(
            slack_notify.Slack, "call", lambda *a, **k: pytest.fail("must not call Slack")
        )
        assert pr_feed.main() == 0

    def test_slack_failure_fails_the_run(self, monkeypatch, tmp_path):
        event = tmp_path / "event.json"
        event.write_text(
            json.dumps({**pr_event("opened", make_pr()), "repository": {"full_name": REPO}})
        )
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_PR_CHANNEL_ID", CHANNEL)
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        def fail(self, method, **params):
            raise slack_notify.SlackError(f"{method}: not_in_channel")

        monkeypatch.setattr(slack_notify.Slack, "call", fail)
        assert pr_feed.main() == 1


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestSlackClient:
    CREDENTIAL = "fake-bot-credential"

    def client(self, *responses, sleeps=None):
        requests = []
        queue = list(responses)

        def opener(req, timeout):
            requests.append(req)
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return FakeResponse(json.dumps(item).encode())

        sleep = sleeps.append if sleeps is not None else lambda s: None
        return slack_notify.Slack(self.CREDENTIAL, opener=opener, sleep=sleep), requests

    @staticmethod
    def form(req):
        return dict(urllib.parse.parse_qsl(req.data.decode()))

    def test_post_sends_form_with_metadata(self):
        slack, requests = self.client({"ok": True, "ts": "123.456"})
        meta = slack_notify.pr_metadata(REPO, 7, "pr", "open")
        assert slack.post(CHANNEL, "hi", metadata=meta) == "123.456"
        req = requests[0]
        assert req.full_url == "https://slack.com/api/chat.postMessage"
        assert req.get_header("Authorization") == f"Bearer {self.CREDENTIAL}"
        body = self.form(req)
        assert body["channel"] == CHANNEL and body["text"] == "hi"
        assert json.loads(body["metadata"]) == meta
        assert body["unfurl_links"] == "false"
        assert "thread_ts" not in body

    def test_error_names_the_method_but_never_the_token(self):
        slack, _ = self.client({"ok": False, "error": "invalid_auth"})
        with pytest.raises(slack_notify.SlackError) as e:
            slack.post(CHANNEL, "hi")
        assert str(e.value) == "chat.postMessage: invalid_auth"
        assert self.CREDENTIAL not in str(e.value)

    def test_rate_limit_is_retried(self):
        limited = urllib.error.HTTPError(
            "https://slack.com/api/chat.update",
            429,
            "Too Many Requests",
            {"Retry-After": "3"},
            None,
        )
        sleeps = []
        slack, requests = self.client(limited, {"ok": True}, sleeps=sleeps)
        slack.update(CHANNEL, "1.0", "text")
        assert sleeps == [3]
        assert len(requests) == 2

    def test_find_pages_through_history(self):
        other = {"ts": "9", "metadata": slack_notify.pr_metadata("other/repo", 7, "pr", "open")}
        mine = {"ts": "5", "metadata": slack_notify.pr_metadata(REPO, 7, "pr", "open")}
        slack, requests = self.client(
            {
                "ok": True,
                "messages": [other, {"ts": "8"}],
                "response_metadata": {"next_cursor": "c2"},
            },
            {"ok": True, "messages": [mine]},
        )
        assert slack.find_pr_message(CHANNEL, REPO, 7, oldest=1700000000.5) == mine
        first, second = (self.form(r) for r in requests)
        assert first["oldest"] == "1700000000.500000"
        assert first["include_all_metadata"] == "true"
        assert "cursor" not in first
        assert second["cursor"] == "c2"

    def test_find_returns_none_when_absent(self):
        slack, _ = self.client({"ok": True, "messages": [{"ts": "1"}]})
        assert slack.find_pr_message(CHANNEL, REPO, 7) is None

    def test_escape(self):
        assert slack_notify.escape("a<b>&c") == "a&lt;b&gt;&amp;c"
