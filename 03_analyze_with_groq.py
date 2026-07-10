"""
03_generate_report.py
======================
Interactive tool: ask any question about project viability,
risks, or patterns, based on Square of Youth's past projects
and any reference documents added to the system.

Installation:
    pip install groq

Environment variable to add to your existing .env:
    GROQ_API_KEY=your_groq_key
"""

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


# ── Projects (Square of Youth's own past projects) ──────────

def find_similar_projects(query: str, n_results: int = 6, min_satisfaction: float = 0.0, project_type: str = None) -> list[dict]:
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


def build_context_from_projects(projects: list[dict]) -> str:
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

def find_similar_documents(query: str, n_results: int = 4) -> list[dict]:
    result = voyage.embed(texts=[query], model="voyage-multilingual-2", input_type="query")
    query_embedding = result.embeddings[0]

    response = supabase.rpc("search_similar_documents", {
        "query_embedding": query_embedding,
        "match_count": n_results,
    }).execute()

    return response.data


def build_context_from_documents(documents: list[dict]) -> str:
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

def ask(question: str, n_similar: int = 6, min_satisfaction: float = 0.0) -> str:
    """
    Answers any free-form question about project viability, risk,
    or patterns, grounded in Square of Youth's own past projects
    and any reference documents added to the system.
    """
    print(f"\nSearching for relevant past projects and reference documents...\n")

    similar_projects = find_similar_projects(query=question, n_results=n_similar, min_satisfaction=min_satisfaction)
    similar_documents = find_similar_documents(query=question, n_results=4)

    print(f"{len(similar_projects)} relevant projects found, {len(similar_documents)} relevant reference documents found\n")

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

    return response.choices[0].message.content


def interactive_loop():
    print("=" * 60)
    print("Square of Youth — Project Analysis Assistant")
    print("=" * 60)
    print("Ask anything about project viability, risks, or patterns.")
    print("You can write your question in any language, and include")
    print("as much project detail as you want. Type 'exit' to quit.\n")

    while True:
        question = input("Your question:\n> ").strip()
        if question.lower() in ("exit", "quit", "q"):
            print("Goodbye.")
            break
        if not question:
            continue

        answer = ask(question)

        print("\n" + "=" * 60)
        print("ANALYSIS")
        print("=" * 60)
        print(answer)
        print("\n")


if __name__ == "__main__":
    interactive_loop()