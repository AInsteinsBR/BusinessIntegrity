import logging
import os

import mysql.connector

logger = logging.getLogger(__name__)


from dotenv import load_dotenv

load_dotenv()



def connect_to_database(config):
    try:
        connection = mysql.connector.connect(**config)
        if connection.is_connected():
            return connection
    except mysql.connector.Error as e:
        logger.error(f"Database connection error: {e}")
        raise


def create_table_if_not_exists(connection):
    query_result_analysis = """
    CREATE TABLE IF NOT EXISTS result_analysis (
    id INT AUTO_INCREMENT PRIMARY KEY,
    search_query TEXT NOT NULL,
    search_datetime DATETIME NOT NULL,
    analysis TEXT,
    reasoning TEXT,
    conclusion TEXT
    );"""

    query_serp_results = """
    CREATE TABLE IF NOT EXISTS serp_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    analysis_id INT NOT NULL,
    search_query TEXT NOT NULL,
    search_datetime DATETIME NOT NULL,
    result_title TEXT,
    result_link TEXT,
    result_snippet TEXT,
    position INT,
    FOREIGN KEY (analysis_id) REFERENCES result_analysis(id) ON DELETE CASCADE
    );"""

    queries = [query_result_analysis, query_serp_results]

    for query in queries:
        cursor = connection.cursor()
        cursor.execute(query)
        connection.commit()


config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}


connection = connect_to_database(config)
create_table_if_not_exists(connection)
