from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from .routes import root_bp, api_bp
from pathlib import Path

def create_app() -> Flask:
    load_dotenv()

    # PROJECT_ROOT is two levels up from this file: .../GroceryAppClean/python/app/__init__.py
    project_root = Path(__file__).resolve().parents[2]

    app = Flask(
        __name__,
        template_folder=str(project_root / "html"),
        static_folder=str(project_root / "photos"),
    )
    CORS(app)

    app.register_blueprint(root_bp)
    app.register_blueprint(api_bp)

    return app
