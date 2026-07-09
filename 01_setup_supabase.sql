-- ============================================================
-- ÉTAPE 1 : Activer l'extension pgvector
-- À coller dans l'éditeur SQL de Supabase
-- ============================================================

create extension if not exists vector;

-- ============================================================
-- ÉTAPE 2 : Table principale des projets
-- Contient à la fois les métadonnées ET le vecteur
-- ============================================================

create table projects (
  -- Identifiant unique auto-généré
  id            bigserial primary key,

  -- Informations de base
  name          text not null,                        -- "Youth Exchange Pologne 2024"
  project_type  text not null,                        -- 'youth_exchange' | 'local_workshop'
  start_date    date,
  end_date      date,
  duration_days int generated always as
                  (end_date - start_date) stored,     -- calculé automatiquement

  -- Géographie
  host_country  text,                                 -- "Pologne"
  partner_countries text[],                           -- ["Hongrie","France","Roumanie"]
  nb_countries  int,

  -- Participants
  nb_participants     int,
  age_range_min       int,
  age_range_max       int,

  -- Thématique & contenu
  theme         text,                                 -- "citoyenneté européenne"
  theme_tags    text[],                               -- ["droits","démocratie","participation"]
  objectives    text,                                 -- description libre

  -- Résultats mesurés
  satisfaction_score  numeric(3,1),                   -- 4.7 (sur 5)
  completion_rate     numeric(5,2),                   -- 94.5 (%)
  youthpass_delivered int,
  budget_planned      numeric(10,2),
  budget_actual       numeric(10,2),
  budget_delta_pct    numeric(6,2) generated always as
                        (round((budget_actual - budget_planned)
                         / nullif(budget_planned,0) * 100, 2)) stored,

  -- Points qualitatifs (texte libre)
  strengths     text,                                 -- ce qui a bien marché
  weaknesses    text,                                 -- ce qui a moins marché
  lessons       text,                                 -- leçons apprises
  notes         text,                                 -- notes libres

  -- Le vecteur d'embedding (1536 dims pour Voyage AI / OpenAI)
  embedding     vector(1536),

  -- Timestamps
  created_at    timestamptz default now(),
  updated_at    timestamptz default now()
);

-- ============================================================
-- ÉTAPE 3 : Index vectoriel pour la recherche par similarité
-- HNSW = Hierarchical Navigable Small World (le plus rapide)
-- ============================================================

create index on projects
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- ============================================================
-- ÉTAPE 4 : Index classiques pour les filtres SQL
-- ============================================================

create index on projects (project_type);
create index on projects (host_country);
create index on projects (start_date);
create index on projects (satisfaction_score);
create index on projects (nb_participants);

-- ============================================================
-- ÉTAPE 5 : Fonction de recherche sémantique
-- Appelée depuis Python : cherche les N projets les plus proches
-- avec des filtres optionnels
-- ============================================================

create or replace function search_similar_projects(
  query_embedding   vector(1536),       -- vecteur de la requête
  match_count       int     default 5,  -- nombre de résultats
  min_satisfaction  float   default 0,  -- filtre : score min
  project_type_filter text  default null,
  min_date          date    default null
)
returns table (
  id                bigint,
  name              text,
  project_type      text,
  host_country      text,
  partner_countries text[],
  nb_participants   int,
  duration_days     int,
  theme             text,
  satisfaction_score numeric,
  strengths         text,
  weaknesses        text,
  lessons           text,
  similarity        float
)
language sql stable
as $$
  select
    p.id,
    p.name,
    p.project_type,
    p.host_country,
    p.partner_countries,
    p.nb_participants,
    p.duration_days,
    p.theme,
    p.satisfaction_score,
    p.strengths,
    p.weaknesses,
    p.lessons,
    1 - (p.embedding <=> query_embedding) as similarity
  from projects p
  where
    p.embedding is not null
    and p.satisfaction_score >= min_satisfaction
    and (project_type_filter is null or p.project_type = project_type_filter)
    and (min_date is null or p.start_date >= min_date)
  order by p.embedding <=> query_embedding
  limit match_count;
$$;

-- ============================================================
-- ÉTAPE 6 : Données de test — 3 projets fictifs pour vérifier
-- ============================================================

insert into projects (
  name, project_type, start_date, end_date,
  host_country, partner_countries, nb_countries,
  nb_participants, theme, theme_tags,
  satisfaction_score, completion_rate, youthpass_delivered,
  budget_planned, budget_actual,
  strengths, weaknesses, lessons
) values
(
  'Youth Exchange Budapest 2024',
  'youth_exchange',
  '2024-03-10', '2024-03-18',
  'Hongrie', ARRAY['Pologne','Roumanie','France'], 4,
  24, 'citoyenneté européenne', ARRAY['démocratie','participation','droits'],
  4.8, 95.8, 22,
  8000, 7850,
  'Équipe de facilitateurs très soudée. Programme varié.',
  'Barrière de langue lors des soirées informelles.',
  'Prévoir 2h de team building le jour 1.'
),
(
  'Workshop local — Droits numériques',
  'local_workshop',
  '2024-01-20', '2024-01-21',
  'Hongrie', ARRAY[]::text[], 1,
  12, 'droits numériques', ARRAY['privacy','tech','citoyenneté'],
  4.3, 100, 0,
  1200, 1180,
  'Format court très apprécié. Intervenants pertinents.',
  'Salle trop petite pour les activités en groupe.',
  'Réserver une salle avec espace de travail modulable.'
),
(
  'Youth Exchange Varsovie 2023',
  'youth_exchange',
  '2023-07-03', '2023-07-11',
  'Pologne', ARRAY['Hongrie','Espagne','Italie','Allemagne'], 5,
  30, 'inclusion sociale', ARRAY['diversité','inclusion','solidarité'],
  4.6, 93.3, 28,
  12000, 12400,
  'Très bonne dynamique interculturelle. Activités outdoor réussies.',
  'Budget légèrement dépassé sur la restauration.',
  'Négocier les repas en amont avec le lieu daccueil.'
);

-- Vérification
select id, name, project_type, satisfaction_score from projects;
