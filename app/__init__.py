# app/__init__.py
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from .routes import root_bp, api_bp

def create_app() -> Flask:
    # Load env so Flask sees .env in any entrypoint
    load_dotenv()

    app = Flask(__name__)
    CORS(app)

    # Register routes
    app.register_blueprint(root_bp)
    app.register_blueprint(api_bp)

    return app
