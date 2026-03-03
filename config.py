#!/usr/bin/env python3
"""Application configuration management"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DATABASE_PATH = BASE_DIR / 'website.db'
    TEMPLATES_FOLDER = BASE_DIR / 'app' / 'templates'
    STATIC_FOLDER = BASE_DIR / 'app' / 'static'
    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SECRET_KEY = os.environ.get('SECRET_KEY')  # Must be set in environment


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DATABASE_PATH = BASE_DIR / 'test.db'
    SECRET_KEY = 'test-secret-key'


def get_config(config_name='development'):
    """Get configuration by name"""
    configs = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'testing': TestingConfig,
    }
    return configs.get(config_name, DevelopmentConfig)
