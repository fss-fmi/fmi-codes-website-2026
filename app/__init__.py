"""Flask application factory and initialization"""
import sqlite3
from flask import Flask
from pathlib import Path
from config import get_config


def create_app(config_name='development'):
    """Create and configure Flask application"""
    config = get_config(config_name)
    
    app = Flask(__name__, 
                template_folder=str(config.TEMPLATES_FOLDER),
                static_folder=str(config.STATIC_FOLDER))
    app.config.from_object(config)
    
    # Initialize database
    from app.database import init_database
    init_database(app)
    
    # Register blueprints
    from app.routes import auth_bp, mentors_bp, teams_bp, pages_bp, api_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(mentors_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    
    return app
