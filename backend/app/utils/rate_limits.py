"""Rate limits are written at prod's values and scaled by RATELIMIT_MULTIPLIER.

Staging sets the multiplier because every staging visitor arrives through the one
Tailscale proxy and shares each bucket. The limiter stays on there, so its Redis
wiring and the 429 path keep running before prod.

Each limit keys on what it protects (ADR-014): the account a login or reset names,
the signed-in user, and only otherwise the client address, which every device on a
shared network (the university's, during the event) has in common.
"""

import hashlib
import hmac
import os
from collections.abc import Callable

import jwt
from flask import Response, current_app, request
from flask_limiter.util import get_remote_address

_IDENTITY = "fmi.rate_limit_identity"


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


def per_identity(signed_in: str, anonymous: str) -> Callable[[], str]:
    """`signed_in` per user, `anonymous` per address, both scaled."""
    user_limit, address_limit = scaled(signed_in), scaled(anonymous)

    def current() -> str:
        return user_limit() if identity_key().startswith("user:") else address_limit()

    return current


def address_key() -> str:
    return f"ip:{get_remote_address()}"


def identity_key() -> str:
    """The user of a validly signed token, otherwise the client address."""
    if _IDENTITY not in request.environ:
        request.environ[_IDENTITY] = _signed_in_user() or address_key()
    return request.environ[_IDENTITY]


def _signed_in_user() -> str | None:
    from app.services.auth_service import decode_token
    from app.utils.auth_decorators import extract_token

    token = extract_token()
    if not token:
        return None
    # Signature and expiry only: a revoked token still belongs to its owner, and minting one
    # needs the secret, so skipping the blocklist and epoch lookups costs nothing here.
    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        return None
    role, user_id = payload.get("role"), payload.get("user_id")
    if role is None or user_id is None:
        return None
    return f"user:{role}:{user_id}"


def account_key() -> str:
    """The account a login or reset request names, otherwise the client address.

    Keyed by an HMAC of role and email so Redis never holds the address and a list of known
    addresses can't be hashed to find one.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return address_key()
    email, role = data.get("email"), data.get("role")
    if not isinstance(email, str) or not email.strip():
        return address_key()
    if not isinstance(role, str) or not role.strip():
        role = "participant"
    message = f"{role.strip().lower()}:{email.strip().lower()}".encode()
    secret = current_app.config["SECRET_KEY"].encode()
    return f"account:{hmac.new(secret, message, hashlib.sha256).hexdigest()[:32]}"


def failed_login(response: Response) -> bool:
    return response.status_code == 401
