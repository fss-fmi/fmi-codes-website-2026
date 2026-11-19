"""Centralized Redis connection + fail-open access helpers.

This module is the single source of truth for how the app talks to Redis. It
supports two connection modes selected purely by config/env, with NO call-site
differences between them:

  - Sentinel mode:  REDIS_SENTINELS ("host:port,host2:port2,...") + REDIS_MASTER_NAME
                    → redis.sentinel.Sentinel(...).master_for(name, ...)
                    This is the HA shape production (k8s + Helm-managed Sentinel)
                    uses. The client re-resolves the master after a failover.
  - Single mode:    REDIS_URL → redis.from_url(...)
                    The simple single-instance shape for local/everyday dev.
  - Disabled:       neither set → get_redis_client() returns None, callers fall
                    back to Postgres/file.

A Redis outage may only turn off what Redis provides, never slow down or break a
request (#256). Every request-path use goes through the helpers below, which share
one circuit breaker per process: the first connection error or timeout marks Redis
down for BREAKER_OPEN_SECONDS, during which every helper returns its fallback without
touching the network. After that one call tries Redis again and closes the breaker
when it answers. The client is built without contacting Redis, so a process that
starts while Redis is away picks it up as soon as it answers.
"""

import logging
import os
import random as _random
import threading
import time
from collections.abc import Callable
from urllib.parse import quote, urlparse, urlunparse

from redis.backoff import NoBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.retry import Retry

import redis

logger = logging.getLogger(__name__)

# In-cluster Redis answers in well under a millisecond, and the limiter and the
# caches sit on every request's path, so a stalled Redis must cost little.
_DEFAULT_SOCKET_TIMEOUT = 0.5
_DEFAULT_CONNECT_TIMEOUT = 0.5
BREAKER_OPEN_SECONDS = 5.0

_DOWN_ERRORS = (RedisConnectionError, RedisTimeoutError, OSError)

_lock = threading.Lock()
_client = None
_target = None
_built = False
_state = "unknown"  # "up" once Redis answered, "down" while the breaker is open
_down_until = 0.0
_probing = False
_now = time.monotonic


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


def _timeout_env(name: str, default: float) -> float:
    """A positive number of seconds from env; blank or invalid means the default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if not value > 0:
        logger.warning("Invalid %s=%r, using the default %s", name, raw, default)
        return default
    return value


def _timeouts() -> tuple[float, float]:
    return (
        _timeout_env("REDIS_SOCKET_TIMEOUT", _DEFAULT_SOCKET_TIMEOUT),
        _timeout_env("REDIS_CONNECT_TIMEOUT", _DEFAULT_CONNECT_TIMEOUT),
    )


def _retry_policy() -> Retry:
    """One immediate retry when an open connection drops (a pooled socket Redis closed, a
    failover), none on a timeout: a second wait on a stalled Redis only doubles the cost."""
    return Retry(NoBackoff(), 1, supported_errors=(RedisConnectionError,))


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


def _sentinel_config() -> tuple[list[tuple[str, int]], str] | None:
    """(hosts, master name) when Sentinel mode is configured, else None."""
    sentinels_raw = os.environ.get("REDIS_SENTINELS", "").strip()
    master_name = os.environ.get("REDIS_MASTER_NAME", "").strip()
    if not (sentinels_raw and master_name):
        return None
    hosts = _parse_sentinels(sentinels_raw)
    if not hosts:
        logger.warning("REDIS_SENTINELS=%r parsed to zero valid hosts", sentinels_raw)
        return None
    return hosts, master_name


def _build_client():
    """(client, what it points at) from env config, or (None, None) if Redis is not
    configured.

    Nothing here talks to Redis, so a build never waits on or fails from an outage.
    Sentinel mode takes precedence over REDIS_URL when both are set.
    """
    socket_timeout, connect_timeout = _timeouts()
    redis_password = os.environ.get("REDIS_PASSWORD", "").strip() or None
    common_kwargs = {
        "socket_timeout": socket_timeout,
        "socket_connect_timeout": connect_timeout,
        "retry": _retry_policy(),
        "decode_responses": True,
    }
    if redis_password:
        common_kwargs["password"] = redis_password

    sentinel = _sentinel_config()
    if sentinel:
        from redis.sentinel import Sentinel

        hosts, master_name = sentinel
        # The sentinel-query connections need their own timeouts and, when the deployment
        # password-protects the sentinels (Bitnami does with auth.enabled=true), the password.
        sentinel_kwargs = {
            "socket_timeout": socket_timeout,
            "socket_connect_timeout": connect_timeout,
            "retry": _retry_policy(),
        }
        if redis_password:
            sentinel_kwargs["password"] = redis_password
        client = Sentinel(hosts, sentinel_kwargs=sentinel_kwargs).master_for(
            master_name, **common_kwargs
        )
        return client, f"Sentinel master {master_name}"

    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        return redis.from_url(redis_url, **common_kwargs), _redact_url(redis_url)

    return None, None


def get_redis_client():
    """Return the shared Redis client, or None if Redis is not configured.

    The client is built once per process. A build that raises (a malformed URL) is
    retried behind the breaker instead of turning Redis off for the process's life.
    The raw client bypasses the breaker: request paths use the helpers below.
    """
    global _client, _target, _built
    if _built:
        return _client
    with _lock:
        if not _built:
            try:
                _client, _target = _build_client()
            except Exception as exc:
                _trip_locked(exc)
                return None
            _built = True
    return _client


def reset_client():
    """Forget the client and the breaker state; the next call rebuilds the client.

    Used by tests that swap REDIS_URL between cases.
    """
    global _client, _target, _built, _state, _down_until, _probing
    with _lock:
        _client = None
        _target = None
        _built = False
        _state = "unknown"
        _down_until = 0.0
        _probing = False


def _trip_locked(exc: BaseException) -> None:
    global _state, _down_until
    _down_until = _now() + BREAKER_OPEN_SECONDS
    if _state != "down":
        logger.warning(
            "Redis unreachable, so caching and token revocation are off in this process; "
            "trying again every %ss: %s",
            BREAKER_OPEN_SECONDS,
            exc,
        )
    _state = "down"


def _acquire():
    """(client, whether this call is the probe), or (None, False) when the call must use
    its fallback right away."""
    global _probing
    if _state == "up":
        return get_redis_client(), False
    with _lock:
        probe = _state == "down"
        if probe:
            if _now() < _down_until or _probing:
                return None, False
            _probing = True
    client = get_redis_client()
    if client is None:
        _release(probe)
    return client, probe


def _succeeded(probe: bool) -> None:
    global _state, _down_until, _probing
    if _state == "up" and not probe:
        return
    with _lock:
        if _state == "down":
            logger.warning("Redis reachable again; caching and token revocation are back on")
        elif _state == "unknown":
            logger.info("✓ Redis connected (%s)", _target)
        _state = "up"
        _down_until = 0.0
        if probe:
            _probing = False


def _failed(exc: BaseException, probe: bool) -> None:
    global _probing
    with _lock:
        _trip_locked(exc)
        if probe:
            _probing = False


def _release(probe: bool) -> None:
    global _probing
    if probe:
        with _lock:
            _probing = False


def _run(what: str, command: Callable, fallback):
    """*command*(client) through the breaker, or *fallback* when Redis is not configured,
    down or the command fails. Never raises."""
    client, probe = _acquire()
    if client is None:
        return fallback
    try:
        result = command(client)
    except _DOWN_ERRORS as exc:
        _failed(exc, probe)
        return fallback
    except Exception as exc:
        _release(probe)
        logger.warning("Redis %s failed, falling back: %s", what, exc)
        return fallback
    _succeeded(probe)
    return result


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
    """Fail-open GET. Returns the string value, or *default* on a miss or any error."""
    value = _run(f"GET {key}", lambda c: c.get(key), None)
    return value if value is not None else default


def redis_set(key: str, value: str, ttl: int | None = None) -> bool:
    """Fail-open SET (with optional TTL in seconds). Returns True on success."""

    def command(client):
        if ttl is not None and ttl > 0:
            client.setex(key, ttl, value)
        else:
            client.set(key, value)
        return True

    return _run(f"SET {key}", command, False)


def redis_del(*keys: str) -> bool:
    """Fail-open DEL. Returns True if the delete command was issued successfully.

    Used for cache invalidation. A failure here means a stale key may linger
    until its TTL expires.
    """
    if not keys:
        return False

    def command(client):
        client.delete(*keys)
        return True

    return _run(f"DEL {keys}", command, False)


def redis_incr(key: str) -> bool:
    """Fail-open INCR. Returns True if the increment was issued successfully.

    Used to bump a cache version key; a failure leaves the old version in use
    until its entries expire.
    """

    def command(client):
        client.incr(key)
        return True

    return _run(f"INCR {key}", command, False)


def redis_exists(key: str) -> bool:
    """Fail-open EXISTS: False on a miss or any error."""
    return _run(f"EXISTS {key}", lambda c: bool(c.exists(key)), False)


def redis_status() -> str:
    """Redis's state for the readiness report: disabled, ok or down."""
    if get_redis_client() is None and _state != "down":
        return "disabled"
    return "ok" if _run("PING", lambda c: bool(c.ping()), False) else "down"


def build_limiter_storage_uri() -> str:
    """Build the Flask-Limiter storage_uri from the same Redis config.

    The `limits` library (Flask-Limiter's backend) natively understands the
    `redis+sentinel://:password@host:port,host2:port2/master_name` scheme. It
    threads the userinfo password into BOTH the sentinel-query connections and
    the data-node connections, so a password-protected Sentinel deployment
    authenticates correctly. Returns "memory://" when Redis is disabled so local
    dev without Redis still rate-limits per-process.
    """
    redis_password = os.environ.get("REDIS_PASSWORD", "").strip() or None

    sentinel = _sentinel_config()
    if sentinel:
        hosts, master_name = sentinel
        host_list = ",".join(f"{h}:{p}" for h, p in hosts)
        userinfo = f":{quote(redis_password, safe='')}@" if redis_password else ""
        return f"redis+sentinel://{userinfo}{host_list}/{master_name}"

    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        return redis_url

    return "memory://"


def build_limiter_storage_options() -> dict:
    """Timeouts and retry policy for the limiter's Redis connections.

    Without them redis-py waits on a stalled Redis forever, and the limiter's in-memory
    fallback never starts, since only an error starts it. Sentinel mode needs them twice:
    on the data connections and on the sentinel-query connections.
    """
    if build_limiter_storage_uri() == "memory://":
        return {}
    socket_timeout, connect_timeout = _timeouts()
    options = {
        "socket_timeout": socket_timeout,
        "socket_connect_timeout": connect_timeout,
        "retry": _retry_policy(),
    }
    if _sentinel_config():
        options["sentinel_kwargs"] = dict(options, retry=_retry_policy())
    return options
