"""JWT token revocation blocklist backed by Redis.

H1: Stores revoked jti values so stolen tokens can't be replayed even if
    they haven't expired yet.  The TTL on each entry equals the remaining
    lifetime of the original token — Redis cleans them up automatically.

When REDIS_URL is not configured the module degrades gracefully:
  - revoke_token() logs a warning and does nothing.
  - is_revoked()   always returns False (fail-open).

This means token revocation is effectively disabled in dev/local environments
that don't run Redis.  Ensure REDIS_URL is set in production.
"""

import logging
import os

logger = logging.getLogger(__name__)

_KEY_PREFIX = "jti:blocked:"
_client = None


def _get_client():
    """Lazily create and return the Redis client.  Returns None if REDIS_URL is unset."""
    global _client
    if _client is not None:
        return _client

    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return None

    try:
        import redis  # type: ignore[import]

        _client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        _client.ping()  # Fail fast if the URL is wrong
        logger.info("✓ Redis token blocklist connected (%s)", redis_url.split("@")[-1])
    except Exception as exc:
        logger.error("Redis blocklist unavailable — token revocation disabled: %s", exc)
        _client = None

    return _client


def revoke_token(jti: str, ttl_seconds: int) -> None:
    """Mark *jti* as revoked for *ttl_seconds*.

    After the TTL expires Redis removes the key automatically, which aligns
    with the token's own expiry so storage never grows unboundedly.
    """
    if not jti or ttl_seconds <= 0:
        return

    client = _get_client()
    if client is None:
        logger.warning(
            "REDIS_URL not configured — token jti=%s NOT revoked (set REDIS_URL in production)",
            jti,
        )
        return

    try:
        client.setex(f"{_KEY_PREFIX}{jti}", ttl_seconds, "1")
    except Exception as exc:
        logger.error("Failed to revoke token jti=%s: %s", jti, exc)


def is_revoked(jti: str) -> bool:
    """Return True if *jti* is in the revocation blocklist.

    Fails open (returns False) if Redis is unavailable so a Redis outage
    doesn't lock all users out.
    """
    if not jti:
        return False

    client = _get_client()
    if client is None:
        return False

    try:
        return bool(client.exists(f"{_KEY_PREFIX}{jti}"))
    except Exception as exc:
        logger.error("Failed to check blocklist for jti=%s: %s", jti, exc)
        return False  # Fail open
