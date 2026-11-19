"""JWT token revocation blocklist backed by Redis.

H1: Stores revoked jti values so stolen tokens can't be replayed even if
    they haven't expired yet.  The TTL on each entry equals the remaining
    lifetime of the original token — Redis cleans them up automatically.

Every call goes through the fail-open helpers in redis_client, so a Redis
outage never waits on Redis longer than its breaker allows (#256):
  - revoke_token() logs a warning and does nothing.
  - is_revoked()   returns False (fail-open).

This means token revocation is off while Redis is down or not configured.
Ensure Redis is configured in production.
"""

import logging

from app.services.redis_client import redis_exists, redis_set

logger = logging.getLogger(__name__)

_KEY_PREFIX = "jti:blocked:"


def revoke_token(jti: str, ttl_seconds: int) -> None:
    """Mark *jti* as revoked for *ttl_seconds*.

    After the TTL expires Redis removes the key automatically, which aligns
    with the token's own expiry so storage never grows unboundedly.
    """
    if not jti or ttl_seconds <= 0:
        return
    if not redis_set(f"{_KEY_PREFIX}{jti}", "1", ttl=ttl_seconds):
        logger.warning("Token jti=%s NOT revoked: Redis is down or not configured", jti)


def is_revoked(jti: str) -> bool:
    """Return True if *jti* is in the revocation blocklist.

    Fails open (returns False) if Redis is unavailable so a Redis outage
    doesn't lock all users out.
    """
    if not jti:
        return False
    return redis_exists(f"{_KEY_PREFIX}{jti}")
