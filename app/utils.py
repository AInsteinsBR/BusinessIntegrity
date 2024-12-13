import asyncio
import io
import logging
import os
import re
from io import BytesIO
from time import time

import aiohttp
import cohere as co
import numpy as np
from docx import Document
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

SERP_API_KEY = os.getenv("SERPER_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


cohere_client = co.ClientV2(api_key=COHERE_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

system_message = """You will analyze a collection of documents to determine if a company is involved in corruption or fraud schemes based on either their fantasy name or CNPJ (Brazilian company registration number). 

Begin your analysis by following these steps:

1. First identify whether the query is a company name or CNPJ by checking if it consists of 14 digits (CNPJ) or contains letters/other characters (company name)

2. Search through the documents for:
- Direct mentions of the company name, company name variations or CNPJ
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
[EVIDÊNCIA DE CORRUPÇÃO]
[ATIVIDADE SUSPEITA]
[SEM EVIDÊNCIA]
[DADOS INSUFICIENTES]
</conclusion>

Important rules:
- Only make conclusions based on evidence found in the provided documents
- Clearly distinguish between direct evidence and circumstantial connections
- If the company name/CNPJ is not found in the documents, state this clearly
- Do not include any external information not found in the documents
- provide the analysis in Portuguese

Here is an example of response:
## Análise
<analysis>
</analysis>

## Pensamento
<reasoning>
</reasoning>

## Conclusão
<conclusion>
</conclusion>

Begin your analysis now.
"""


def format_user_message(query, documents):
    user_message = "<documents>\n"
    for index, document in enumerate(documents, start=1):
        user_message += f"<document {index}>\n{document.strip()}\n</document {index}>\n"
    user_message += "</documents>\n\n"

    return user_message + "User query: " + query


def analyze_text(query, documents):

    user_message = format_user_message(query, documents)

    print(user_message)

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini-2024-07-18",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
    )

    return completion.choices[0].message.content


def split_text(texts, chunk_size=1024):
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


def create_embeddings(
    texts,
):
    texts_embeddings = []

    results = openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=texts,
        encoding_format="float",
    )
    for text, embeddings in zip(texts, results.data):
        texts_embeddings.append({"text": text, "embedding": embeddings.embedding})

    return texts_embeddings


def similarity_search(query, texts_embeddings, top_n=20):
    def cosine_similarity(a, b):
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        return dot_product / (norm_a * norm_b)

    results = []
    common_words = ["Corrupção", "Fraude", "Suborno", "Escandalos", "Multas"]

    for word in common_words:
        query_embedding = openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=query + " " + word,
            encoding_format="float",
        )

        query_embedding = query_embedding.data[0].embedding
        similarities = np.array(
            [
                cosine_similarity(query_embedding, emb["embedding"])
                for emb in texts_embeddings
            ]
        )

        top_n_indices = similarities.argsort()[-top_n:][::-1]
        results.extend([texts_embeddings[i]["text"] for i in top_n_indices])

    results = list(set(results))

    return results


def rerank_documents(query, documents, top_n=10):
    response = cohere_client.rerank(
        model="rerank-v3.5",
        query=query,
        documents=documents,
        top_n=top_n,
    )

    reranked_documents = [documents[result.index] for result in response.results]
    return reranked_documents


def google_search(query):
    results = []
    seen_links = set()

    search = GoogleSerperAPIWrapper(serper_api_key=SERP_API_KEY)
    search.gl = "br"
    search.hl = "pt-br"
    search.k = 10

    common_words = ["Corrupção", "Fraude", "Suborno", "Escandalos", "Multas"]
    for word in common_words:
        result = search.results(query + " " + word)
        if result["organic"]:
            for item in result["organic"]:
                if item["link"] not in seen_links:
                    results.append(item)
                    seen_links.add(item["link"])

    return results


def extract_text_from_pdf(pdf_data):
    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_data))
        return "\n".join(
            page.extract_text() for page in pdf_reader.pages if page.extract_text()
        )
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return None


def extract_text_from_doc(doc_content, content_type):
    if "wordprocessingml.document" in content_type:
        doc = Document(BytesIO(doc_content))
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])
    else:
        logger.error("Unsupported document type")
        return None


def extract_text_from_html(url):
    loader = WebBaseLoader(url)
    docs = loader.load()
    return docs[0].page_content


async def scrape_content(search_results):
    scraped_data = {}

    async with aiohttp.ClientSession() as session:
        for result in search_results:
            url = result.get("link")
            title = result.get("title")

            try:
                async with session.get(url) as response:
                    content_type = response.headers.get("Content-Type", "").lower()
                    logger.info(f"Content-Type: {content_type}")
                    if "pdf" in content_type:
                        pdf_content = await response.read()
                        text = extract_text_from_pdf(pdf_content)
                    elif "html" in content_type:
                        text = extract_text_from_html(url)
                    elif (
                        "msword" in content_type
                        or "wordprocessingml.document" in content_type
                    ):
                        doc_content = await response.read()
                        text = extract_text_from_doc(doc_content, content_type)

                    else:
                        text = None
                    scraped_data[url] = {"title": title, "text": text}
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                scraped_data[url] = None

    return scraped_data


def validate_cnpj(cnpj):
    """Validate the CNPJ format (Brazilian business number)."""
    cnpj_regex = r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$"
    return re.match(cnpj_regex, cnpj) is not None


async def run_search(query):
    results = google_search(query)

    if not results:
        return None

    scraped_data = await scrape_content(results)

    embeddings = []
    for url, data in scraped_data.items():
        if data:
            logger.info(f"URL: {url}")
            logger.info(f"Title: {data['title']}")
            documents = split_text(data["text"])
            search_embedding = create_embeddings(documents)
            embeddings.extend(search_embedding)

    similar_documents = similarity_search(query, embeddings, top_n=30)
    reranked_documents = rerank_documents(query, similar_documents, top_n=15)
    analysis = analyze_text(query, reranked_documents)

    return {"results": results, "analysis": analysis}


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
