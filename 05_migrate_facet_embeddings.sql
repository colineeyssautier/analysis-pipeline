-- ============================================================
-- Migration 05 : embeddings multi-facettes pour les projets
-- À coller dans l'éditeur SQL de Supabase.
-- Sûr à exécuter sur la base de production : uniquement des
-- ALTER TABLE / CREATE INDEX / CREATE OR REPLACE FUNCTION.
-- L'ancienne colonne `embedding` et la fonction
-- `search_similar_projects` restent en place (non supprimées),
-- comme filet de sécurité en cas de rollback.
-- ============================================================

-- 1. Nouvelles colonnes d'embedding par facette
alter table projects add column if not exists embedding_thematic    vector(1536);
alter table projects add column if not exists embedding_logistics   vector(1536);
alter table projects add column if not exists embedding_qualitative vector(1536);

-- 2. Un index HNSW par facette
create index if not exists projects_embedding_thematic_hnsw
  on projects using hnsw (embedding_thematic vector_cosine_ops)
  with (m = 16, ef_construction = 64);

create index if not exists projects_embedding_logistics_hnsw
  on projects using hnsw (embedding_logistics vector_cosine_ops)
  with (m = 16, ef_construction = 64);

create index if not exists projects_embedding_qualitative_hnsw
  on projects using hnsw (embedding_qualitative vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- 3. Fonction de recherche multi-facettes
--    Compare UN embedding de requête aux 3 colonnes de facette,
--    retourne le meilleur score par projet + la facette gagnante.
--    NULL-safe : les comparaisons utilisent coalesce(..., -999)
--    uniquement en interne, les colonnes de sortie gardent la
--    vraie valeur (potentiellement NULL tant que le backfill
--    n'est pas terminé).
create or replace function search_projects_by_facets(
  query_embedding      vector(1536),
  match_count          int   default 8,
  min_satisfaction     float default 0,
  project_type_filter  text  default null,
  min_date             date  default null
)
returns table (
  id                 bigint,
  name               text,
  project_type       text,
  host_country       text,
  partner_countries  text[],
  nb_participants    int,
  duration_days      int,
  theme              text,
  satisfaction_score numeric,
  strengths          text,
  weaknesses         text,
  lessons            text,
  best_facet         text,
  similarity         float,
  sim_thematic       float,
  sim_logistics      float,
  sim_qualitative    float
)
language sql stable
as $$
  with scored as (
    select
      p.*,
      (1 - (p.embedding_thematic    <=> query_embedding)) as sim_thematic,
      (1 - (p.embedding_logistics   <=> query_embedding)) as sim_logistics,
      (1 - (p.embedding_qualitative <=> query_embedding)) as sim_qualitative
    from projects p
    where
      p.satisfaction_score >= min_satisfaction
      and (project_type_filter is null or p.project_type = project_type_filter)
      and (min_date is null or p.start_date >= min_date)
  )
  select
    s.id, s.name, s.project_type, s.host_country, s.partner_countries,
    s.nb_participants, s.duration_days, s.theme, s.satisfaction_score,
    s.strengths, s.weaknesses, s.lessons,
    case
      when coalesce(s.sim_thematic, -999) >= coalesce(s.sim_logistics, -999)
       and coalesce(s.sim_thematic, -999) >= coalesce(s.sim_qualitative, -999)
        then 'thematic'
      when coalesce(s.sim_logistics, -999) >= coalesce(s.sim_qualitative, -999)
        then 'logistics'
      else 'qualitative'
    end as best_facet,
    greatest(
      coalesce(s.sim_thematic, -999),
      coalesce(s.sim_logistics, -999),
      coalesce(s.sim_qualitative, -999)
    ) as similarity,
    s.sim_thematic, s.sim_logistics, s.sim_qualitative
  from scored s
  where s.sim_thematic is not null or s.sim_logistics is not null or s.sim_qualitative is not null
  order by similarity desc
  limit match_count;
$$;
