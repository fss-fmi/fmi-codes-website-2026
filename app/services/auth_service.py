"""Authentication service — JWT token management and password hashing"""
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from flask import current_app

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(password: str, hash_value: str) -> bool:
    """Verify a password against its bcrypt hash"""
    return bcrypt.checkpw(password.encode(), hash_value.encode())


def generate_token(user_id: int, role: str) -> str:
    """Generate a JWT access token.

    Args:
        user_id: The participant or mentor id.
        role: 'participant', 'mentor', or 'admin'.

    Returns:
        Encoded JWT string.
    """
    expiry_days = current_app.config.get('JWT_EXPIRY_DAYS', 3)
    payload = {
        'user_id': user_id,
        'role': role,
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(days=expiry_days),
    }
    secret = current_app.config['JWT_SECRET_KEY']
    return jwt.encode(payload, secret, algorithm='HS256')


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Returns:
        Decoded payload dict with 'user_id' and 'role'.

    Raises:
        jwt.ExpiredSignatureError: If token expired.
        jwt.InvalidTokenError: If token is invalid.
    """
    secret = current_app.config['JWT_SECRET_KEY']
    return jwt.decode(token, secret, algorithms=['HS256'])
