"""Slack Web API helper for the GitHub Actions notification workflows.

Stdlib only, so a workflow runs it with the runner's python3 and installs nothing.
Messages that belong to a pull request carry Slack message metadata
(event_type github_pr, payload {repo, pr_number, kind, state}); that is how a
later run finds the PR's parent message again without any other storage.
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


def pr_metadata(repo: str, pr_number: int, kind: str, state: str) -> dict:
    """kind is "pr" (threaded parent) or "flux" (one-liner); state is the PR's last posted state."""
    return {
        "event_type": PR_EVENT_TYPE,
        "event_payload": {"repo": repo, "pr_number": pr_number, "kind": kind, "state": state},
    }


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
                    wait = min(int(e.headers.get("Retry-After", "1")), MAX_RETRY_AFTER)
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

    def find_pr_message(self, channel: str, repo: str, pr_number: int, oldest: float = 0):
        """The channel message tagged with this PR's metadata, or None.

        *oldest* (epoch seconds) bounds the scan; pass the PR's creation time.
        """
        cursor = None
        for _ in range(MAX_HISTORY_PAGES):
            data = self.call(
                "conversations.history",
                channel=channel,
                oldest=f"{oldest:.6f}",
                limit=200,
                include_all_metadata=True,
                cursor=cursor,
            )
            for message in data.get("messages", []):
                meta = message.get("metadata") or {}
                payload = meta.get("event_payload") or {}
                if (
                    meta.get("event_type") == PR_EVENT_TYPE
                    and payload.get("repo") == repo
                    and str(payload.get("pr_number")) == str(pr_number)
                ):
                    return message
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return None
        logger.warning(
            "No parent for %s#%s in %d history pages", repo, pr_number, MAX_HISTORY_PAGES
        )
        return None
