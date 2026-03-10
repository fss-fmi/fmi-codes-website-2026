#!/usr/bin/env python3
"""Application configuration management"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', SECRET_KEY)
    JWT_EXPIRY_DAYS = int(os.environ.get('JWT_EXPIRY_DAYS', 3))

    # Admin credentials
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@fmicodes.bg')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

    # PostgreSQL database configuration
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', 5432)
    DB_NAME = os.environ.get('DB_NAME', 'fmi_hackathon_2026_dev')
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')

    # Connection pool sizing (per worker process)
    DB_POOL_MIN = int(os.environ.get('DB_POOL_MIN', 2))
    DB_POOL_MAX = int(os.environ.get('DB_POOL_MAX', 10))

    # Build connection string — prefer DATABASE_URL if set (e.g. Railway injects this automatically)
    DATABASE_URL = os.environ.get(
        'DATABASE_URL',
        f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    )

    TEMPLATES_FOLDER = BASE_DIR / 'app' / 'templates'
    STATIC_FOLDER = BASE_DIR / 'app' / 'static'
    MENTORS_STAY_TUNED = os.environ.get('MENTORS_STAY_TUNED', 'false').lower() == 'true'
    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')
    DB_NAME = os.environ.get('DB_NAME', 'fmi_hackathon_2026_dev')
    DATABASE_URL = os.environ.get(
        'DATABASE_URL',
        f'postgresql://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}:{Config.DB_PORT}/{DB_NAME}'
    )


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SECRET_KEY = os.environ.get('SECRET_KEY')  # Must be set in environment
    DB_NAME = os.environ.get('DB_NAME', 'fmi_hackathon_2026')
    DATABASE_URL = os.environ.get(
        'DATABASE_URL',
        f'postgresql://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}:{Config.DB_PORT}/{DB_NAME}'
    )


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SECRET_KEY = 'test-secret-key'
    DB_NAME = 'fmi_hackathon_2026_test'
    DATABASE_URL = os.environ.get(
        'DATABASE_URL',
        f'postgresql://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}:{Config.DB_PORT}/{DB_NAME}'
    )


def get_config(config_name='development'):
    """Get configuration by name"""
    configs = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'testing': TestingConfig,
    }
    return configs.get(config_name, DevelopmentConfig)
