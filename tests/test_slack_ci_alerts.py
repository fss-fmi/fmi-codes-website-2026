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
        "pull_requests": [{"number": 7, "head": {"sha": "abc1234def5678"}}] if prs is None else prs,
        "head_repository": {"full_name": REPO, "owner": {"login": "fss-fmi"}},
        "repository": {"html_url": REPO_URL},
        "triggering_actor": {"login": "alice"},
    }
    run.update(extra)
    return run


def make_pr(number=7, head="feature/x", draft=False):
    return {
        "number": number,
        "title": "feat: add things",
        "html_url": f"{REPO_URL}/pull/{number}",
        "user": {"login": "alice"},
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
            prs=[{"number": 152, "head": {"sha": "abc1234def5678"}}],
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
