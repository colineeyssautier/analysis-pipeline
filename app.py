"""
app.py
======
Square of Youth — Project Analysis Assistant (Streamlit interface)

Two features:
1. Ask any question about project viability, risks, or patterns.
2. Upload reference documents (PDFs) — they are automatically
   chunked, embedded, and added to the knowledge base. No code
   changes needed to add new sources.

Installation:
    pip install streamlit groq voyageai supabase python-dotenv pdfplumber

Run:
    streamlit run app.py

Requires the same .env file used by your other scripts:
    SUPABASE_URL=...
    SUPABASE_KEY=...
    VOYAGE_API_KEY=...
    GROQ_API_KEY=...
"""

import os
import time
from pathlib import Path

import streamlit as st
import pdfplumber

from retrieval import supabase, voyage, ask

st.set_page_config(page_title="Square of Youth — Project Analysis", page_icon="🌍", layout="wide")

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


# ── Document ingestion (used by the upload feature) ──────────

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
        if progress_callback:
            progress_callback(i + 1, len(chunks))

    return {"status": "success", "reason": None, "chunks": len(chunks)}


# ── Streamlit UI ──────────────────────────────────────────────

st.title("🌍 Square of Youth — Project Analysis Assistant")

tab_ask, tab_upload = st.tabs(["💬 Ask a question", "📄 Add reference documents"])

# --- Tab 1: Q&A ---
with tab_ask:
    st.write(
        "Ask anything about project viability, risks, or patterns. "
        "You can write your question in any language and include as much project detail as you want."
    )

    if "history" not in st.session_state:
        st.session_state.history = []

    with st.form("ask_form", clear_on_submit=True):
        question = st.text_area("Your question", height=120, placeholder="e.g. What are the main risks for a Youth Exchange on climate activism with 30 participants over 7 days?")
        col1, col2 = st.columns(2)
        with col1:
            min_satisfaction = st.slider("Minimum satisfaction score of referenced past projects", 0.0, 5.0, 0.0, 0.5)
        with col2:
            n_similar = st.slider("Number of past projects to consider", 1, 10, 6)
        use_decomposition = st.checkbox(
            "Use multi-angle query decomposition (slower, more thorough)",
            value=True,
            help="Splits your question into a few focused sub-questions (e.g. thematic fit, logistics, budget) and retrieves evidence for each before answering, instead of a single search.",
        )
        submitted = st.form_submit_button("Ask")

    if submitted and question.strip():
        with st.spinner("Searching past projects and reference documents, then generating analysis..."):
            answer, subqueries, projects, documents = ask(
                question, n_similar=n_similar, min_satisfaction=min_satisfaction,
                use_decomposition=use_decomposition,
            )
        st.session_state.history.insert(0, {
            "question": question,
            "answer": answer,
            "subqueries": subqueries,
            "projects": projects,
            "documents": documents,
        })

    for entry in st.session_state.history:
        with st.container(border=True):
            st.markdown(f"**Q: {entry['question']}**")
            st.caption(f"Based on {len(entry['projects'])} similar past project(s) and {len(entry['documents'])} reference document chunk(s)")
            st.markdown(entry["answer"])
            with st.expander("How this answer was built"):
                st.markdown("**Angles explored:**")
                if len(entry["subqueries"]) > 1:
                    for sq in entry["subqueries"]:
                        st.write(f"- {sq}")
                else:
                    st.write("(no decomposition — question used as-is)")
                st.markdown("**Matched projects:**")
                for p in entry["projects"]:
                    matched_by = ", ".join(sorted(p.get("_matched_by", []))) or "n/a"
                    facet = f", best facet: {p['best_facet']}" if p.get("best_facet") else ""
                    st.write(f"- {p['name']} — matched via {matched_by}{facet}")
                st.markdown("**Matched reference chunks:**")
                if entry["documents"]:
                    for d in entry["documents"]:
                        matched_by = ", ".join(sorted(d.get("_matched_by", []))) or "n/a"
                        st.write(f"- {d['title']} (chunk {d['chunk_index']}) — matched via {matched_by}")
                else:
                    st.write("(none)")

# --- Tab 2: Document upload ---
with tab_upload:
    st.write(
        "Upload any reference PDF (official guidelines, criteria, articles, internal notes...). "
        "It is automatically split into chunks, embedded, and added to the knowledge base — "
        "no code changes needed. Already-ingested documents (same title) are skipped automatically."
    )

    source_type = st.selectbox(
        "Document type",
        ["reference", "eu_guideline", "article", "internal_note", "other"],
        help="Used to label the source when the assistant cites it in an answer."
    )

    uploaded_files = st.file_uploader(
        "Choose PDF file(s)",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files and st.button("Process and add to knowledge base"):
        results = []
        for uploaded_file in uploaded_files:
            title = Path(uploaded_file.name).stem
            temp_path = Path(f"/tmp/{uploaded_file.name}")
            temp_path.write_bytes(uploaded_file.getbuffer())

            status_placeholder = st.empty()
            progress_bar = st.progress(0)

            def update_progress(done, total):
                progress_bar.progress(done / total)
                status_placeholder.text(f"{title}: embedding chunk {done}/{total}")

            status_placeholder.text(f"Processing {title}...")
            result = ingest_document(temp_path, title, source_type, progress_callback=update_progress)
            results.append((title, result))

            progress_bar.empty()
            status_placeholder.empty()

            temp_path.unlink(missing_ok=True)

        for title, result in results:
            if result["status"] == "success":
                st.success(f"✅ {title}: added ({result['chunks']} chunks)")
            elif result["status"] == "skipped":
                st.info(f"⏭️ {title}: skipped ({result['reason']})")
            else:
                st.error(f"❌ {title}: failed ({result['reason']})")

    st.divider()
    st.subheader("Documents currently in the knowledge base")
    try:
        docs_response = supabase.table("documents").select("title, source_type, chunk_index").execute()
        titles = {}
        for row in docs_response.data:
            titles.setdefault(row["title"], {"source_type": row["source_type"], "chunks": 0})
            titles[row["title"]]["chunks"] += 1
        if titles:
            for title, info in titles.items():
                st.write(f"- **{title}** ({info['source_type']}) — {info['chunks']} chunks")
        else:
            st.write("No reference documents added yet.")
    except Exception as e:
        st.error(f"Could not load document list: {e}")