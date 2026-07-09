import os
import time
from dotenv import load_dotenv
from supabase import create_client
import voyageai

load_dotenv()

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])


def search_projects(
    query: str,
    n_results: int = 5,
    min_satisfaction: float = 0.0,
    project_type: str = None
) -> list[dict]:
    """
    Recherche les projets les plus similaires a une question.

    Exemples de requetes :
    - "youth exchange avec bonne cohesion de groupe"
    - "workshop sur les droits numeriques"
    - "projet avec budget maitrise et participants motives"
    """
    print(f"Recherche : '{query}'")

    result = voyage.embed(
        texts=[query],
        model="voyage-multilingual-2",
        input_type="query"
    )
    query_embedding = result.embeddings[0]

    response = supabase.rpc("search_similar_projects", {
        "query_embedding": query_embedding,
        "match_count": n_results,
        "min_satisfaction": min_satisfaction,
        "project_type_filter": project_type,
        "min_date": None
    }).execute()

    return response.data


if __name__ == "__main__":
    results = search_projects(
        query="youth exchange réussi avec bonne dynamique interculturelle",
        n_results=3,
        min_satisfaction=4.0
    )

    print(f"\n→ {len(results)} projets trouvés :\n")
    for r in results:
        sim_pct = round(r['similarity'] * 100, 1)
        print(f"  [{sim_pct}% similaire] {r['name']}")
        print(f"    Score : {r['satisfaction_score']}/5 | "
              f"{r['nb_participants']} participants | "
              f"{r['duration_days']} jours")
        strengths = r.get('strengths') or ''
        print(f"    Forces : {strengths[:80]}...")
        print()