"""Bug report service — fire-and-forget Discord webhook delivery.

Uses only stdlib (urllib) so no extra dependencies are required.
A bounded ThreadPoolExecutor absorbs bursts of concurrent submissions
(500+ simultaneous reports) without blocking the request thread.
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


def _truncate(text: str, limit: int = _FIELD_LIMIT) -> str:
    """Trim a string to Discord's field-value character limit."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


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

    role_emoji = {"participant": "👤", "mentor": "🧑‍💼", "admin": "🔑"}.get(reporter_role, "❓")

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

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            # Discord/Cloudflare rejects Python-urllib's default UA (CF error 1010).
            # Identify ourselves as a Discord-compatible bot client.
            "User-Agent": "DiscordBot (https://fmicodes.bg, 1.0)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
        if status in (200, 204):
            logger.info(
                "Discord bug report sent (reporter=%s, page=%s)", reporter_email, page_url
            )
            return True
        logger.error("Discord webhook returned unexpected status %s", status)
        return False
    except urllib.error.HTTPError as e:
        logger.error("Discord webhook HTTP error %s: %s", e.code, e.reason)
        return False
    except Exception as e:
        logger.error("Failed to send Discord bug report (reporter=%s): %s", reporter_email, e)
        return False


def submit_bug_report_async(
    webhook_url: str,
    reporter_name: str,
    reporter_email: str,
    reporter_role: str,
    page_url: str,
    what_did: str,
    what_happened: str,
) -> None:
    """Queue a Discord bug report for fire-and-forget delivery.

    Returns immediately; the webhook POST runs in the background thread pool.
    """
    _executor.submit(
        send_discord_bug_report,
        webhook_url,
        reporter_name,
        reporter_email,
        reporter_role,
        page_url,
        what_did,
        what_happened,
    )
