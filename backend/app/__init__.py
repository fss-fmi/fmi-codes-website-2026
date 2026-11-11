"""Flask application factory and initialization"""

import logging
import os
from importlib import import_module

from config import get_config
from flask import Flask, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from prometheus_flask_exporter import PrometheusMetrics
from werkzeug.middleware.proxy_fix import ProxyFix

from app.services.redis_client import build_limiter_storage_uri
from app.utils.rate_limits import (
    identity_key,
    is_signed_in,
    multiplier_from_env,
    per_identity,
    scaled,
)
from app.utils.request_json import InvalidJsonFieldError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Module-level limiter — attached to app in create_app()
# H7: Share the limit across all Gunicorn workers via Redis. The storage URI is
# resolved from the centralized redis_client config inside create_app() (see
# RATELIMIT_STORAGE_URI below), so it transparently supports Sentinel mode
# (REDIS_SENTINELS + REDIS_MASTER_NAME) or single-instance (REDIS_URL), and
# falls back to in-memory for local dev without Redis.
# The default is per route; the application limit caps one anonymous address across all
# routes, so a scraper can't take 3000/min from every public route at once.
limiter = Limiter(
    key_func=identity_key,
    default_limits=[per_identity("200 per minute", "3000 per minute")],
    application_limits=[scaled("6000 per minute")],
    application_limits_exempt_when=is_signed_in,
)


def create_app(config_name="development"):
    """Create and configure Flask application"""
    config = get_config(config_name)

    # C2: Hard-fail on missing/weak secrets in production so misconfigured
    # deployments are caught at startup rather than discovered after a breach.
    if config_name == "production":
        from config import validate_production_secrets

        validate_production_secrets()

    app = Flask(__name__, static_folder=None)
    app.config.from_object(config)

    # Address-keyed limits read remote_addr, otherwise the proxy's address for every visitor.
    # Exactly one hop sits in front in every deployment (ingress-nginx in k3s, the frontend's
    # nginx in Compose). Trusting more would let a client pick its bucket with a forged header.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

    # Under Gunicorn, PROMETHEUS_MULTIPROC_DIR (gunicorn.conf.py) makes prometheus_client keep
    # values in shared files and the exporter's /metrics sum them across workers.
    # url_rule, not the raw path, labels the latency histogram: every unknown URL a scanner
    # tries would otherwise add series that the multiprocess files never drop.
    # Kubelet probes would swamp the request rate and dilute the 5xx share the alert reads.
    PrometheusMetrics(
        app,
        group_by="url_rule",
        excluded_paths=[r"^/api/health(/ready)?$"],
    )

    # Resolve the rate-limit storage URI now that env/config is loaded, then
    # attach the limiter. build_limiter_storage_uri() returns a redis+sentinel://
    # / redis:// / memory:// string depending on the Redis config present.
    app.config["RATELIMIT_STORAGE_URI"] = build_limiter_storage_uri()
    app.config["RATELIMIT_MULTIPLIER"] = multiplier_from_env()
    limiter.init_app(app)

    # The SPA shows a response's `error` field; without one a 429 reads "HTTP 429".
    @app.errorhandler(429)
    def too_many_requests(_e):
        return jsonify(
            {"success": False, "error": "Too many requests. Wait a moment and try again."}
        ), 429

    @app.errorhandler(InvalidJsonFieldError)
    def invalid_json_field(e):
        return jsonify({"success": False, "error": str(e)}), 400

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
