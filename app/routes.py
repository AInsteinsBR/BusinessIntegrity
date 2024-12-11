import logging

import markdown
from aiomysql import create_pool
from flask import Blueprint, current_app, jsonify, render_template, request
from models import store_serp_results_with_analysis
from utils import run_search, validate_cnpj

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
async def search():
    data = request.json
    search_type = data.get("searchType")
    input_value = data.get("inputValue")

    if not input_value:
        return jsonify({"error": "Input value is required"}), 400

    if search_type == "query":
        query = input_value
        return await process_query_search(query)

    elif search_type == "cnpj":
        cnpj = input_value
        if not validate_cnpj(cnpj):
            return jsonify({"error": "Invalid CNPJ format"}), 400
        return await process_cnpj_search(cnpj)

    else:
        return jsonify({"error": "Invalid search type"}), 400


async def process_query_search(query):
    try:
        search_results = await run_search(query)
        await insert_search_results("QUERY", query, search_results)

        analysis_md = markdown.markdown(search_results["analysis"])
        return render_template("analysis_result.html", analysis=analysis_md)
    except Exception as e:
        logger.error(f"Error processing query search: {e}")
        return jsonify({"error": str(e)}), 500


async def process_cnpj_search(cnpj):
    try:
        query = f"empresa {cnpj}"
        search_results = await run_search(query)
        await insert_search_results("CNPJ", cnpj, search_results)

        analysis_md = markdown.markdown(search_results["analysis"])
        return render_template("analysis_result.html", analysis=analysis_md)
    except Exception as e:
        logger.error(f"Error processing CNPJ search: {e}")
        return jsonify({"error": str(e)}), 500


async def insert_search_results(query_type, query, search_results):
    db_config = current_app.config["DB_CONFIG"]
    async with create_pool(**db_config) as pool:
        async with pool.acquire() as connection:
            await store_serp_results_with_analysis(
                connection,
                query_type,
                query,
                search_results["results"],
                search_results["analysis"],
            )


@utility_routes.route("/")
async def home():
    return render_template("index.html")


@utility_routes.route("/view-table")
async def view_table():
    try:
        db_config = current_app.config["DB_CONFIG"]

        async with create_pool(**db_config) as pool:
            async with pool.acquire() as connection:
                async with connection.cursor() as cursor:
                    query = """
                    SELECT sr.*, ra.ai_analysis
                    FROM serp_results sr 
                    JOIN result_analysis ra ON sr.analysis_id = ra.id 
                    ORDER BY ra.search_datetime DESC
                    """
                    await cursor.execute(query)
                    rows = await cursor.fetchall()
        return render_template("view_table.html", rows=rows)
    except Exception as e:
        logger.error(f"Error rendering table: {e}")
        return jsonify({"error": str(e)}), 500


@utility_routes.route("/last-rows", methods=["GET"])
async def get_last_rows():
    try:
        db_config = current_app.config["DB_CONFIG"]
        row_limit = int(request.args.get("limit", 10))

        async with create_pool(**db_config) as pool:
            async with pool.acquire() as connection:
                async with connection.cursor() as cursor:
                    query = """
                    SELECT sr.*, ra.ai_analysis
                    FROM serp_results sr 
                    JOIN result_analysis ra ON sr.analysis_id = ra.id 
                    ORDER BY ra.search_datetime DESC
                    LIMIT %s
                    """
                    await cursor.execute(query, (row_limit,))
                    rows = await cursor.fetchall()
        return render_template("view_rows.html", rows=rows)
    except Exception as e:
        logger.error(f"Error fetching last rows: {e}")
        return jsonify({"error": str(e)}), 500
