"""Flask-Limiter with a switch to its in-memory fallback that never answers 500 (#261).

Flask-Limiter 4.1 falls back only for the first request whose storage call fails. A
request whose call was already in flight fails after the switch and is re-raised (500),
any error at all (a key function's bug too) switches the worker, and its storage ping
right after a switch could put a failing Redis back in use. This class owns the request
check: only a Redis error switches, every request it hits reruns on memory, and the
worker waits out a hold after its last Redis error before it pings Redis again.

It reaches into Flask-Limiter's private methods, so requirements.txt pins the minor
version and tests/test_redis_outage.py checks their signatures. Only the request check
is covered: the rate-limit headers, the one other place Flask-Limiter switches on its own,
are off in this app, and it uses no conditional deductions (those 500 on a storage error).
"""

import threading
import time
from typing import override

import flask
from flask_limiter import Limiter, RateLimitExceeded
from limits import RateLimitItem
from limits.strategies import RateLimiter
from redis.exceptions import RedisError

from app.services import redis_client

# Every Redis error, data errors included: during a Sentinel failover the old master
# answers writes with READONLY, a ResponseError.
STORAGE_ERRORS = (RedisError, ConnectionError, TimeoutError)
UNREACHABLE = "Rate limit storage unreachable - falling back to in-memory storage"
# Which store this request was counted in, for the rest of the request: "memory" once it
# was counted there, "redis" while a check runs on Redis and after a refusal there.
_STORE = "fmi.rate_limit_store"

_now = time.monotonic


class FailOpenLimiter(Limiter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._local = threading.local()
        self._switch_lock = threading.Lock()
        self._hold_until = 0.0
        self._last_storage_error = float("-inf")
        self._pending_clears: set[tuple[RateLimitItem, tuple[str, ...]]] = set()

    @property
    @override
    def limiter(self) -> RateLimiter:
        store = flask.request.environ.get(_STORE) if flask.has_request_context() else None
        if store == "memory":
            return self._fallback_limiter
        if store == "redis":
            return self._limiter
        return super().limiter

    @override
    def _check_request_limit(
        self, callable_name: str | None = None, in_middleware: bool = True
    ) -> None:
        endpoint = self.identify_request()
        try:
            self._evaluate(endpoint, callable_name, in_middleware)
        except RateLimitExceeded:
            raise
        except Exception as e:
            if not (self._in_memory_fallback_enabled and isinstance(e, STORAGE_ERRORS)):
                if self._swallow_errors:
                    self.logger.exception("Failed to rate limit. Swallowing error")
                    return
                raise
            self._switch_to_memory()
            # Limits counted before the failure would otherwise be skipped as already seen.
            self.context.seen_limits.clear()
            flask.request.environ[_STORE] = "memory"
            self._evaluate(endpoint, callable_name, in_middleware)

    def clear_everywhere(self, item: RateLimitItem, *identifiers: str) -> None:
        """Clear a limit in memory and in Redis. On the fallback the Redis clear waits until
        the worker is back on Redis, so a hung Redis costs the request no wait."""
        if self._fallback_limiter is not None:
            self._fallback_limiter.clear(item, *identifiers)
        if self._storage_dead:
            with self._switch_lock:
                self._pending_clears.add((item, identifiers))
            return
        try:
            self._limiter.clear(item, *identifiers)
        except STORAGE_ERRORS:
            self._switch_to_memory()
            with self._switch_lock:
                self._pending_clears.add((item, identifiers))
            raise

    def _evaluate(self, endpoint: str, callable_name: str | None, in_middleware: bool) -> None:
        self._local.ping_started = None
        limits = self._Limiter__filter_limits(
            endpoint, flask.request.blueprint, callable_name, in_middleware
        )
        if self._local.ping_started is not None:
            self._after_ping(self._local.ping_started)

        environ = flask.request.environ
        if environ.get(_STORE) != "memory":
            on_memory = self._storage_dead and self._fallback_limiter is not None
            environ[_STORE] = "memory" if on_memory else "redis"
        try:
            self._Limiter__evaluate_limits(endpoint, limits)
        except RateLimitExceeded:
            raise
        except Exception:
            self._unpin_redis(environ)
            raise
        self._unpin_redis(environ)

    @staticmethod
    def _unpin_redis(environ: dict) -> None:
        # Only a refusal keeps Redis pinned (for the 429's Retry-After); a later check in
        # the same request goes wherever the worker is by then.
        if environ.get(_STORE) == "redis":
            del environ[_STORE]

    def _after_ping(self, started: float) -> None:
        """Flask-Limiter has just pinged. A Redis error that landed since the ping started
        means its answer is stale, even if Flask-Limiter has already switched back."""
        with self._switch_lock:
            if self._storage_dead:
                return
            if self._last_storage_error >= started:
                self.logger.warning(UNREACHABLE)
                self._storage_dead = True
                return
            pending, self._pending_clears = self._pending_clears, set()
        self._apply_pending_clears(list(pending))

    def _apply_pending_clears(self, pending: list) -> None:
        for done, (item, identifiers) in enumerate(pending):
            try:
                self._limiter.clear(item, *identifiers)
            except STORAGE_ERRORS:
                self._switch_to_memory()
                with self._switch_lock:
                    self._pending_clears.update(pending[done:])
                return

    def _switch_to_memory(self) -> None:
        # Read at call time: the e2e outage tests shorten the breaker's open time.
        with self._switch_lock:
            self._last_storage_error = _now()
            self._hold_until = self._last_storage_error + redis_client.BREAKER_OPEN_SECONDS
            if not self._storage_dead:
                self.logger.warning(UNREACHABLE)
                self._storage_dead = True

    @override
    def _Limiter__should_check_backend(self) -> bool:
        if _now() < self._hold_until:
            return False
        if Limiter._Limiter__should_check_backend(self):
            self._local.ping_started = _now()
            return True
        return False
