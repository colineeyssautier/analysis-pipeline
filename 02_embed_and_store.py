"""
02_embed_and_store.py
=====================
Génère les embeddings de vos projets via Voyage AI
et les stocke dans Supabase.

Installation :
    pip install supabase voyageai python-dotenv

Variables d'environnement à créer dans un fichier .env :
    SUPABASE_URL=https://xxxx.supabase.co
    SUPABASE_KEY=votre_clé_anon
    VOYAGE_API_KEY=votre_clé_voyage
"""

import os
import time
from dotenv import load_dotenv
from supabase import create_client
import voyageai

load_dotenv()

# ── Connexions ──────────────────────────────────────────────
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
voyage   = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])


# ── Fonctions : construire les textes à embedder (une par facette) ──
#
# Au lieu d'un seul embedding qui mélange toutes les dimensions du
# projet (thématique, logistique, qualitatif), on en construit trois
# distincts. Cela évite qu'une recherche sur un aspect précis (ex :
# "budget maîtrisé") soit diluée par le reste du texte du projet.

def build_thematic_text(project: dict) -> str:
    tags = ", ".join(project.get("theme_tags") or [])
    return f"""
Projet : {project['name']}
Type : {project['project_type']}
Thématique : {project.get('theme', '')}
Mots-clés : {tags}
Objectifs : {project.get('objectives', '')}
    """.strip()


def build_logistics_text(project: dict) -> str:
    countries = ", ".join(project.get("partner_countries") or [])
    return f"""
Projet : {project['name']}
Pays hôte : {project.get('host_country', '')}
Pays partenaires : {countries}
Nombre de pays : {project.get('nb_countries', '')}
Durée : {project.get('duration_days', '')} jours
Participants : {project.get('nb_participants', '')}
Tranche d'âge : {project.get('age_range_min', '')}-{project.get('age_range_max', '')}
Budget prévu : {project.get('budget_planned', '')}
Budget réel : {project.get('budget_actual', '')}
    """.strip()


def build_qualitative_text(project: dict) -> str:
    return f"""
Projet : {project['name']}
Score de satisfaction : {project.get('satisfaction_score', '')}/5
Taux de complétion : {project.get('completion_rate', '')}%
Points forts : {project.get('strengths', '')}
Points faibles : {project.get('weaknesses', '')}
Leçons apprises : {project.get('lessons', '')}
Notes : {project.get('notes', '')}
    """.strip()


# ── Fonction : générer les 3 embeddings d'un projet ─────────
def get_facet_embeddings(project: dict) -> dict:
    """
    Un seul appel Voyage groupant les 3 textes (pas 3 appels séparés),
    pour ne pas tripler la consommation de l'API ni le temps de
    backfill par rapport à l'ancien embedding unique.
    """
    texts = [
        build_thematic_text(project),
        build_logistics_text(project),
        build_qualitative_text(project),
    ]
    result = voyage.embed(texts=texts, model="voyage-multilingual-2", input_type="document")
    return {
        "embedding_thematic":    result.embeddings[0],
        "embedding_logistics":   result.embeddings[1],
        "embedding_qualitative": result.embeddings[2],
    }


# ── Fonction : mettre à jour les embeddings d'un projet ─────
def embed_project(project_id: int) -> bool:
    """
    Récupère un projet depuis Supabase, génère ses 3 embeddings
    de facette, les sauvegarde.
    """
    # 1. Récupérer le projet
    response = (
        supabase.table("projects")
        .select("*")
        .eq("id", project_id)
        .single()
        .execute()
    )
    project = response.data
    if not project:
        print(f"  ✗ Projet {project_id} introuvable")
        return False

    # 2. Générer les 3 embeddings (thématique / logistique / qualitatif)
    embeddings = get_facet_embeddings(project)
    print(f"  → 3 embeddings générés (thematic/logistics/qualitative)")

    # 3. Sauvegarder dans Supabase
    supabase.table("projects").update(embeddings).eq("id", project_id).execute()

    print(f"  ✓ Projet {project_id} — '{project['name']}' indexé (facettes)")
    return True


# ── Fonction : indexer TOUS les projets sans embedding complet ──
def embed_all_missing():
    response = (
        supabase.table("projects")
        .select("id, name")
        .or_("embedding_thematic.is.null,embedding_logistics.is.null,embedding_qualitative.is.null")
        .execute()
    )
    projects = response.data

    if not projects:
        print("Tous les projets ont déjà un embedding.")
        return

    print(f"→ {len(projects)} projets à indexer\n")

    for i, p in enumerate(projects, 1):
        print(f"[{i}/{len(projects)}] {p['name']}")
        success = False
        for attempt in range(3):
            try:
                embed_project(p["id"])
                success = True
                break
            except Exception as e:
                if "RateLimitError" in str(type(e).__name__) or "rate limit" in str(e).lower():
                    print(f"  Rate limit, attente 25s (tentative {attempt+1}/3)...")
                    time.sleep(25)
                else:
                    print(f"  [!] Erreur : {e}")
                    break
        if not success:
            print(f"  [!] Echec pour le projet {p['id']} apres plusieurs tentatives")

        if i < len(projects):
            time.sleep(21)

    print(f"\n✓ Terminé — traitement complet")


# ── Fonction : recherche sémantique ─────────────────────────
def search_projects(
    query: str,
    n_results: int = 5,
    min_satisfaction: float = 0.0,
    project_type: str = None
) -> list[dict]:
    """
    Recherche les projets les plus similaires à une question.

    Exemples de requêtes :
    - "youth exchange avec bonne cohésion de groupe"
    - "workshop sur les droits numériques"
    - "projet avec budget maîtrisé et participants motivés"
    """
    print(f"Recherche : '{query}'")

    # 1. Embedder la requête (input_type='query' pour la recherche)
    result = voyage.embed(
        texts=[query],
        model="voyage-multilingual-2",
        input_type="query"
    )
    query_embedding = result.embeddings[0]

    # 2. Appeler la fonction SQL de recherche multi-facettes
    response = supabase.rpc("search_projects_by_facets", {
        "query_embedding": query_embedding,
        "match_count": n_results,
        "min_satisfaction": min_satisfaction,
        "project_type_filter": project_type,
        "min_date": None
    }).execute()

    return response.data


# ── Démonstration ────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Square of Youth — Indexation Supabase + pgvector")
    print("=" * 55)

    # Indexer les projets sans embedding
    print("\n[1] Génération des embeddings manquants")
    print("-" * 40)
    embed_all_missing()

    # Exemple de recherche
    print("\n[2] Test de recherche sémantique")
    print("-" * 40)
    results = search_projects(
        query="youth exchange réussi avec bonne dynamique interculturelle",
        n_results=3,
        min_satisfaction=4.0
    )

    print(f"\n→ {len(results)} projets trouvés :\n")
    for r in results:
        sim_pct = round(r['similarity'] * 100, 1)
        print(f"  [{sim_pct}% similaire — facette : {r['best_facet']}] {r['name']}")
        print(f"    thematic={round((r['sim_thematic'] or 0) * 100, 1)}% "
              f"logistics={round((r['sim_logistics'] or 0) * 100, 1)}% "
              f"qualitative={round((r['sim_qualitative'] or 0) * 100, 1)}%")
        print(f"    Score : {r['satisfaction_score']}/5 | "
              f"{r['nb_participants']} participants | "
              f"{r['duration_days']} jours")
        print(f"    Forces : {r['strengths'][:80]}...")
        print()
