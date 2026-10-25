#!/usr/bin/env python3
"""Application configuration management"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent


class Config:
    """Base configuration"""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_EXPIRY_DAYS = int(os.environ.get("JWT_EXPIRY_DAYS", 3))

    # Admin credentials — store bcrypt hash, never plaintext
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@fmicodes.bg")
    # Generate with: python -c "import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt(12)).decode())"
    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")  # Must be set in .env

    # Request size guard — large bodies are fully parsed before any truncation otherwise
    MAX_CONTENT_LENGTH = 64 * 1024  # 64 KB hard limit

    # PostgreSQL database configuration
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", 5432)
    DB_NAME = os.environ.get("DB_NAME", "fmi_hackathon_2026_dev")
    DB_USER = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

    # Connection pool sizing (per worker process)
    DB_POOL_MIN = int(os.environ.get("DB_POOL_MIN", 2))
    DB_POOL_MAX = int(os.environ.get("DB_POOL_MAX", 20))
    DB_POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", 5))

    # Build connection string — prefer DATABASE_URL if set (e.g. Railway injects this automatically)
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    # Email / SMTP configuration (used for password reset emails)
    MAIL_HOST = os.environ.get("MAIL_HOST", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "fss.fmi.uni.sofia@gmail.com")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")  # Must be set in .env
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"

    # Redis — redis_client.py reads these from os.environ directly (so it works at
    # import time before app context); these fields expose them for discoverability
    # and current_app.config access. Set REDIS_SENTINELS + REDIS_MASTER_NAME for HA
    # Sentinel mode, or REDIS_URL for a single instance; leave all unset to disable.
    REDIS_URL = os.environ.get("REDIS_URL", "")
    REDIS_SENTINELS = os.environ.get("REDIS_SENTINELS", "")
    REDIS_MASTER_NAME = os.environ.get("REDIS_MASTER_NAME", "")
    REDIS_SOCKET_TIMEOUT = int(os.environ.get("REDIS_SOCKET_TIMEOUT", 2))
    REDIS_CONNECT_TIMEOUT = int(os.environ.get("REDIS_CONNECT_TIMEOUT", 2))

    # Discord webhook for bug reports — set DISCORD_BUG_WEBHOOK_URL in .env
    DISCORD_BUG_WEBHOOK_URL = os.environ.get("DISCORD_BUG_WEBHOOK_URL", "")
    # Slack incoming webhook for the same reports; both are used when both are set
    SLACK_BUG_WEBHOOK_URL = os.environ.get("SLACK_BUG_WEBHOOK_URL", "")

    # Social media / contact links
    DISCORD_URL = os.environ.get("DISCORD_URL", "")
    INSTAGRAM_URL = os.environ.get("INSTAGRAM_URL", "")
    FACEBOOK_URL = os.environ.get("FACEBOOK_URL", "")
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")
    CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "")

    STATIC_FOLDER = BASE_DIR / "app" / "static"
    MENTORS_STAY_TUNED = os.environ.get("MENTORS_STAY_TUNED", "false").lower() == "true"
    REGISTRATION_OPEN = os.environ.get("REGISTRATION_OPEN", "false").lower() == "true"
    RANKINGS_LIVE = os.environ.get("RANKINGS_LIVE", "false").lower() == "true"
    REQUIRE_EMAIL_VERIFICATION = (
        os.environ.get("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"
    )
    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    """Development configuration"""

    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-12345")
    DB_NAME = os.environ.get("DB_NAME", "fmi_hackathon_2026_dev")
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        f"postgresql://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}:{Config.DB_PORT}/{DB_NAME}",
    )


class ProductionConfig(Config):
    """Production configuration"""

    DEBUG = False
    SECRET_KEY = os.environ.get("SECRET_KEY")  # Must be set in environment
    DB_NAME = os.environ.get("DB_NAME", "fmi_hackathon_2026")
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        f"postgresql://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}:{Config.DB_PORT}/{DB_NAME}",
    )


class TestingConfig(Config):
    """Testing configuration"""

    TESTING = True
    SECRET_KEY = "test-secret-key"
    DB_NAME = "fmi_hackathon_2026_test"
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        f"postgresql://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}:{Config.DB_PORT}/{DB_NAME}",
    )
    # Disable flask-limiter so E2E tests never trip rate-limit counters
    RATELIMIT_ENABLED = False


_WEAK_SECRETS = {
    "dev-secret-key-change-in-production",
    "dev-secret-key-12345",
    "dev-secret-key",
    "",
}


def validate_production_secrets():
    """Hard-fail if weak or missing secrets are detected in production.

    Call this inside create_app() when config_name == 'production'.
    """
    secret = os.environ.get("SECRET_KEY", "")
    jwt_secret = os.environ.get("JWT_SECRET_KEY", "")

    if not secret or secret in _WEAK_SECRETS:
        raise RuntimeError(
            "CRITICAL: SECRET_KEY is missing or uses a known-weak default. "
            "Set a strong random value in your deployment secrets."
        )
    if not jwt_secret or jwt_secret in _WEAK_SECRETS:
        raise RuntimeError(
            "CRITICAL: JWT_SECRET_KEY is missing or uses a known-weak default. "
            "Set a strong random value in your deployment secrets."
        )
    if not os.environ.get("ADMIN_PASSWORD_HASH"):
        raise RuntimeError(
            "CRITICAL: ADMIN_PASSWORD_HASH is not set. "
            'Generate with: python -c "import bcrypt, getpass; '
            'print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt(12)).decode())"'
        )


def get_config(config_name="development"):
    """Get configuration by name"""
    configs = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "testing": TestingConfig,
    }
    return configs.get(config_name, DevelopmentConfig)
