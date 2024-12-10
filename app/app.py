import logging
import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates")
    CORS(app)

    app.config["DB_CONFIG"] = {
        "host": os.getenv("DB_HOST"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
    }
    app.config["SERPER_API_KEY"] = os.getenv("SERPER_API_KEY")

    with app.app_context():
        from routes import register_search_routes, register_utility_routes

        register_search_routes(app)
        register_utility_routes(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=8080, use_reloader=True)
