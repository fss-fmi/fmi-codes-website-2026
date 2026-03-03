"""Route blueprints"""
from flask import Blueprint

# Define blueprints
auth_bp = Blueprint('auth', __name__, url_prefix='')
mentors_bp = Blueprint('mentors', __name__, url_prefix='')
teams_bp = Blueprint('teams', __name__, url_prefix='')
pages_bp = Blueprint('pages', __name__, url_prefix='')
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Import route handlers to register them with blueprints
from app.routes import auth, mentors, teams, pages, api_routes

__all__ = ['auth_bp', 'mentors_bp', 'teams_bp', 'pages_bp', 'api_bp']
