import io
import logging
import os
import re
import uuid
from io import BytesIO

import aiohttp
import chromadb
import cohere as co
import docx
from langchain_chroma import Chroma
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

SERP_API_KEY = os.getenv("SERPER_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


cohere_client = co.ClientV2(api_key=COHERE_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
open_ai_embeddings = OpenAIEmbeddings(
    model="text-embedding-3-large", openai_api_key=OPENAI_API_KEY
)

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


def create_vector_store(documents):
    chromadb.api.client.SharedSystemClient.clear_system_cache()

    vector_store = Chroma(
        embedding_function=open_ai_embeddings,
    )

    langchain_documents = []
    for i, document in enumerate(documents):
        langchain_documents.append(Document(page_content=document, id=i))

    uuids = [str(uuid.uuid4()) for _ in range(len(documents))]
    vector_store.add_documents(documents=langchain_documents, ids=uuids)
    return vector_store


def similarity_search(query, vector_store, top_n=20):

    results = []
    common_words = ["Corrupção", "Fraude", "Suborno", "Escandalos", "Multas"]

    queries = [query + " " + word for word in common_words]

    for query in queries:
        documents = vector_store.similarity_search(query, k=top_n)
        results.extend(documents)

    results = list(set([doc.page_content for doc in results]))

    return results


def rerank_documents(query, documents, top_n=10):
    common_words = ["Corrupção", "Fraude", "Suborno", "Escandalos", "Multas"]
    queries = [query + " " + word for word in common_words]

    indexes = []
    for query in queries:
        response = cohere_client.rerank(
            model="rerank-v3.5",
            query=query,
            documents=documents,
            top_n=top_n,
        )
        indexes.extend([result.index for result in response.results])

    indexes = list(set(indexes))

    reranked_documents = [documents[index] for index in indexes]
    return reranked_documents


def google_search(query):
    results = []
    seen_links = set()

    search = GoogleSerperAPIWrapper(serper_api_key=SERP_API_KEY)
    search.gl = "br"
    search.hl = "pt-br"
    search.k = 5

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
        doc = docx.Document(BytesIO(doc_content))
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
                    logger.info(
                        f"""
                    URL: {url}
                    Title: {title}
                    """
                    )
                    if "pdf" in content_type:
                        content = await response.read()
                        text = extract_text_from_pdf(content)
                    elif "html" in content_type:
                        text = extract_text_from_html(url)
                    elif (
                        "msword" in content_type
                        or "wordprocessingml.document" in content_type
                    ):
                        content = await response.read()
                        text = extract_text_from_doc(content, content_type)
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

    documents = []
    for url, data in scraped_data.items():
        logger.info(f"URL: {url}")
        if data and data["text"]:
            logger.info(f"Title: {data['title']}")
            documents.extend(split_text(data["text"]))
            continue
        logger.info(f"No text found for URL: {url}")

    vector_store = create_vector_store(documents)
    similiar_documents = similarity_search(query, vector_store, top_n=30)
    reranked_documents = rerank_documents(query, similiar_documents, top_n=15)
    analysis = analyze_text(query, reranked_documents)

    return {"results": results, "analysis": analysis}
