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
from github_api import GitHub
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
# pytest -v prints one line per passing test; CI runs it that way, so without this
# the last lines before the failure summary are all "... PASSED [ 97%]". Parametrised
# ids can contain spaces. The session header says nothing about the failure either.
PYTEST_PROGRESS_RE = re.compile(r"^\S+::.*? (?:PASSED|SKIPPED|XFAIL|XPASS)\b.*\[ *\d+%\]$")
PYTEST_HEADER_RE = re.compile(
    r"^(=+ test session starts =+$|platform \S+ -- Python |cachedir: |rootdir: |configfile: "
    r"|testpaths: |plugins: |collecting \.\.\. |collected \d+ items?)"
)

# GitHub masks registered secrets in logs, but not values derived from them or
# credentials a step prints that were never registered.
REDACTED = "[redacted]"
TOKEN_RE = re.compile(
    r"xox[abeprs]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}"
    r"|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|sk-[A-Za-z0-9_-]{20,}|glpat-[A-Za-z0-9_-]{20,}"
    r"|tskey-[A-Za-z0-9-]{10,}|dckr_pat_[A-Za-z0-9_-]{20,}|npm_[A-Za-z0-9]{36}"
    r"|AGE-SECRET-KEY-1[0-9A-Z]+"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"
    r"|hooks\.slack\.com/\S+|discord(?:app)?\.com/api/webhooks/\S+"
)
URL_CREDS_RE = re.compile(r"(://[^/\s:@]+:)[^/\s@]+@")
AUTH_HEADER_RE = re.compile(r"(?i)\b(bearer|basic|token)(\s+)[A-Za-z0-9._~+/=-]{12,}")
ASSIGNMENT_RE = re.compile(
    r"(?i)\b((?:password|passwd|pwd|secret|token|api[_-]?key|client[_-]?secret|private[_-]?key)"
    r"[\"']?\s*[:=]\s*)[\"']?[^\s\"']{6,}[\"']?"
)
ENV_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)[A-Z0-9_]*\s*[:=]\s*)\S{6,}"
)


def redact(text: str) -> str:
    text = TOKEN_RE.sub(REDACTED, text)
    text = URL_CREDS_RE.sub(rf"\g<1>{REDACTED}@", text)
    text = AUTH_HEADER_RE.sub(rf"\g<1>\g<2>{REDACTED}", text)
    text = ASSIGNMENT_RE.sub(rf"\g<1>{REDACTED}", text)
    return ENV_ASSIGNMENT_RE.sub(rf"\g<1>{REDACTED}", text)


def log_tail(log: str, step_completed_at: str | None = None) -> str:
    """The failed step's error, without timestamps, colours, stack frames, pytest
    progress lines or credentials.

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
    in_key = False
    for text in section:
        if in_key:
            in_key = "-----END" not in text
            continue
        if "-----BEGIN" in text and "PRIVATE KEY" in text:
            kept.append("[redacted private key]")
            in_key = "-----END" not in text.split("-----BEGIN", 1)[1]
            continue
        if skip_code and text.startswith("    "):
            skip_code = False
            continue
        skip_code = False
        if FRAME_RE.match(text):
            skip_code = text.lstrip().startswith("File ")
            continue
        if text.startswith("Traceback (most recent call last)") or CARETS_RE.match(text):
            continue
        if PYTEST_PROGRESS_RE.match(text) or PYTEST_HEADER_RE.match(text):
            continue
        if text == "##[endgroup]":
            continue
        text = re.sub(r"^##\[error\]", "Error: ", text)
        text = re.sub(r"^##\[warning\]", "Warning: ", text)
        text = re.sub(r"^##\[\w+\]", "", text)
        if text.strip():
            kept.append(redact(text).replace("```", "'''"))

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
        # The PR feed owns thread lookup, keyed replies and the push check; reuse them.
        self.feed = pr_feed.Feed(slack, pr_channel, repo, github.get)

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
            return self.feed.can_push(pr["user"], pr)
        return (run.get("head_repository") or {}).get("full_name") == self.repo

    # --- where the run belongs -------------------------------------------------

    def find_pr(self, run: dict):
        if run["event"] not in PR_EVENTS:
            return None
        repo_id = (run.get("repository") or {}).get("id")
        # The list can include PRs in other repos (a fork's PR whose head is a branch
        # here); their numbers mean nothing in this repo.
        prs = [
            p
            for p in run.get("pull_requests") or []
            if ((p.get("base") or {}).get("repo") or {}).get("id") == repo_id
        ]
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
        ts = self._posted_ts(run, "failure")
        if ts:
            logger.info("Alert for run %s attempt %s already posted", run["id"], run["run_attempt"])
        else:
            job, step, tail = self._failed_step(run)
            ts = self.slack.post(
                self.actions_channel,
                alert_text(run, self.where(run, pr), job, step, tail),
                metadata=alert_metadata(self.repo, run["id"], run["run_attempt"], "failure"),
            )
        # Even when the alert already exists: a re-run must finish a thread reply that failed.
        alert = self.slack.permalink(self.actions_channel, ts)
        self._pr_note(
            pr,
            f"❌ {link(run['html_url'], run['name'])} failed · {link(alert, 'details')}",
            flux_suffix=f"CI failed ❌ ({link(alert, 'alert')})",
            key=_run_key(run, "failure"),
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
            self._pr_note(
                pr,
                f"✅ {link(run['html_url'], run['name'])} passed",
                flux_suffix=None,
                key=_run_key(run, "success"),
            )
            return
        if not self._posted_ts(run, "recovery"):
            self.slack.post(
                self.actions_channel,
                f"✅ {link(run['html_url'], run['name'])} is green again on {self.where(run, pr)}",
                metadata=alert_metadata(self.repo, run["id"], run["run_attempt"], "recovery"),
            )
        self._pr_note(
            pr,
            f"✅ {link(run['html_url'], run['name'])} green again",
            flux_suffix="",
            key=_run_key(run, "recovery"),
        )

    def _previous_failed(self, run: dict) -> bool:
        """Did the last finished run of this workflow on this branch fail?"""
        if run["run_attempt"] > 1:
            prev = self.gh.get(
                f"/repos/{self.repo}/actions/runs/{run['id']}/attempts/{run['run_attempt'] - 1}"
            ).get("conclusion")
            if prev in FAILED:
                return True
            if prev == "success":
                # Re-running a green run: any recovery was reported by the earlier attempt.
                return False
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

    def _posted_ts(self, run: dict, kind: str):
        """The ts of this run attempt's alert or recovery ping, if already posted."""
        oldest = pr_feed.epoch(run["run_started_at"]) - 60
        message = self.slack.find_message(
            self.actions_channel,
            ALERT_EVENT_TYPE,
            oldest,
            repo=self.repo,
            run_id=run["id"],
            run_attempt=run["run_attempt"],
            kind=kind,
        )
        return message["ts"] if message else None

    def _pr_note(self, pr, text: str, flux_suffix: str | None, key: str) -> None:
        """A reply in the PR's thread; for a Flux bump, set its one-liner's suffix instead.

        flux_suffix None leaves a Flux one-liner untouched. A merged or closed bump
        keeps its final state; CI results no longer change it.
        """
        if not pr or not self.pr_channel or pr.get("draft"):
            return
        parent = self.feed.find(pr)
        if not parent:
            return
        kind = ((parent.get("metadata") or {}).get("event_payload") or {}).get("kind")
        if kind != "flux":
            self.feed.reply_once(pr, parent, text, key)
            return
        state = pr_feed.pr_state(pr)
        if flux_suffix is None or state in ("merged", "closed"):
            return
        self.slack.update(
            self.pr_channel,
            parent["ts"],
            pr_feed.flux_text(pr, self.feed.bumps(pr), flux_suffix),
            metadata=pr_metadata(self.repo, pr["number"], "flux", state),
        )


def _run_key(run: dict, kind: str) -> str:
    return f"run:{run['id']}:{run['run_attempt']}:{kind}"


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
