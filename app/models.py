import logging
from datetime import datetime

import mysql.connector

logger = logging.getLogger(__name__)


def connect_to_database(config):
    try:
        connection = mysql.connector.connect(**config)
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
