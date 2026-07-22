"""
ingestion.py
============
Document ingestion pipeline (PDF -> text -> chunks -> embeddings -> Supabase).
Used by server.py (FastAPI web interface).
"""

import time

import pdfplumber
from voyageai.error import RateLimitError

from retrieval import supabase, voyage

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
EMBED_BATCH_SIZE = 10
EMBED_MAX_RETRIES = 3
EMBED_RETRY_DELAY = 25  # seconds, matches 02_embed_and_store.py's rate-limit backoff


def extract_text(pdf_path):
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n\n".join(text_parts)


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return [c for c in chunks if c.strip()]


def already_ingested(title):
    response = supabase.table("documents").select("id").eq("title", title).limit(1).execute()
    return len(response.data) > 0


def ingest_document(file_path, title, source_type, progress_callback=None):
    if already_ingested(title):
        return {"status": "skipped", "reason": "already in database", "chunks": 0}

    text = extract_text(file_path)
    if not text.strip():
        return {"status": "failed", "reason": "no extractable text (scanned PDF? needs OCR)", "chunks": 0}

    chunks = chunk_text(text)
    print(f"Processing: {title} ({len(chunks)} chunks)")

    for batch_start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[batch_start:batch_start + EMBED_BATCH_SIZE]
        for attempt in range(EMBED_MAX_RETRIES):
            try:
                result = voyage.embed(texts=batch, model="voyage-multilingual-2", input_type="document")
                break
            except RateLimitError:
                if attempt == EMBED_MAX_RETRIES - 1:
                    raise
                print(f"  Rate limit, attente {EMBED_RETRY_DELAY}s (tentative {attempt + 1}/{EMBED_MAX_RETRIES})...")
                time.sleep(EMBED_RETRY_DELAY)
        rows = [
            {
                "title": title,
                "source_type": source_type,
                "chunk_index": batch_start + i,
                "content": chunk,
                "embedding": embedding,
            }
            for i, (chunk, embedding) in enumerate(zip(batch, result.embeddings))
        ]
        supabase.table("documents").insert(rows).execute()
        if progress_callback:
            progress_callback(min(batch_start + EMBED_BATCH_SIZE, len(chunks)), len(chunks))

    print(f"  -> Ingested ({len(chunks)} chunks)")
    return {"status": "success", "reason": None, "chunks": len(chunks)}
