"""Slack Web API helper for the GitHub Actions notification workflows.

Stdlib only, so a workflow runs it with the runner's python3 and installs nothing.
Messages that belong to a pull request carry Slack message metadata
(event_type github_pr, payload {repo, pr_number, kind, state, head}); that is how a
later run finds the PR's parent message again without any other storage. CI
alerts carry github_ci_alert {repo, run_id, run_attempt, kind} the same way, so
a duplicate event never posts the same alert twice.
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("slack_notify")

API = "https://slack.com/api/"
PR_EVENT_TYPE = "github_pr"
ALERT_EVENT_TYPE = "github_ci_alert"
REPLY_EVENT_TYPE = "github_pr_reply"
# conversations.history pages scanned before giving up; 200 messages per page.
MAX_HISTORY_PAGES = 10
MAX_RETRIES = 3
MAX_RETRY_AFTER = 30


class SlackError(Exception):
    pass


def escape(text: str) -> str:
    # Slack reads <...> as links/mentions and & as an entity; PR titles can contain all three.
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def link(url: str, label: str) -> str:
    return f"<{url}|{escape(label)}>"


def pr_metadata(repo: str, pr_number: int, kind: str, state: str, head: str | None = None) -> dict:
    """kind is "pr" (threaded parent) or "flux" (one-liner); state is the PR's last posted state.

    *head* is the PR's head commit when the parent was first posted: the PR feed's
    first push reply lists the commits after it.
    """
    payload = {"repo": repo, "pr_number": pr_number, "kind": kind, "state": state}
    if head:
        payload["head"] = head
    return {"event_type": PR_EVENT_TYPE, "event_payload": payload}


def alert_metadata(repo: str, run_id: int, run_attempt: int, kind: str) -> dict:
    """kind is "failure" or "recovery"."""
    return {
        "event_type": ALERT_EVENT_TYPE,
        "event_payload": {
            "repo": repo,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "kind": kind,
        },
    }


def reply_metadata(repo: str, pr_number: int, key: str, head: str | None = None) -> dict:
    """*key* names what the thread reply reports (a review, a comment, a run result, a push).

    *head* marks the PR head commit the thread has caught up to; the next push
    reply lists the commits after the newest one.
    """
    payload = {"repo": repo, "pr_number": pr_number, "key": key}
    if head:
        payload["head"] = head
    return {"event_type": REPLY_EVENT_TYPE, "event_payload": payload}


def _retry_after(value) -> int:
    try:
        return max(1, min(int(value), MAX_RETRY_AFTER))
    except (TypeError, ValueError):
        return 1


def _form_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict | list):
        return json.dumps(value)
    return str(value)


class Slack:
    def __init__(self, token: str, opener=urllib.request.urlopen, sleep=time.sleep):
        self._token = token
        self._open = opener
        self._sleep = sleep

    def call(self, method: str, **params) -> dict:
        """POST a Web API method and return its JSON body. Raises SlackError unless ok."""
        # Form-encoded, not JSON: Slack accepts JSON bodies only on write methods.
        body = urllib.parse.urlencode(
            {k: _form_value(v) for k, v in params.items() if v is not None}
        ).encode("utf-8")
        for attempt in range(MAX_RETRIES + 1):
            req = urllib.request.Request(
                API + method,
                data=body,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            try:
                with self._open(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < MAX_RETRIES:
                    wait = _retry_after(e.headers.get("Retry-After"))
                    logger.info("Slack rate limit on %s, retrying in %ss", method, wait)
                    self._sleep(wait)
                    continue
                raise SlackError(f"{method}: HTTP {e.code}") from None
            except urllib.error.URLError as e:
                raise SlackError(f"{method}: {e.reason}") from None
            if not data.get("ok"):
                raise SlackError(f"{method}: {data.get('error', 'unknown error')}")
            return data
        raise SlackError(f"{method}: still rate limited after {MAX_RETRIES} retries")

    def post(self, channel: str, text: str, thread_ts: str | None = None, metadata=None) -> str:
        """Post a message (a thread reply when thread_ts is given) and return its ts."""
        data = self.call(
            "chat.postMessage",
            channel=channel,
            text=text,
            thread_ts=thread_ts,
            metadata=metadata,
            unfurl_links=False,
            unfurl_media=False,
        )
        return data["ts"]

    def update(self, channel: str, ts: str, text: str, metadata=None) -> None:
        self.call("chat.update", channel=channel, ts=ts, text=text, metadata=metadata)

    def delete(self, channel: str, ts: str) -> None:
        self.call("chat.delete", channel=channel, ts=ts)

    def permalink(self, channel: str, ts: str) -> str:
        return self.call("chat.getPermalink", channel=channel, message_ts=ts)["permalink"]

    def find_pr_message(self, channel: str, repo: str, pr_number: int, oldest: float = 0):
        """The channel message tagged with this PR's metadata, or None.

        *oldest* (epoch seconds) bounds the scan; pass the PR's creation time.
        """
        return self.find_message(channel, PR_EVENT_TYPE, oldest, repo=repo, pr_number=pr_number)

    def find_message(self, channel: str, event_type: str, oldest: float = 0, **match):
        """The newest channel message whose metadata has *event_type* and every *match* value."""
        return next(
            self._matches("conversations.history", channel, event_type, oldest, match), None
        )

    def find_reply(self, channel: str, thread_ts: str, event_type: str, **match):
        """The reply in *thread_ts* whose metadata has *event_type* and every *match* value."""
        return next(
            self._matches("conversations.replies", channel, event_type, 0, match, ts=thread_ts),
            None,
        )

    def find_replies(self, channel: str, thread_ts: str, event_type: str, **match) -> list:
        """Every reply in *thread_ts* whose metadata matches, oldest first."""
        return list(
            self._matches("conversations.replies", channel, event_type, 0, match, ts=thread_ts)
        )

    def post_unique(self, channel: str, text: str, metadata: dict, oldest: float, **match) -> str:
        """Post a top-level message that must exist once, and return the surviving ts.

        Find-then-post is not atomic: two runs for the same event can both find
        nothing and both post. Each run checks again afterwards and the newer
        message deletes itself, so exactly one survives without dropping events.
        """
        ts = self.post(channel, text, metadata=metadata)
        found = list(
            self._matches("conversations.history", channel, metadata["event_type"], oldest, match)
        )
        first = min((m["ts"] for m in found), key=float, default=ts)
        if float(first) < float(ts):
            logger.info("Another run posted this message first; deleting the duplicate")
            self.delete(channel, ts)
            return first
        return ts

    def _matches(self, method: str, channel: str, event_type: str, oldest: float, match, **extra):
        cursor = None
        for _ in range(MAX_HISTORY_PAGES):
            data = self.call(
                method,
                channel=channel,
                oldest=f"{oldest:.6f}",
                limit=200,
                include_all_metadata=True,
                cursor=cursor,
                **extra,
            )
            for message in data.get("messages", []):
                meta = message.get("metadata") or {}
                payload = meta.get("event_payload") or {}
                if meta.get("event_type") == event_type and all(
                    str(payload.get(k)) == str(v) for k, v in match.items()
                ):
                    yield message
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return
        logger.warning("Stopped after %d %s pages looking for %s", MAX_HISTORY_PAGES, method, match)
