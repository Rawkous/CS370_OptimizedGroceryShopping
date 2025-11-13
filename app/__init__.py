# app/__init__.py
import os
from pathlib import Path
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from .tunnel import maybe_start_tunnel
from .routes import api_bp, root_bp

def create_app() -> Flask:
    # Load env, then (optionally) start SSH tunnel so DB_* are rewritten if needed.
    load_dotenv()
    maybe_start_tunnel()

    app = Flask(__name__)
    CORS(app)

    # Register routes
    app.register_blueprint(root_bp)  # "/" + fallback index
    app.register_blueprint(api_bp, url_prefix="")  # /api/* and /healthz

    return app
