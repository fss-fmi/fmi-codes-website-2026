"""Flask application factory and initialization"""

import logging
from importlib import import_module

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import get_config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Module-level limiter — attached to app in create_app()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"],
    storage_uri="memory://",
)


def create_app(config_name="development"):
    """Create and configure Flask application"""
    config = get_config(config_name)

    app = Flask(
        __name__,
        template_folder=str(config.TEMPLATES_FOLDER),
        static_folder=str(config.STATIC_FOLDER),
    )
    app.config.from_object(config)

    # Attach rate limiter
    limiter.init_app(app)

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
        "app.routes.pages",
        "app.routes.teams",
    ):
        import_module(module)

    # Register blueprints
    from app.routes import api_bp, auth_bp, mentors_bp, pages_bp, teams_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(mentors_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)

    logger.info("✓ All blueprints registered successfully")

    return app
