import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def store_serp_results_with_analysis(
    connection, search_query, results, analysis_text
):
    async with connection.cursor() as cursor:
        # Insert into result_analysis and get the analysis ID
        analysis_query = """
        INSERT INTO result_analysis (search_query, search_datetime, analysis, reasoning, conclusion)
        VALUES (%s, %s, %s, '', '')
        """
        search_datetime = datetime.now()
        await cursor.execute(
            analysis_query, (search_query, search_datetime, analysis_text)
        )
        analysis_id = cursor.lastrowid

        # Insert the SERP results linked to the analysis
        serp_query = """
        INSERT INTO serp_results (analysis_id, search_query, search_datetime, result_title, result_link, result_snippet, position)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        for result in results:
            data = (
                analysis_id,
                search_query,
                search_datetime,
                result.get("title"),
                result.get("link"),
                result.get("snippet"),
                result.get("position"),
            )
            await cursor.execute(serp_query, data)

        await connection.commit()
