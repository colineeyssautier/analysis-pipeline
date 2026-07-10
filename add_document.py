"""
04_add_document.py
===================
Ingests any reference PDF (EU guidelines, articles, notes...)
into the knowledge base. Just drop PDFs in the INPUT_FOLDER
and run this script — no need to modify any code.

Usage:
    1. Put your PDF(s) in the folder below
    2. Run: python 04_add_document.py
    3. Move processed PDFs anywhere you like (they're now in the DB)
"""

import os
import re
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client
import voyageai
import pdfplumber

load_dotenv()

INPUT_FOLDER = r"C:\Users\colin\OneDrive\Dokumente\SOYA\data_processing\new_documents"
CHUNK_SIZE = 1500       # characters per chunk
CHUNK_OVERLAP = 200

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])


def extract_text(pdf_path: Path) -> str:
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n\n".join(text_parts)


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


def add_document(pdf_path: Path, source_type: str = "reference"):
    title = pdf_path.stem

    if already_ingested(title):
        print(f"  Skipped (already in database): {title}")
        return

    print(f"Processing: {title}")
    text = extract_text(pdf_path)
    if not text.strip():
        print(f"  [!] No extractable text in {title} (scanned PDF? needs OCR)")
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


def main():
    folder = Path(INPUT_FOLDER)
    folder.mkdir(exist_ok=True)

    pdf_files = list(folder.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {INPUT_FOLDER}")
        print("Drop your reference PDFs there and run this script again.")
        return

    print(f"{len(pdf_files)} PDF(s) found\n")
    for pdf_path in pdf_files:
        add_document(pdf_path)

    print("Done.")


if __name__ == "__main__":
    main()