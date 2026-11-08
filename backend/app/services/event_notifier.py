"""Event feed: posts event notices to the Slack incoming webhook in SLACK_EVENTS_WEBHOOK_URL.

Each environment's webhook points at its own channel (#event-feed-prod,
#event-feed-staging). Posts run in a bounded thread pool so the request that
triggered the event is never delayed or failed by Slack. Without the webhook
the notice is only logged.

*text* is Slack mrkdwn and goes out as is: callers escape anything a user typed.
"""

import json
import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from flask import current_app

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="event-notifier")


def _post(webhook_url: str, text: str) -> bool:
    """POST *text* to the webhook. Returns True on success; never raises."""
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
        if status in (200, 204):
            return True
        logger.error("Event feed webhook returned unexpected status %s", status)
        return False
    except urllib.error.HTTPError as e:
        logger.error("Event feed webhook HTTP error %s: %s", e.code, e.reason)
        return False
    except Exception as e:
        logger.error("Failed to post to the event feed: %s", e)
        return False


def notify(text: str) -> None:
    """Queue *text* for the event feed and return immediately. Needs an app context."""
    webhook_url = current_app.config.get("SLACK_EVENTS_WEBHOOK_URL", "")
    if not webhook_url:
        logger.info("SLACK_EVENTS_WEBHOOK_URL not set, event not posted: %s", text)
        return
    _executor.submit(_post, webhook_url, text)
