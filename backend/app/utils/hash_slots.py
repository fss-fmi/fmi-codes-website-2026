"""Caps the password hashes a pod runs at once and sheds the rest (#269, ADR-016).

A pod has HASH_SLOTS hash slots, its CPU limit in whole cores (the Deployment sets it through
the downward API), shared by all its Gunicorn workers as lock files. A hash takes a free slot.
If none is free it needs one of the waiting slots (two per hash slot) to wait up to
WAIT_SECONDS for one; with no waiting slot free it is shed at once. A shed raises
HashSlotsFullError, which the app answers with 429 and Retry-After before the route has
written anything, so the client can send the same request again.

Every attempt opens its file itself: flock locks belong to the open file, so two threads of
one worker exclude each other (fcntl and lockf locks belong to the process and would not),
and the kernel drops the lock when its holder dies, so a worker Gunicorn kills mid-hash
can't keep its slot. Without HASH_SLOTS (local dev, tests) nothing is capped.
"""

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import NoReturn

from prometheus_client import Counter

try:
    import fcntl
except ImportError:
    fcntl = None

SLOTS_DIR = "/tmp/hash-slots"
WAITING_PER_SLOT = 2
WAIT_SECONDS = 2.0
POLL_SECONDS = 0.025
RETRY_AFTER_SECONDS = 2
_REASONS = ("waiting_room_full", "wait_timeout")

SHED = Counter(
    "password_hash_shed",
    "Password hashes refused with a 429 because every hash slot in the pod was busy",
    ["reason"],
)
for _reason in _REASONS:
    SHED.labels(reason=_reason)


class HashSlotsFullError(Exception):
    """Every hash slot stayed busy, so the request is answered 429 without running."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def configured_slots() -> int:
    raw = (os.environ.get("HASH_SLOTS") or "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        # A typo must not quietly lift the cap, or set it to nothing.
        raise ValueError(f"HASH_SLOTS must be a positive whole number, got {raw!r}")
    return value


def check_config() -> int:
    """The slot count, or 0 for no cap; raises at boot on a value the cap can't run with."""
    slots = configured_slots()
    if slots and fcntl is None:
        raise RuntimeError("HASH_SLOTS needs flock, which this platform doesn't have")
    return slots


def _take(kind: str, count: int) -> int | None:
    """A file descriptor holding one free `kind` slot, or None when all `count` are taken."""
    for index in range(count):
        fd = os.open(os.path.join(SLOTS_DIR, f"{kind}-{index}"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            continue
        except BaseException:
            os.close(fd)
            raise
        return fd
    return None


def _shed(reason: str) -> NoReturn:
    SHED.labels(reason=reason).inc()
    raise HashSlotsFullError(reason)


def _wait_for_slot(slots: int) -> int:
    waiting = _take("wait", slots * WAITING_PER_SLOT)
    if waiting is None:
        _shed("waiting_room_full")
    try:
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            # Before the first sleep too: a slot may have freed while this took its waiting slot.
            held = _take("hash", slots)
            if held is not None:
                return held
            if time.monotonic() >= deadline:
                break
            time.sleep(POLL_SECONDS)
    finally:
        os.close(waiting)
    _shed("wait_timeout")


@contextmanager
def hash_slot() -> Iterator[None]:
    """Holds one of the pod's hash slots for the duration of a bcrypt call."""
    slots = configured_slots()
    if not slots:
        yield
        return
    os.makedirs(SLOTS_DIR, exist_ok=True)
    held = _take("hash", slots)
    if held is None:
        held = _wait_for_slot(slots)
    try:
        yield
    finally:
        os.close(held)
