-- ============================================================
-- Migration 06 : recherche hybride (pgvector + plein texte)
-- À coller dans l'éditeur SQL de Supabase, après la migration 05.
-- Sûr à exécuter sur la base de production : uniquement des
-- ALTER TABLE / CREATE INDEX / CREATE OR REPLACE FUNCTION, et un
-- CREATE TABLE IF NOT EXISTS qui ne fait rien si `documents`
-- existe déjà (c'est le cas — colonnes confirmées en lecture
-- directe sur la base live : id, title, source_type, chunk_index,
-- content, embedding, created_at).
-- ============================================================

-- 1. Documente (pour la première fois dans le repo) la table
--    `documents`, qui n'existait jusque-là que côté Supabase.
create table if not exists documents (
  id           bigserial primary key,
  title        text not null,
  source_type  text not null,
  chunk_index  int not null,
  content      text not null,
  embedding    vector(1536),
  created_at   timestamptz default now()
);

create index if not exists documents_embedding_hnsw
  on documents using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- 2. Colonnes de recherche plein texte. Config 'simple' (pas de
--    stemming) : le contenu mélange français/anglais/hongrois, et
--    un stemming pensé pour une seule langue fausserait le matching
--    dans les autres.
--
--    to_tsvector(regconfig, text) est marquée STABLE par Postgres
--    (pas IMMUTABLE, même via une fonction wrapper), donc on
--    n'utilise pas de colonne GENERATED ici. À la place : une
--    colonne normale tenue à jour par un trigger BEFORE INSERT/
--    UPDATE (les triggers n'ont aucune contrainte d'immutabilité),
--    plus un UPDATE ponctuel pour backfiller les lignes déjà en base.
alter table projects add column if not exists fts tsvector;

create or replace function projects_fts_trigger() returns trigger
language plpgsql
as $$
begin
  new.fts := to_tsvector('simple',
    coalesce(new.name, '') || ' ' ||
    coalesce(new.theme, '') || ' ' ||
    coalesce(array_to_string(new.theme_tags, ' '), '') || ' ' ||
    coalesce(new.objectives, '') || ' ' ||
    coalesce(new.host_country, '') || ' ' ||
    coalesce(array_to_string(new.partner_countries, ' '), '') || ' ' ||
    coalesce(new.strengths, '') || ' ' ||
    coalesce(new.weaknesses, '') || ' ' ||
    coalesce(new.lessons, '') || ' ' ||
    coalesce(new.notes, '')
  );
  return new;
end;
$$;

drop trigger if exists projects_fts_update on projects;
create trigger projects_fts_update
  before insert or update on projects
  for each row execute function projects_fts_trigger();

-- backfill des lignes existantes (le trigger ne s'applique qu'aux
-- futurs insert/update, pas aux lignes déjà en base)
update projects set updated_at = updated_at;

create index if not exists projects_fts_gin on projects using gin (fts);

alter table documents add column if not exists fts tsvector;

create or replace function documents_fts_trigger() returns trigger
language plpgsql
as $$
begin
  new.fts := to_tsvector('simple', coalesce(new.content, ''));
  return new;
end;
$$;

drop trigger if exists documents_fts_update on documents;
create trigger documents_fts_update
  before insert or update on documents
  for each row execute function documents_fts_trigger();

-- backfill via le même mécanisme que ci-dessus (fait refaire le
-- trigger plutôt que dupliquer l'expression to_tsvector ici)
update documents set chunk_index = chunk_index;

create index if not exists documents_fts_gin on documents using gin (fts);

-- 3. Fonctions de recherche plein texte. websearch_to_tsquery
--    accepte du texte libre (question de l'utilisateur ou
--    sous-question générée par le LLM) sans erreur sur une
--    ponctuation isolée, contrairement à to_tsquery.
create or replace function search_projects_fulltext(
  query_text           text,
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
  rank               float
)
language sql stable
as $$
  select
    p.id, p.name, p.project_type, p.host_country, p.partner_countries,
    p.nb_participants, p.duration_days, p.theme, p.satisfaction_score,
    p.strengths, p.weaknesses, p.lessons,
    ts_rank(p.fts, websearch_to_tsquery('simple', query_text)) as rank
  from projects p
  where
    p.fts @@ websearch_to_tsquery('simple', query_text)
    and p.satisfaction_score >= min_satisfaction
    and (project_type_filter is null or p.project_type = project_type_filter)
    and (min_date is null or p.start_date >= min_date)
  order by rank desc
  limit match_count;
$$;

create or replace function search_documents_fulltext(
  query_text    text,
  match_count   int default 6
)
returns table (
  id           bigint,
  title        text,
  source_type  text,
  chunk_index  int,
  content      text,
  rank         float
)
language sql stable
as $$
  select
    d.id, d.title, d.source_type, d.chunk_index, d.content,
    ts_rank(d.fts, websearch_to_tsquery('simple', query_text)) as rank
  from documents d
  where d.fts @@ websearch_to_tsquery('simple', query_text)
  order by rank desc
  limit match_count;
$$;
