"""Flask application factory and initialization"""

import logging
import os
from importlib import import_module

from config import get_config
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Module-level limiter — attached to app in create_app()
# H7: Use Redis when REDIS_URL is configured so the limit is shared across all
# Gunicorn workers.  Falls back to in-memory for local dev without Redis.
_redis_url = os.environ.get("REDIS_URL", "")
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"],
    storage_uri=_redis_url if _redis_url else "memory://",
)


def create_app(config_name="development"):
    """Create and configure Flask application"""
    config = get_config(config_name)

    # C2: Hard-fail on missing/weak secrets in production so misconfigured
    # deployments are caught at startup rather than discovered after a breach.
    if config_name == "production":
        from config import validate_production_secrets

        validate_production_secrets()

    app = Flask(
        __name__,
        static_folder=str(config.STATIC_FOLDER),
    )
    app.config.from_object(config)

    # Attach rate limiter
    limiter.init_app(app)

    # CORS — allow frontend origin with credentials (httpOnly cookies)
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
    CORS(
        app,
        origins=[frontend_origin],
        supports_credentials=True,
    )

    # Initialize database connection pool
    from app.database import close_pool, init_database

    try:
        init_database(app)
        logger.info(f"✓ Database initialized successfully ({config_name} mode)")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
        raise

    # Ensure pool is cleaned up when the app shuts down
    import atexit

    atexit.register(close_pool)

    # Import route modules explicitly so their decorators register endpoints.
    for module in (
        "app.routes.api_routes",
        "app.routes.auth",
        "app.routes.mentors",
        "app.routes.teams",
    ):
        import_module(module)

    # Register blueprints
    from app.routes import api_bp, auth_bp, mentors_bp, teams_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(mentors_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(api_bp)

    logger.info("✓ All blueprints registered successfully")

    return app
