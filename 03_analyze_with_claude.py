"""
03_analyze_with_claude.py
=========================
Utilise la recherche sémantique Supabase pour trouver
les projets pertinents, puis Claude pour analyser les patterns
et évaluer la viabilité d'un nouveau projet.

Installation :
    pip install anthropic supabase voyageai python-dotenv

Variables dans .env :
    ANTHROPIC_API_KEY=votre_clé_anthropic
    SUPABASE_URL=...
    SUPABASE_KEY=...
    VOYAGE_API_KEY=...
"""

import os
import json
from dotenv import load_dotenv
from supabase import create_client
import voyageai
import anthropic

load_dotenv()

supabase  = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
voyage    = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
claude    = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ── Formater un projet pour le prompt ───────────────────────
def format_project_for_prompt(p: dict, rank: int) -> str:
    countries = ", ".join(p.get("partner_countries") or [])
    sim = round(p.get("similarity", 0) * 100, 1)
    return f"""
--- Projet {rank} (similarité : {sim}%) ---
Nom : {p['name']}
Type : {p['project_type']}
Durée : {p.get('duration_days')} jours | Participants : {p.get('nb_participants')}
Pays partenaires : {countries or 'aucun'}
Thématique : {p.get('theme')}
Score de satisfaction : {p.get('satisfaction_score')}/5
Forces : {p.get('strengths')}
Faiblesses : {p.get('weaknesses')}
Leçons apprises : {p.get('lessons')}
""".strip()


# ── Recherche sémantique (réutilisée depuis script 02) ───────
def search_projects(query: str, n: int = 5) -> list[dict]:
    result = voyage.embed(
        texts=[query],
        model="voyage-multilingual-2",
        input_type="query"
    )
    response = supabase.rpc("search_similar_projects", {
        "query_embedding": result.embeddings[0],
        "match_count": n,
        "min_satisfaction": 0,
        "project_type_filter": None,
        "min_date": None
    }).execute()
    return response.data


# ── Analyse principale avec Claude ──────────────────────────
def analyze_new_project(new_project: dict) -> str:
    """
    Analyse la viabilité d'un nouveau projet en le comparant
    aux projets passés les plus similaires.

    new_project : dict décrivant le projet à évaluer
    """

    # 1. Construire une requête de recherche depuis le nouveau projet
    query = f"""
    {new_project.get('project_type', '')} {new_project.get('theme', '')}
    {new_project.get('nb_participants', '')} participants
    {new_project.get('nb_countries', '')} pays
    {new_project.get('duration_days', '')} jours
    """.strip()

    # 2. Trouver les projets passés les plus similaires
    print("→ Recherche des projets similaires...")
    similar = search_projects(query, n=5)
    print(f"  {len(similar)} projets trouvés\n")

    if not similar:
        return "Aucun projet similaire trouvé dans la base. Indexez d'abord vos projets passés."

    # 3. Formater le contexte pour Claude
    projects_context = "\n\n".join(
        format_project_for_prompt(p, i+1)
        for i, p in enumerate(similar)
    )

    new_project_desc = f"""
Nom : {new_project.get('name', 'Nouveau projet')}
Type : {new_project.get('project_type')}
Thématique prévue : {new_project.get('theme')}
Pays hôte prévu : {new_project.get('host_country')}
Pays partenaires prévus : {', '.join(new_project.get('partner_countries', []))}
Nombre de participants prévu : {new_project.get('nb_participants')}
Durée prévue : {new_project.get('duration_days')} jours
Budget prévu : {new_project.get('budget_planned', 'non défini')} €
Objectifs : {new_project.get('objectives', 'non définis')}
    """.strip()

    # 4. Prompt système
    system_prompt = """
Tu es un expert en gestion de projets Erasmus+ et youth exchanges,
travaillant pour Square of Youth, une ONG basée à Budapest.

Tu analyses les données historiques de leurs projets pour identifier
des patterns de réussite et d'échec, et pour évaluer la viabilité
de nouveaux projets.

Tes analyses sont basées UNIQUEMENT sur les données réelles fournies.
Tu es factuel, concis, et tu formules des recommandations concrètes
et actionnables. Tu n'inventes pas de données.

Réponds toujours en français.
    """.strip()

    # 5. Prompt utilisateur
    user_prompt = f"""
Voici les {len(similar)} projets passés de Square of Youth
les plus similaires au nouveau projet en cours de planification.

## Projets passés similaires

{projects_context}

## Nouveau projet à évaluer

{new_project_desc}

## Ta mission

Analyse ces données et produis un rapport structuré avec :

1. **Score de viabilité** (0-10) avec justification en 2-3 phrases

2. **Patterns de réussite identifiés**
   Quels facteurs reviennent dans les projets similaires qui ont bien fonctionné ?
   (durée, nombre de pays, thématique, profil participants...)

3. **Signaux d'alerte**
   Y a-t-il des caractéristiques du nouveau projet qui ressemblent
   à des projets passés difficiles ? Si oui, lesquels et pourquoi ?

4. **Recommandations concrètes** (5 maximum)
   Basées sur les leçons apprises des projets similaires.
   Formule chaque recommandation comme une action précise.

5. **Comparaison directe**
   Quel est le projet passé le plus proche, et qu'est-ce qu'on
   peut en apprendre directement ?

Sois direct et concis. Évite les généralités.
    """.strip()

    # 6. Appel à Claude
    print("→ Analyse Claude en cours...")
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )

    return response.content[0].text


# ── Exemple d'utilisation ────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Square of Youth — Analyse de viabilité de projet")
    print("=" * 55)

    # Définir le nouveau projet à évaluer
    nouveau_projet = {
        "name": "Youth Exchange Bratislava 2025",
        "project_type": "youth_exchange",
        "theme": "participation citoyenne et démocratie locale",
        "host_country": "Slovaquie",
        "partner_countries": ["Hongrie", "Pologne", "République tchèque", "Autriche"],
        "nb_participants": 25,
        "duration_days": 8,
        "budget_planned": 9500,
        "objectives": (
            "Sensibiliser des jeunes de 18-25 ans à la participation "
            "démocratique locale. Développer des outils de civic engagement "
            "adaptés à chaque contexte national."
        )
    }

    print(f"\nProjet : {nouveau_projet['name']}")
    print(f"Type   : {nouveau_projet['project_type']}")
    print(f"Thème  : {nouveau_projet['theme']}")
    print(f"Durée  : {nouveau_projet['duration_days']} jours | "
          f"{nouveau_projet['nb_participants']} participants\n")
    print("-" * 55)

    # Lancer l'analyse
    rapport = analyze_new_project(nouveau_projet)

    print("\n" + "=" * 55)
    print("  RAPPORT D'ANALYSE")
    print("=" * 55)
    print(rapport)
    print()

    # Optionnel : sauvegarder le rapport
    with open("rapport_viabilite.txt", "w", encoding="utf-8") as f:
        f.write(f"Projet : {nouveau_projet['name']}\n")
        f.write("=" * 55 + "\n\n")
        f.write(rapport)
    print("→ Rapport sauvegardé dans rapport_viabilite.txt")
