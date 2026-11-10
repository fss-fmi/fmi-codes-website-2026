"""Rate limits are written at prod's values and scaled by RATELIMIT_MULTIPLIER.

Staging sets the multiplier because every anonymous staging visitor arrives through
the one Tailscale proxy and shares each address bucket. The limiter stays on there,
so its Redis wiring and the 429 path keep running before prod.

Each limit keys on what it protects (ADR-014): the account a login or reset names,
the signed-in user and only otherwise the client address, which every device on a
shared network (the university's, during the event) has in common.
"""

import hashlib
import hmac
import logging
import os
from collections.abc import Callable

import jwt
from flask import current_app, request
from flask_limiter.util import get_remote_address
from limits import parse

logger = logging.getLogger(__name__)

_IDENTITY = "fmi.rate_limit_identity"
LOGIN_ACCOUNT_LIMIT = "15 per minute"


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
        return user_limit() if is_signed_in() else address_limit()

    return current


def address_key() -> str:
    return f"ip:{get_remote_address()}"


def identity_key() -> str:
    """The user of a validly signed token, otherwise the client address."""
    if _IDENTITY not in request.environ:
        request.environ[_IDENTITY] = _signed_in_user() or address_key()
    return request.environ[_IDENTITY]


def is_signed_in() -> bool:
    return identity_key().startswith("user:")


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


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _role(default: str | None) -> str | None:
    role = _body().get("role")
    if isinstance(role, str) and role.strip():
        return role.strip().lower()
    return default


def _account_key(role: str | None) -> str:
    """HMAC of role and email, so Redis never holds the address and a list of known
    addresses can't be hashed to find one. No usable email or role means the address."""
    email = _body().get("email")
    if role not in ("participant", "mentor", "admin") or not isinstance(email, str):
        return address_key()
    email = email.strip().lower()
    if not email:
        return address_key()
    message = f"{role}:{email}".encode()
    secret = current_app.config["SECRET_KEY"].encode()
    return f"account:{hmac.new(secret, message, hashlib.sha256).hexdigest()[:32]}"


def login_account_key() -> str:
    """The account a login names; login treats a missing role as participant."""
    return _account_key(_role("participant"))


def reset_account_key() -> str:
    """The account a reset names. Reset rejects a missing or admin role with a 400, so
    those requests count against the address, never against someone's account."""
    role = _role(None)
    return _account_key(role if role in ("participant", "mentor") else None)


def forget_login_attempts() -> None:
    """Clear the account's attempts after a successful login.

    Every attempt is counted when it arrives, not after its response, so parallel wrong
    passwords can't all pass the check before any is counted. Clearing on success keeps the
    owner from being blocked by their own earlier typos.
    """
    from app import limiter

    item = parse(scaled(LOGIN_ACCOUNT_LIMIT)())
    try:
        limiter.limiter.clear(item, login_account_key(), request.endpoint)
    except Exception as e:
        logger.warning("Could not clear failed logins: %s", e)
