import asyncio
import io
import logging
import os
import re
from time import time

import aiohttp
import cohere as co
import numpy as np
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from PyPDF2 import PdfReader
from requests_html import HTMLSession

logger = logging.getLogger(__name__)

SERP_API_KEY = os.getenv("SERPER_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")


cohere_client = co.ClientV2(COHERE_API_KEY)
session = HTMLSession()

system_message = """You will analyze a collection of documents to determine if a company is involved in corruption or fraud schemes based on either their fantasy name or CNPJ (Brazilian company registration number). 

Begin your analysis by following these steps:

1. First identify whether the query is a company name or CNPJ by checking if it consists of 14 digits (CNPJ) or contains letters/other characters (company name)

2. Search through the documents for:
- Direct mentions of the company name or CNPJ
- Mentions of individuals associated with the company
- References to suspicious transactions, contracts, or activities
- Connections to known corruption schemes or investigations
- Red flags such as shell companies, unusual financial patterns, or political connections

3. Document your findings in a structured analysis using these tags:

<analysis>
- Note connections between different pieces of evidence
- Identify patterns of suspicious activity
- Evaluate the reliability and significance of each piece of evidence
</analysis 

4. Based on your analysis, provide your reasoning and conclusion:

<reasoning>
Explain the logic behind your conclusion, including:
- Strength of evidence found
- Patterns identified
- Credibility of sources
- Potential alternative explanations
</reasoning>

<conclusion>
State whether there is:
[EVIDENCE OF CORRUPTION]: Strong evidence of corruption/fraud found
[SUSPICIOUS ACTIVITY]: Some suspicious patterns but inconclusive evidence
[NO EVIDENCE]: No significant evidence of corruption/fraud
[INSUFFICIENT DATA]: Not enough information to make a determination
</conclusion>

Important rules:
- Only make conclusions based on evidence found in the provided documents
- Maintain objectivity and avoid speculation
- Clearly distinguish between direct evidence and circumstantial connections
- If the company name/CNPJ is not found in the documents, state this clearly
- Do not include any external information not found in the documents
- If documents are in Portuguese, analyze them in their original language but provide the analysis in English

Begin your analysis now.
"""


def analyze_text(query, documents):
    response = cohere_client.chat(
        model="command-r-plus-08-2024",
        messages=[
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": query,
            },
        ],
        documents=documents,
        temperature=0.3,
    )

    return response.message.content[0].text


def split_text(texts, chunk_size=512):
    """
    Split the text into chunks of a specified size.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=20,
        length_function=len,
        is_separator_regex=False,
    )

    documents = text_splitter.create_documents([texts])

    return [doc.page_content for doc in documents]


async def create_embeddings(
    texts,
    max_retries=5,
    backoff_factor=2,
    initial_wait=1,
    rate_limit=100,
    rate_period=60,
):
    texts_embeddings = []
    request_times = []  # Track the timestamps of recent requests

    for i in range(0, len(texts), 96):
        retries = 0
        success = False

        while not success and retries < max_retries:
            try:
                # Enforce rate limiting
                current_time = time()
                # Remove timestamps outside the rate period
                request_times = [
                    t for t in request_times if current_time - t < rate_period
                ]
                if len(request_times) >= rate_limit:
                    # Calculate wait time until a slot becomes available
                    wait_time = rate_period - (current_time - request_times[0])
                    logger.info(
                        f"Rate limit reached. Waiting {wait_time:.2f} seconds..."
                    )
                    await asyncio.sleep(wait_time)

                # Wrap synchronous cohere call in a coroutine
                results = await asyncio.to_thread(
                    cohere_client.embed,
                    model="embed-multilingual-v3.0",
                    input_type="search_document",
                    texts=texts[i : i + 96],
                    embedding_types=["float"],
                )
                for text, embeddings in zip(results.texts, results.embeddings.float):
                    texts_embeddings.append({"text": text, "embedding": embeddings})

                # Log the request timestamp
                request_times.append(time())

                success = True
            except Exception as e:
                if hasattr(e, "status_code") and e.status_code == 429:
                    retries += 1
                    wait_time = initial_wait * (backoff_factor**retries)
                    logger.warning(
                        f"Rate limit hit. Retrying in {wait_time:.2f} seconds... (Retry {retries}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Error generating embeddings: {e}")
                    raise e
                if retries >= max_retries:
                    logger.warning("Max retries reached. Skipping current request.")
                    break

    return texts_embeddings


async def similarity_search(query, texts_embeddings, top_n=20):
    def cosine_similarity(a, b):
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        return dot_product / (norm_a * norm_b)

    # Wrap synchronous embedding generation in a coroutine
    query_embedding = await asyncio.to_thread(
        cohere_client.embed,
        model="embed-multilingual-v3.0",
        input_type="search_query",
        texts=[query],
        embedding_types=["float"],
    )

    query_embedding = query_embedding.embeddings.float[0]
    similarities = np.array(
        [
            cosine_similarity(query_embedding, emb["embedding"])
            for emb in texts_embeddings
        ]
    )

    top_n_indices = similarities.argsort()[-top_n:][::-1]
    results = [texts_embeddings[i]["text"] for i in top_n_indices]

    return results


async def rerank_documents(query, documents, top_n=10):
    response = await asyncio.to_thread(
        cohere_client.rerank,
        model="rerank-v3.5",
        query=query,
        documents=documents,
        top_n=top_n,
    )

    reranked_documents = [documents[result.index] for result in response.results]
    return reranked_documents


async def google_search(query):
    headers = {
        "X-API-KEY": SERP_API_KEY,
        "Content-Type": "application/json",
    }
    params = {"q": query, "gl": "br", "hl": "pt-br", "num": 10}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://google.serper.dev/search", headers=headers, json=params
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("organic", [])
        except aiohttp.ClientError as e:
            logger.error(f"Error in SERP API request: {e}")
            raise


async def extract_text_from_pdf(pdf_data):
    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_data))
        return "\n".join(
            page.extract_text() for page in pdf_reader.pages if page.extract_text()
        )
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return None


async def extract_text_from_html(response):
    try:
        html = await response.text()
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text()
    except Exception as e:
        logger.error(f"HTML extraction error: {e}")
        return None


async def scrape_content(search_results):
    scraped_data = {}

    async with aiohttp.ClientSession() as session:
        for result in search_results:
            url = result.get("link")
            title = result.get("title")

            try:
                async with session.get(url) as response:
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "pdf" in content_type:
                        pdf_content = await response.read()
                        text = await extract_text_from_pdf(pdf_content)
                    elif "html" in content_type:
                        text = await extract_text_from_html(response)
                    else:
                        text = None
                    scraped_data[url] = {"title": title, "text": text}
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                scraped_data[url] = None
    return scraped_data


def validate_cnpj(cnpj):
    """Validate the CNPJ format (Brazilian business number)."""
    # Basic regex check for CNPJ format (XX.XXX.XXX/XXXX-XX)
    cnpj_regex = r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$"
    return re.match(cnpj_regex, cnpj) is not None


# if __name__ == "__main__":
#     query = "AJEL MONTAGEM E AUTOMACAO INDUSTRIAL LTDA fraude"
#     results = google_search(query)
#     scraped_data = scrape_content(results)
#     embeddings = []
#     for url, data in scraped_data.items():
#         if data:
#             logger.info(f"URL: {url}")
#             logger.info(f"Title: {data['title']}")
#             documents = split_text(data["text"])
#             search_embedding = create_embeddings(documents)
#             embeddings.extend(search_embedding)

#     similiar_documents = similarity_search(query, embeddings, top_n=30)
#     reranked_documents = rerank_documents(query, similiar_documents, top_n=15)
#     analysis = analyze_text(query, reranked_documents)
