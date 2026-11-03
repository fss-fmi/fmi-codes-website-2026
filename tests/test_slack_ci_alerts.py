"""Unit tests for .github/scripts/ci_alerts.py and github_api.py (no network)."""

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".github" / "scripts"))

import ci_alerts  # noqa: E402
import github_api  # noqa: E402
import pr_feed  # noqa: E402
import slack_notify  # noqa: E402

REPO = "fss-fmi/fmi-codes-website-2026"
ACTIONS = "C0ACTIONS"
PRS = "C0PRFEED"
REPO_URL = f"https://github.com/{REPO}"

FAILED_LOG = """\
2026-10-12T23:45:17.0000000Z ##[group]Run actions/checkout@v4
2026-10-12T23:45:17.0000001Z with:
2026-10-12T23:45:17.0000002Z ##[endgroup]
2026-10-12T23:45:23.1000000Z ##[group]Run ruff format --check .
2026-10-12T23:45:23.1000001Z \x1b[36;1mruff format --check .\x1b[0m
2026-10-12T23:45:23.1000002Z ##[endgroup]
2026-10-12T23:45:23.2000000Z Would reformat: backend/app/x.py
2026-10-12T23:45:23.2838841Z ##[error]Process completed with exit code 1.
2026-10-12T23:45:23.7178050Z ##[group]Run pytest tests/
2026-10-12T23:45:23.7178229Z \x1b[36;1mpytest tests/\x1b[0m
2026-10-12T23:45:23.7248121Z shell: /usr/bin/bash -e {0}
2026-10-12T23:45:23.7248283Z env:
2026-10-12T23:45:23.7248470Z   REDIS_URL: redis://localhost:6379
2026-10-12T23:45:23.7249834Z ##[endgroup]
2026-10-12T23:45:37.0000000Z Traceback (most recent call last):
2026-10-12T23:45:37.0000001Z   File "/srv/app/services/team_service.py", line 42, in join
2026-10-12T23:45:37.0000002Z     raise ValueError("team is full")
2026-10-12T23:45:37.0000003Z     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
2026-10-12T23:45:37.0000004Z     at Object.<anonymous> (/app/x.js:1:1)
2026-10-12T23:45:37.0000005Z \x1b[31mE   ValueError: team is full <&>\x1b[0m
2026-10-12T23:45:37.0000006Z FAILED tests/test_team_service.py::test_join - ValueError
2026-10-12T23:45:38.3129361Z ##[error]Process completed with exit code 1.
2026-10-12T23:45:38.3229723Z Post job cleanup.
2026-10-12T23:45:38.4000000Z ##[error]post step noise
"""


REPO_ID = 4242


def pr_ref(number, sha="abc1234def5678", base_repo_id=REPO_ID):
    """A workflow_run.pull_requests entry (only what GitHub puts there)."""
    return {"number": number, "head": {"sha": sha}, "base": {"repo": {"id": base_repo_id}}}


def make_run(conclusion="failure", event="pull_request", attempt=1, prs=None, **extra):
    run = {
        "id": 900,
        "name": "CI",
        "workflow_id": 11,
        "conclusion": conclusion,
        "event": event,
        "run_attempt": attempt,
        "head_branch": "feature/x",
        "head_sha": "abc1234def5678",
        "html_url": f"{REPO_URL}/actions/runs/900",
        "created_at": "2026-11-03T01:00:00Z",
        "run_started_at": "2026-11-03T01:00:00Z",
        "pull_requests": [pr_ref(7)] if prs is None else prs,
        "head_repository": {"full_name": REPO, "owner": {"login": "fss-fmi"}},
        "repository": {"html_url": REPO_URL, "id": REPO_ID},
        "triggering_actor": {"login": "alice"},
    }
    run.update(extra)
    return run


def make_pr(number=7, head="feature/x", draft=False):
    return {
        "number": number,
        "title": "feat: add things",
        "html_url": f"{REPO_URL}/pull/{number}",
        "user": {"login": "alice", "type": "User"},
        "author_association": "MEMBER",
        "draft": draft,
        "state": "open",
        "merged": False,
        "created_at": "2026-11-03T00:00:00Z",
        "base": {"ref": "main"},
        "head": {"ref": head, "label": f"fss-fmi:{head}", "repo": {"full_name": REPO}},
    }


class FakeSlack:
    def __init__(self):
        self.messages = []

    def post(self, channel, text, thread_ts=None, metadata=None):
        ts = f"{len(self.messages) + 1}.000"
        self.messages.append(
            {
                "channel": channel,
                "ts": ts,
                "text": text,
                "thread_ts": thread_ts,
                "metadata": metadata,
            }
        )
        return ts

    def update(self, channel, ts, text, metadata=None):
        message = next(m for m in self.messages if m["ts"] == ts)
        message.update(text=text, metadata=metadata)

    def permalink(self, channel, ts):
        return f"https://slack.test/archives/{channel}/p{ts}"

    def find_message(self, channel, event_type, oldest=0, **match):
        for m in reversed(self.messages):
            meta = m["metadata"] or {}
            payload = meta.get("event_payload") or {}
            if (
                m["channel"] == channel
                and m["thread_ts"] is None
                and meta.get("event_type") == event_type
                and all(str(payload.get(k)) == str(v) for k, v in match.items())
            ):
                return m
        return None

    def find_pr_message(self, channel, repo, pr_number, oldest=0):
        return self.find_message(
            channel, slack_notify.PR_EVENT_TYPE, oldest, repo=repo, pr_number=pr_number
        )

    def find_reply(self, channel, thread_ts, event_type, **match):
        for m in self.messages:
            meta = m["metadata"] or {}
            payload = meta.get("event_payload") or {}
            if (
                m["thread_ts"] == thread_ts
                and meta.get("event_type") == event_type
                and all(str(payload.get(k)) == str(v) for k, v in match.items())
            ):
                return m
        return None

    def in_channel(self, channel):
        return [m for m in self.messages if m["channel"] == channel and m["thread_ts"] is None]

    def replies(self):
        return [m for m in self.messages if m["thread_ts"] is not None]


class FakeGitHub:
    def __init__(self, pr=None, previous=(), attempts=None, log=FAILED_LOG, files=()):
        self.pr = pr if pr is not None else make_pr()
        self.previous = list(previous)
        self.attempts = attempts or {}
        self.log = log
        self.files = list(files)
        self.calls = []

    def get(self, path, **params):
        self.calls.append((path, params))
        if path.endswith("/permission"):
            return {"permission": "write"}
        if path == f"/repos/{REPO}/pulls/{self.pr['number']}":
            return self.pr
        if path == f"/repos/{REPO}/pulls/{self.pr['number']}/files":
            return self.files
        if path == f"/repos/{REPO}/pulls":
            return [self.pr] if params.get("head") == f"mallory:{self.pr['head']['ref']}" else []
        if path.endswith("/jobs"):
            return {
                "jobs": [
                    {"id": 1, "name": "Lint", "conclusion": "success", "steps": []},
                    {
                        "id": 2,
                        "name": "Unit & E2E tests",
                        "conclusion": "failure",
                        "steps": [
                            {"name": "Ruff format check (advisory)", "conclusion": "success"},
                            {
                                "name": "Run unit tests",
                                "conclusion": "failure",
                                "completed_at": "2026-10-12T23:45:38Z",
                            },
                        ],
                    },
                ]
            }
        if "/attempts/" in path:
            return {"conclusion": self.attempts[int(path.rsplit("/", 1)[1])]}
        if path.endswith("/runs"):
            return {"workflow_runs": self.previous}
        raise AssertionError(f"unexpected GET {path}")

    def text(self, path, **params):
        assert path == f"/repos/{REPO}/actions/jobs/2/logs"
        return self.log


def prior(conclusion, run_id=899, created_at="2026-11-03T00:30:00Z", head=REPO):
    return {
        "id": run_id,
        "conclusion": conclusion,
        "created_at": created_at,
        "head_repository": {"full_name": head},
    }


@pytest.fixture()
def slack():
    return FakeSlack()


def with_parent(slack, pr=None, kind="pr", text="🟢 parent"):
    pr = pr or make_pr()
    slack.post(PRS, text, metadata=slack_notify.pr_metadata(REPO, pr["number"], kind, "open"))
    return slack.messages[-1]


def alerts(slack, gh):
    return ci_alerts.Alerts(slack, gh, REPO, ACTIONS, PRS)


class TestLogTail:
    def test_failed_steps_error_not_an_earlier_advisory_one(self):
        tail = ci_alerts.log_tail(FAILED_LOG, "2026-10-12T23:45:38Z")
        assert "Would reformat" not in tail
        assert "ValueError: team is full" in tail
        assert tail.endswith("Error: Process completed with exit code 1.")

    def test_strips_header_timestamps_colours_and_frames(self):
        tail = ci_alerts.log_tail(FAILED_LOG, "2026-10-12T23:45:38Z")
        for gone in (
            "2026-10-12T",
            "\x1b[",
            "REDIS_URL",
            "pytest tests/\n",
            'File "',
            "    at ",
            "^^^",
            "Traceback",
            'raise ValueError("team is full")',
            "post step noise",
        ):
            assert gone not in tail, gone
        assert tail.splitlines() == [
            "E   ValueError: team is full <&>",
            "FAILED tests/test_team_service.py::test_join - ValueError",
            "Error: Process completed with exit code 1.",
        ]

    def test_caps_lines_and_chars(self):
        body = "".join(f"2026-10-12T23:45:30.{i:07d}Z line {i} {'x' * 100}\n" for i in range(60))
        log = (
            f"2026-10-12T23:45:29.0Z ##[group]Run make\n2026-10-12T23:45:29.1Z ##[endgroup]\n{body}"
        )
        tail = ci_alerts.log_tail(log + "2026-10-12T23:45:31.0Z ##[error]boom\n")
        assert len(tail.splitlines()) <= ci_alerts.TAIL_LINES
        assert len(tail) <= ci_alerts.TAIL_CHARS
        assert tail.endswith("Error: boom")

    def test_no_error_marker_takes_the_last_lines(self):
        assert ci_alerts.log_tail("one\ntwo\nthree\n") == "one\ntwo\nthree"

    def test_code_fences_cannot_close_the_block(self):
        assert "```" not in ci_alerts.log_tail("```\n##[error]x\n")


class TestFailure:
    def test_pr_failure_posts_one_alert_and_one_thread_reply(self, slack):
        parent = with_parent(slack)
        alerts(slack, FakeGitHub()).handle(make_run())

        [alert] = slack.in_channel(ACTIONS)
        text = alert["text"]
        assert text.startswith(
            f"❌ *<{REPO_URL}/actions/runs/900|CI>* failed on <{REPO_URL}/pull/7|#7 feat: add things>"
        )
        assert "job `Unit &amp; E2E tests` · step `Run unit tests`" in text
        assert f"commit <{REPO_URL}/commit/abc1234def5678|abc1234>" in text
        assert "ValueError: team is full &lt;&amp;&gt;" in text
        assert alert["metadata"]["event_payload"] == {
            "repo": REPO,
            "run_id": 900,
            "run_attempt": 1,
            "kind": "failure",
        }

        [reply] = slack.replies()
        assert reply["thread_ts"] == parent["ts"]
        assert reply["text"] == (
            f"❌ <{REPO_URL}/actions/runs/900|CI> failed · "
            f"<https://slack.test/archives/{ACTIONS}/p{alert['ts']}|details>"
        )

    def test_main_failure_posts_only_the_alert(self, slack):
        run = make_run(event="push", prs=[], head_branch="main", name="Build and Push Docker Image")
        gh = FakeGitHub()
        alerts(slack, gh).handle(run)
        [alert] = slack.in_channel(ACTIONS)
        assert "failed on `main`" in alert["text"]
        assert slack.replies() == []
        assert not any(path.startswith(f"/repos/{REPO}/pulls") for path, _ in gh.calls)

    def test_manual_runs_name_who_ran_them(self, slack):
        run = make_run(
            event="workflow_dispatch", prs=[], head_branch="main", name="Migrate database"
        )
        alerts(slack, FakeGitHub()).handle(run)
        assert "workflow_dispatch by alice" in slack.in_channel(ACTIONS)[0]["text"]

    def test_same_attempt_never_posts_twice(self, slack):
        with_parent(slack)
        for _ in range(3):
            alerts(slack, FakeGitHub()).handle(make_run())
        assert len(slack.in_channel(ACTIONS)) == 1
        assert len(slack.replies()) == 1

    def test_a_new_attempt_that_fails_again_is_a_new_alert(self, slack):
        alerts(slack, FakeGitHub()).handle(make_run(attempt=1))
        alerts(slack, FakeGitHub()).handle(make_run(attempt=2))
        assert len(slack.in_channel(ACTIONS)) == 2

    def test_draft_pr_gets_the_alert_but_no_thread_reply(self, slack):
        with_parent(slack)
        alerts(slack, FakeGitHub(pr=make_pr(draft=True))).handle(make_run())
        assert len(slack.in_channel(ACTIONS)) == 1
        assert slack.replies() == []

    def test_fork_pr_is_found_by_head_branch(self, slack):
        with_parent(slack)
        run = make_run(
            prs=[], head_repository={"full_name": "mallory/fork", "owner": {"login": "mallory"}}
        )
        alerts(slack, FakeGitHub()).handle(run)
        assert "#7 feat: add things" in slack.in_channel(ACTIONS)[0]["text"]
        assert len(slack.replies()) == 1

    def test_unreadable_log_still_alerts(self, slack):
        class NoLogs(FakeGitHub):
            def text(self, path, **params):
                raise OSError("410 Gone")

        alerts(slack, NoLogs()).handle(make_run())
        [alert] = slack.in_channel(ACTIONS)
        assert "step `Run unit tests`" in alert["text"]
        assert "```" not in alert["text"]

    def test_timed_out_counts_as_failure(self, slack):
        alerts(slack, FakeGitHub()).handle(make_run(conclusion="timed_out"))
        assert len(slack.in_channel(ACTIONS)) == 1

    @pytest.mark.parametrize("conclusion", ["cancelled", "skipped", "neutral"])
    def test_cancelled_and_skipped_post_nothing(self, slack, conclusion):
        with_parent(slack)
        alerts(slack, FakeGitHub()).handle(make_run(conclusion=conclusion))
        assert len(slack.messages) == 1


class TestFluxBumps:
    FILES = [
        {
            "patch": '-  newTag: 1-aaaaaaa # {"$imagepolicy": "flux-system:fmi-codes-backend-staging:tag"}\n'
            '+  newTag: 2-bbbbbbb # {"$imagepolicy": "flux-system:fmi-codes-backend-staging:tag"}'
        }
    ]

    def gh(self, **kw):
        return FakeGitHub(pr=make_pr(number=152, head=pr_feed.FLUX_BRANCH), files=self.FILES, **kw)

    def run(self, **kw):
        return make_run(
            prs=[pr_ref(152)],
            head_branch=pr_feed.FLUX_BRANCH,
            **kw,
        )

    def test_failure_edits_the_one_liner_instead_of_a_thread(self, slack):
        line = with_parent(slack, make_pr(number=152, head=pr_feed.FLUX_BRANCH), kind="flux")
        alerts(slack, self.gh()).handle(self.run())
        assert slack.replies() == []
        assert line["text"].startswith("⬆️ fmi-codes-backend bumped `1-aaaaaaa` → `2-bbbbbbb`")
        alert_ts = slack.in_channel(ACTIONS)[0]["ts"]
        assert line["text"].endswith(
            f" · CI failed ❌ (<https://slack.test/archives/{ACTIONS}/p{alert_ts}|alert>)"
        )
        assert line["metadata"]["event_payload"]["kind"] == "flux"

    def test_recovery_clears_the_failure(self, slack):
        line = with_parent(slack, make_pr(number=152, head=pr_feed.FLUX_BRANCH), kind="flux")
        alerts(slack, self.gh()).handle(self.run())
        alerts(
            slack, self.gh(previous=[prior("failure", run_id=900)], attempts={1: "failure"})
        ).handle(self.run(conclusion="success", attempt=2))
        assert "CI failed" not in line["text"]
        assert line["text"].endswith("|#152>")

    def test_plain_success_leaves_the_one_liner_alone(self, slack):
        line = with_parent(
            slack, make_pr(number=152, head=pr_feed.FLUX_BRANCH), kind="flux", text="orig"
        )
        alerts(slack, self.gh(previous=[prior("success")])).handle(self.run(conclusion="success"))
        assert line["text"] == "orig"
        assert slack.replies() == []


class TestSuccess:
    def test_plain_success_is_a_thread_line_only(self, slack):
        with_parent(slack)
        alerts(slack, FakeGitHub(previous=[prior("success")])).handle(
            make_run(conclusion="success")
        )
        assert slack.in_channel(ACTIONS) == []
        assert slack.replies()[0]["text"] == f"✅ <{REPO_URL}/actions/runs/900|CI> passed"

    def test_green_again_after_a_failed_run(self, slack):
        with_parent(slack)
        gh = FakeGitHub(previous=[prior("cancelled", run_id=898), prior("failure", run_id=897)])
        alerts(slack, gh).handle(make_run(conclusion="success"))
        [ping] = slack.in_channel(ACTIONS)
        assert ping["text"] == (
            f"✅ <{REPO_URL}/actions/runs/900|CI> is green again on "
            f"<{REPO_URL}/pull/7|#7 feat: add things>"
        )
        assert slack.replies()[0]["text"] == f"✅ <{REPO_URL}/actions/runs/900|CI> green again"

    def test_green_again_on_main(self, slack):
        run = make_run(conclusion="success", event="push", prs=[], head_branch="main")
        alerts(slack, FakeGitHub(previous=[prior("failure")])).handle(run)
        assert slack.in_channel(ACTIONS)[0]["text"].endswith("is green again on `main`")

    def test_rerun_that_passes_is_a_recovery(self, slack):
        alerts(slack, FakeGitHub(attempts={1: "failure"})).handle(
            make_run(conclusion="success", attempt=2)
        )
        assert "green again" in slack.in_channel(ACTIONS)[0]["text"]

    def test_recovery_posts_once(self, slack):
        gh = FakeGitHub(previous=[prior("failure")])
        for _ in range(2):
            alerts(slack, gh).handle(make_run(conclusion="success"))
        assert len(slack.in_channel(ACTIONS)) == 1

    def test_ignores_newer_runs_and_other_forks(self, slack):
        gh = FakeGitHub(
            previous=[
                prior("failure", run_id=901, created_at="2026-11-03T02:00:00Z"),
                prior("failure", run_id=896, head="mallory/fork"),
                prior("success", run_id=895),
            ]
        )
        alerts(slack, gh).handle(make_run(conclusion="success"))
        assert slack.in_channel(ACTIONS) == []

    def test_no_pr_channel_means_no_thread_replies(self, slack):
        with_parent(slack)
        ci_alerts.Alerts(slack, FakeGitHub(), REPO, ACTIONS, "").handle(make_run())
        assert len(slack.in_channel(ACTIONS)) == 1
        assert slack.replies() == []


class TestMain:
    def test_skips_quietly_when_unconfigured(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.delenv("SLACK_ACTIONS_CHANNEL_ID", raising=False)
        monkeypatch.setattr(
            slack_notify.Slack, "call", lambda *a, **k: pytest.fail("must not call Slack")
        )
        assert ci_alerts.main() == 0


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestGitHubClient:
    def test_token_is_not_forwarded_on_redirects(self):
        seen = []

        def opener(req, timeout):
            seen.append(req)
            return FakeResponse(json.dumps({"ok": 1}).encode())

        gh = github_api.GitHub("fake-gh-credential", opener=opener)
        assert gh.get("/repos/x/y/pulls", state="open", head="o:b") == {"ok": 1}
        req = seen[0]
        assert req.full_url == "https://api.github.com/repos/x/y/pulls?state=open&head=o%3Ab"
        assert req.unredirected_hdrs["Authorization"] == "Bearer fake-gh-credential"
        assert "Authorization" not in req.headers


class Outsider(FakeGitHub):
    def __init__(self, permission="read", **kw):
        pr = make_pr()
        pr["user"] = {"login": "mallory", "type": "User"}
        pr["author_association"] = "NONE"
        pr["head"]["repo"] = {"full_name": "mallory/fork"}
        super().__init__(pr=pr, **kw)
        self.permission = permission

    def get(self, path, **params):
        if path.endswith("/permission"):
            self.calls.append((path, params))
            return {"permission": self.permission}
        return super().get(path, **params)


FORK_HEAD = {"full_name": "mallory/fork", "owner": {"login": "mallory"}}


class TestTrust:
    def test_outsider_fork_pr_failure_posts_nothing(self, slack):
        gh = Outsider()
        alerts(slack, gh).handle(make_run(prs=[], head_repository=FORK_HEAD))
        assert slack.messages == []
        assert not any(path.endswith("/logs") for path, _ in gh.calls)

    def test_outsider_success_posts_nothing(self, slack):
        with_parent(slack)
        alerts(slack, Outsider(previous=[prior("failure")])).handle(
            make_run(conclusion="success", prs=[], head_repository=FORK_HEAD)
        )
        assert len(slack.messages) == 1

    def test_fork_run_without_a_pr_posts_nothing(self, slack):
        class NoPR(FakeGitHub):
            def get(self, path, **params):
                if path == f"/repos/{REPO}/pulls":
                    return []
                return super().get(path, **params)

        alerts(slack, NoPR()).handle(make_run(prs=[], head_repository=FORK_HEAD))
        assert slack.messages == []

    def test_repo_branch_without_a_pr_still_alerts(self, slack):
        class NoPR(FakeGitHub):
            def get(self, path, **params):
                if path == f"/repos/{REPO}/pulls":
                    return []
                return super().get(path, **params)

        alerts(slack, NoPR()).handle(make_run(prs=[]))
        assert "failed on `feature/x`" in slack.in_channel(ACTIONS)[0]["text"]

    def test_outsider_who_can_push_is_trusted(self, slack):
        alerts(slack, Outsider(permission="write")).handle(
            make_run(prs=[], head_repository=FORK_HEAD)
        )
        assert len(slack.in_channel(ACTIONS)) == 1

    def test_deleted_fork_does_not_crash(self, slack):
        alerts(slack, FakeGitHub()).handle(make_run(prs=[], head_repository=None))
        assert slack.messages == []


class TestCanPush:
    def test_association_is_never_trusted_on_its_own(self):
        # MEMBER and COLLABORATOR include read-only access.
        assert not github_api.can_push(None, REPO, {"login": "a"}, None)

    @pytest.mark.parametrize(
        ("permission", "expected"),
        [("admin", True), ("write", True), ("read", False), ("none", False), (None, False)],
    )
    def test_permission_api(self, permission, expected):
        def get(path):
            assert path == f"/repos/{REPO}/collaborators/a%2Fb/permission"
            return {"permission": permission}

        assert github_api.can_push(get, REPO, {"login": "a/b"}, None) is expected

    def test_bots_only_from_this_repo(self):
        bot = {"login": "fmi-codes-bot[bot]", "type": "Bot"}
        assert github_api.can_push(None, REPO, bot, REPO)
        assert not github_api.can_push(None, REPO, bot, "mallory/fork")


class TestRedirects:
    """The token follows API redirects on api.github.com, never off-host ones (log blobs)."""

    @staticmethod
    def follow(newurl):
        req = github_api.GitHub("fake-gh-credential")._request("/repos/x/y", {})
        handler = github_api._SameHostAuthRedirect()
        return handler.redirect_request(req, None, 302, "Found", {}, newurl)

    def test_same_host_redirect_keeps_the_token(self):
        new = self.follow("https://api.github.com/repositories/1/pulls")
        assert new.unredirected_hdrs["Authorization"] == "Bearer fake-gh-credential"

    def test_off_host_redirect_drops_it(self):
        new = self.follow("https://productionresultssa1.blob.core.windows.net/logs/1.txt?sig=x")
        assert "Authorization" not in new.unredirected_hdrs
        assert "Authorization" not in new.headers


class TestReviewFixes:
    def test_rerun_of_a_green_run_is_not_a_second_recovery(self, slack):
        with_parent(slack)
        gh = FakeGitHub(previous=[prior("failure", run_id=850)], attempts={1: "success"})
        alerts(slack, gh).handle(make_run(conclusion="success", attempt=1))
        assert len(slack.in_channel(ACTIONS)) == 1
        alerts(slack, gh).handle(make_run(conclusion="success", attempt=2))
        assert len(slack.in_channel(ACTIONS)) == 1
        assert [r["text"].split("|CI> ")[1] for r in slack.replies()] == ["green again", "passed"]

    def test_rerun_finishes_a_thread_reply_that_failed(self, slack):
        with_parent(slack)
        alerts(slack, FakeGitHub()).handle(make_run())
        slack.messages = [m for m in slack.messages if m["thread_ts"] is None]
        alerts(slack, FakeGitHub()).handle(make_run())
        assert len(slack.in_channel(ACTIONS)) == 1
        [reply] = slack.replies()
        assert "failed" in reply["text"]

    def test_rerun_finishes_a_recovery_thread_reply(self, slack):
        with_parent(slack)
        gh = FakeGitHub(previous=[prior("failure")])
        alerts(slack, gh).handle(make_run(conclusion="success"))
        slack.messages = [m for m in slack.messages if m["thread_ts"] is None]
        alerts(slack, gh).handle(make_run(conclusion="success"))
        assert len(slack.in_channel(ACTIONS)) == 1
        assert len(slack.replies()) == 1

    def test_pull_requests_from_other_repos_are_ignored(self, slack):
        with_parent(slack)
        gh = FakeGitHub()
        run = make_run(prs=[pr_ref(3, sha="other", base_repo_id=999), pr_ref(7, sha="other")])
        alerts(slack, gh).handle(run)
        assert "#7 feat: add things" in slack.in_channel(ACTIONS)[0]["text"]
        assert not any(path.endswith("/pulls/3") for path, _ in gh.calls)

    def test_only_foreign_pull_requests_fall_back_to_the_head_lookup(self, slack):
        gh = FakeGitHub()
        alerts(slack, gh).handle(make_run(prs=[pr_ref(3, base_repo_id=999)]))
        assert any(path == f"/repos/{REPO}/pulls" for path, _ in gh.calls)
        assert not any(path.endswith("/pulls/3") for path, _ in gh.calls)

    @pytest.mark.parametrize("merged", [True, False])
    def test_ci_results_never_overwrite_a_closed_flux_line(self, slack, merged):
        pr = make_pr(number=152, head=pr_feed.FLUX_BRANCH)
        pr.update(state="closed", merged=merged)
        line = with_parent(slack, pr, kind="flux", text="final state")
        gh = FakeGitHub(pr=pr, previous=[prior("failure")])
        run = make_run(conclusion="success", prs=[pr_ref(152)], head_branch=pr_feed.FLUX_BRANCH)
        alerts(slack, gh).handle(run)
        alerts(slack, gh).handle(make_run(prs=[pr_ref(152)], head_branch=pr_feed.FLUX_BRANCH))
        assert line["text"] == "final state"

    def test_read_only_member_runs_post_nothing(self, slack):
        class ReadOnly(FakeGitHub):
            def get(self, path, **params):
                if path.endswith("/permission"):
                    return {"permission": "read"}
                return super().get(path, **params)

        alerts(slack, ReadOnly()).handle(make_run())
        assert slack.messages == []


# Fake credentials are assembled from pieces so this file itself never looks like a leak.
FAKE = {
    "slack": "xox" + "b-" + "1234567890-abcdefghijkl",
    "github": "gh" + "p_" + "A" * 36,
    "aws": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "jwt": "eyJ" + "a" * 12 + ".eyJ" + "b" * 12 + "." + "c" * 12,
    "webhook": "https://hooks.slack" + ".com/services/T000/B000/" + "x" * 24,
}


class TestRedaction:
    @pytest.mark.parametrize("kind", sorted(FAKE))
    def test_token_shapes(self, kind):
        out = ci_alerts.redact(f"error: auth failed with {FAKE[kind]} (401)")
        assert FAKE[kind] not in out
        assert "[redacted]" in out
        assert out.startswith("error: auth failed with ")

    @pytest.mark.parametrize(
        ("line", "kept"),
        [
            (
                "git clone https://deploy:" + "s3cr3tvalue@example.com/x/y",
                "https://deploy:[redacted]@example.com",
            ),
            ("Authorization: Bearer " + "abcdefghijklmnop1234", "Authorization: Bearer [redacted]"),
            ("password=" + "hunter2hunter2", "password=[redacted]"),
            ("api_key: " + "'abcdef123456'", "api_key: [redacted]"),
            ("DB_PASSWORD=" + "correcthorse", "DB_PASSWORD=[redacted]"),
        ],
    )
    def test_credentials_in_context(self, line, kept):
        assert kept in ci_alerts.redact(line)

    def test_ordinary_errors_are_untouched(self):
        line = "FAILED tests/test_auth.py::test_token_expiry - AssertionError: token expired"
        assert ci_alerts.redact(line) == line

    def test_private_key_blocks_are_dropped(self):
        log = "\n".join(
            [
                "2026-10-12T23:45:30.0Z ##[group]Run deploy",
                "2026-10-12T23:45:30.1Z ##[endgroup]",
                "2026-10-12T23:45:31.0Z -----BEGIN " + "OPENSSH PRIVATE KEY-----",
                "2026-10-12T23:45:31.1Z b3BlbnNzaC1rZXktdjEAAAAABG5vbmU",
                "2026-10-12T23:45:31.2Z -----END " + "OPENSSH PRIVATE KEY-----",
                "2026-10-12T23:45:32.0Z Permission denied (publickey).",
                "2026-10-12T23:45:33.0Z ##[error]Process completed with exit code 255.",
            ]
        )
        tail = ci_alerts.log_tail(log)
        assert tail.splitlines() == [
            "[redacted private key]",
            "Permission denied (publickey).",
            "Error: Process completed with exit code 255.",
        ]

    def test_alert_never_carries_a_token(self, slack):
        log = FAILED_LOG.replace("FAILED tests", f"token {FAKE['github']} FAILED tests")
        alerts(slack, FakeGitHub(log=log)).handle(make_run())
        assert FAKE["github"] not in slack.in_channel(ACTIONS)[0]["text"]


class TestThreadIdempotency:
    def test_success_reply_posts_once_per_run_attempt(self, slack):
        with_parent(slack)
        gh = FakeGitHub(previous=[prior("success")], attempts={1: "success"})
        for _ in range(3):
            alerts(slack, gh).handle(make_run(conclusion="success"))
        assert len(slack.replies()) == 1
        alerts(slack, gh).handle(make_run(conclusion="success", attempt=2))
        assert len(slack.replies()) == 2

    def test_failure_reply_has_its_own_key(self, slack):
        with_parent(slack)
        alerts(slack, FakeGitHub()).handle(make_run())
        [reply] = slack.replies()
        assert reply["metadata"]["event_payload"]["key"] == "run:900:1:failure"


PYTEST_V_LOG = "\n".join(
    [
        "2026-11-03T00:58:00.0Z ##[group]Run pytest tests/ --ignore=tests/e2e -v",
        "2026-11-03T00:58:00.1Z ##[endgroup]",
        "2026-11-03T00:58:00.2Z ============================= test session starts ==============================",
        "2026-11-03T00:58:00.3Z platform linux -- Python 3.12.15, pytest-9.0.3, pluggy-1.6.0 -- /usr/bin/python",
        "2026-11-03T00:58:00.4Z cachedir: .pytest_cache",
        "2026-11-03T00:58:00.5Z rootdir: /srv/app",
        "2026-11-03T00:58:00.6Z configfile: pytest.ini",
        "2026-11-03T00:58:00.7Z plugins: flask-1.3.0",
        "2026-11-03T00:58:00.8Z collecting ... collected 304 items",
        *(
            f"2026-11-03T00:58:01.{i}Z tests/test_team_service.py::TestCodes::test_{i} PASSED [ {90 + i}%]"
            for i in range(8)
        ),
        "2026-11-03T00:58:01.8Z tests/test_x.py::test_param[admin-True] PASSED [ 98%]",
        "2026-11-03T00:58:01.85Z tests/test_x.py::test_ctx[git clone x-y] PASSED [ 98%]",
        "2026-11-03T00:58:01.9Z tests/test_x.py::test_redis SKIPPED (no redis) [ 99%]",
        "2026-11-03T00:58:02.0Z tests/test_x.py::test_known XFAIL (bug 12) [ 99%]",
        "2026-11-03T00:58:02.1Z tests/test_slack_live_check.py::test_live_check FAILED [100%]",
        "2026-11-03T00:58:02.2Z =================================== FAILURES ===================================",
        "2026-11-03T00:58:02.3Z _______________________________ test_live_check ________________________________",
        "2026-11-03T00:58:02.4Z E       AssertionError: deliberate failure",
        "2026-11-03T00:58:02.5Z FAILED tests/test_slack_live_check.py::test_live_check - AssertionError",
        "2026-11-03T00:58:02.6Z ======================== 1 failed, 303 passed in 3.98s =========================",
        "2026-11-03T00:58:02.7Z ##[error]Process completed with exit code 1.",
    ]
)


class TestPytestProgress:
    def test_passed_skipped_and_xfail_lines_are_dropped(self):
        tail = ci_alerts.log_tail(PYTEST_V_LOG)
        for noise in (
            " PASSED [",
            " SKIPPED (",
            " XFAIL (",
            "rootdir:",
            "plugins:",
            "collected 304",
        ):
            assert noise not in tail, noise
        assert tail.splitlines() == [
            "tests/test_slack_live_check.py::test_live_check FAILED [100%]",
            "=================================== FAILURES ===================================",
            "_______________________________ test_live_check ________________________________",
            "E       AssertionError: deliberate failure",
            "FAILED tests/test_slack_live_check.py::test_live_check - AssertionError",
            "======================== 1 failed, 303 passed in 3.98s =========================",
            "Error: Process completed with exit code 1.",
        ]

    @pytest.mark.parametrize(
        "line",
        [
            "PASSED all checks",
            "tests/test_x.py::test_y passed in 0.1s",
            "assert result == 'PASSED [ 5%]'",
        ],
    )
    def test_lines_that_only_mention_passed_are_kept(self, line):
        assert ci_alerts.log_tail(f"{line}\n##[error]boom\n").splitlines()[0] == line
