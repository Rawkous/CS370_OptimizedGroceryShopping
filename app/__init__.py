# app/__init__.py
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

def create_app():
    # Load env first so config is available everywhere
    load_dotenv()

    app = Flask(__name__)
    CORS(app)

    # Register all HTTP routes (root + /api/*)
    from .routes import register_routes
    register_routes(app)

    # Optionally start the SSH tunnel (idempotent; safe to call more than once)
    from .tunnel import maybe_start_tunnel
    maybe_start_tunnel()

    return app
