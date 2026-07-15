"""
add_website.py
===============
Ingests web pages (EU guideline pages, articles, blog posts...) into
the knowledge base, the same way add_document.py does for PDFs.

Usage:
    1. Add one URL per line to new_websites.txt (lines starting with
       # are ignored). Create the file if it doesn't exist yet.
    2. Run: python add_website.py
    3. Already-ingested URLs are skipped automatically on future runs.
"""

import os
import re
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client
import voyageai
import requests
from bs4 import BeautifulSoup

load_dotenv()

URLS_FILE = r"C:\Users\colin\OneDrive\Dokumente\SOYA\data_processing\new_websites.txt"
CHUNK_SIZE = 1500       # characters per chunk
CHUNK_OVERLAP = 200
REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; SquareOfYouthBot/1.0)"

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])


def fetch_page(url: str):
    """Downloads a URL and returns (title, main_text)."""
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    page_title = soup.title.string.strip() if soup.title and soup.title.string else url
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    clean_text = "\n".join(line for line in lines if line)

    return page_title, clean_text


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Splits text into overlapping chunks so context isn't lost at boundaries."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return [c for c in chunks if c.strip()]


def already_ingested(title: str) -> bool:
    response = supabase.table("documents").select("id").eq("title", title).limit(1).execute()
    return len(response.data) > 0


def add_website(url: str, source_type: str = "website"):
    title = f"{url}"

    if already_ingested(title):
        print(f"  Skipped (already in database): {url}")
        return

    print(f"Processing: {url}")
    try:
        page_title, text = fetch_page(url)
    except requests.RequestException as e:
        print(f"  [!] Could not fetch {url}: {e}")
        return

    if not text.strip():
        print(f"  [!] No extractable text on {url}")
        return

    title = f"{page_title} ({url})"
    if already_ingested(title):
        print(f"  Skipped (already in database): {url}")
        return

    chunks = chunk_text(text)
    print(f"  {len(chunks)} chunks to embed")

    for i, chunk in enumerate(chunks):
        result = voyage.embed(texts=[chunk], model="voyage-multilingual-2", input_type="document")
        embedding = result.embeddings[0]

        supabase.table("documents").insert({
            "title": title,
            "source_type": source_type,
            "chunk_index": i,
            "content": chunk,
            "embedding": embedding,
        }).execute()

    print(f"  -> Ingested ({len(chunks)} chunks)\n")


def read_urls(path: Path) -> list[str]:
    if not path.exists():
        return []
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def main():
    path = Path(URLS_FILE)
    urls = read_urls(path)

    if not urls:
        path.touch(exist_ok=True)
        print(f"No URLs found in {URLS_FILE}")
        print("Add one URL per line to that file and run this script again.")
        return

    print(f"{len(urls)} URL(s) found\n")
    for url in urls:
        add_website(url)

    print("Done.")


if __name__ == "__main__":
    main()
