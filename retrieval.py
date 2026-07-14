"""
retrieval.py
============
Shared retrieval + analysis logic used by both app.py (Streamlit UI)
and 03_analyze_with_groq.py (CLI). Previously duplicated between the
two — factored out here so it's only written once.

Retrieval pipeline, in three layers:
1. Raw search primitives — vector (facet-aware for projects) and
   full-text search against Supabase, one table/method per function.
2. rrf_merge — Reciprocal Rank Fusion, used both to merge vector +
   fulltext for a single query, and to merge results across the
   multiple sub-questions a question gets decomposed into.
3. ask() — decomposes the question into sub-questions, retrieves for
   each, merges everything, and does one final synthesis call.

Requires the same .env file used by the other scripts:
    SUPABASE_URL=...
    SUPABASE_KEY=...
    VOYAGE_API_KEY=...
    GROQ_API_KEY=...
"""

import concurrent.futures
import json
import os

from dotenv import load_dotenv
from supabase import create_client
import voyageai
from groq import Groq

load_dotenv()

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

MODEL = "llama-3.3-70b-versatile"
DECOMP_MODEL = "llama-3.1-8b-instant"

RRF_K = 60
MAX_SUBQUERIES = 4
MAX_PROJECTS = 8
MAX_DOCUMENTS = 6


def embed_query(query):
    return voyage.embed(texts=[query], model="voyage-multilingual-2", input_type="query").embeddings[0]


# ── Raw search primitives ────────────────────────────────────

def search_projects_vector(query, n_results=MAX_PROJECTS, min_satisfaction=0.0, project_type=None):
    query_embedding = embed_query(query)
    return supabase.rpc("search_projects_by_facets", {
        "query_embedding": query_embedding,
        "match_count": n_results,
        "min_satisfaction": min_satisfaction,
        "project_type_filter": project_type,
        "min_date": None,
    }).execute().data


def search_projects_fulltext(query, n_results=MAX_PROJECTS, min_satisfaction=0.0, project_type=None):
    return supabase.rpc("search_projects_fulltext", {
        "query_text": query,
        "match_count": n_results,
        "min_satisfaction": min_satisfaction,
        "project_type_filter": project_type,
        "min_date": None,
    }).execute().data


def search_documents_vector(query, n_results=MAX_DOCUMENTS):
    query_embedding = embed_query(query)
    return supabase.rpc("search_similar_documents", {
        "query_embedding": query_embedding,
        "match_count": n_results,
    }).execute().data


def search_documents_fulltext(query, n_results=MAX_DOCUMENTS):
    return supabase.rpc("search_documents_fulltext", {
        "query_text": query,
        "match_count": n_results,
    }).execute().data


# ── Reciprocal Rank Fusion ───────────────────────────────────

def rrf_merge(labeled_lists, id_key="id"):
    """
    labeled_lists: [(label, ranked_results), ...] — each ranked_results
    list is already sorted best-first. Returns items deduped by id_key,
    each tagged with `_rrf_score` (sum of 1/(RRF_K+rank) across every
    list it appeared in) and `_matched_by` (labels of every list that
    surfaced it), sorted by `_rrf_score` descending.
    """
    scores = {}
    items = {}
    for label, results in labeled_lists:
        for rank, item in enumerate(results, start=1):
            item_id = item[id_key]
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (RRF_K + rank)
            entry = items.setdefault(item_id, {**item, "_matched_by": set()})
            entry["_matched_by"].add(label)
    merged = list(items.values())
    for it in merged:
        it["_rrf_score"] = scores[it[id_key]]
    merged.sort(key=lambda it: it["_rrf_score"], reverse=True)
    return merged


# ── Projects (Square of Youth's own past projects) ──────────

def find_similar_projects(query, n_results=MAX_PROJECTS, min_satisfaction=0.0, project_type=None):
    """Single-query hybrid search: facet-vector + full-text, merged via RRF."""
    vector_hits = search_projects_vector(query, n_results, min_satisfaction, project_type)
    fulltext_hits = search_projects_fulltext(query, n_results, min_satisfaction, project_type)
    return rrf_merge([("vector", vector_hits), ("fulltext", fulltext_hits)])[:n_results]


def build_context_from_projects(projects):
    if not projects:
        return "No similar project found in the history."
    blocks = []
    for i, p in enumerate(projects, 1):
        matched_by = ", ".join(sorted(p.get("_matched_by", []))) or "n/a"
        facet = p.get("best_facet")
        facet_note = f", best-matching facet: {facet}" if facet else ""
        blocks.append(f"""
Project {i} (matched via: {matched_by}{facet_note})
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

def find_similar_documents(query, n_results=MAX_DOCUMENTS):
    """Single-query hybrid search: vector + full-text, merged via RRF."""
    vector_hits = search_documents_vector(query, n_results)
    fulltext_hits = search_documents_fulltext(query, n_results)
    return rrf_merge([("vector", vector_hits), ("fulltext", fulltext_hits)])[:n_results]


def build_context_from_documents(documents):
    if not documents:
        return "No reference document found."
    blocks = []
    for i, d in enumerate(documents, 1):
        matched_by = ", ".join(sorted(d.get("_matched_by", []))) or "n/a"
        blocks.append(f"""
Reference {i} (matched via: {matched_by}) — from "{d.get('title', 'N/A')}" ({d.get('source_type', 'N/A')})
{d.get('content', '')}
""".strip())
    return "\n\n".join(blocks)


# ── Query decomposition ──────────────────────────────────────

DECOMPOSITION_PROMPT = """You are a research assistant helping decompose a question about EU-funded youth exchange projects into focused sub-questions.

Given the question below, break it into 2 to {max_subqueries} sub-questions that each explore a DIFFERENT angle relevant to answering it well (for example, but not limited to: thematic fit, logistics/feasibility, historical outcomes or risks, budget, participant profile, partner-country dynamics). Only include angles that are actually relevant to THIS question — do not force a fixed template, and do not produce near-duplicate sub-questions.

Question: "{question}"

Respond with ONLY a JSON object of the form {{"subquestions": ["...", "..."]}}, no other text.
"""


def decompose_question(question):
    try:
        kwargs = dict(
            model=DECOMP_MODEL,
            messages=[{"role": "user", "content": DECOMPOSITION_PROMPT.format(
                question=question, max_subqueries=MAX_SUBQUERIES)}],
            max_tokens=300,
            temperature=0.3,
        )
        try:
            response = groq_client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
        except Exception:
            response = groq_client.chat.completions.create(**kwargs)

        raw = response.choices[0].message.content.strip().strip("`")
        data = json.loads(raw)
        subqueries = data["subquestions"] if isinstance(data, dict) else data
        if not isinstance(subqueries, list) or not all(isinstance(s, str) and s.strip() for s in subqueries):
            raise ValueError("decomposition did not return a list of non-empty strings")
        subqueries = [s.strip() for s in subqueries][:MAX_SUBQUERIES]
        if not subqueries:
            raise ValueError("empty decomposition")
        return subqueries
    except Exception as e:
        print(f"[decompose_question] falling back to single query: {e}")
        return [question]


def retrieve_for_question(question, n_projects=MAX_PROJECTS, n_documents=MAX_DOCUMENTS,
                           min_satisfaction=0.0, project_type=None, use_decomposition=True):
    subqueries = decompose_question(question) if use_decomposition else [question]

    tasks = {}
    project_labeled_lists = []
    document_labeled_lists = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for i, sq in enumerate(subqueries, start=1):
            tasks[pool.submit(search_projects_vector, sq, n_projects, min_satisfaction, project_type)] = (f"sq{i}:vector", "projects")
            tasks[pool.submit(search_projects_fulltext, sq, n_projects, min_satisfaction, project_type)] = (f"sq{i}:fulltext", "projects")
            tasks[pool.submit(search_documents_vector, sq, n_documents)] = (f"sq{i}:vector", "documents")
            tasks[pool.submit(search_documents_fulltext, sq, n_documents)] = (f"sq{i}:fulltext", "documents")

        for future in concurrent.futures.as_completed(tasks):
            label, table = tasks[future]
            try:
                results = future.result()
            except Exception as e:
                print(f"[retrieve_for_question] {label}/{table} failed: {e}")
                results = []
            (project_labeled_lists if table == "projects" else document_labeled_lists).append((label, results))

    merged_projects = rrf_merge(project_labeled_lists)[:n_projects]
    merged_documents = rrf_merge(document_labeled_lists)[:n_documents]
    return subqueries, merged_projects, merged_documents


# ── Main analysis function ───────────────────────────────────

def ask(question, n_similar=MAX_PROJECTS, n_documents=MAX_DOCUMENTS,
        min_satisfaction=0.0, project_type=None, use_decomposition=True):
    subqueries, similar_projects, similar_documents = retrieve_for_question(
        question, n_projects=n_similar, n_documents=n_documents,
        min_satisfaction=min_satisfaction, project_type=project_type,
        use_decomposition=use_decomposition,
    )

    project_context = build_context_from_projects(similar_projects)
    document_context = build_context_from_documents(similar_documents)
    subquery_block = (
        "\n".join(f"- {sq}" for sq in subqueries)
        if len(subqueries) > 1 else "(no decomposition — question used as-is)"
    )

    prompt = f"""You are an analyst supporting Square of Youth, an NGO coordinating EU-funded Erasmus+ youth exchanges.

You have access to two types of sources:
1. Square of Youth's own past projects (grant applications and feedback)
2. Reference documents that may include official guidelines, criteria, or other knowledge added to the system

The question or scenario being asked:
"{question}"

To gather evidence, the question was explored from these angles:
{subquery_block}

PAST PROJECTS (each tagged with which angle/method surfaced it):
{project_context}

REFERENCE DOCUMENTS (each tagged with which angle/method surfaced it):
{document_context}

Instructions:
- Answer in English, regardless of the language of the question.
- Clearly distinguish between claims based on Square of Youth's own project history versus claims based on reference documents (official guidelines etc.) — cite which source each point comes from.
- Weave together the different angles explored above where relevant.
- If a specific angle above has no supporting evidence in the sources, say so explicitly rather than speculating.
- Structure your answer with clear sections appropriate to the question.
- Be concise but substantive.
"""

    response = groq_client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1800,
    )
    return response.choices[0].message.content, subqueries, similar_projects, similar_documents
