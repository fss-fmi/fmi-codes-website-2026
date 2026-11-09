"""Rate limits are written at prod's values and scaled by RATELIMIT_MULTIPLIER.

Staging sets the multiplier because every staging visitor arrives through the one
Tailscale proxy and shares each bucket. The limiter stays on there, so its Redis
wiring and the 429 path keep running before prod.
"""

import os
from collections.abc import Callable

from flask import current_app


def multiplier_from_env() -> int:
    raw = (os.environ.get("RATELIMIT_MULTIPLIER") or "1").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        # Refuse to boot: a 0 would turn every limit into "0 per minute" and a typo must not
        # quietly change prod's limits.
        raise ValueError(f"RATELIMIT_MULTIPLIER must be a positive whole number, got {raw!r}")
    return value


def scaled(limit: str) -> Callable[[], str]:
    """`limit` like "10 per minute"; Flask-Limiter calls the result on every request."""
    count, _, period = limit.partition(" ")
    base = int(count)

    def current() -> str:
        return f"{base * current_app.config['RATELIMIT_MULTIPLIER']} {period}"

    return current
