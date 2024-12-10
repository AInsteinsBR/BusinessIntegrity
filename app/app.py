import logging
import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    CORS(app)

    # Load configurations
    app.config["DB_CONFIG"] = {
        "host": os.getenv("DB_HOST", "localhost"),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "yourpassword"),
        "database": os.getenv("DB_NAME", "serp_database"),
    }
    app.config["SERPER_API_KEY"] = os.getenv("SERPER_API_KEY")

    with app.app_context():
        from .routes import register_routes

        register_routes(app)

    return app
