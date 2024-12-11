import logging

from aiomysql import create_pool
from flask import Blueprint, current_app, jsonify, render_template, request
from models import store_serp_results_with_analysis
from utils import (
    analyze_text,
    create_embeddings,
    google_search,
    rerank_documents,
    scrape_content,
    similarity_search,
    split_text,
    validate_cnpj,
)

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

        results = await google_search(query)

        scraped_data = await scrape_content(results)

        embeddings = []
        for url, data in scraped_data.items():
            if data:
                logger.info(f"URL: {url}")
                logger.info(f"Title: {data['title']}")
                documents = split_text(data["text"])
                search_embedding = await create_embeddings(documents)
                embeddings.extend(search_embedding)

        similar_documents = await similarity_search(query, embeddings, top_n=30)
        reranked_documents = await rerank_documents(query, similar_documents, top_n=15)
        analysis = analyze_text(query, reranked_documents)

        db_config = current_app.config["DB_CONFIG"]

        async with create_pool(**db_config) as pool:
            async with pool.acquire() as connection:
                await store_serp_results_with_analysis(
                    connection, query, results, analysis
                )

        return jsonify({"results": results, "analysis": analysis})
    except Exception as e:
        logger.error(f"Error processing query search: {e}")
        return jsonify({"error": str(e)}), 500


async def process_cnpj_search(cnpj):
    try:
        cnpj_data = {"cnpj": cnpj, "company_name": "Example Company"}
        return jsonify({"cnpj_data": cnpj_data})
    except Exception as e:
        logger.error(f"Error processing CNPJ search: {e}")
        return jsonify({"error": str(e)}), 500


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
                    SELECT sr.*, ra.analysis, ra.reasoning, ra.conclusion 
                    FROM serp_results sr 
                    JOIN result_analysis ra ON sr.analysis_id = ra.id 
                    ORDER BY sr.search_datetime DESC
                    """
                    await cursor.execute(query)
                    rows = await cursor.fetchall()
        return jsonify(rows)
    except Exception as e:
        logger.error(f"Error rendering table: {e}")
        return jsonify({"error": str(e)}), 500
