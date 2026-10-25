"""Bug report service — fire-and-forget delivery to Discord and Slack webhooks.

Uses only stdlib (urllib) so no extra dependencies are required.
A bounded ThreadPoolExecutor absorbs bursts of concurrent submissions
(500+ simultaneous reports) without blocking the request thread.
Each configured webhook gets its own job, so one failing never affects the other.
"""

import json
import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# 20 workers per gunicorn worker process.
# The executor's internal queue is unbounded, so all 500 submissions
# queued simultaneously are accepted immediately and drained in order.
_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="bug-report-worker")

# Discord embed colour — pink (#F472B6)
_EMBED_COLOR = 0xF472B6

# Discord field value limit
_FIELD_LIMIT = 1024

# Slack Block Kit limits: 2000 chars per section field, 3000 per section text.
_SLACK_FIELD_LIMIT = 1000
_SLACK_TEXT_LIMIT = 2900

_ROLE_EMOJI = {"participant": "👤", "mentor": "🧑‍💼", "admin": "🔑"}


def _truncate(text: str, limit: int = _FIELD_LIMIT) -> str:
    """Trim a string to Discord's field-value character limit."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _slack_text(text: str, limit: int = _SLACK_FIELD_LIMIT) -> str:
    """Escape *text* for Slack mrkdwn and trim the escaped result to *limit* chars.

    Reports can be anonymous, and Slack reads <...> as links and mentions, so an
    unescaped "<!channel>" would ping the whole channel.
    """
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if len(escaped) <= limit:
        return escaped
    cut = escaped[: limit - 3]
    # After escaping every "&" starts an entity; drop one that the cut split.
    amp = cut.rfind("&")
    if amp != -1 and ";" not in cut[amp:]:
        cut = cut[:amp]
    return cut + "..."


def _post_webhook(
    service: str,
    webhook_url: str,
    payload: dict,
    headers: dict,
    reporter_email: str,
    page_url: str,
) -> bool:
    """POST *payload* as JSON. Returns True on success, False on any failure (never raises)."""
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
        if status in (200, 204):
            logger.info(
                "%s bug report sent (reporter=%s, page=%s)", service, reporter_email, page_url
            )
            return True
        logger.error("%s webhook returned unexpected status %s", service, status)
        return False
    except urllib.error.HTTPError as e:
        logger.error("%s webhook HTTP error %s: %s", service, e.code, e.reason)
        return False
    except Exception as e:
        logger.error("Failed to send %s bug report (reporter=%s): %s", service, reporter_email, e)
        return False


def send_discord_bug_report(
    webhook_url: str,
    reporter_name: str,
    reporter_email: str,
    reporter_role: str,
    page_url: str,
    what_did: str,
    what_happened: str,
) -> bool:
    """POST a rich Discord embed to *webhook_url*.

    Returns True on success, False on any failure (never raises).
    """
    if not webhook_url:
        logger.warning("DISCORD_BUG_WEBHOOK_URL is not configured — cannot send bug report")
        return False

    role_emoji = _ROLE_EMOJI.get(reporter_role, "❓")

    payload = {
        "username": "Bug Report Halka",
        "embeds": [
            {
                "title": "🐛 New Bug Report",
                "color": _EMBED_COLOR,
                "fields": [
                    {
                        "name": "Reporter",
                        "value": _truncate(reporter_name),
                        "inline": True,
                    },
                    {
                        "name": "Role",
                        "value": f"{role_emoji} {_truncate(reporter_role)}",
                        "inline": True,
                    },
                    {
                        "name": "Email",
                        "value": _truncate(reporter_email),
                        "inline": False,
                    },
                    {
                        "name": "Page",
                        "value": f"`{_truncate(page_url, 512)}`",
                        "inline": False,
                    },
                    {
                        "name": "What they were doing",
                        "value": _truncate(what_did),
                        "inline": False,
                    },
                    {
                        "name": "What went wrong",
                        "value": _truncate(what_happened),
                        "inline": False,
                    },
                ],
                "footer": {"text": "FMI Codes 2026 — Bug Report System"},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ],
    }

    return _post_webhook(
        "Discord",
        webhook_url,
        payload,
        # Discord/Cloudflare rejects Python-urllib's default UA (CF error 1010).
        # Identify ourselves as a Discord-compatible bot client.
        {"User-Agent": "DiscordBot (https://fmicodes.bg, 1.0)"},
        reporter_email,
        page_url,
    )


def send_slack_bug_report(
    webhook_url: str,
    reporter_name: str,
    reporter_email: str,
    reporter_role: str,
    page_url: str,
    what_did: str,
    what_happened: str,
) -> bool:
    """POST a Block Kit message to the Slack incoming webhook *webhook_url*.

    Returns True on success, False on any failure (never raises).
    """
    if not webhook_url:
        logger.warning("SLACK_BUG_WEBHOOK_URL is not configured — cannot send bug report")
        return False

    role_emoji = _ROLE_EMOJI.get(reporter_role, "❓")

    payload = {
        # Shown in notifications and by clients that can't render blocks.
        "text": f"🐛 New bug report from {_slack_text(reporter_name, 200)}",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🐛 New Bug Report"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Reporter*\n{_slack_text(reporter_name)}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Role*\n{role_emoji} {_slack_text(reporter_role)}",
                    },
                    {"type": "mrkdwn", "text": f"*Email*\n{_slack_text(reporter_email)}"},
                    {"type": "mrkdwn", "text": f"*Page*\n`{_slack_text(page_url, 512)}`"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*What they were doing*\n{_slack_text(what_did, _SLACK_TEXT_LIMIT)}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*What went wrong*\n{_slack_text(what_happened, _SLACK_TEXT_LIMIT)}",
                },
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "FMI Codes 2026 — Bug Report System"}],
            },
        ],
    }

    return _post_webhook("Slack", webhook_url, payload, {}, reporter_email, page_url)


def submit_bug_report_async(
    discord_webhook_url: str,
    slack_webhook_url: str,
    reporter_name: str,
    reporter_email: str,
    reporter_role: str,
    page_url: str,
    what_did: str,
    what_happened: str,
) -> None:
    """Queue the report for every configured webhook, fire-and-forget.

    Returns immediately; each webhook POST runs in the background thread pool.
    """
    report = (reporter_name, reporter_email, reporter_role, page_url, what_did, what_happened)

    if not discord_webhook_url and not slack_webhook_url:
        logger.warning(
            "No bug-report webhook configured (DISCORD_BUG_WEBHOOK_URL, SLACK_BUG_WEBHOOK_URL) "
            "— report dropped"
        )
        return
    if discord_webhook_url:
        _executor.submit(send_discord_bug_report, discord_webhook_url, *report)
    if slack_webhook_url:
        _executor.submit(send_slack_bug_report, slack_webhook_url, *report)
