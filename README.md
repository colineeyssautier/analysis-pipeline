# Square of Youth — Guide de démarrage RAG

## Ce que ce système fait

Vous posez une question sur vos projets Erasmus+ en langage naturel.
Le système trouve les projets passés les plus similaires dans votre base,
et Claude génère une analyse de patterns et un rapport de viabilité.

---

## Structure des fichiers

```
square-of-youth/
├── scripts/
│   ├── 01_setup_supabase.sql     ← à coller dans Supabase
│   ├── 02_embed_and_store.py     ← indexe vos projets
│   └── 03_analyze_with_claude.py ← analyse + rapport
├── config/
│   └── .env.example              ← template pour vos clés API
├── requirements.txt
└── README.md
```

---

## Étape 1 — Créer votre compte Supabase (5 min)

1. Allez sur **https://app.supabase.com**
2. Cliquez "New project" → choisissez un nom (ex: `square-of-youth`)
3. Choisissez la région **EU (Frankfurt)** pour RGPD
4. Notez le mot de passe de la base (vous en aurez besoin plus tard)
5. Attendez ~2 min que le projet se crée

**Récupérer vos clés :**
- Dans le menu gauche : `Settings → API`
- Copiez `Project URL` et `anon public` key

---

## Étape 2 — Configurer la base de données (3 min)

1. Dans Supabase, menu gauche : `SQL Editor`
2. Cliquez `New query`
3. Copiez-collez le contenu de `01_setup_supabase.sql`
4. Cliquez `Run` (bouton vert en bas à droite)
5. Vous devriez voir : `3 rows` dans les résultats (les projets de test)

---

## Étape 3 — Créer vos clés API (10 min)

### Voyage AI (embeddings)
1. https://dash.voyageai.com → Sign up
2. `API Keys` → `Create new key`
3. Copiez la clé

### Anthropic (Claude)
1. https://console.anthropic.com → Sign up
2. `API Keys` → `Create Key`
3. Copiez la clé

---

## Étape 4 — Installer Python et les dépendances (5 min)

```bash
# Vérifier que Python est installé (version 3.10+)
python --version

# Créer un environnement virtuel (recommandé)
python -m venv venv
source venv/bin/activate    # Mac/Linux
venv\Scripts\activate       # Windows

# Installer les dépendances
pip install -r requirements.txt
```

---

## Étape 5 — Configurer les variables d'environnement (2 min)

```bash
# Copier le template
cp config/.env.example .env

# Ouvrir .env dans votre éditeur et remplir les valeurs
# SUPABASE_URL, SUPABASE_KEY, VOYAGE_API_KEY, ANTHROPIC_API_KEY
```

---

## Étape 6 — Indexer vos projets (quelques secondes par projet)

```bash
# Génère les embeddings des 3 projets de test
python scripts/02_embed_and_store.py
```

Vous devriez voir :
```
→ 3 projets à indexer
[1/3] Youth Exchange Budapest 2024
  → Texte construit (412 caractères)
  → Embedding généré (1536 dimensions)
  ✓ Projet 1 — 'Youth Exchange Budapest 2024' indexé
...
✓ Terminé — 3 projets indexés
```

---

## Étape 7 — Analyser un nouveau projet

```bash
python scripts/03_analyze_with_claude.py
```

Modifiez le dictionnaire `nouveau_projet` dans le script
avec les vraies données de votre prochain projet.

---

## Ajouter vos vrais projets

Dans `02_embed_and_store.py`, vous pouvez ajouter des projets
directement en SQL dans Supabase (table `projects`),
ou écrire un script d'import depuis Google Sheets / Excel.

Pour chaque nouveau projet ajouté, relancez :
```bash
python scripts/02_embed_and_store.py
```
Le script ne re-génère que les embeddings manquants.

---

## Coûts estimés (mensuel, usage Square of Youth)

| Service       | Usage estimé          | Coût     |
|---------------|-----------------------|----------|
| Supabase      | < 500 Mo              | Gratuit  |
| Voyage AI     | ~50 projets indexés   | ~0.01€   |
| Claude API    | 20 analyses/mois      | ~5-10€   |
| **Total**     |                       | **~10€** |

---

## Questions fréquentes

**Les données sont-elles sécurisées ?**
Oui. Supabase est hébergé en EU Frankfurt, conforme RGPD.
Seule la clé `anon` est dans le code — elle ne donne accès
qu'aux données que vous autorisez explicitement.

**Que faire si un projet change ?**
Mettez à jour la ligne dans Supabase, puis relancez
`02_embed_and_store.py` — il re-génère l'embedding automatiquement
si vous remettez `embedding` à NULL dans la base.

**Peut-on interroger en hongrois ou anglais ?**
Oui. Le modèle `voyage-multilingual-2` gère nativement
le français, anglais, hongrois et les autres langues Erasmus+.
