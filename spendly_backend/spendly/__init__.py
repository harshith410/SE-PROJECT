"""Spendly backend - Flask application factory."""
import logging
import os

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from . import auth, budgets, transactions
from .db import close_db, init_db
from .utils import ApiError

DEV_SECRET = "dev-only-change-me"
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", DEV_SECRET),
        DATABASE=os.environ.get("DATABASE", os.path.join(app.instance_path, "spendly.db")),
        CORS_ORIGINS=os.environ.get("CORS_ORIGINS", "*"),
        TOKEN_HOURS=int(os.environ.get("TOKEN_HOURS", "24")),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if app.config["SECRET_KEY"] == DEV_SECRET and not app.config.get("TESTING"):
        logging.warning("Using the default SECRET_KEY. Set the SECRET_KEY environment variable.")

    os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    for module in (auth, transactions, budgets):
        app.register_blueprint(module.bp)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.get("/")
    def index():
        """Serve the web app so the page and the API share one origin."""
        return send_from_directory(WEB_DIR, "index.html")

    @app.after_request
    def add_headers(resp):
        allowed = app.config["CORS_ORIGINS"]
        origin = request.headers.get("Origin")
        if allowed == "*":
            resp.headers["Access-Control-Allow-Origin"] = "*"
        elif origin and origin in [o.strip() for o in allowed.split(",")]:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.errorhandler(ApiError)
    def api_error(e):
        return jsonify(error=e.message), e.status

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify(error=e.description), e.code

    @app.errorhandler(Exception)
    def server_error(e):
        app.logger.exception("Unhandled error")
        return jsonify(error="Internal server error"), 500

    return app
