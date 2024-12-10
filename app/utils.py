import io
import logging

import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)


def google_search(api_key, query):
    headers = {
        "X-API-KEY": api_key,
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
