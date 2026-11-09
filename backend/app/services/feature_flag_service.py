"""Feature flags in the feature_flags table, switched or scheduled from Mission Control.

A scheduled change needs no scheduler: the first read after its time applies
it. The apply locks the due rows (SELECT ... FOR UPDATE), so when several
workers read at once only the first gets the rows back and posts the notice;
the others wait for its commit, re-check, and find nothing due.

Reads are cached in Redis for a few seconds under a versioned key, and every
write bumps the version after commit. A reader that loaded the old value just
before a write can then only refill the old key, which nobody reads any more;
deleting a single key would let it put the old value back. While a schedule is
pending the TTL never outlives it, so a cached value can't hide a change that
has come due.
"""

import json
import logging
from datetime import datetime

from flask import current_app

from app.database import execute_query, get_db_cursor
from app.services import event_notifier
from app.services.redis_client import redis_get, redis_incr, redis_set

logger = logging.getLogger(__name__)

FLAG_NAMES = ("registration_open", "rankings_live", "mentors_stay_tuned")

_LABELS = {
    "registration_open": "Participant registration",
    "rankings_live": "Live rankings",
    "mentors_stay_tuned": 'Mentors "coming soon" placeholder',
}

_CACHE_VERSION_KEY = "cache:feature_flags:version"
_CACHE_TTL = 10

_SELECT_ROWS = """
    SELECT name, enabled, scheduled_value, scheduled_at, updated_at, NOW() AS now
    FROM feature_flags
"""


def _read_rows() -> list[dict]:
    return [dict(r) for r in execute_query(current_app, _SELECT_ROWS, fetch_all=True) or []]


def _cache_key() -> str:
    return f"cache:feature_flags:v{redis_get(_CACHE_VERSION_KEY, '0')}"


def invalidate_cache() -> None:
    """Point every reader at a fresh cache key. Call after a committed write."""
    redis_incr(_CACHE_VERSION_KEY)


def _any_due(rows: list[dict]) -> bool:
    return any(r["scheduled_at"] is not None and r["scheduled_at"] <= r["now"] for r in rows)


def _slack_time(at: datetime) -> str:
    """Slack date token: each reader sees the time in their own timezone."""
    return f"<!date^{int(at.timestamp())}^{{date_short_pretty}} at {{time}}|{at.isoformat()}>"


def _on_off(value: bool) -> str:
    return "ON" if value else "OFF"


def _announce(name: str, old: bool, new: bool, scheduled_at: datetime | None) -> None:
    how = f"scheduled for {_slack_time(scheduled_at)}" if scheduled_at else "switched by the admin"
    logger.info(
        "Feature flag %s changed %s -> %s (%s)",
        name,
        _on_off(old),
        _on_off(new),
        f"scheduled for {scheduled_at.isoformat()}" if scheduled_at else "manual",
    )
    event_notifier.notify(f"🚦 *{_LABELS[name]}*: {_on_off(old)} → *{_on_off(new)}* ({how})")


def _apply_due() -> None:
    """Apply every schedule whose time has passed, posting one notice per change."""
    changes = []
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT name, enabled, scheduled_value, scheduled_at
            FROM feature_flags
            WHERE scheduled_at <= NOW()
            FOR UPDATE
            """
        )
        due = cursor.fetchall()
        for row in due:
            new = row["scheduled_value"]
            if new != row["enabled"]:
                cursor.execute(
                    """
                    UPDATE feature_flags
                    SET enabled = %s, scheduled_value = NULL, scheduled_at = NULL,
                        updated_at = NOW()
                    WHERE name = %s
                    """,
                    (new, row["name"]),
                )
                changes.append((row["name"], row["enabled"], new, row["scheduled_at"]))
            else:
                # A manual switch already set this value: clear the schedule quietly.
                cursor.execute(
                    "UPDATE feature_flags SET scheduled_value = NULL, scheduled_at = NULL"
                    " WHERE name = %s",
                    (row["name"],),
                )
    if not due:
        return
    invalidate_cache()
    for change in changes:
        _announce(*change)


def _load() -> tuple[dict[str, bool], int]:
    """Read the flags from the DB, applying due schedules. Returns (flags, cache TTL)."""
    rows = _read_rows()
    if _any_due(rows):
        _apply_due()
        rows = _read_rows()

    flags = dict.fromkeys(FLAG_NAMES, False)
    ttl = _CACHE_TTL
    for r in rows:
        if r["name"] in flags:
            flags[r["name"]] = bool(r["enabled"])
        if r["scheduled_at"] is not None:
            ttl = min(ttl, int((r["scheduled_at"] - r["now"]).total_seconds()))
    return flags, ttl


def get_flags() -> dict[str, bool]:
    """Effective value of every flag. Raises if the DB can't be read."""
    # The key is fixed before the DB read, so a write during the read retires it.
    key = _cache_key()
    cached = redis_get(key)
    if cached is not None:
        try:
            flags = json.loads(cached)
            if isinstance(flags, dict) and set(flags) == set(FLAG_NAMES):
                return flags
        except (ValueError, TypeError):
            pass  # corrupt cache entry: reload

    flags, ttl = _load()
    if ttl > 0:
        redis_set(key, json.dumps(flags), ttl)
    return flags


def is_enabled(name: str) -> bool:
    return get_flags()[name]


def list_flags() -> list[dict]:
    """Every flag with its value, last change and pending schedule, for the admin."""
    rows = _read_rows()
    if _any_due(rows):
        _apply_due()
        rows = _read_rows()
    by_name = {r["name"]: r for r in rows}
    result = []
    for name in FLAG_NAMES:
        r = by_name.get(name)
        if r is None:
            continue
        result.append(
            {
                "name": name,
                "enabled": bool(r["enabled"]),
                "updated_at": r["updated_at"].isoformat(),
                "scheduled_value": r["scheduled_value"],
                "scheduled_at": r["scheduled_at"].isoformat() if r["scheduled_at"] else None,
            }
        )
    return result


def set_flag(name: str, enabled: bool) -> bool:
    """Switch *name* to *enabled* now. Returns True if the value changed.

    A pending schedule is kept: if it later sets the same value, it is
    cleared without a notice.
    """
    _apply_due()
    with get_db_cursor() as cursor:
        cursor.execute("SELECT enabled FROM feature_flags WHERE name = %s FOR UPDATE", (name,))
        row = cursor.fetchone()
        if row is None:
            raise LookupError(name)
        old = row["enabled"]
        if old == enabled:
            return False
        cursor.execute(
            "UPDATE feature_flags SET enabled = %s, updated_at = NOW() WHERE name = %s",
            (enabled, name),
        )
    invalidate_cache()
    _announce(name, old, enabled, None)
    return True


def schedule_flag(name: str, value: bool, at: datetime) -> str | None:
    """Schedule *name* to become *value* at *at* (timezone-aware).

    Replaces any pending schedule. Returns an error message for the admin, or
    None on success. The server's clock (Postgres NOW()) decides what is past.
    """
    _apply_due()
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT enabled, %s::timestamptz <= NOW() AS is_past,"
            " scheduled_at IS NOT NULL AS has_schedule"
            " FROM feature_flags WHERE name = %s FOR UPDATE",
            (at, name),
        )
        row = cursor.fetchone()
        if row is None:
            raise LookupError(name)
        if row["is_past"]:
            return "Scheduled time must be in the future"
        if row["enabled"] == value:
            message = f"The flag is already {_on_off(value).lower()}"
            if row["has_schedule"]:
                message += "; cancel the pending schedule to keep it that way"
            return message
        cursor.execute(
            "UPDATE feature_flags SET scheduled_value = %s, scheduled_at = %s WHERE name = %s",
            (value, at, name),
        )
    invalidate_cache()
    return None


def cancel_schedule(name: str) -> bool:
    """Drop the pending schedule of *name*. Returns True if there was one."""
    _apply_due()
    with get_db_cursor() as cursor:
        cursor.execute(
            "UPDATE feature_flags SET scheduled_value = NULL, scheduled_at = NULL"
            " WHERE name = %s AND scheduled_at IS NOT NULL RETURNING name",
            (name,),
        )
        cancelled = cursor.fetchone() is not None
        if not cancelled:
            cursor.execute("SELECT 1 FROM feature_flags WHERE name = %s", (name,))
            if cursor.fetchone() is None:
                raise LookupError(name)
    invalidate_cache()
    return cancelled
