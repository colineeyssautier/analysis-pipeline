# Square of Youth — Assistant d'analyse de projets

## L'idée

Square of Youth monte des projets Erasmus+ depuis des années : des dizaines de
demandes de subvention, de rapports de fin de projet, de retours de
participants. Toute cette expérience existe, mais elle est dispersée dans des
fichiers, et personne ne la relit vraiment avant de monter le projet suivant.

Cet outil sert à ça : poser une question sur un futur projet ("est-ce que ce
type d'échange fonctionne bien avec ce format ?", "quels risques sur ce genre
de thématique ?") et obtenir une réponse qui s'appuie sur nos propres projets
passés — pas des généralités trouvées sur internet.

On peut aussi lui donner des documents de référence (lignes directrices Erasmus+,
critères d'évaluation, notes internes...) pour qu'il les prenne en compte dans
ses réponses, en plus de notre historique de projets.

## Comment ça fonctionne, en gros

1. **Les projets passés sont stockés dans une base de données** (Supabase),
   avec toutes leurs infos : pays, participants, thématique, score de
   satisfaction, points forts/faibles, leçons apprises.
2. **Chaque projet est transformé en "empreinte" numérique** (un embedding)
   qui capture son contenu. C'est ce qui permet de retrouver les projets les
   plus proches d'une question donnée, même si les mots utilisés sont
   différents.
3. **Quand on pose une question**, l'outil retrouve les projets et documents
   les plus pertinents, puis demande à une IA de rédiger une analyse à partir
   de ces éléments — en précisant toujours si un point vient de notre
   historique ou d'un document de référence.

## Ce qu'il faut pour que ça tourne

L'outil s'appuie sur trois services externes, chacun avec un compte et une
clé API à créer :

- **Supabase** — la base de données où sont stockés les projets et les
  documents.
- **Voyage AI** — génère les embeddings (l'"empreinte" numérique des textes).
- **Groq** — fait tourner le modèle d'IA qui rédige les analyses.

Ces clés vont dans un fichier `.env` à la racine du projet (non versionné,
donc à recréer sur chaque machine). Python et les dépendances du fichier
`requirements.txt` doivent être installés.

Les coûts sont faibles : Supabase et Voyage AI restent gratuits à notre
échelle d'usage, seul Groq coûte réellement quelque chose (quelques euros par
mois selon le nombre de questions posées).

## Utiliser l'outil

L'interface principale est une page web (`frontend/`, en HTML/CSS/TypeScript)
servie par un backend FastAPI (`server.py`), avec deux fonctions :

- **Poser une question** — on écrit sa question (dans n'importe quelle
  langue), l'outil cherche les projets et documents pertinents et génère une
  analyse.
- **Ajouter des documents de référence** — on dépose un PDF, il est
  automatiquement découpé, indexé, et devient utilisable dans les réponses.
  Pas besoin de toucher au code.

Pour lancer l'application : `uvicorn server:app --reload`, puis ouvrir
`http://127.0.0.1:8000`.

Une version en ligne de commande existe aussi (`03_analyze_with_groq.py`), si
on préfère poser des questions sans interface graphique.

### Ajouter de nouveaux projets

Les projets sont d'abord saisis dans deux Google Sheets (demandes de
subvention et retours de fin de projet). Pour les faire entrer dans le
système :

1. `import_from_sheet.py` — récupère les nouvelles lignes des Sheets et les
   ajoute à la base (sans embedding).
2. `02_embed_and_store.py` — génère les embeddings des projets qui n'en ont
   pas encore.

Ces deux scripts ne retraitent que ce qui est nouveau : on peut les relancer
à volonté sans dupliquer les projets déjà présents.

## Question fréquente

**Les données sont-elles sécurisées ?**
Oui — la base Supabase est hébergée en Europe (Frankfurt), et la clé utilisée
dans le code (`anon`) ne donne accès qu'aux données explicitement autorisées.
