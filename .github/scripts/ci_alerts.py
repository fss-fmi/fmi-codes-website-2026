"""Failed-run alerts in #actions-notifications plus CI results in the PR feed (issue #155).

Run by .github/workflows/slack-ci-alerts.yaml on workflow_run completed. The one
handler for every finished run, so nothing else posts CI results:

- failure: an alert in #actions-notifications (workflow, where, job, step,
  commit, a short log tail), then a reply in the PR's #pr-updates thread linking
  it. A Flux bump's one-liner is edited to "CI failed" instead.
- success after a failure: "green again" in #actions-notifications and the thread
  (a Flux one-liner drops its "CI failed").
- other success: a one-line result in the PR thread only.

Cancelled and skipped runs post nothing. Draft PRs get no thread replies.
"""

import json
import logging
import os
import re
import sys

import pr_feed
import slack_notify
from github_api import GitHub, can_push
from slack_notify import ALERT_EVENT_TYPE, alert_metadata, escape, link, pr_metadata

logger = logging.getLogger("ci_alerts")

FAILED = {"failure", "timed_out", "startup_failure"}
PR_EVENTS = {"pull_request", "pull_request_target"}
TAIL_LINES = 20
TAIL_CHARS = 1500

TS_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?Z ?")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
FRAME_RE = re.compile(r'^\s+(File ".*", line \d+|at \S)')
CARETS_RE = re.compile(r"^\s*[\^~]+\s*$")


def log_tail(log: str, step_completed_at: str | None = None) -> str:
    """The failed step's error, without timestamps, colours or stack frames.

    The job stops at its failed step, so that step's error is the last ##[error]
    at or before the step's completion, ahead of the post-job cleanup. Earlier
    ##[error] lines can belong to continue-on-error steps that did not fail the job.
    """
    lines = []
    for raw in log.replace("\r", "").split("\n"):
        m = TS_RE.match(raw)
        lines.append((m.group(1) if m else None, ANSI_RE.sub("", raw[m.end() :] if m else raw)))

    limit = next((i for i, (_, t) in enumerate(lines) if t == "Post job cleanup."), len(lines))
    cutoff = step_completed_at[:19] if step_completed_at else None
    errors = [
        i
        for i, (ts, t) in enumerate(lines[:limit])
        if t.startswith("##[error]") and (not cutoff or not ts or ts <= cutoff)
    ]
    end = errors[-1] if errors else limit - 1
    start = next((i for i in range(end, -1, -1) if lines[i][1].startswith("##[group]Run ")), 0)

    section = [t for _, t in lines[start : end + 1]]
    if section and section[0].startswith("##[group]Run "):
        # The step header: the command echo plus its env block.
        close = next((i for i, t in enumerate(section) if t == "##[endgroup]"), 0)
        section = section[close + 1 :]

    kept = []
    skip_code = False
    for text in section:
        if skip_code and text.startswith("    "):
            skip_code = False
            continue
        skip_code = False
        if FRAME_RE.match(text):
            skip_code = text.lstrip().startswith("File ")
            continue
        if text.startswith("Traceback (most recent call last)") or CARETS_RE.match(text):
            continue
        if text == "##[endgroup]":
            continue
        text = re.sub(r"^##\[error\]", "Error: ", text)
        text = re.sub(r"^##\[warning\]", "Warning: ", text)
        text = re.sub(r"^##\[\w+\]", "", text)
        if text.strip():
            kept.append(text.replace("```", "'''"))

    kept = kept[-TAIL_LINES:]
    while len(kept) > 1 and len("\n".join(kept)) > TAIL_CHARS:
        kept.pop(0)
    tail = "\n".join(kept)
    return tail[-TAIL_CHARS:]


class Alerts:
    def __init__(self, slack, github, repo: str, actions_channel: str, pr_channel: str = ""):
        self.slack = slack
        self.gh = github
        self.repo = repo
        self.actions_channel = actions_channel
        self.pr_channel = pr_channel

    def handle(self, run: dict) -> None:
        if run["conclusion"] not in FAILED | {"success"}:
            return
        pr = self.find_pr(run)
        if not self._trusted(run, pr):
            logger.info("Run %s is from someone who can't push here; not posted", run["id"])
            return
        if run["conclusion"] in FAILED:
            self._failure(run, pr)
        else:
            self._success(run, pr)

    def _trusted(self, run: dict, pr) -> bool:
        """Only runs of code and PRs from people who can push here reach Slack.

        Fork PRs can also add their own workflow with a watched name, since
        workflow_run matches by name; their author still has to be trusted.
        """
        if pr:
            head_repo = (pr["head"].get("repo") or {}).get("full_name")
            return can_push(
                self.gh.get, self.repo, pr["user"], pr.get("author_association"), head_repo
            )
        return (run.get("head_repository") or {}).get("full_name") == self.repo

    # --- where the run belongs -------------------------------------------------

    def find_pr(self, run: dict):
        if run["event"] not in PR_EVENTS:
            return None
        prs = run.get("pull_requests") or []
        number = next((p["number"] for p in prs if p["head"]["sha"] == run["head_sha"]), None)
        if number is None and prs:
            number = prs[0]["number"]
        if number is None:
            # GitHub leaves pull_requests empty for runs on fork PRs.
            owner = ((run.get("head_repository") or {}).get("owner") or {}).get("login")
            if not owner:
                return None
            found = self.gh.get(
                f"/repos/{self.repo}/pulls", state="open", head=f"{owner}:{run['head_branch']}"
            )
            number = found[0]["number"] if found else None
        return self.gh.get(f"/repos/{self.repo}/pulls/{number}") if number else None

    @staticmethod
    def where(run: dict, pr) -> str:
        if pr:
            return link(pr["html_url"], f"#{pr['number']} {pr['title']}")
        return f"`{escape(run['head_branch'] or 'unknown')}`"

    # --- failure ---------------------------------------------------------------

    def _failure(self, run: dict, pr) -> None:
        if self._already_posted(run, "failure"):
            logger.info("Alert for run %s attempt %s already posted", run["id"], run["run_attempt"])
            return
        job, step, tail = self._failed_step(run)
        ts = self.slack.post(
            self.actions_channel,
            alert_text(run, self.where(run, pr), job, step, tail),
            metadata=alert_metadata(self.repo, run["id"], run["run_attempt"], "failure"),
        )
        alert = self.slack.permalink(self.actions_channel, ts)
        self._pr_note(
            pr,
            f"❌ {link(run['html_url'], run['name'])} failed · {link(alert, 'details')}",
            flux_suffix=f"CI failed ❌ ({link(alert, 'alert')})",
        )

    def _failed_step(self, run: dict):
        try:
            jobs = self.gh.get(
                f"/repos/{self.repo}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs",
                per_page=100,
            )["jobs"]
        except Exception as e:
            logger.warning("Could not list the run's jobs: %s", e)
            return None, None, ""
        job = next((j for j in jobs if j.get("conclusion") in FAILED), None)
        if not job:
            return None, None, ""
        step = next((s for s in job.get("steps") or [] if s.get("conclusion") in FAILED), None)
        try:
            log = self.gh.text(f"/repos/{self.repo}/actions/jobs/{job['id']}/logs")
            tail = log_tail(log, step.get("completed_at") if step else None)
        except Exception as e:
            logger.warning("Could not read the failed job's log: %s", e)
            tail = ""
        return job, step, tail

    # --- success ---------------------------------------------------------------

    def _success(self, run: dict, pr) -> None:
        if not self._previous_failed(run):
            self._pr_note(pr, f"✅ {link(run['html_url'], run['name'])} passed", flux_suffix=None)
            return
        if self._already_posted(run, "recovery"):
            return
        self.slack.post(
            self.actions_channel,
            f"✅ {link(run['html_url'], run['name'])} is green again on {self.where(run, pr)}",
            metadata=alert_metadata(self.repo, run["id"], run["run_attempt"], "recovery"),
        )
        self._pr_note(pr, f"✅ {link(run['html_url'], run['name'])} green again", flux_suffix="")

    def _previous_failed(self, run: dict) -> bool:
        """Did the last finished run of this workflow on this branch fail?"""
        if run["run_attempt"] > 1:
            prev = self.gh.get(
                f"/repos/{self.repo}/actions/runs/{run['id']}/attempts/{run['run_attempt'] - 1}"
            )
            if prev.get("conclusion") in FAILED:
                return True
        if not run.get("head_branch"):
            return False
        runs = self.gh.get(
            f"/repos/{self.repo}/actions/workflows/{run['workflow_id']}/runs",
            branch=run["head_branch"],
            status="completed",
            per_page=10,
        )["workflow_runs"]
        head_repo = (run.get("head_repository") or {}).get("full_name")
        for r in runs:
            if r["id"] == run["id"] or r["created_at"] > run["created_at"]:
                continue
            if (r.get("head_repository") or {}).get("full_name") != head_repo:
                continue
            # Superseded runs are cancelled by the CI concurrency group; look past them.
            if r["conclusion"] in FAILED:
                return True
            if r["conclusion"] == "success":
                return False
        return False

    # --- shared ----------------------------------------------------------------

    def _already_posted(self, run: dict, kind: str) -> bool:
        oldest = pr_feed.epoch(run["run_started_at"]) - 60
        return bool(
            self.slack.find_message(
                self.actions_channel,
                ALERT_EVENT_TYPE,
                oldest,
                repo=self.repo,
                run_id=run["id"],
                run_attempt=run["run_attempt"],
                kind=kind,
            )
        )

    def _pr_note(self, pr, text: str, flux_suffix: str | None) -> None:
        """A reply in the PR's thread; for a Flux bump, set its one-liner's suffix instead.

        flux_suffix None leaves a Flux one-liner untouched.
        """
        if not pr or not self.pr_channel or pr.get("draft"):
            return
        parent = self.slack.find_pr_message(
            self.pr_channel, self.repo, pr["number"], pr_feed.epoch(pr["created_at"]) - 60
        )
        if not parent:
            return
        kind = ((parent.get("metadata") or {}).get("event_payload") or {}).get("kind")
        if kind != "flux":
            self.slack.post(self.pr_channel, text, thread_ts=parent["ts"])
            return
        if flux_suffix is None:
            return
        feed = pr_feed.Feed(self.slack, self.pr_channel, self.repo, self.gh.get)
        self.slack.update(
            self.pr_channel,
            parent["ts"],
            pr_feed.flux_text(pr, feed.bumps(pr), flux_suffix),
            metadata=pr_metadata(self.repo, pr["number"], "flux", pr_feed.pr_state(pr)),
        )


def alert_text(run: dict, where: str, job, step, tail: str) -> str:
    lines = [f"❌ *{link(run['html_url'], run['name'])}* failed on {where}"]
    details = []
    if job:
        details.append(f"job `{escape(job['name'])}`")
    if step:
        details.append(f"step `{escape(step['name'])}`")
    commit_url = f"{run['repository']['html_url']}/commit/{run['head_sha']}"
    details.append(f"commit {link(commit_url, run['head_sha'][:7])}")
    if run["event"] not in PR_EVENTS | {"push"}:
        actor = (run.get("triggering_actor") or run.get("actor") or {}).get("login", "unknown")
        details.append(f"{escape(run['event'])} by {escape(actor)}")
    lines.append(" · ".join(details))
    if tail:
        lines.append(f"```{escape(tail)}```")
    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    actions_channel = os.environ.get("SLACK_ACTIONS_CHANNEL_ID", "")
    if not token or not actions_channel:
        logger.info("SLACK_BOT_TOKEN or SLACK_ACTIONS_CHANNEL_ID not set; skipping")
        return 0
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    alerts = Alerts(
        slack_notify.Slack(token),
        GitHub(os.environ["GITHUB_TOKEN"]),
        event["repository"]["full_name"],
        actions_channel,
        os.environ.get("SLACK_PR_CHANNEL_ID", ""),
    )
    try:
        alerts.handle(event["workflow_run"])
    except slack_notify.SlackError as e:
        logger.error("Slack call failed: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
