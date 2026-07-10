"""JWT token revocation blocklist backed by Redis.

H1: Stores revoked jti values so stolen tokens can't be replayed even if
    they haven't expired yet.  The TTL on each entry equals the remaining
    lifetime of the original token — Redis cleans them up automatically.

The Redis connection is provided by the centralized redis_client module, which
selects Sentinel mode (REDIS_SENTINELS + REDIS_MASTER_NAME) or single-instance
mode (REDIS_URL) purely from config — this module no longer owns its own
connection.

When Redis is not configured the module degrades gracefully:
  - revoke_token() logs a warning and does nothing.
  - is_revoked()   always returns False (fail-open).

This means token revocation is effectively disabled in dev/local environments
that don't run Redis.  Ensure Redis is configured in production.
"""

import logging

from app.services.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_KEY_PREFIX = "jti:blocked:"


def revoke_token(jti: str, ttl_seconds: int) -> None:
    """Mark *jti* as revoked for *ttl_seconds*.

    After the TTL expires Redis removes the key automatically, which aligns
    with the token's own expiry so storage never grows unboundedly.
    """
    if not jti or ttl_seconds <= 0:
        return

    client = get_redis_client()
    if client is None:
        logger.warning(
            "REDIS not configured — token jti=%s NOT revoked (configure Redis in production)",
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

    client = get_redis_client()
    if client is None:
        return False

    try:
        return bool(client.exists(f"{_KEY_PREFIX}{jti}"))
    except Exception as exc:
        logger.warning(
            "SECURITY: blocklist unavailable — token revocation bypassed (jti=%s): %s", jti, exc
        )
        return False  # Fail open
