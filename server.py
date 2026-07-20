"""
server.py
=========
FastAPI backend for the JS/TS web interface (frontend/). Wraps the
retrieval + ingestion logic so the frontend only talks HTTP/JSON.

Installation:
    pip install fastapi uvicorn python-multipart

Run:
    uvicorn server:app --reload
Then open http://127.0.0.1:8000

Requires the same .env file used by the other scripts:
    SUPABASE_URL=...
    SUPABASE_KEY=...
    VOYAGE_API_KEY=...
    GROQ_API_KEY=...
"""

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ingestion import ingest_document
from retrieval import ask, supabase

app = FastAPI(title="Square of Youth — Project Analysis Assistant")


@app.get("/health")
def health():
    return {"status": "ok"}


class AskRequest(BaseModel):
    question: str
    n_similar: int = 6
    min_satisfaction: float = 0.0
    use_decomposition: bool = True


def _serialize(items):
    """Sets (e.g. _matched_by) aren't JSON-serializable — convert to sorted lists."""
    serialized = []
    for item in items:
        cleaned = dict(item)
        if "_matched_by" in cleaned:
            cleaned["_matched_by"] = sorted(cleaned["_matched_by"])
        serialized.append(cleaned)
    return serialized


@app.post("/api/ask")
def api_ask(req: AskRequest):
    answer, subqueries, projects, documents = ask(
        req.question,
        n_similar=req.n_similar,
        min_satisfaction=req.min_satisfaction,
        use_decomposition=req.use_decomposition,
    )
    return {
        "answer": answer,
        "subqueries": subqueries,
        "projects": _serialize(projects),
        "documents": _serialize(documents),
    }


@app.get("/api/documents")
def api_documents():
    response = supabase.table("documents").select("title, source_type, chunk_index").execute()
    titles = {}
    for row in response.data:
        entry = titles.setdefault(row["title"], {"source_type": row["source_type"], "chunks": 0})
        entry["chunks"] += 1
    return {"documents": [{"title": title, **info} for title, info in titles.items()]}


@app.post("/api/upload")
def api_upload(source_type: str = Form(...), files: list[UploadFile] = File(...)):
    results = []
    for uploaded in files:
        title = Path(uploaded.filename).stem
        temp_path = Path(tempfile.gettempdir()) / uploaded.filename
        temp_path.write_bytes(uploaded.file.read())
        try:
            result = ingest_document(temp_path, title, source_type)
        finally:
            temp_path.unlink(missing_ok=True)
        results.append({"title": title, **result})
    return {"results": results}


# Static frontend (index.html, styles.css, main.js) — mounted last so
# the /api/* routes above take precedence.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
