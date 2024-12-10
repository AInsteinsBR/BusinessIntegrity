import logging

from flask import jsonify, request

from .models import connect_to_database, create_table_if_not_exists, store_serp_results
from .utils import google_search, scrape_content

logger = logging.getLogger(__name__)


def register_routes(app):
    @app.route("/search", methods=["POST"])
    def search():
        data = request.json
        query = data.get("query")
        if not query:
            return jsonify({"error": "Query is required"}), 400

        try:
            # Fetch results from SERP API
            results = google_search(app.config["SERPER_API_KEY"], query)

            # Store results in the database
            connection = connect_to_database(app.config["DB_CONFIG"])
            create_table_if_not_exists(connection)
            store_serp_results(connection, query, results)

            # Scrape content from result URLs
            urls = [result.get("link") for result in results if result.get("link")]
            scraped_content = scrape_content(urls)

            return jsonify({"results": results, "scraped_content": scraped_content})
        except Exception as e:
            logger.error(f"Error processing search: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/")
    def home():
        return app.send_static_file("index.html")

    @app.route("/view-table")
    def view_table():
        try:
            connection = connect_to_database(app.config["DB_CONFIG"])
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM serp_results ORDER BY search_datetime DESC")
            rows = cursor.fetchall()
            return jsonify(rows)
        except Exception as e:
            logger.error(f"Error rendering table: {e}")
            return jsonify({"error": str(e)}), 500
