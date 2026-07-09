"""Unit tests for app.services.auth_service.

Covers:
- bcrypt password hashing and verification
- JWT token generation and decoding
- Expired / tampered token rejection
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import app.services.auth_service as auth_service

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_returns_string(self):
        hashed = auth_service.hash_password("hunter2")
        assert isinstance(hashed, str)

    def test_hash_is_bcrypt_prefixed(self):
        hashed = auth_service.hash_password("hunter2")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_hash_differs_from_plaintext(self):
        pw = "supersecret"
        assert auth_service.hash_password(pw) != pw

    def test_two_hashes_of_same_password_differ(self):
        """bcrypt uses a random salt, so hashes should not collide."""
        pw = "samepassword"
        assert auth_service.hash_password(pw) != auth_service.hash_password(pw)


class TestPasswordVerification:
    def test_correct_password_verifies(self):
        pw = "correcthorsebatterystaple"
        hashed = auth_service.hash_password(pw)
        assert auth_service.verify_password(pw, hashed) is True

    def test_wrong_password_fails(self):
        hashed = auth_service.hash_password("realpassword")
        assert auth_service.verify_password("wrongpassword", hashed) is False

    def test_empty_password_fails_against_non_empty_hash(self):
        hashed = auth_service.hash_password("notempty")
        assert auth_service.verify_password("", hashed) is False


# ---------------------------------------------------------------------------
# JWT generation and decoding  (requires Flask app context)
# ---------------------------------------------------------------------------

class TestJWTGeneration:
    def test_generate_token_returns_string(self, app_ctx):
        token = auth_service.generate_token(42, "participant")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_correct_user_id(self, app_ctx):
        token = auth_service.generate_token(7, "mentor")
        payload = auth_service.decode_token(token)
        assert payload["user_id"] == 7

    def test_token_contains_correct_role(self, app_ctx):
        for role in ("participant", "mentor", "admin"):
            token = auth_service.generate_token(1, role)
            payload = auth_service.decode_token(token)
            assert payload["role"] == role

    def test_token_has_expiry(self, app_ctx):
        token = auth_service.generate_token(1, "participant")
        payload = auth_service.decode_token(token)
        assert "exp" in payload

    def test_token_expiry_is_approximately_3_days(self, app_ctx):
        before = datetime.now(UTC)
        token = auth_service.generate_token(1, "participant")
        payload = auth_service.decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        delta = exp - before
        # Allow ±5 s around the nominal 3-day expiry
        assert timedelta(days=3) - timedelta(seconds=5) <= delta <= timedelta(days=3) + timedelta(seconds=5)


class TestJWTDecoding:
    def test_decode_valid_token(self, app_ctx):
        token = auth_service.generate_token(99, "admin")
        payload = auth_service.decode_token(token)
        assert payload["user_id"] == 99
        assert payload["role"] == "admin"

    def test_tampered_token_raises(self, app_ctx):
        token = auth_service.generate_token(1, "participant")
        # Flip the last character to corrupt the signature
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with pytest.raises(jwt.InvalidTokenError):
            auth_service.decode_token(tampered)

    def test_expired_token_raises(self, app_ctx):
        """Forge an already-expired token and verify the decoder rejects it."""
        secret = app_ctx.config["JWT_SECRET_KEY"]
        payload = {
            "user_id": 1,
            "role": "participant",
            "iat": datetime.now(UTC) - timedelta(days=10),
            "exp": datetime.now(UTC) - timedelta(days=7),   # already expired
        }
        expired_token = jwt.encode(payload, secret, algorithm="HS256")
        with pytest.raises(jwt.ExpiredSignatureError):
            auth_service.decode_token(expired_token)

    def test_wrong_secret_raises(self, app_ctx):
        wrong_secret = "totally-wrong-secret-key-padded-to-32-bytes!!"
        payload = {
            "user_id": 1,
            "role": "participant",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(days=3),
        }
        token_with_wrong_secret = jwt.encode(payload, wrong_secret, algorithm="HS256")
        with pytest.raises(jwt.InvalidTokenError):
            auth_service.decode_token(token_with_wrong_secret)
