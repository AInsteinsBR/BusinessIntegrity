import io
import logging
import os
import random
import time

import cohere as co
import numpy as np
import requests
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from PyPDF2 import PdfReader
from requests_html import HTMLSession

logger = logging.getLogger(__name__)

SERP_API_KEY = os.getenv("SERPER_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")


cohere_client = co.ClientV2(COHERE_API_KEY)
session = HTMLSession()


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


def create_embeddings(texts, max_retries=5, backoff_factor=2, initial_wait=1):
    texts_embeddings = []

    for i in range(0, len(texts), 96):
        retries = 0
        success = False

        while not success and retries < max_retries:
            try:
                # Make the API call to generate embeddings
                results = cohere_client.embed(
                    model="embed-multilingual-v3.0",
                    input_type="search_document",
                    texts=texts[i : i + 96],
                    embedding_types=["float"],
                )

                # Process the embeddings if the request is successful
                for text, embeddings in zip(results.texts, results.embeddings.float):
                    texts_embeddings.append(
                        {
                            "text": text,
                            "embedding": embeddings,
                        }
                    )

                success = True  # If the request is successful, exit the loop
            except Exception as e:
                # Handle the rate limit error (429 status)
                if hasattr(e, "status_code") and e.status_code == 429:
                    retries += 1
                    wait_time = initial_wait * (
                        backoff_factor**retries
                    ) + random.uniform(0, 1)
                    logger.warning(
                        f"Rate limit hit. Retrying in {wait_time:.2f} seconds... (Retry {retries}/{max_retries})"
                    )
                    time.sleep(wait_time)
                else:
                    # If a non-rate-limit error occurs, re-raise it
                    logger.error(f"An error occurred: {e}")
                    raise e
                # Break out of the retry loop if we've exceeded max retries
                if retries >= max_retries:
                    logger.warning("Max retries reached. Skipping current request.")
                    break

    return texts_embeddings


def similarity_search(query, texts_embeddings, top_n=20):
    """
    Given a query and a list of text embeddings, return the top N most
    similar texts to the query based on cosine similarity.
    """

    def cosine_similarity(a, b):
        """
        Compute cosine similarity between two vectors.
        Cosine similarity = (a . b) / (||a|| * ||b||)
        where a and b are vectors, and . is the dot product.
        """
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        return dot_product / (norm_a * norm_b)

    # Get the embedding for the query text
    query_embedding = cohere_client.embed(
        model="embed-multilingual-v3.0",
        input_type="search_query",
        texts=[query],
        embedding_types=["float"],
    ).embeddings.float[0]

    # Compute cosine similarity between the query's embedding and all other embeddings
    similarities = np.array(
        [
            cosine_similarity(query_embedding, emb["embedding"])
            for emb in texts_embeddings
        ]
    )

    # Get the indices of the top N most similar embeddings
    top_n_indices = similarities.argsort()[-top_n:][::-1]  # Top N similar

    # Fetch the top N most similar texts along with their unique IDs and similarities
    results = [texts_embeddings[i]["text"] for i in top_n_indices]

    return results


def rerank_documents(query, documents, top_n=10):
    """
    Rerank the documents based on their similarity to the query.
    """
    response = cohere_client.rerank(
        model="rerank-v3.5",
        query=query,
        documents=documents,
        top_n=top_n,
    )

    reranked_documents = []
    for result in response.results:
        reranked_documents.append(documents[result.index])

    return reranked_documents


def google_search(query):
    headers = {
        "X-API-KEY": SERP_API_KEY,
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


def scrape_content(search_results):
    scraped_data = {}
    for result in search_results:
        url = result.get("link")
        title = result.get("title")
        try:
            response = session.get(url)
            # response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if "pdf" in content_type:
                text = extract_text_from_pdf(response.content)
            elif "html" in content_type:
                text = extract_text_from_html(response)
            else:
                text = None
            scraped_data[url] = {"title": title, "text": text}
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


def extract_text_from_html(response):
    try:
        response.html.render()
        soup = BeautifulSoup(response.html.raw_html, "html.parser")
        return soup.get_text()
    except Exception as e:
        logger.error(f"HTML extraction error: {e}")
        return None


if __name__ == "__main__":
    query = "AJEL MONTAGEM E AUTOMACAO INDUSTRIAL LTDA fraude"
    results = google_search(query)
    scraped_data = scrape_content(results)
    for url, data in scraped_data.items():
        if data:
            logger.info(f"URL: {url}")
            logger.info(f"Title: {data['title']}")
            documents = split_text(data["text"])
            embeddings = create_embeddings(documents)
            similiar_documents = similarity_search(query, embeddings)
            reranked_documents = rerank_documents(query, similiar_documents)
