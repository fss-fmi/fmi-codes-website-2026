"""Threaded PR feed for the #pr-updates Slack channel (issue #154).

Run by .github/workflows/slack-pr-feed.yaml on pull_request_target,
pull_request_review and issue_comment events. Reads the event from
GITHUB_EVENT_PATH and only calls the Slack and GitHub APIs; it never checks out
or runs PR code.

One parent message per ready PR, edited in place as its state changes; every
later event is a one-line reply in its thread, and each push lists its new
commits there (issue #171). Draft PRs post nothing until they are ready. Flux
image-bump PRs get a single one-liner, edited in place, no thread.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime

import slack_notify
from github_api import GitHub, can_push
from slack_notify import REPLY_EVENT_TYPE, escape, link, pr_metadata, reply_metadata

logger = logging.getLogger("pr_feed")

FLUX_BRANCH = "flux-image-updates"
# kustomization.yaml lines Flux rewrites: newTag: <tag> # {"$imagepolicy": "flux-system:<policy>:tag"}
TAG_LINE_RE = re.compile(
    r'^([+-])\s*newTag:\s*(\S+)\s*#\s*\{"\$imagepolicy":\s*"[^:"]+:([^:"]+):tag"\}'
)
TITLE_PAIR_RE = re.compile(r"(\S+) -> (\S+)")
CREATES_PARENT = {"opened", "ready_for_review", "reopened"}
TRANSITIONS = {"ready_for_review", "converted_to_draft", "closed", "reopened"}
STATUS_EMOJI = {"open": "🟢", "draft": "📝", "merged": "🟣", "closed": "🔴"}
COMMITS_SHOWN = 5
# GET /pulls/{n}/commits returns at most this many, oldest first.
MAX_PR_COMMITS = 250
SUBJECT_CHARS = 72


def epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def meta_payload(message: dict) -> dict:
    return (message.get("metadata") or {}).get("event_payload") or {}


def is_flux_bump(pr: dict, repo: str) -> bool:
    head_repo = (pr["head"].get("repo") or {}).get("full_name")
    return pr["head"]["ref"] == FLUX_BRANCH and head_repo == repo


def pr_state(pr: dict) -> str:
    if pr.get("merged"):
        return "merged"
    if pr["state"] == "closed":
        return "closed"
    return "draft" if pr.get("draft") else "open"


def transition_text(event: dict, pr: dict) -> str:
    action = event["action"]
    actor = escape(event["sender"]["login"])
    if action == "closed":
        if pr.get("merged"):
            by = escape((pr.get("merged_by") or event["sender"])["login"])
            return f"🟣 merged into `{escape(pr['base']['ref'])}` by {by}"
        return f"🔴 closed without merging by {actor}"
    if action == "converted_to_draft":
        return f"📝 converted to draft by {actor}; updates paused until it's ready"
    if action == "reopened":
        paused = " as a draft; updates paused until it's ready" if pr.get("draft") else ""
        return f"🟢 reopened by {actor}{paused}"
    return f"🟢 ready for review again ({actor})"


def parent_text(pr: dict, repo: str) -> str:
    status = STATUS_EMOJI[pr_state(pr)]
    head_repo = (pr["head"].get("repo") or {}).get("full_name")
    head = pr["head"]["ref"] if head_repo == repo else pr["head"]["label"]
    return (
        f"{status} *{link(pr['html_url'], pr['title'])}* · #{pr['number']}"
        f" · {escape(pr['user']['login'])} · `{escape(pr['base']['ref'])}` ← `{escape(head)}`"
    )


def subject(message: str) -> str:
    line = message.split("\n", 1)[0].strip()
    if len(line) > SUBJECT_CHARS:
        line = line[: SUBJECT_CHARS - 1].rstrip() + "…"
    return escape(line)


def changes_url(pr: dict, base: str, head: str) -> str:
    # The PR's own range view also works for commits that live in a fork.
    return f"{pr['html_url']}/files/{base}..{head}"


def push_text(pr: dict, pusher: str, commits: list[dict], base: str, head: str) -> str:
    """🔨 2 new commits by alice · view changes, then one line per commit, oldest first."""
    changes = changes_url(pr, base, head)
    noun = "commit" if len(commits) == 1 else "commits"
    lines = [f"🔨 {len(commits)} new {noun} by {escape(pusher)} · {link(changes, 'view changes')}"]
    for c in commits[:COMMITS_SHOWN]:
        url = f"{pr['html_url']}/commits/{c['sha']}"
        lines.append(f"• {link(url, c['sha'][:7])} {subject(c['commit']['message'])}")
    if len(commits) > COMMITS_SHOWN:
        lines.append(link(changes, f"+{len(commits) - COMMITS_SHOWN} more"))
    return "\n".join(lines)


def force_push_text(pr: dict, pusher: str, old: str, new: str) -> str:
    compare = f"{pr['html_url'].rsplit('/pull/', 1)[0]}/compare/{old}..{new}"
    return f"⚠️ force-pushed by {escape(pusher)} · {link(compare, f'{old[:7]} → {new[:7]}')}"


def bumps_from_files(files: list[dict]) -> list[tuple[str, str, str]]:
    """(image, old, new) for every image tag the PR's diff changes."""
    old, new = {}, {}
    for f in files:
        for line in (f.get("patch") or "").splitlines():
            m = TAG_LINE_RE.match(line)
            if m:
                sign, tag, policy = m.groups()
                (old if sign == "-" else new)[policy] = tag
    bumps = []
    for policy in sorted(new):
        image = policy.removesuffix("-staging").removesuffix("-prod")
        bumps.append((image, old.get(policy, "?"), new[policy]))
    return bumps


def flux_text(pr: dict, bumps: list[tuple[str, str, str]], suffix: str = "") -> str:
    """⬆️ fmi-codes-backend, fmi-codes-frontend bumped A → B · #152[ · suffix]"""
    groups: dict[tuple[str, str], list[str]] = {}
    for image, old, new in bumps:
        groups.setdefault((old, new), []).append(image)
    if not groups:
        # Fall back to the commit-message title: deploy: bump A -> B C -> D
        for old, new in dict.fromkeys(TITLE_PAIR_RE.findall(pr["title"])):
            groups[(old, new)] = ["staging images"]
    if groups:
        parts = [
            f"{', '.join(images)} bumped `{escape(old)}` → `{escape(new)}`"
            for (old, new), images in groups.items()
        ]
        body = "; ".join(parts)
    else:
        body = escape(pr["title"])
    line = f"⬆️ {body} · {link(pr['html_url'], '#' + str(pr['number']))}"
    return f"{line} · {suffix}" if suffix else line


def flux_suffix(pr: dict) -> str:
    if pr.get("merged"):
        return "merged ✅"
    if pr["state"] == "closed":
        return "closed without merging"
    return ""


class Feed:
    def __init__(self, slack, channel: str, repo: str, github=None):
        self.slack = slack
        self.channel = channel
        self.repo = repo
        self.github = github

    def oldest(self, pr: dict) -> float:
        # The parent never predates the PR; the margin absorbs clock skew between GitHub and Slack.
        return epoch(pr["created_at"]) - 60

    def find(self, pr: dict):
        return self.slack.find_pr_message(self.channel, self.repo, pr["number"], self.oldest(pr))

    def _post_parent(self, pr: dict, text: str, kind: str, head: str | None = None) -> None:
        self.slack.post_unique(
            self.channel,
            text,
            self._meta(pr, kind, head),
            self.oldest(pr),
            repo=self.repo,
            pr_number=pr["number"],
        )

    def _meta(self, pr: dict, kind: str, head: str | None = None) -> dict:
        return pr_metadata(self.repo, pr["number"], kind, state=pr_state(pr), head=head)

    def _reply(self, parent: dict, text: str, metadata=None) -> None:
        self.slack.post(self.channel, text, thread_ts=parent["ts"], metadata=metadata)

    def reply_once(self, pr: dict, parent: dict, text: str, key: str) -> None:
        """A thread reply keyed by what it reports; a re-run finds it and stays silent."""
        if self.slack.find_reply(
            self.channel,
            parent["ts"],
            REPLY_EVENT_TYPE,
            repo=self.repo,
            pr_number=pr["number"],
            key=key,
        ):
            return
        self.slack.post(
            self.channel,
            text,
            thread_ts=parent["ts"],
            metadata=reply_metadata(self.repo, pr["number"], key),
        )

    def _upsert_parent(self, pr: dict, parent) -> None:
        text = parent_text(pr, self.repo)
        if parent:
            # Keep the head the parent was posted at: this run is not ordered with
            # push runs, so writing the current head here could skip their commits.
            meta = self._meta(pr, "pr", meta_payload(parent).get("head"))
            self.slack.update(self.channel, parent["ts"], text, metadata=meta)
        else:
            self._post_parent(pr, text, "pr", pr["head"].get("sha"))

    def can_push(self, user: dict, pr: dict) -> bool:
        head_repo = (pr["head"].get("repo") or {}).get("full_name")
        return can_push(self.github, self.repo, user, head_repo)

    def handle(self, event_name: str, event: dict) -> None:
        if event_name == "issue_comment":
            comment = event["comment"]
            # Cheap checks first: most comments are discarded before any API call.
            if (
                event["action"] != "created"
                or "pull_request" not in event["issue"]
                or comment["user"].get("type") == "Bot"
                or not self.github
            ):
                return
            pr = self.github(f"/repos/{self.repo}/pulls/{event['issue']['number']}")
        else:
            pr = event["pull_request"]
        if not self.can_push(pr["user"], pr):
            logger.info(
                "#%s is by %s, who can't push here; not posted", pr["number"], pr["user"]["login"]
            )
            return
        if is_flux_bump(pr, self.repo):
            self._handle_flux(event_name, event, pr)
        elif event_name == "pull_request_review":
            self._handle_review(event, pr)
        elif event_name == "pull_request_target" and event["action"] == "synchronize":
            self._handle_push(event, pr)
        elif event_name == "pull_request_target":
            self._handle_pr(event, pr)
        elif event_name == "issue_comment":
            self._handle_comment(event, pr)

    def _handle_pr(self, event: dict, pr: dict) -> None:
        action = event["action"]
        if action not in CREATES_PARENT | TRANSITIONS | {"edited"}:
            return
        parent = self.find(pr)
        new = pr_state(pr)
        if not parent:
            if action in CREATES_PARENT and new == "open":
                self._upsert_parent(pr, None)
            return
        old = meta_payload(parent).get("state")
        renamed = action == "edited" and {"title", "base"} & set(event.get("changes") or {})
        if old != new or renamed:
            self._upsert_parent(pr, parent)
        # Replies only on a real state change, so re-runs and duplicate events stay silent.
        if action in TRANSITIONS and old != new:
            metadata = None
            head = pr["head"].get("sha")
            if new == "open" and head:
                # The next push lists commits from here on, not those pushed while
                # the PR was a draft or closed.
                metadata = reply_metadata(self.repo, pr["number"], f"state:open:{head}", head)
            self._reply(parent, transition_text(event, pr), metadata)

    def _handle_push(self, event: dict, pr: dict) -> None:
        """One reply per push listing its new commits, or saying it was a force push.

        Push runs for one PR queue in order (the workflow's concurrency group), but
        GitHub cancels all but the newest pending run. So each reply records the head
        it reached, and the next one lists every commit after it, covering any run
        that was cancelled.
        """
        if pr.get("draft") or pr["state"] != "open" or not self.github:
            return
        parent = self.find(pr)
        if not parent or meta_payload(parent).get("kind") != "pr":
            return
        after = event["after"]
        key = f"push:{after}"
        replies = self.slack.find_replies(
            self.channel, parent["ts"], REPLY_EVENT_TYPE, repo=self.repo, pr_number=pr["number"]
        )
        if any(meta_payload(r).get("key") == key for r in replies):
            return
        recorded = [meta_payload(parent).get("head")]
        recorded += [meta_payload(r).get("head") for r in replies]
        recorded = [h for h in recorded if h] or [event["before"]]

        commits = self.pr_commits(pr)
        shas = [c["sha"] for c in commits]
        pusher = event["sender"]["login"]
        metadata = reply_metadata(self.repo, pr["number"], key, after)
        if len(commits) >= MAX_PR_COMMITS and after not in shas:
            text = (
                f"🔨 new commits by {escape(pusher)}"
                f" · {link(changes_url(pr, recorded[-1], after), 'view changes')}"
                f" (over {MAX_PR_COMMITS} commits, not listed)"
            )
            self._reply(parent, text, metadata)
            return
        if after not in shas:
            logger.info("%s is no longer on #%s; a later push run covers it", after, pr["number"])
            return
        if recorded[-1] not in shas:
            self._reply(parent, force_push_text(pr, pusher, recorded[-1], after), metadata)
            return
        # The furthest recorded head, not the newest reply: a "ready again" reply can
        # land after a push reply that already went past it.
        base = max((h for h in recorded if h in shas), key=shas.index)
        new = commits[shas.index(base) + 1 : shas.index(after) + 1]
        if new:
            self._reply(parent, push_text(pr, pusher, new, base, after), metadata)

    def pr_commits(self, pr: dict) -> list[dict]:
        commits = []
        for page in range(1, MAX_PR_COMMITS // 100 + 2):
            batch = self.github(
                f"/repos/{self.repo}/pulls/{pr['number']}/commits", per_page=100, page=page
            )
            commits.extend(batch)
            if len(batch) < 100:
                break
        return commits

    def _handle_review(self, event: dict, pr: dict) -> None:
        if event["action"] != "submitted" or pr.get("draft"):
            return
        review = event["review"]
        if review["user"].get("type") == "Bot":
            return
        if not self.can_push(review["user"], pr):
            return
        state = review["state"].lower()
        reviewer = escape(review["user"]["login"])
        if state == "approved":
            text = f"✅ {link(review['html_url'], 'approved')} by {reviewer}"
        elif state == "changes_requested":
            text = f"🔁 {link(review['html_url'], 'changes requested')} by {reviewer}"
        elif state == "commented" and (review.get("body") or "").strip():
            # Each reply in an inline thread is its own "commented" review with an empty
            # body; only reviews with a summary are worth a line, or replies flood the thread.
            text = f"💬 {link(review['html_url'], 'review comments')} by {reviewer}"
        else:
            return
        parent = self.find(pr)
        if parent:
            self.reply_once(pr, parent, text, f"review:{review['id']}")

    def _handle_comment(self, event: dict, pr: dict) -> None:
        comment = event["comment"]
        if pr.get("draft") or not self.can_push(comment["user"], pr):
            return
        parent = self.find(pr)
        if parent:
            text = (
                f"💬 {link(comment['html_url'], 'comment')} by {escape(comment['user']['login'])}"
            )
            self.reply_once(pr, parent, text, f"comment:{comment['id']}")

    def _handle_flux(self, event_name: str, event: dict, pr: dict) -> None:
        if event_name != "pull_request_target" or pr.get("draft"):
            return
        if event["action"] not in (
            "opened",
            "reopened",
            "ready_for_review",
            "closed",
            "synchronize",
        ):
            return
        parent = self.find(pr)
        # synchronize: Flux pushed newer tags to the open bump PR; re-render them.
        if event["action"] in ("closed", "synchronize") and not parent:
            return
        text = flux_text(pr, self.bumps(pr), flux_suffix(pr))
        if parent:
            self.slack.update(self.channel, parent["ts"], text, metadata=self._meta(pr, "flux"))
        else:
            self._post_parent(pr, text, "flux")

    def bumps(self, pr: dict) -> list[tuple[str, str, str]]:
        if not self.github:
            return []
        try:
            return bumps_from_files(self.github(f"/repos/{self.repo}/pulls/{pr['number']}/files"))
        except Exception as e:
            logger.warning("Could not read the bump PR's files, using its title: %s", e)
            return []


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = os.environ.get("SLACK_PR_CHANNEL_ID", "")
    if not token or not channel:
        logger.info("SLACK_BOT_TOKEN or SLACK_PR_CHANNEL_ID not set; skipping")
        return 0
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    github = GitHub(gh_token).get if gh_token else None
    feed = Feed(slack_notify.Slack(token), channel, event["repository"]["full_name"], github)
    try:
        feed.handle(os.environ["GITHUB_EVENT_NAME"], event)
    except slack_notify.SlackError as e:
        logger.error("Slack call failed: %s", e)
        return 1
    except OSError as e:
        logger.error("GitHub call failed: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
