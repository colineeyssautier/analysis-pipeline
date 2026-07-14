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
from dotenv import load_dotenv
from supabase import create_client
import voyageai
from groq import Groq
import pdfplumber

st.set_page_config(page_title="Square of Youth — Project Analysis", page_icon="🌍", layout="wide")

load_dotenv()

MODEL = "llama-3.3-70b-versatile"
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


@st.cache_resource
def get_clients():
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return supabase, voyage, groq_client


supabase, voyage, groq_client = get_clients()


# ── Projects (Square of Youth's own past projects) ──────────

def find_similar_projects(query, n_results=6, min_satisfaction=0.0, project_type=None):
    result = voyage.embed(texts=[query], model="voyage-multilingual-2", input_type="query")
    query_embedding = result.embeddings[0]
    response = supabase.rpc("search_similar_projects", {
        "query_embedding": query_embedding,
        "match_count": n_results,
        "min_satisfaction": min_satisfaction,
        "project_type_filter": project_type,
        "min_date": None
    }).execute()
    return response.data


def build_context_from_projects(projects):
    if not projects:
        return "No similar project found in the history."
    blocks = []
    for i, p in enumerate(projects, 1):
        sim_pct = round(p.get("similarity", 0) * 100, 1)
        blocks.append(f"""
Project {i} (similarity: {sim_pct}%)
- Name: {p.get('name', 'N/A')}
- Type: {p.get('project_type', 'N/A')}
- Host country: {p.get('host_country', 'N/A')}
- Partner countries: {', '.join(p.get('partner_countries') or [])}
- Participants: {p.get('nb_participants', 'N/A')}
- Duration: {p.get('duration_days', 'N/A')} days
- Theme: {p.get('theme', 'N/A')}
- Satisfaction score: {p.get('satisfaction_score', 'N/A')}/5
- Strengths: {p.get('strengths', 'N/A')}
- Weaknesses: {p.get('weaknesses', 'N/A')}
- Lessons learned: {p.get('lessons', 'N/A')}
""".strip())
    return "\n\n".join(blocks)


# ── Documents (reference material: guidelines, articles, notes) ──

def find_similar_documents(query, n_results=4):
    result = voyage.embed(texts=[query], model="voyage-multilingual-2", input_type="query")
    query_embedding = result.embeddings[0]
    response = supabase.rpc("search_similar_documents", {
        "query_embedding": query_embedding,
        "match_count": n_results,
    }).execute()
    return response.data


def build_context_from_documents(documents):
    if not documents:
        return "No reference document found."
    blocks = []
    for i, d in enumerate(documents, 1):
        sim_pct = round(d.get("similarity", 0) * 100, 1)
        blocks.append(f"""
Reference {i} (similarity: {sim_pct}%) — from "{d.get('title', 'N/A')}" ({d.get('source_type', 'N/A')})
{d.get('content', '')}
""".strip())
    return "\n\n".join(blocks)


# ── Main analysis function ───────────────────────────────────

def ask(question, n_similar=6, min_satisfaction=0.0):
    similar_projects = find_similar_projects(question, n_results=n_similar, min_satisfaction=min_satisfaction)
    similar_documents = find_similar_documents(question, n_results=4)

    project_context = build_context_from_projects(similar_projects)
    document_context = build_context_from_documents(similar_documents)

    prompt = f"""You are an analyst supporting Square of Youth, an NGO coordinating EU-funded Erasmus+ youth exchanges.

You have access to two types of sources:
1. Square of Youth's own past projects (grant applications and feedback)
2. Reference documents that may include official guidelines, criteria, or other knowledge added to the system

The question or scenario being asked:
"{question}"

PAST PROJECTS:
{project_context}

REFERENCE DOCUMENTS:
{document_context}

Instructions:
- Answer in English, regardless of the language of the question.
- Clearly distinguish between claims based on Square of Youth's own project history versus claims based on reference documents (official guidelines etc.) — cite which source each point comes from.
- If neither source supports a confident answer, say so directly rather than speculating.
- Structure your answer with clear sections appropriate to the question.
- Be concise but substantive.
"""

    response = groq_client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1800,
    )
    return response.choices[0].message.content, len(similar_projects), len(similar_documents)


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
        submitted = st.form_submit_button("Ask")

    if submitted and question.strip():
        with st.spinner("Searching past projects and reference documents, then generating analysis..."):
            answer, n_proj, n_doc = ask(question, n_similar=n_similar, min_satisfaction=min_satisfaction)
        st.session_state.history.insert(0, {
            "question": question,
            "answer": answer,
            "n_proj": n_proj,
            "n_doc": n_doc,
        })

    for entry in st.session_state.history:
        with st.container(border=True):
            st.markdown(f"**Q: {entry['question']}**")
            st.caption(f"Based on {entry['n_proj']} similar past project(s) and {entry['n_doc']} reference document chunk(s)")
            st.markdown(entry["answer"])

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