import io
import logging
import os
from datetime import datetime

import mysql.connector
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from PyPDF2 import PdfReader

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
CORS(app)

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "yourpassword"),
    "database": os.getenv("DB_NAME", "serp_database"),
}

# Serper API key
SERPER_API_KEY = os.getenv("SERPER_API_KEY")


def connect_to_database():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except mysql.connector.Error as e:
        logger.error(f"Database connection error: {e}")
        raise


def create_table_if_not_exists(connection):
    query = """
    CREATE TABLE IF NOT EXISTS serp_results (
        id INT AUTO_INCREMENT PRIMARY KEY,
        search_query TEXT NOT NULL,
        search_datetime DATETIME NOT NULL,
        result_title TEXT,
        result_link TEXT,
        result_snippet TEXT,
        position INT
    )
    """
    cursor = connection.cursor()
    cursor.execute(query)
    connection.commit()


def store_serp_results(connection, search_query, results):
    query = """
    INSERT INTO serp_results (search_query, search_datetime, result_title, result_link, result_snippet, position)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    search_datetime = datetime.now()
    cursor = connection.cursor()

    for result in results:
        data = (
            search_query,
            search_datetime,
            result.get("title"),
            result.get("link"),
            result.get("snippet"),
            result.get("position"),
        )
        cursor.execute(query, data)

    connection.commit()


def google_search(query):
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    params = {"q": query, "gl": "br", "hl": "pt-br", "num": 10}
    try:
        response = requests.post(
            "https://google.serper.dev/search", headers=headers, json=params
        )
        response.raise_for_status()
        return response.json().get("organic", [])
    except requests.RequestException as e:
        logger.error(f"Error in SERP API request: {e}")
        raise


def scrape_content(urls):
    scraped_data = {}
    for url in urls:
        try:
            response = requests.get(url)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if "pdf" in content_type:
                text = extract_text_from_pdf(response.content)
            elif "html" in content_type:
                text = extract_text_from_html(response.text)
            else:
                text = None
            scraped_data[url] = text
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            scraped_data[url] = None
    return scraped_data


def extract_text_from_pdf(pdf_data):
    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_data))
        return "\n".join(
            page.extract_text() for page in pdf_reader.pages if page.extract_text()
        )
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return None


def extract_text_from_html(html_content):
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        return " ".join(soup.get_text().split())
    except Exception as e:
        logger.error(f"HTML extraction error: {e}")
        return None


@app.route("/search", methods=["POST"])
def search():
    data = request.json
    query = data.get("query")
    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        # Fetch results from SERP API
        results = google_search(query)

        # Store results in the database
        connection = connect_to_database()
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
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Search SERP API</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
                padding: 20px;
            }
            input, button {
                padding: 10px;
                margin: 5px 0;
                width: 100%;
            }
            textarea {
                width: 100%;
                height: 200px;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <h1>Search SERP API</h1>
        <form id="searchForm">
            <label for="query">Enter your search query:</label>
            <input type="text" id="query" name="query" required>
            <button type="submit">Search</button>
        </form>
        <div id="results" style="margin-top: 20px;">
            <h2>Results:</h2>
            <textarea readonly id="output"></textarea>
        </div>
        <script>
            const form = document.getElementById("searchForm");
            form.addEventListener("submit", async (e) => {
                e.preventDefault();
                const query = document.getElementById("query").value;
                const output = document.getElementById("output");
                output.value = "Loading...";
                try {
                    const response = await fetch("/search", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                        },
                        body: JSON.stringify({ query }),
                    });
                    const data = await response.json();
                    output.value = JSON.stringify(data, null, 2);
                } catch (error) {
                    output.value = "Error: " + error.message;
                }
            });
        </script>
    </body>
    </html>
    """


@app.route("/view-table")
def view_table():
    try:
        connection = connect_to_database()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM serp_results ORDER BY search_datetime DESC")
        rows = cursor.fetchall()

        # Build HTML table
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Database Results</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    padding: 20px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                }
                th, td {
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }
                th {
                    background-color: #f2f2f2;
                }
            </style>
        </head>
        <body>
            <h1>Database Results</h1>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Search Query</th>
                        <th>Search Datetime</th>
                        <th>Result Title</th>
                        <th>Result Link</th>
                        <th>Result Snippet</th>
                        <th>Position</th>
                    </tr>
                </thead>
                <tbody>
        """
        for row in rows:
            html += f"""
                <tr>
                    <td>{row['id']}</td>
                    <td>{row['search_query']}</td>
                    <td>{row['search_datetime']}</td>
                    <td>{row['result_title']}</td>
                    <td><a href="{row['result_link']}" target="_blank">{row['result_link']}</a></td>
                    <td>{row['result_snippet']}</td>
                    <td>{row['position']}</td>
                </tr>
            """
        html += """
                </tbody>
            </table>
        </body>
        </html>
        """
        return html
    except Exception as e:
        logger.error(f"Error rendering table: {e}")
        return f"Error: {e}", 500


if __name__ == "__main__":
    app.run(debug=True)
