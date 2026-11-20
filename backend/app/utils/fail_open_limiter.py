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
from collections.abc import Iterator
from contextlib import contextmanager
from typing import override

import flask
from flask_limiter import Limiter, RateLimitExceeded
from limits.strategies import RateLimiter
from redis.exceptions import RedisError

from app.services import redis_client

STORAGE_ERRORS = (RedisError, ConnectionError, TimeoutError)

_now = time.monotonic


class FailOpenLimiter(Limiter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._local = threading.local()
        self._switch_lock = threading.Lock()
        self._hold_until = 0.0

    @property
    def limiter(self) -> RateLimiter:
        # A rerun must not reach Redis even when another thread's ping puts it back in use.
        if getattr(self._local, "memory_only", False):
            return self._fallback_limiter
        return super().limiter

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
            with self._memory_only():
                self._evaluate(endpoint, callable_name, in_middleware)

    def _evaluate(self, endpoint: str, callable_name: str | None, in_middleware: bool) -> None:
        limits = self._Limiter__filter_limits(
            endpoint, flask.request.blueprint, callable_name, in_middleware
        )
        self._Limiter__evaluate_limits(endpoint, limits)

    def _switch_to_memory(self) -> None:
        # Read at call time: the e2e outage tests shorten the breaker's open time.
        with self._switch_lock:
            self._hold_until = _now() + redis_client.BREAKER_OPEN_SECONDS
            if not self._storage_dead:
                self.logger.warning(
                    "Rate limit storage unreachable - falling back to in-memory storage"
                )
                self._storage_dead = True

    @contextmanager
    def _memory_only(self) -> Iterator[None]:
        previous = getattr(self._local, "memory_only", False)
        self._local.memory_only = True
        try:
            yield
        finally:
            self._local.memory_only = previous

    @override
    def _Limiter__should_check_backend(self) -> bool:
        if _now() < self._hold_until:
            return False
        return Limiter._Limiter__should_check_backend(self)
