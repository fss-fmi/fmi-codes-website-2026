"""Centralized Redis connection + fail-open access helpers.

This module is the single source of truth for how the app talks to Redis. It
supports two connection modes selected purely by config/env, with NO call-site
differences between them:

  - Sentinel mode:  REDIS_SENTINELS ("host:port,host2:port2,...") + REDIS_MASTER_NAME
                    → redis.sentinel.Sentinel(...).master_for(name, ...)
                    This is the HA shape production (k8s + Helm-managed Sentinel)
                    will use. Switching to a Helm-managed Sentinel later is an
                    env-var change only — no code changes here.
  - Single mode:    REDIS_URL → redis.from_url(...)
                    The simple single-instance shape for local/everyday dev.
  - Disabled:       neither set → get_redis_client() returns None, callers fall
                    back to Postgres/file (same graceful degradation as before).

Timeouts, retry-on-timeout, and decode_responses are centralized here so every
Redis consumer (blocklist, caches, epoch check) shares identical, well-behaved
connection settings.

All application read/write paths MUST go through the fail-open helpers
(redis_get / redis_set / redis_del) rather than the raw client, so a Redis
outage degrades to a logged warning and a DB/file fallback — never a 500.
"""

import logging
import os
import random as _random
import threading
from urllib.parse import quote, urlparse, urlunparse

logger = logging.getLogger(__name__)

# Defaults (seconds) — overridable via config/env. Kept short so a Redis blip
# fails fast into the fallback path rather than stalling a request.
_DEFAULT_SOCKET_TIMEOUT = 2
_DEFAULT_CONNECT_TIMEOUT = 2

_client = None
_client_initialized = False
_client_lock = threading.Lock()


def _redact_url(url: str) -> str:
    """Return the URL with the password replaced by *** for safe logging."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            userinfo = f"{parsed.username}:***" if parsed.username else ":***"
            host = parsed.hostname or ""
            if parsed.port:
                host += f":{parsed.port}"
            netloc = f"{userinfo}@{host}"
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        pass
    return url


def _int_env(name: str, default: int) -> int:
    """Read an int from env, tolerating blank/garbage values by using the default."""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r — using default %d", name, raw, default)
        return default


def _parse_sentinels(raw: str) -> list[tuple[str, int]]:
    """Parse "host:port,host2:port2" into [(host, port), ...].

    Entries without an explicit port default to 26379 (the Sentinel default).
    Blank/malformed entries are skipped with a warning rather than crashing
    connection setup.
    """
    pairs: list[tuple[str, int]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        host, _, port = entry.partition(":")
        host = host.strip()
        if not host:
            continue
        try:
            port_num = int(port) if port else 26379
        except (TypeError, ValueError):
            logger.warning("Skipping malformed sentinel entry %r", entry)
            continue
        pairs.append((host, port_num))
    return pairs


def _build_client():
    """Construct a redis client from env config, or None if Redis is disabled.

    Sentinel mode takes precedence over REDIS_URL when both are set, so a
    deployment that provides Sentinel config gets HA discovery even if a legacy
    REDIS_URL is still floating around in the environment.
    """
    try:
        from redis.sentinel import Sentinel  # type: ignore[import]

        import redis  # type: ignore[import]
    except Exception as exc:  # pragma: no cover - redis is a hard dependency
        logger.error("redis-py import failed — Redis disabled: %s", exc)
        return None

    socket_timeout = _int_env("REDIS_SOCKET_TIMEOUT", _DEFAULT_SOCKET_TIMEOUT)
    connect_timeout = _int_env("REDIS_CONNECT_TIMEOUT", _DEFAULT_CONNECT_TIMEOUT)
    redis_password = os.environ.get("REDIS_PASSWORD", "").strip() or None

    common_kwargs = {
        "socket_timeout": socket_timeout,
        "socket_connect_timeout": connect_timeout,
        "retry_on_timeout": True,
        "decode_responses": True,
    }
    if redis_password:
        common_kwargs["password"] = redis_password

    sentinels_raw = os.environ.get("REDIS_SENTINELS", "").strip()
    master_name = os.environ.get("REDIS_MASTER_NAME", "").strip()

    if sentinels_raw and master_name:
        sentinel_hosts = _parse_sentinels(sentinels_raw)
        if not sentinel_hosts:
            logger.error(
                "REDIS_SENTINELS=%r parsed to zero valid hosts — Redis disabled", sentinels_raw
            )
            return None
        try:
            # The Sentinel object needs its own connect timeout so a dead
            # sentinel node doesn't hang master discovery. When the deployment
            # password-protects the sentinels themselves (Bitnami does when
            # auth.enabled=true), the sentinel-query connections need the
            # password too — that goes via sentinel_kwargs, separate from the
            # data-node password threaded through common_kwargs below.
            sentinel_kwargs = {
                "socket_timeout": socket_timeout,
                "socket_connect_timeout": connect_timeout,
            }
            if redis_password:
                sentinel_kwargs["password"] = redis_password
            sentinel = Sentinel(sentinel_hosts, sentinel_kwargs=sentinel_kwargs)
            # master_for returns a client that re-resolves the current master
            # via the sentinels on each use, so a failover promotion is picked
            # up automatically without a cached IP / app restart.
            client = sentinel.master_for(master_name, **common_kwargs)
            client.ping()  # Fail fast if discovery is misconfigured
            logger.info(
                "✓ Redis connected via Sentinel (master=%s, sentinels=%s)",
                master_name,
                sentinels_raw,
            )
            return client
        except Exception as exc:
            logger.error("Redis Sentinel connection failed — Redis disabled: %s", exc)
            return None

    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        try:
            client = redis.from_url(redis_url, **common_kwargs)
            client.ping()  # Fail fast if the URL is wrong
            logger.info("✓ Redis connected (%s)", _redact_url(redis_url))
            return client
        except Exception as exc:
            logger.error("Redis connection failed — Redis disabled: %s", exc)
            return None

    return None


def get_redis_client():
    """Return the shared Redis client, or None if Redis is disabled/unreachable.

    Lazy singleton with double-checked locking so concurrent threads under a
    threaded Gunicorn worker don't race on initialization.
    The Sentinel-backed client re-resolves the master on each command, so reuse
    does NOT pin us to a stale master after a failover.
    """
    global _client, _client_initialized
    if _client_initialized:
        return _client
    with _client_lock:
        if not _client_initialized:
            _client = _build_client()
            _client_initialized = True
    return _client


def reset_client():
    """Drop the cached client so the next get_redis_client() rebuilds it.

    Used by tests that swap REDIS_URL between cases; not needed in production
    since the Sentinel client already handles failover internally.
    """
    global _client, _client_initialized
    _client = None
    _client_initialized = False


def jittered_ttl(base_seconds: int, jitter_seconds: int) -> int:
    """Return base_seconds ± up to jitter_seconds (never below 1).

    Spreads key expiry across workers/pods so they don't all miss the cache and
    hit the DB in the same instant (cache stampede).
    """
    if jitter_seconds <= 0:
        return max(1, base_seconds)
    offset = _random.randint(-jitter_seconds, jitter_seconds)
    return max(1, base_seconds + offset)


def redis_get(key: str, default=None):
    """Fail-open GET. Returns the string value, or *default* on miss/any error.

    Never raises — a Redis outage yields *default* (treated as a cache miss by
    callers) plus a logged warning, so route handlers keep working off the DB.
    """
    client = get_redis_client()
    if client is None:
        return default
    try:
        value = client.get(key)
        return value if value is not None else default
    except Exception as exc:
        logger.warning("Redis GET %s failed — falling back: %s", key, exc)
        return default


def redis_set(key: str, value: str, ttl: int | None = None) -> bool:
    """Fail-open SET (with optional TTL in seconds). Returns True on success.

    No-ops and returns False (with a logged warning) on any error, so a write
    to the cache can never break the write path it decorates.
    """
    client = get_redis_client()
    if client is None:
        return False
    try:
        if ttl is not None and ttl > 0:
            client.setex(key, ttl, value)
        else:
            client.set(key, value)
        return True
    except Exception as exc:
        logger.warning("Redis SET %s failed — ignoring: %s", key, exc)
        return False


def redis_del(*keys: str) -> bool:
    """Fail-open DEL. Returns True if the delete command was issued successfully.

    Used for cache invalidation. A failure here means a stale key may linger
    until its TTL expires — logged, but never fatal.
    """
    if not keys:
        return False
    client = get_redis_client()
    if client is None:
        return False
    try:
        client.delete(*keys)
        return True
    except Exception as exc:
        logger.warning("Redis DEL %s failed — ignoring: %s", keys, exc)
        return False


def build_limiter_storage_uri() -> str:
    """Build the Flask-Limiter storage_uri from the same Redis config.

    The `limits` library (Flask-Limiter's backend) natively understands the
    `redis+sentinel://:password@host:port,host2:port2/master_name` scheme. It
    threads the userinfo password into BOTH the sentinel-query connections and
    the data-node connections, so a password-protected Sentinel deployment
    authenticates correctly. Returns "memory://" when Redis is disabled so local
    dev without Redis still rate-limits per-process (unchanged from prior
    behaviour).
    """
    sentinels_raw = os.environ.get("REDIS_SENTINELS", "").strip()
    master_name = os.environ.get("REDIS_MASTER_NAME", "").strip()
    redis_password = os.environ.get("REDIS_PASSWORD", "").strip() or None

    if sentinels_raw and master_name:
        hosts = _parse_sentinels(sentinels_raw)
        if hosts:
            host_list = ",".join(f"{h}:{p}" for h, p in hosts)
            userinfo = f":{quote(redis_password, safe='')}@" if redis_password else ""
            return f"redis+sentinel://{userinfo}{host_list}/{master_name}"
        logger.warning(
            "REDIS_SENTINELS=%r parsed to zero valid hosts — limiter falling back", sentinels_raw
        )

    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        return redis_url

    return "memory://"
