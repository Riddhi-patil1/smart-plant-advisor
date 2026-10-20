"""Smart Plant Monitoring and Watering Advisory System: Flask application factory."""
import logging
import os
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from . import api
from .config import ALLOWED_ORIGINS, DEFAULT_DB_PATH, FRONTEND_DIST
from .db import connect, init_db
from .seed import seed_example_plants
from .simulation import SimulationManager

log = logging.getLogger(__name__)
_warned = False


def _install_cors(app):
    """Allow only the local frontend origins. Uses Flask-CORS when installed."""
    global _warned
    try:
        from flask_cors import CORS

        CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGINS}})
        app.config["CORS_IMPLEMENTATION"] = "flask-cors"
        return
    except ImportError:
        if not _warned:
            log.warning("flask-cors is not installed; using the built-in equivalent. Run: pip install -r requirements.txt")
            _warned = True
    app.config["CORS_IMPLEMENTATION"] = "built-in fallback"

    def add_headers(response):
        origin = request.headers.get("Origin")
        if origin in ALLOWED_ORIGINS and request.path.startswith("/api/"):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @app.before_request
    def preflight():
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            return add_headers(app.make_response(("", 204)))

    app.after_request(add_headers)


def create_app(database=None, seed=True):
    app = Flask(__name__)
    app.config["DATABASE"] = str(database or DEFAULT_DB_PATH)
    app.json.sort_keys = False

    init_db(app.config["DATABASE"])
    if seed:
        conn = connect(app.config["DATABASE"])
        try:
            seed_example_plants(conn)
        finally:
            conn.close()

    app.extensions["simulation"] = SimulationManager(app.config["DATABASE"])
    _install_cors(app)
    app.register_blueprint(api.bp)

    dist_path = Path(FRONTEND_DIST)
    if os.environ.get("SERVE_FRONTEND", "").lower() in ("1", "true") and dist_path.is_dir():
        from werkzeug.exceptions import MethodNotAllowed, NotFound

        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
        def serve_frontend(path):
            if path.startswith("api/") or path == "api":
                raise NotFound()
            if request.method not in ("GET", "HEAD"):
                raise MethodNotAllowed()
            target = dist_path / path
            if path and target.is_file():
                return send_from_directory(dist_path, path)
            return send_from_directory(dist_path, "index.html")

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.after_request
    def no_store(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(HTTPException)
    def http_error(exc):
        codes = {404: "not_found", 405: "method_not_allowed", 400: "bad_request"}
        return jsonify({"error": {"code": codes.get(exc.code, "http_error"), "message": exc.description}}), exc.code

    @app.errorhandler(Exception)
    def unexpected(exc):
        app.logger.exception("Unhandled error")
        return jsonify({"error": {"code": "internal_error", "message": "An unexpected server error occurred."}}), 500

    return app
