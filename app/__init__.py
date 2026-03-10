"""Flask application factory and initialization"""
from flask import Flask
from pathlib import Path
from config import get_config
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app(config_name='development'):
    """Create and configure Flask application"""
    config = get_config(config_name)

    app = Flask(__name__,
                template_folder=str(config.TEMPLATES_FOLDER),
                static_folder=str(config.STATIC_FOLDER))
    app.config.from_object(config)

    # Initialize database connection pool
    from app.database import init_database, close_pool
    try:
        init_database(app)
        logger.info(f"✓ Database initialized successfully ({config_name} mode)")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
        raise

    # Ensure pool is cleaned up when the app shuts down
    import atexit
    atexit.register(close_pool)

    # Register blueprints
    from app.routes import auth_bp, mentors_bp, teams_bp, pages_bp, api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(mentors_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)

    logger.info("✓ All blueprints registered successfully")

    return app
