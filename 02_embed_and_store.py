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


# ── Fonction : construire le texte à embedder ────────────────
def build_text_for_embedding(project: dict) -> str:
    """
    On construit un texte riche qui capture TOUTES les dimensions
    importantes du projet. Plus ce texte est descriptif,
    meilleure sera la recherche sémantique.
    """
    countries = ", ".join(project.get("partner_countries") or [])
    tags      = ", ".join(project.get("theme_tags") or [])

    return f"""
Projet : {project['name']}
Type : {project['project_type']}
Pays hôte : {project.get('host_country', '')}
Pays partenaires : {countries}
Nombre de pays : {project.get('nb_countries', '')}
Durée : {project.get('duration_days', '')} jours
Participants : {project.get('nb_participants', '')}
Thématique : {project.get('theme', '')}
Mots-clés : {tags}
Objectifs : {project.get('objectives', '')}
Score de satisfaction : {project.get('satisfaction_score', '')}/5
Taux de complétion : {project.get('completion_rate', '')}%
Points forts : {project.get('strengths', '')}
Points faibles : {project.get('weaknesses', '')}
Leçons apprises : {project.get('lessons', '')}
    """.strip()


# ── Fonction : générer un embedding ─────────────────────────
def get_embedding(text: str) -> list[float]:
    """
    voyage-multilingual-2 : le meilleur modèle Voyage pour
    du texte mélangé français/anglais/hongrois.
    """
    result = voyage.embed(
        texts=[text],
        model="voyage-multilingual-2",
        input_type="document"   # 'document' pour indexation
    )
    return result.embeddings[0]


# ── Fonction : mettre à jour l'embedding d'un projet ────────
def embed_project(project_id: int) -> bool:
    """
    Récupère un projet depuis Supabase, génère son embedding,
    le sauvegarde.
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

    # 2. Construire le texte
    text = build_text_for_embedding(project)
    print(f"  → Texte construit ({len(text)} caractères)")

    # 3. Générer l'embedding
    embedding = get_embedding(text)
    print(f"  → Embedding généré ({len(embedding)} dimensions)")

    # 4. Sauvegarder dans Supabase
    supabase.table("projects").update(
        {"embedding": embedding}
    ).eq("id", project_id).execute()

    print(f"  ✓ Projet {project_id} — '{project['name']}' indexé")
    return True


# ── Fonction : indexer TOUS les projets sans embedding ───────
def embed_all_missing():
    response = (
        supabase.table("projects")
        .select("id, name")
        .is_("embedding", "null")
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

    # 2. Appeler la fonction SQL de recherche
    response = supabase.rpc("search_similar_projects", {
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
        print(f"  [{sim_pct}% similaire] {r['name']}")
        print(f"    Score : {r['satisfaction_score']}/5 | "
              f"{r['nb_participants']} participants | "
              f"{r['duration_days']} jours")
        print(f"    Forces : {r['strengths'][:80]}...")
        print()
