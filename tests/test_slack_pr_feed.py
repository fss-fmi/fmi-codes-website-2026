"""Unit tests for .github/scripts/slack_notify.py and pr_feed.py (no network)."""

import io
import json
import math
import re
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
        # Epoch seconds for the next ts; unset, ts counts 1.000, 2.000, ...
        self.now = None

    def post(self, channel, text, thread_ts=None, metadata=None):
        n = len(self.messages) + 1
        ts = f"{n}.000" if self.now is None else f"{self.now + n / 1000:.6f}"
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

    def post_unique(self, channel, text, metadata, oldest, **match):
        return self.post(channel, text, metadata=metadata)

    def find_reply(self, channel, thread_ts, event_type, **match):
        for m in self.messages:
            meta = m["metadata"] or {}
            payload = meta.get("event_payload", {})
            if (
                m["thread_ts"] == thread_ts
                and meta.get("event_type") == event_type
                and all(str(payload.get(k)) == str(v) for k, v in match.items())
            ):
                return m
        return None

    def find_replies(self, channel, thread_ts, event_type, **match):
        return [
            m
            for m in self.messages
            if m["thread_ts"] == thread_ts
            and (m["metadata"] or {}).get("event_type") == event_type
            and all(str(m["metadata"]["event_payload"].get(k)) == str(v) for k, v in match.items())
        ]

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
        "user": {"login": "alice", "type": "User"},
        "author_association": "MEMBER",
        "draft": draft,
        "state": state,
        "merged": merged,
        "merged_by": {"login": "bob"} if merged else None,
        "created_at": "2026-11-03T00:00:00Z",
        "base": {"ref": "main", "repo": {"html_url": f"https://github.com/{REPO}"}},
        "head": {"ref": head, "label": f"alice:{head}", "repo": {"full_name": REPO}},
    }
    pr.update(extra)
    return pr


def pr_event(action, pr, sender="alice", **extra):
    return {"action": action, "pull_request": pr, "sender": {"login": sender}, **extra}


def review_event(pr, state, reviewer="carol", review_id=1, body=""):
    return {
        "action": "submitted",
        "pull_request": pr,
        "sender": {"login": reviewer},
        "review": {
            "id": review_id,
            "state": state,
            "body": body,
            "user": {"login": reviewer, "type": "User"},
            "author_association": "MEMBER",
            "html_url": f"{pr['html_url']}#pullrequestreview-1",
        },
    }


REPO_ID = 4242
RUN_CREATED = "2026-11-03T01:00:00Z"
SAME_REPO = {"full_name": REPO, "owner": {"login": "fss-fmi"}}


def rest_review(
    state, reviewer="carol", review_id=1, body="", submitted_at="2026-11-03T00:59:00Z", **extra
):
    """A review as GET /pulls/{n}/reviews returns it: the state in upper case."""
    review = {
        "id": review_id,
        "state": state.upper(),
        "body": body,
        "user": {"login": reviewer, "type": "User"},
        "html_url": f"https://github.com/{REPO}/pull/7#pullrequestreview-{review_id}",
        "submitted_at": submitted_at,
    }
    review.update(extra)
    return review


def relay_run(
    pr,
    created_at=RUN_CREATED,
    head_sha=None,
    pull_requests=None,
    head_repository=SAME_REPO,
    event="pull_request_review",
):
    """The workflow_run event for a finished PR review relay run on *pr*."""
    sha = head_sha or pr["head"].get("sha") or "reviewedsha"
    if pull_requests is None:
        pull_requests = [
            {"number": pr["number"], "head": {"sha": sha}, "base": {"repo": {"id": REPO_ID}}}
        ]
    return {
        "action": "completed",
        "workflow_run": {
            "event": event,
            "created_at": created_at,
            "head_sha": sha,
            "head_branch": pr["head"]["ref"],
            "head_repository": head_repository,
            "pull_requests": pull_requests,
            "repository": {"id": REPO_ID, "full_name": REPO},
        },
    }


def review(feed, pr, *reviews, **run):
    """Submit *reviews* on *pr*, then deliver the relay run that follows."""
    feed.github.pr = pr
    feed.github.reviews += reviews
    feed.handle("workflow_run", relay_run(pr, **run))


@pytest.fixture()
def slack():
    return FakeSlack()


def github_stub(
    files=(), pr=None, read_only=("mallory",), error=None, commits=(), reviews=(), listed=()
):
    """The GitHub API surface Feed uses: everyone can push except *read_only* users.

    GET /pulls/{n} serves get.pr or a PR in get.listed, which GET /pulls?head= also
    searches. get.reviews and get.events serve every PR's reviews and issue events.
    """
    calls = []

    def get(path, **params):
        calls.append(path)
        if path.endswith("/permission"):
            if error:
                raise error
            login = path.split("/")[-2]
            return {"permission": "read" if login in read_only else "write"}
        if path.endswith("/files"):
            return list(files)
        if path.endswith("/commits"):
            size = params["per_page"]
            start = (params["page"] - 1) * size
            return list(commits)[: pr_feed.MAX_PR_COMMITS][start : start + size]
        if path.endswith("/reviews") or path.endswith("/events"):
            size = params["per_page"]
            start = (params["page"] - 1) * size
            items = get.reviews if path.endswith("/reviews") else get.events
            return items[start : start + size]
        if path == f"/repos/{REPO}/pulls":
            return [
                p
                for p in get.listed
                if p["head"]["label"] == params["head"] and params["state"] in ("all", p["state"])
            ]
        prs = {p["number"]: p for p in (get.pr, *get.listed) if p}
        m = re.fullmatch(rf"/repos/{re.escape(REPO)}/pulls/(\d+)", path)
        assert m and int(m.group(1)) in prs, path
        return prs[int(m.group(1))]

    get.calls = calls
    get.pr = pr
    get.reviews = list(reviews)
    get.listed = list(listed)
    get.events = []
    return get


@pytest.fixture()
def feed(slack):
    return pr_feed.Feed(slack, CHANNEL, REPO, github=github_stub())


def target(feed, action, pr, **extra):
    feed.handle("pull_request_target", pr_event(action, pr, **extra))


class TestDrafts:
    def test_draft_posts_nothing_until_ready(self, feed, slack):
        target(feed, "opened", make_pr(draft=True))
        review(feed, make_pr(draft=True), rest_review("approved"))
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

        review(feed, make_pr(draft=True), rest_review("approved"))
        assert len(slack.replies) == 1

        target(feed, "ready_for_review", make_pr())
        assert slack.parents[0]["text"].startswith("🟢")
        assert "ready for review again" in slack.replies[-1]["text"]
        assert len(slack.parents) == 1


class TestThread:
    def test_one_parent_and_every_later_event_in_its_thread(self, feed, slack):
        target(feed, "opened", make_pr())
        review(feed, make_pr(), rest_review("changes_requested", review_id=1))
        review(feed, make_pr(), rest_review("commented", review_id=2, body="A few nits inline."))
        review(feed, make_pr(), rest_review("approved", review_id=3))
        target(feed, "closed", make_pr(state="closed", merged=True))

        assert len(slack.parents) == 1
        parent_ts = slack.parents[0]["ts"]
        assert all(r["thread_ts"] == parent_ts for r in slack.replies)
        texts = [r["text"] for r in slack.replies]
        assert "changes requested" in texts[0] and "carol" in texts[0]
        assert "review comments" in texts[1] and texts[1].startswith("💬")
        assert "approved" in texts[2]
        assert texts[3] == "🟣 merged into `main` by bob"
        assert len(texts) == 4

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
        review(feed, make_pr(), rest_review("approved"))
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
        return pr_feed.Feed(slack, CHANNEL, REPO, github=github_stub(files=self.FILES))

    def test_single_one_liner_from_the_diff(self, flux_feed, slack):
        target(flux_feed, "opened", self.bump(), sender="fmi-codes-bot[bot]")
        assert len(slack.messages) == 1
        assert slack.messages[0]["text"] == (
            "⬆️ fmi-codes-backend, fmi-codes-frontend bumped `1792976992-d6162fc` → "
            f"`1793041510-85d3415` · <https://github.com/{REPO}/pull/152|#152>"
        )
        assert slack.messages[0]["metadata"]["event_payload"]["kind"] == "flux"

    def test_closed_without_merge(self, flux_feed, slack):
        target(flux_feed, "opened", self.bump())
        target(flux_feed, "closed", self.bump(state="closed"))
        assert slack.messages[0]["text"].endswith(" · closed without merging")

    def test_falls_back_to_the_title_when_the_diff_is_unreadable(self, slack):
        def broken(path):
            if path.endswith("/permission"):
                return {"permission": "write"}
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
        monkeypatch.setenv("GITHUB_TOKEN", "fake-gh-credential")
        monkeypatch.setattr(pr_feed.GitHub, "get", lambda self, path, **p: {"permission": "write"})

        def fail(self, method, **params):
            raise slack_notify.SlackError(f"{method}: not_in_channel")

        monkeypatch.setattr(slack_notify.Slack, "call", fail)
        assert pr_feed.main() == 1

    def test_no_github_token_posts_nothing(self, monkeypatch, tmp_path):
        event = tmp_path / "event.json"
        event.write_text(
            json.dumps({**pr_event("opened", make_pr()), "repository": {"full_name": REPO}})
        )
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_PR_CHANNEL_ID", CHANNEL)
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(
            slack_notify.Slack, "call", lambda *a, **k: pytest.fail("must not call Slack")
        )
        assert pr_feed.main() == 0


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


def outsider_pr(**kw):
    pr = make_pr(**kw)
    pr["user"] = {"login": "mallory", "type": "User"}
    pr["author_association"] = "NONE"
    pr["head"]["repo"] = {"full_name": "mallory/fork"}
    pr["title"] = "Free credits https://phish.example"
    return pr


class TestTrust:
    def test_outsider_prs_post_nothing(self, slack):
        feed = pr_feed.Feed(slack, CHANNEL, REPO, github=github_stub())
        for action in ("opened", "ready_for_review", "reopened"):
            target(feed, action, outsider_pr())
        target(feed, "edited", outsider_pr(), changes={"title": {"from": "x"}})
        assert slack.messages == []

    def test_outsider_pr_from_an_existing_repo_branch_posts_nothing(self, slack):
        pr = outsider_pr()
        pr["head"]["repo"] = {"full_name": REPO}
        target(pr_feed.Feed(slack, CHANNEL, REPO, github=github_stub()), "opened", pr)
        assert slack.messages == []

    def test_outsider_on_the_flux_branch_is_not_a_flux_bump(self, slack):
        pr = outsider_pr(head=pr_feed.FLUX_BRANCH)
        pr["head"]["repo"] = {"full_name": REPO}
        target(pr_feed.Feed(slack, CHANNEL, REPO, github=github_stub()), "opened", pr)
        assert slack.messages == []

    def test_the_permission_api_decides_not_the_association(self, slack):
        # MEMBER and COLLABORATOR include read-only access; only the permission counts.
        api = github_stub(read_only=("alice",))
        feed = pr_feed.Feed(slack, CHANNEL, REPO, github=api)
        for association in ("OWNER", "MEMBER", "COLLABORATOR"):
            target(feed, "opened", make_pr(author_association=association))
        assert slack.messages == []
        assert api.calls == [f"/repos/{REPO}/collaborators/alice/permission"] * 3

    def test_writer_with_any_association_is_posted(self, slack):
        feed = pr_feed.Feed(slack, CHANNEL, REPO, github=github_stub())
        target(feed, "opened", make_pr(author_association="NONE"))
        assert len(slack.parents) == 1

    def test_permission_api_failure_fails_closed(self, slack):
        api = github_stub(error=OSError("403"))
        target(pr_feed.Feed(slack, CHANNEL, REPO, github=api), "opened", make_pr())
        assert slack.messages == []

    def test_no_github_token_trusts_nobody_but_repo_bots(self, slack):
        target(pr_feed.Feed(slack, CHANNEL, REPO), "opened", make_pr(author_association="OWNER"))
        assert slack.messages == []

    def test_outsider_reviews_on_a_member_pr_post_nothing(self, slack, feed):
        target(feed, "opened", make_pr())
        review(
            feed,
            make_pr(),
            rest_review("approved", reviewer="mallory", review_id=1),
            rest_review("approved", reviewer="carol", review_id=2),
        )
        [reply] = slack.replies
        assert "by carol" in reply["text"]

    def test_repo_bot_prs_are_trusted_without_the_api(self, slack):
        pr = TestFluxBumps.bump()
        pr["user"] = {"login": "fmi-codes-bot[bot]", "type": "Bot"}
        target(pr_feed.Feed(slack, CHANNEL, REPO), "opened", pr)
        assert slack.messages[0]["text"].startswith("⬆️ ")

    def test_bots_from_forks_are_not(self, slack):
        pr = make_pr()
        pr["user"] = {"login": "evil[bot]", "type": "Bot"}
        pr["head"]["repo"] = {"full_name": "mallory/fork"}
        target(pr_feed.Feed(slack, CHANNEL, REPO, github=github_stub()), "opened", pr)
        assert slack.messages == []


def comment_event(
    pr_number=7,
    commenter="carol",
    association="MEMBER",
    comment_id=55,
    user_type="User",
    issue_is_pr=True,
):
    issue = {"number": pr_number}
    if issue_is_pr:
        issue["pull_request"] = {"url": f"https://api.github.com/repos/{REPO}/pulls/{pr_number}"}
    return {
        "action": "created",
        "issue": issue,
        "sender": {"login": commenter},
        "comment": {
            "id": comment_id,
            "user": {"login": commenter, "type": user_type},
            "author_association": association,
            "html_url": f"https://github.com/{REPO}/pull/{pr_number}#issuecomment-{comment_id}",
        },
    }


class TestComments:
    @pytest.fixture()
    def api(self):
        state = {"pr": make_pr()}
        base = github_stub()

        def get(path, **params):
            if path.endswith("/permission"):
                return base(path, **params)
            base.calls.append(path)
            assert path == f"/repos/{REPO}/pulls/7", path
            return state["pr"]

        get.state = state
        get.calls = base.calls
        return get

    @pytest.fixture()
    def cfeed(self, slack, api):
        f = pr_feed.Feed(slack, CHANNEL, REPO, github=api)
        target(f, "opened", make_pr())
        return f

    def test_member_comment_is_a_thread_reply(self, cfeed, slack):
        cfeed.handle("issue_comment", comment_event())
        [reply] = slack.replies
        assert reply["thread_ts"] == slack.parents[0]["ts"]
        assert (
            reply["text"]
            == f"💬 <https://github.com/{REPO}/pull/7#issuecomment-55|comment> by carol"
        )

    def test_rerun_posts_the_comment_once(self, cfeed, slack):
        for _ in range(3):
            cfeed.handle("issue_comment", comment_event())
        cfeed.handle("issue_comment", comment_event(comment_id=56))
        assert len(slack.replies) == 2

    def test_outsider_and_bot_comments_post_nothing(self, cfeed, slack):
        cfeed.handle("issue_comment", comment_event(commenter="mallory", association="NONE"))
        cfeed.handle(
            "issue_comment",
            comment_event(commenter="github-actions[bot]", association="NONE", user_type="Bot"),
        )
        cfeed.handle(
            "issue_comment",
            comment_event(
                commenter="fmi-codes-bot[bot]", association="CONTRIBUTOR", user_type="Bot"
            ),
        )
        assert slack.replies == []

    def test_comment_on_an_outsiders_pr_posts_nothing(self, slack, api):
        api.state["pr"] = outsider_pr()
        f = pr_feed.Feed(slack, CHANNEL, REPO, github=api)
        f.handle("issue_comment", comment_event())
        assert slack.messages == []

    def test_issue_comments_and_drafts_post_nothing(self, cfeed, slack, api):
        cfeed.handle("issue_comment", comment_event(issue_is_pr=False))
        api.state["pr"] = make_pr(draft=True)
        cfeed.handle("issue_comment", comment_event())
        assert slack.replies == []

    def test_edited_comments_post_nothing(self, cfeed, slack):
        event = comment_event()
        event["action"] = "edited"
        cfeed.handle("issue_comment", event)
        assert slack.replies == []

    def test_no_parent_means_no_reply(self, slack, api):
        pr_feed.Feed(slack, CHANNEL, REPO, github=api).handle("issue_comment", comment_event())
        assert slack.messages == []

    def test_bot_and_edited_comments_cost_no_api_call(self, slack, api):
        f = pr_feed.Feed(slack, CHANNEL, REPO, github=api)
        f.handle("issue_comment", comment_event(commenter="dependabot[bot]", user_type="Bot"))
        edited = comment_event()
        edited["action"] = "edited"
        f.handle("issue_comment", edited)
        assert api.calls == []


class TestSlackClientRaces:
    meta = slack_notify.pr_metadata(REPO, 7, "pr", "open")

    def client(self, *responses, sleeps=None):
        return TestSlackClient.client(TestSlackClient(), *responses, sleeps=sleeps)

    def test_post_unique_keeps_the_older_message(self):
        slack, requests = self.client(
            {"ok": True, "ts": "200.5"},
            {
                "ok": True,
                "messages": [
                    {"ts": "200.5", "metadata": self.meta},
                    {"ts": "100.5", "metadata": self.meta},
                ],
            },
            {"ok": True},
        )
        assert slack.post_unique(CHANNEL, "hi", self.meta, 0, repo=REPO, pr_number=7) == "100.5"
        assert requests[2].full_url.endswith("/chat.delete")
        assert TestSlackClient.form(requests[2])["ts"] == "200.5"

    def test_post_unique_without_a_race_deletes_nothing(self):
        slack, requests = self.client(
            {"ok": True, "ts": "200.5"},
            {"ok": True, "messages": [{"ts": "200.5", "metadata": self.meta}]},
        )
        assert slack.post_unique(CHANNEL, "hi", self.meta, 0, repo=REPO, pr_number=7) == "200.5"
        assert len(requests) == 2

    def test_find_reply_reads_the_thread(self):
        reply = {"ts": "3", "metadata": slack_notify.reply_metadata(REPO, 7, "comment:55")}
        slack, requests = self.client(
            {"ok": True, "messages": [{"ts": "1", "metadata": self.meta}, reply]}
        )
        assert (
            slack.find_reply(CHANNEL, "1", slack_notify.REPLY_EVENT_TYPE, key="comment:55") == reply
        )
        assert requests[0].full_url.endswith("/conversations.replies")
        assert TestSlackClient.form(requests[0])["ts"] == "1"

    @pytest.mark.parametrize(
        ("header", "expected"), [("soon", 1), (None, 1), ("0", 1), ("999", 30), ("4", 4)]
    )
    def test_retry_after_is_parsed_safely(self, header, expected):
        headers = {"Retry-After": header} if header is not None else {}
        limited = urllib.error.HTTPError(
            "https://slack.com/api/chat.update", 429, "Too Many", headers, None
        )
        sleeps = []
        slack, _ = self.client(limited, {"ok": True}, sleeps=sleeps)
        slack.update(CHANNEL, "1.0", "text")
        assert sleeps == [expected]


def sha(n):
    return f"sha{n:04d}" + "0" * 33


def commit(n, message=None, parents=None):
    if parents is None:
        parents = [n - 1]
    return {
        "sha": sha(n),
        "commit": {"message": message or f"commit {n}\n\nbody {n}"},
        "parents": [{"sha": sha(p)} for p in parents],
    }


def pr_at(n, **kw):
    pr = make_pr(**kw)
    pr["head"]["sha"] = sha(n)
    return pr


PR_URL = f"https://github.com/{REPO}/pull/7"


class TestPushes:
    @pytest.fixture()
    def commits(self):
        return [commit(1)]

    @pytest.fixture()
    def current(self):
        """The PR as GET /pulls/7 returns it now."""
        return pr_at(1)

    @pytest.fixture()
    def api(self, commits, current):
        return github_stub(commits=commits, pr=current)

    @pytest.fixture()
    def sleeps(self):
        return []

    @pytest.fixture()
    def pfeed(self, slack, api, sleeps):
        f = pr_feed.Feed(slack, CHANNEL, REPO, github=api, sleep=sleeps.append)
        target(f, "opened", pr_at(1))
        # TestOpeningCommits covers the opening list; these tests only count push replies.
        [opening] = slack.replies
        slack.messages.remove(opening)
        return f

    @staticmethod
    def push(feed, before, after, sender="alice", head=None, **kw):
        """Push *before* -> *after*; *head* is the PR's head by the time the run reads it."""
        feed.github.pr["head"]["sha"] = sha(head or after)
        target(
            feed,
            "synchronize",
            pr_at(after, **kw),
            sender=sender,
            before=sha(before),
            after=sha(after),
        )

    def test_parent_records_the_head_it_was_posted_at(self, pfeed, slack):
        assert slack.parents[0]["metadata"]["event_payload"]["head"] == sha(1)

    def test_push_lists_its_new_commits(self, pfeed, slack, commits):
        commits += [commit(2), commit(3, "fix: <!channel> & co")]
        self.push(pfeed, 1, 3, sender="bob")
        [reply] = slack.replies
        assert reply["thread_ts"] == slack.parents[0]["ts"]
        assert reply["text"] == "\n".join(
            [
                f"🔨 2 new commits by bob · <{PR_URL}/files/{sha(1)}..{sha(3)}|view changes>",
                f"• <{PR_URL}/commits/{sha(2)}|sha0002> commit 2",
                f"• <{PR_URL}/commits/{sha(3)}|sha0003> fix: &lt;!channel&gt; &amp; co",
            ]
        )
        payload = reply["metadata"]["event_payload"]
        assert payload["key"] == f"push:{sha(1)}..{sha(3)}" and payload["head"] == sha(3)

    def test_one_commit_is_singular(self, pfeed, slack, commits):
        commits.append(commit(2))
        self.push(pfeed, 1, 2)
        assert slack.replies[0]["text"].startswith("🔨 1 new commit by alice · ")

    def test_long_subjects_are_cut(self, pfeed, slack, commits):
        commits.append(commit(2, "x" * 100 + "\nbody"))
        self.push(pfeed, 1, 2)
        line = slack.replies[0]["text"].split("\n")[1]
        assert line.endswith(" " + "x" * 71 + "…")

    def test_more_than_five_commits_collapse(self, pfeed, slack, commits):
        commits += [commit(n) for n in range(2, 10)]
        self.push(pfeed, 1, 9)
        lines = slack.replies[0]["text"].split("\n")
        assert lines[0].startswith("🔨 8 new commits")
        assert [line.split("|")[1][:7] for line in lines[1:6]] == [
            "sha0002",
            "sha0003",
            "sha0004",
            "sha0005",
            "sha0006",
        ]
        assert lines[6] == f"<{PR_URL}/files/{sha(1)}..{sha(9)}|+3 more>"
        assert len(lines) == 7

    def test_force_push(self, pfeed, slack, commits):
        commits[:] = [commit(101), commit(102)]
        self.push(pfeed, 1, 102)
        assert slack.replies[-1]["text"] == (
            f"⚠️ force-pushed by alice · <https://github.com/{REPO}/compare/{sha(1)}..{sha(102)}"
            "|sha0001 → sha0102>"
        )
        commits.append(commit(103))
        self.push(pfeed, 102, 103)
        assert slack.replies[-1]["text"].startswith("🔨 1 new commit")
        assert sha(103) in slack.replies[-1]["text"]

    def test_pushing_back_to_an_earlier_head_is_reported(self, pfeed, slack, commits):
        commits += [commit(2), commit(3)]
        self.push(pfeed, 1, 3)
        commits.pop()
        self.push(pfeed, 3, 2)
        assert slack.replies[-1]["text"].startswith("⚠️ force-pushed by alice")
        commits.append(commit(3))
        self.push(pfeed, 2, 3)
        assert len(slack.replies) == 3
        assert slack.replies[-1]["text"].startswith("🔨 1 new commit")

    def test_merge_from_main_is_one_commit(self, pfeed, slack, commits):
        # GET /pulls/7/commits leaves out main's commits; the merge's other parent is one.
        commits.append(commit(2, "Merge branch 'main' into feature/x", parents=[1, 900]))
        self.push(pfeed, 1, 2)
        lines = slack.replies[0]["text"].split("\n")
        assert lines[0].startswith("🔨 1 new commit")
        assert lines[1].endswith("Merge branch 'main' into feature/x")

    def test_commits_sorted_before_the_last_head_are_still_listed(self, pfeed, slack, commits):
        commits += [commit(2), commit(3)]
        self.push(pfeed, 1, 3)
        # A cherry-pick with an old date: GitHub lists it before the commits it follows.
        commits.insert(1, commit(4, "cherry-picked fix", parents=[3]))
        self.push(pfeed, 3, 4)
        text = slack.replies[-1]["text"]
        assert text.startswith("🔨 1 new commit") and text.endswith("cherry-picked fix")

    def test_duplicate_delivery_posts_once(self, pfeed, slack, commits, api):
        commits.append(commit(2))
        self.push(pfeed, 1, 2)
        calls = len(api.calls)
        self.push(pfeed, 1, 2)
        assert len(slack.replies) == 1
        assert not any(c.endswith("/commits") for c in api.calls[calls:])

    def test_a_cancelled_run_is_covered_by_the_next(self, pfeed, slack, commits):
        commits += [commit(2), commit(3), commit(4)]
        self.push(pfeed, 1, 2)
        # The run for 2 -> 3 was cancelled as a superseded pending run.
        self.push(pfeed, 3, 4)
        assert len(slack.replies) == 2
        text = slack.replies[1]["text"]
        assert text.startswith("🔨 2 new commits") and f"files/{sha(2)}..{sha(4)}" in text
        assert "|sha0003>" in text and "|sha0004>" in text and "|sha0002>" not in text

    def test_late_rerun_of_an_older_push_posts_nothing(self, pfeed, slack, commits):
        commits += [commit(2), commit(3)]
        self.push(pfeed, 1, 3)
        self.push(pfeed, 1, 2, head=3)
        assert len(slack.replies) == 1

    def test_superseded_push_posts_nothing(self, pfeed, slack, commits, sleeps):
        commits[:] = [commit(101)]
        self.push(pfeed, 1, 2, head=101)
        assert slack.replies == []
        assert sleeps == []

    def test_a_lagging_commit_list_is_retried(self, pfeed, slack, commits, sleeps, monkeypatch):
        def catch_up(seconds):
            sleeps.append(seconds)
            commits.append(commit(2))

        monkeypatch.setattr(pfeed, "sleep", catch_up)
        self.push(pfeed, 1, 2)
        assert sleeps == [pr_feed.POLL_SECONDS]
        assert slack.replies[0]["text"].startswith("🔨 1 new commit")

    def test_a_commit_list_that_never_catches_up_fails_the_run(self, pfeed, slack, sleeps):
        with pytest.raises(pr_feed.CommitListLagError):
            self.push(pfeed, 1, 2)
        assert len(sleeps) == pr_feed.COMMIT_POLLS - 1
        assert slack.replies == []

    def test_draft_pushes_are_never_listed(self, pfeed, slack, commits, api):
        target(pfeed, "converted_to_draft", pr_at(1, draft=True))
        commits.append(commit(2))
        calls = len(api.calls)
        self.push(pfeed, 1, 2, draft=True)
        assert not any(c.endswith("/commits") for c in api.calls[calls:])
        target(pfeed, "ready_for_review", pr_at(2))
        assert slack.replies[-1]["metadata"]["event_payload"]["head"] == sha(2)

        commits.append(commit(3))
        self.push(pfeed, 2, 3)
        text = slack.replies[-1]["text"]
        assert text.startswith("🔨 1 new commit") and "|sha0002>" not in text
        assert [r["text"][0] for r in slack.replies] == ["📝", "🟢", "🔨"]

    def test_push_racing_the_ready_run_waits_for_it(self, pfeed, slack, commits, sleeps):
        target(pfeed, "converted_to_draft", pr_at(1, draft=True))
        commits += [commit(2), commit(3)]

        def ready_run_finishes(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                target(pfeed, "ready_for_review", pr_at(2))

        pfeed.sleep = ready_run_finishes
        # Pushed right after "Ready for review": the payload is no longer a draft.
        self.push(pfeed, 2, 3)
        assert len(sleeps) == 2
        text = slack.replies[-1]["text"]
        assert text.startswith("🔨 1 new commit") and "|sha0002>" not in text

    def test_push_then_draft_conversion_is_still_posted(self, pfeed, slack, commits, api, sleeps):
        commits.append(commit(2))
        # The conversion's run finished before the push run read the thread.
        target(pfeed, "converted_to_draft", pr_at(1, draft=True))
        api.pr["draft"] = True
        self.push(pfeed, 1, 2)
        assert sleeps == []
        assert slack.replies[-1]["text"].startswith("🔨 1 new commit")

    def test_ready_reply_is_posted_before_the_parent_turns_open(self, pfeed, slack):
        target(pfeed, "converted_to_draft", pr_at(1, draft=True))
        seen = []
        update = slack.update

        def spy(channel, ts, text, metadata=None):
            seen.append(len(slack.replies))
            update(channel, ts, text, metadata)

        slack.update = spy
        target(pfeed, "ready_for_review", pr_at(1))
        assert seen == [2]

    def test_parents_posted_before_heads_were_recorded_use_the_event(
        self, slack, api, commits, sleeps
    ):
        f = pr_feed.Feed(slack, CHANNEL, REPO, github=api, sleep=sleeps.append)
        slack.post(
            CHANNEL, "🟢 old parent", metadata=slack_notify.pr_metadata(REPO, 7, "pr", "open")
        )
        commits += [commit(2), commit(3)]
        self.push(f, 2, 3)
        assert slack.replies[0]["text"].startswith("🔨 1 new commit")

    def test_title_edit_keeps_the_parent_head(self, pfeed, slack, commits):
        commits.append(commit(2))
        self.push(pfeed, 1, 2)
        target(pfeed, "edited", pr_at(2, title="feat: renamed"), changes={"title": {"from": "x"}})
        assert "feat: renamed" in slack.parents[0]["text"]
        assert slack.parents[0]["metadata"]["event_payload"]["head"] == sha(1)

    def test_over_the_api_limit_links_instead_of_listing(self, pfeed, slack, commits, api):
        commits += [commit(n) for n in range(2, 262)]
        calls = len(api.calls)
        self.push(pfeed, 260, 261)
        assert slack.replies[0]["text"] == (
            f"🔨 new commits by alice · <{PR_URL}/files/{sha(260)}..{sha(261)}|view changes>"
            " (over 250 commits, not listed)"
        )
        assert sum(c.endswith("/commits") for c in api.calls[calls:]) == 3

    def test_no_parent_waits_then_posts_nothing(self, slack, api, commits, sleeps):
        f = pr_feed.Feed(slack, CHANNEL, REPO, github=api, sleep=sleeps.append)
        commits.append(commit(2))
        self.push(f, 1, 2)
        assert slack.messages == []
        assert len(sleeps) == pr_feed.PARENT_POLLS - 1

    def test_outsider_pr_or_pusher_posts_nothing(self, pfeed, slack, commits, api):
        commits.append(commit(2))
        pr = outsider_pr()
        pr["head"]["sha"] = sha(2)
        target(pfeed, "synchronize", pr, before=sha(1), after=sha(2))
        self.push(pfeed, 1, 2, sender="mallory")
        assert slack.replies == []
        self.push(pfeed, 1, 2)
        assert len(slack.replies) == 1

    def test_closed_pr_posts_nothing(self, pfeed, slack, commits):
        target(pfeed, "closed", pr_at(1, state="closed"))
        commits.append(commit(2))
        self.push(pfeed, 1, 2, state="closed")
        assert len(slack.replies) == 1

    def test_flux_bump_rerenders_the_one_liner(self, slack):
        files = [dict(f) for f in TestFluxBumps.FILES]
        f = pr_feed.Feed(slack, CHANNEL, REPO, github=github_stub(files=files))
        target(f, "synchronize", TestFluxBumps.bump(), before="a", after="b")
        assert slack.messages == []

        target(f, "opened", TestFluxBumps.bump())
        # A new head drops the old head's CI verdict.
        slack.messages[0]["text"] += " · CI failed ❌"
        target(f, "synchronize", TestFluxBumps.bump(), before="a", after="b")
        assert not slack.messages[0]["text"].endswith("CI failed ❌")
        assert slack.messages[0]["metadata"]["event_payload"]["head"] == "b"

        # A re-delivery for the head already shown keeps CI's verdict on it.
        slack.messages[0]["text"] += " · CI failed ❌"
        target(f, "synchronize", TestFluxBumps.bump(), before="a", after="b")
        assert slack.messages[0]["text"].endswith("CI failed ❌")

        files[0]["patch"] = files[0]["patch"].replace("1793041510-85d3415", "1793100000-abcdef0")
        target(f, "synchronize", TestFluxBumps.bump(), before="b", after="c")
        assert len(slack.messages) == 1
        assert slack.messages[0]["text"].endswith(
            f"→ `1793100000-abcdef0` · <https://github.com/{REPO}/pull/152|#152>"
        )
        assert slack.messages[0]["metadata"]["event_payload"]["head"] == "c"

    def test_github_failure_fails_the_run(self, monkeypatch, tmp_path):
        event = tmp_path / "event.json"
        event.write_text(
            json.dumps({**pr_event("opened", make_pr()), "repository": {"full_name": REPO}})
        )
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_PR_CHANNEL_ID", CHANNEL)
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
        monkeypatch.setenv("GITHUB_TOKEN", "fake-gh-credential")

        def boom(self, event_name, event):
            raise urllib.error.HTTPError("https://api.github.com/x", 502, "Bad Gateway", {}, None)

        monkeypatch.setattr(pr_feed.Feed, "handle", boom)
        assert pr_feed.main() == 1

        def lagging(self, event_name, event):
            raise pr_feed.CommitListLagError("sha0002 is #7's head but not in its commit list yet")

        monkeypatch.setattr(pr_feed.Feed, "handle", lagging)
        assert pr_feed.main() == 1


class TestOpeningCommits:
    @pytest.fixture()
    def commits(self):
        return [commit(1), commit(2), commit(3, "fix: <!channel> & co")]

    @pytest.fixture()
    def api(self, commits):
        return github_stub(commits=commits, pr=pr_at(3))

    @pytest.fixture()
    def ofeed(self, slack, api):
        return pr_feed.Feed(slack, CHANNEL, REPO, github=api, sleep=lambda s: None)

    def test_opened_pr_lists_its_commits(self, ofeed, slack):
        target(ofeed, "opened", pr_at(3))
        [reply] = slack.replies
        assert reply["thread_ts"] == slack.parents[0]["ts"]
        assert reply["text"] == "\n".join(
            [
                f"🔨 3 commits in this PR · <{PR_URL}/files|view changes>",
                f"• <{PR_URL}/commits/{sha(1)}|sha0001> commit 1",
                f"• <{PR_URL}/commits/{sha(2)}|sha0002> commit 2",
                f"• <{PR_URL}/commits/{sha(3)}|sha0003> fix: &lt;!channel&gt; &amp; co",
            ]
        )
        assert reply["metadata"]["event_payload"]["key"] == pr_feed.OPENING_KEY
        assert "head" not in reply["metadata"]["event_payload"]

    def test_one_commit_is_singular(self, ofeed, slack, commits, api):
        commits[:] = [commit(1)]
        api.pr["head"]["sha"] = sha(1)
        target(ofeed, "opened", pr_at(1))
        assert slack.replies[0]["text"].startswith("🔨 1 commit in this PR · ")

    def test_more_than_five_collapse_into_the_files_tab(self, ofeed, slack, commits, api):
        commits[:] = [commit(n) for n in range(1, 9)]
        api.pr["head"]["sha"] = sha(8)
        target(ofeed, "opened", pr_at(8))
        lines = slack.replies[0]["text"].split("\n")
        assert lines[0].startswith("🔨 8 commits in this PR")
        assert len(lines) == 7
        assert lines[6] == f"<{PR_URL}/files|+3 more>"

    def test_draft_lists_nothing_until_ready_then_everything(self, ofeed, slack):
        target(ofeed, "opened", pr_at(3, draft=True))
        assert slack.messages == []
        target(ofeed, "ready_for_review", pr_at(3))
        assert slack.replies[0]["text"].startswith("🔨 3 commits in this PR")

    def test_ready_again_does_not_list_them_again(self, ofeed, slack):
        target(ofeed, "opened", pr_at(3))
        target(ofeed, "converted_to_draft", pr_at(3, draft=True))
        target(ofeed, "ready_for_review", pr_at(3))
        assert [r["text"][0] for r in slack.replies] == ["🔨", "📝", "🟢"]

    def test_only_commits_up_to_the_parents_head(self, ofeed, slack, commits):
        # Commit 3 was pushed before this run read the list; its push run reports it.
        target(ofeed, "opened", pr_at(2))
        text = slack.replies[0]["text"]
        assert text.startswith("🔨 2 commits in this PR") and "|sha0003>" not in text

    def test_then_a_push_lists_only_what_came_after(self, ofeed, slack, commits, api):
        commits.pop()
        api.pr["head"]["sha"] = sha(2)
        target(ofeed, "opened", pr_at(2))
        commits.append(commit(3))
        TestPushes.push(ofeed, 2, 3)
        opening, push = (r["text"] for r in slack.replies)
        assert "|sha0002>" in opening and "|sha0003>" not in opening
        assert push.startswith("🔨 1 new commit") and "|sha0002>" not in push

    def test_force_pushed_before_the_list_was_read_posts_no_list(self, ofeed, slack, commits):
        commits[:] = [commit(101)]
        ofeed.github.pr["head"]["sha"] = sha(101)
        target(ofeed, "opened", pr_at(3))
        assert len(slack.parents) == 1
        assert slack.replies == []

    def test_over_the_api_limit_links_instead_of_listing(self, ofeed, slack, commits, api):
        commits[:] = [commit(n) for n in range(1, 262)]
        api.pr["head"]["sha"] = sha(261)
        target(ofeed, "opened", pr_at(261))
        assert slack.replies[0]["text"] == (
            f"🔨 over 250 commits in this PR · <{PR_URL}/files|view changes>"
        )

    def test_duplicate_delivery_lists_once(self, ofeed, slack, api):
        for action in ("opened", "opened", "ready_for_review", "reopened"):
            target(ofeed, action, pr_at(3))
        assert len(slack.parents) == 1
        assert len(slack.replies) == 1

    def test_rerun_finishes_a_list_that_failed(self, ofeed, slack, commits, api):
        def lagging(path, **params):
            if path.endswith("/commits"):
                return []
            return github_stub(commits=commits, pr=pr_at(3))(path, **params)

        ofeed.github = lagging
        with pytest.raises(pr_feed.CommitListLagError):
            target(ofeed, "opened", pr_at(3))
        assert len(slack.parents) == 1 and slack.replies == []

        ofeed.github = api
        target(ofeed, "opened", pr_at(3))
        assert len(slack.parents) == 1
        assert slack.replies[0]["text"].startswith("🔨 3 commits in this PR")

    def test_parents_without_a_recorded_head_list_nothing(self, ofeed, slack):
        slack.post(
            CHANNEL, "🟢 old parent", metadata=slack_notify.pr_metadata(REPO, 7, "pr", "open")
        )
        target(ofeed, "opened", pr_at(3))
        assert slack.replies == []

    def test_no_github_token_lists_nothing(self, slack):
        pr = pr_at(3)
        pr["user"] = {"login": "fmi-codes-bot[bot]", "type": "Bot"}
        target(pr_feed.Feed(slack, CHANNEL, REPO), "opened", pr)
        assert len(slack.parents) == 1
        assert slack.replies == []


class TestSlackReplies:
    def test_find_replies_returns_every_match_oldest_first(self):
        first = {"ts": "2", "metadata": slack_notify.reply_metadata(REPO, 7, "push:a", "a")}
        second = {"ts": "3", "metadata": slack_notify.reply_metadata(REPO, 7, "review:1")}
        parent = {"ts": "1", "metadata": slack_notify.pr_metadata(REPO, 7, "pr", "open", "z")}
        slack, requests = TestSlackClient.client(
            TestSlackClient(), {"ok": True, "messages": [parent, first, second]}
        )
        found = slack.find_replies(CHANNEL, "1", slack_notify.REPLY_EVENT_TYPE, pr_number=7)
        assert found == [first, second]
        assert requests[0].full_url.endswith("/conversations.replies")

    def test_head_is_left_out_when_unset(self):
        assert "head" not in slack_notify.pr_metadata(REPO, 7, "pr", "open")["event_payload"]
        assert "head" not in slack_notify.reply_metadata(REPO, 7, "k")["event_payload"]


class TestReviewRelay:
    """Reviews reach the thread through the relay's workflow_run scan (issue #163)."""

    FORK = {"full_name": "alice/fork", "owner": {"login": "alice"}}

    @staticmethod
    def keys(slack, number=7):
        """The review keys posted in PR *number*'s thread, oldest first."""
        parent = slack.find_pr_message(CHANNEL, REPO, number)
        keys = [
            ((r["metadata"] or {}).get("event_payload") or {}).get("key") or ""
            for r in slack.replies
            if r["thread_ts"] == parent["ts"]
        ]
        return [k for k in keys if k.startswith("review:")]

    @staticmethod
    def fork_pr(number=7, **kw):
        """A PR from a writer's fork: alice can push here."""
        pr = make_pr(number=number, head="patch-1", **kw)
        pr["head"]["repo"] = {"full_name": "alice/fork"}
        pr.setdefault("updated_at", "2026-11-03T00:59:00Z")
        return pr

    def test_approvals_change_requests_and_summaries_post(self, feed, slack):
        target(feed, "opened", make_pr())
        review(
            feed,
            make_pr(),
            rest_review("approved", review_id=1),
            rest_review("changes_requested", review_id=2),
            rest_review("commented", review_id=3, body="A few nits inline."),
        )
        assert [r["state"] for r in feed.github.reviews] == [
            "APPROVED",
            "CHANGES_REQUESTED",
            "COMMENTED",
        ]
        url = f"https://github.com/{REPO}/pull/7#pullrequestreview-"
        assert [r["text"] for r in slack.replies] == [
            f"✅ <{url}1|approved> by carol",
            f"🔁 <{url}2|changes requested> by carol",
            f"💬 <{url}3|review comments> by carol",
        ]
        assert self.keys(slack) == ["review:1", "review:2", "review:3"]

    def test_same_repo_pr_from_the_run_and_foreign_entries_ignored(self, feed, slack):
        target(feed, "opened", make_pr())
        foreign = {"number": 3, "head": {"sha": "reviewedsha"}, "base": {"repo": {"id": 999}}}
        mine = {"number": 7, "head": {"sha": "reviewedsha"}, "base": {"repo": {"id": REPO_ID}}}
        review(feed, make_pr(), rest_review("approved"), pull_requests=[foreign, mine])
        assert self.keys(slack) == ["review:1"]
        assert f"/repos/{REPO}/pulls/3" not in feed.github.calls
        assert f"/repos/{REPO}/pulls" not in feed.github.calls

    def test_fork_pr_is_found_by_its_head(self, feed, slack):
        pr = self.fork_pr()
        target(feed, "opened", pr)
        feed.github.listed = [pr]
        # A deleted fork: no owner to look the PR up by.
        review(
            feed, pr, rest_review("approved", review_id=1), pull_requests=[], head_repository=None
        )
        assert self.keys(slack) == []
        review(
            feed,
            pr,
            rest_review("approved", review_id=2),
            pull_requests=[],
            head_repository=self.FORK,
        )
        assert self.keys(slack) == ["review:1", "review:2"]

    def test_a_reused_head_branch_takes_the_pr_at_the_reviewed_commit(self, feed, slack):
        target(feed, "opened", self.fork_pr(number=5))
        target(feed, "opened", self.fork_pr(number=7))
        old = self.fork_pr(number=5, state="closed", merged=True, updated_at="2025-01-01T00:00:00Z")
        target(feed, "closed", old)
        old["head"]["sha"] = "oldsha"
        new = self.fork_pr(number=7)
        new["head"]["sha"] = "newsha"
        feed.github.listed = [old, new]
        feed.github.reviews.append(rest_review("approved"))

        # Pushed since the review: no PR is at its commit, so only the open one counts.
        run = relay_run(new, head_sha="pushedsince", pull_requests=[], head_repository=self.FORK)
        feed.handle("workflow_run", run)
        assert self.keys(slack, 7) == ["review:1"]
        assert self.keys(slack, 5) == []
        # The list API said #5 is closed and stale, so it isn't even re-read.
        assert f"/repos/{REPO}/pulls/5" not in feed.github.calls

        # A review on the merged PR: its head is the reviewed commit.
        run = relay_run(old, head_sha="oldsha", pull_requests=[], head_repository=self.FORK)
        feed.handle("workflow_run", run)
        assert self.keys(slack, 5) == ["review:1"]
        assert self.keys(slack, 7) == ["review:1"]

    def test_bots_and_reviewers_who_cant_push_post_nothing(self, feed, slack):
        target(feed, "opened", make_pr())
        bot = rest_review("approved", reviewer="ci[bot]", review_id=1)
        bot["user"]["type"] = "Bot"
        review(
            feed,
            make_pr(),
            bot,
            rest_review("approved", reviewer="mallory", review_id=2),
            rest_review("approved", review_id=3),
            rest_review("commented", review_id=4, body="One more thing."),
        )
        assert self.keys(slack) == ["review:3", "review:4"]
        permissions = [c for c in feed.github.calls if c.endswith("/permission")]
        assert permissions.count(f"/repos/{REPO}/collaborators/carol/permission") == 1
        assert f"/repos/{REPO}/collaborators/ci%5Bbot%5D/permission" not in permissions

    def test_dismissed_empty_and_incomplete_reviews_post_nothing(self, feed, slack):
        target(feed, "opened", make_pr())
        review(
            feed,
            make_pr(),
            rest_review("dismissed", review_id=1),
            rest_review("commented", review_id=2, body="  "),
            rest_review("approved", review_id=3, user=None),
            rest_review("approved", review_id=4, submitted_at=None),
            rest_review("pending", review_id=5),
            rest_review("approved", review_id=6),
        )
        assert self.keys(slack) == ["review:6"]

    def test_inline_reply_reviews_without_a_summary_post_nothing(self, feed, slack):
        target(feed, "opened", make_pr())
        review(feed, make_pr(), *(rest_review("commented", review_id=i) for i in range(5)))
        assert slack.replies == []
        review(feed, make_pr(), rest_review("commented", review_id=9, body="Summary"))
        assert self.keys(slack) == ["review:9"]

    def test_reviews_past_the_first_page_are_read(self, feed, slack):
        target(feed, "opened", make_pr())
        inline = [rest_review("commented", review_id=i) for i in range(150)]
        review(feed, make_pr(), *inline, rest_review("approved", review_id=200))
        assert self.keys(slack) == ["review:200"]
        assert sum(c.endswith("/reviews") for c in feed.github.calls) == 2

    def test_untrusted_author_posts_nothing(self, feed, slack):
        slack.post(CHANNEL, "🟢 parent", metadata=slack_notify.pr_metadata(REPO, 9, "pr", "open"))
        review(feed, outsider_pr(number=9), rest_review("approved"))
        assert slack.replies == []
        assert not any(c.endswith("/reviews") for c in feed.github.calls)
        target(feed, "opened", make_pr())
        review(feed, make_pr())
        assert self.keys(slack) == ["review:1"]

    def test_flux_bump_reviews_stay_silent(self, slack):
        f = pr_feed.Feed(slack, CHANNEL, REPO, github=github_stub(files=TestFluxBumps.FILES))
        target(f, "opened", TestFluxBumps.bump())
        review(f, TestFluxBumps.bump(), rest_review("approved"))
        target(f, "closed", TestFluxBumps.bump(state="closed", merged=True))
        target(f, "closed", TestFluxBumps.bump(state="closed", merged=True))
        assert len(slack.messages) == 1
        assert slack.messages[0]["text"].endswith(" · merged ✅")
        assert not any(c.endswith("/reviews") for c in f.github.calls)

        target(f, "opened", make_pr())
        review(f, make_pr())
        assert self.keys(slack) == ["review:1"]

    @staticmethod
    def event(kind, at):
        return {"event": kind, "created_at": f"2026-11-03T{at}Z"}

    def test_draft_spans_come_from_the_issue_events(self):
        at = pr_feed.epoch
        pr = make_pr()
        events = [
            self.event("ready_for_review", "00:10:00"),
            self.event("labeled", "00:15:00"),
            self.event("convert_to_draft", "00:20:00"),
            self.event("ready_for_review", "00:30:00"),
            self.event("convert_to_draft", "00:40:00"),
        ]
        # Opened as a draft (ready first), back to draft once and a draft now.
        assert pr_feed.draft_spans(pr, events) == [
            (at(pr["created_at"]), at("2026-11-03T00:10:00Z")),
            (at("2026-11-03T00:20:00Z"), at("2026-11-03T00:30:00Z")),
            (at("2026-11-03T00:40:00Z"), math.inf),
        ]
        assert pr_feed.draft_spans(pr, events[2:4]) == [
            (at("2026-11-03T00:20:00Z"), at("2026-11-03T00:30:00Z"))
        ]
        assert pr_feed.draft_spans(pr, []) == []

    def test_only_reviews_made_in_a_draft_are_left_out(self, feed, slack):
        target(feed, "opened", make_pr())
        feed.github.events = [
            self.event("convert_to_draft", "00:10:00"),
            self.event("ready_for_review", "00:30:00"),
        ]
        # The thread has no "ready" reply yet: the draft span comes from GitHub alone.
        review(
            feed,
            make_pr(),
            rest_review("approved", review_id=1, submitted_at="2026-11-03T00:05:00Z"),
            rest_review("approved", review_id=2, submitted_at="2026-11-03T00:20:00Z"),
            rest_review("approved", review_id=3, submitted_at="2026-11-03T00:40:00Z"),
        )
        assert self.keys(slack) == ["review:1", "review:3"]

    def test_reviews_before_a_draft_first_turned_ready_never_post(self, feed, slack):
        target(feed, "opened", make_pr())
        feed.github.events = [self.event("ready_for_review", "00:30:00")]
        review(
            feed,
            make_pr(),
            rest_review("approved", review_id=1, submitted_at="2026-11-03T00:10:00Z"),
            rest_review("approved", review_id=2, submitted_at="2026-11-03T00:40:00Z"),
        )
        assert self.keys(slack) == ["review:2"]

    def test_a_review_right_after_ready_waits_for_the_parent(self, slack):
        sleeps = []
        f = pr_feed.Feed(slack, CHANNEL, REPO, github=github_stub(), sleep=sleeps.append)
        # Opened long before the run and never posted: nothing to wait for.
        review(f, make_pr(), rest_review("approved", submitted_at="2026-11-03T00:58:00Z"))
        assert sleeps == [] and slack.messages == []

        def ready_run_finishes(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                target(f, "ready_for_review", make_pr())

        f.sleep = ready_run_finishes
        f.github.events = [self.event("ready_for_review", "00:59:30")]
        # The parent the scan waits for is posted after the review it is for.
        slack.now = pr_feed.epoch("2026-11-03T01:00:50Z")
        review(
            f, make_pr(), rest_review("approved", review_id=2, submitted_at="2026-11-03T00:59:40Z")
        )
        assert sleeps == [pr_feed.POLL_SECONDS] * 2
        assert float(slack.parents[0]["ts"]) > pr_feed.epoch("2026-11-03T00:59:40Z")
        assert self.keys(slack) == ["review:2"]

    def test_a_draft_span_cut_off_by_the_events_cap_is_ignored(self, feed, slack):
        target(feed, "opened", make_pr())
        # The PR is open, so the ready_for_review after this was past the last page.
        feed.github.events = [self.event("convert_to_draft", "00:10:00")]
        review(
            feed,
            make_pr(),
            rest_review("approved", review_id=1, submitted_at="2026-11-03T00:05:00Z"),
            rest_review("approved", review_id=2, submitted_at="2026-11-03T00:40:00Z"),
        )
        assert self.keys(slack) == ["review:1", "review:2"]

    def test_every_pr_at_the_reviewed_commit_is_scanned(self, feed, slack):
        target(feed, "opened", make_pr(number=7))
        target(feed, "opened", make_pr(number=8))
        feed.github.pr = make_pr(number=7)
        feed.github.listed = [make_pr(number=8)]
        feed.github.reviews.append(rest_review("approved"))
        # The same branch PR'd into two bases: both entries are at the reviewed commit.
        entries = [
            {"number": n, "head": {"sha": "reviewedsha"}, "base": {"repo": {"id": REPO_ID}}}
            for n in (7, 8)
        ]
        feed.handle("workflow_run", relay_run(make_pr(), pull_requests=entries))
        assert self.keys(slack, 7) == ["review:1"]
        assert self.keys(slack, 8) == ["review:1"]

    def test_reviews_older_than_the_window_are_left_out(self, feed, slack):
        target(feed, "opened", make_pr())
        review(
            feed,
            make_pr(),
            rest_review("approved", review_id=1, submitted_at="2026-11-02T23:59:59Z"),
            rest_review("approved", review_id=2, submitted_at="2026-11-03T00:00:00Z"),
        )
        assert self.keys(slack) == ["review:2"]

    def test_reviews_the_old_workflow_posted_are_not_posted_again(self, feed, slack):
        target(feed, "opened", make_pr())
        slack.post(
            CHANNEL,
            "✅ approved by carol",
            thread_ts=slack.parents[0]["ts"],
            metadata=slack_notify.reply_metadata(REPO, 7, "review:1"),
        )
        review(
            feed,
            make_pr(),
            rest_review("approved", review_id=1),
            rest_review("approved", reviewer="dave", review_id=2),
        )
        assert self.keys(slack) == ["review:1", "review:2"]
        assert len(slack.replies) == 2

    def test_a_rerun_posts_each_review_once(self, feed, slack):
        target(feed, "opened", make_pr())
        for _ in range(2):
            review(feed, make_pr(), rest_review("approved", review_id=9))
        review(feed, make_pr())
        assert self.keys(slack) == ["review:9"]

    def test_other_runs_and_runs_without_a_pr_post_nothing(self, feed, slack):
        target(feed, "opened", make_pr())
        feed.github.pr = make_pr()
        feed.github.reviews.append(rest_review("approved"))
        feed.handle("workflow_run", relay_run(make_pr(), event="pull_request"))
        feed.handle("workflow_run", relay_run(make_pr(), pull_requests=[]))
        assert slack.replies == []
        review(feed, make_pr())
        assert self.keys(slack) == ["review:1"]

    def test_no_github_token_reads_nothing(self, slack):
        slack.post(CHANNEL, "🟢 parent", metadata=slack_notify.pr_metadata(REPO, 7, "pr", "open"))
        pr_feed.Feed(slack, CHANNEL, REPO).handle("workflow_run", relay_run(make_pr()))
        assert slack.replies == []

    def test_a_review_event_does_nothing(self, feed, slack):
        target(feed, "opened", make_pr())
        calls = len(feed.github.calls)
        feed.handle("pull_request_review", review_event(make_pr(), "approved"))
        assert slack.replies == []
        assert len(feed.github.calls) == calls
        review(feed, make_pr(), rest_review("approved"))
        assert self.keys(slack) == ["review:1"]

    def test_main_runs_the_scan_on_workflow_run(self, monkeypatch, tmp_path):
        event = tmp_path / "event.json"
        event.write_text(
            json.dumps({**relay_run(make_pr()), "repository": {"full_name": REPO}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_PR_CHANNEL_ID", CHANNEL)
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_run")
        monkeypatch.setenv("GITHUB_TOKEN", "fake-gh-credential")
        api = github_stub(pr=make_pr(), reviews=[rest_review("approved")])
        monkeypatch.setattr(pr_feed.GitHub, "get", lambda self, path, **p: api(path, **p))
        fake = FakeSlack()
        fake.post(CHANNEL, "🟢 parent", metadata=slack_notify.pr_metadata(REPO, 7, "pr", "open"))
        monkeypatch.setattr(slack_notify, "Slack", lambda token: fake)
        assert pr_feed.main() == 0
        assert self.keys(fake) == ["review:1"]
