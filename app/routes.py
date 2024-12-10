import logging

from flask import Blueprint, current_app, jsonify, render_template, request
from models import connect_to_database, create_table_if_not_exists, store_serp_results
from utils import google_search, scrape_content

logger = logging.getLogger(__name__)

search_routes = Blueprint("search_routes", __name__)
utility_routes = Blueprint("utility_routes", __name__)


def register_utility_routes(app):
    """Register utility-related routes."""
    app.register_blueprint(utility_routes)


def register_search_routes(app):
    """Register search-related routes."""
    app.register_blueprint(search_routes)


@search_routes.route("/search", methods=["POST"])
def search():
    data = request.json
    query = data.get("query")
    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        # Fetch results from SERP API
        results = google_search(current_app.config["SERPER_API_KEY"], query)

        # Store results in the database
        connection = connect_to_database(current_app.config["DB_CONFIG"])
        create_table_if_not_exists(connection)
        store_serp_results(connection, query, results)

        # Scrape content from result URLs
        urls = [result.get("link") for result in results if result.get("link")]
        scraped_content = scrape_content(urls)

        return jsonify({"results": results, "scraped_content": scraped_content})
    except Exception as e:
        logger.error(f"Error processing search: {e}")
        return jsonify({"error": str(e)}), 500


@utility_routes.route("/")
def home():
    return render_template("index.html")


@utility_routes.route("/view-table")
def view_table():
    try:
        connection = connect_to_database(current_app.config["DB_CONFIG"])
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM serp_results ORDER BY search_datetime DESC")
        rows = cursor.fetchall()
        return jsonify(rows)
    except Exception as e:
        logger.error(f"Error rendering table: {e}")
        return jsonify({"error": str(e)}), 500
