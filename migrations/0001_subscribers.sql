-- Email subscribers list, populated from the homepage/footer signup forms
-- and the post-save prompt on /u/<slug>/.
--
-- Run this once in the Supabase SQL editor.
--
-- Privacy posture: anon can INSERT only. There's no SELECT/UPDATE/DELETE
-- policy, so nobody — including the row's own submitter — can read the
-- table via PostgREST. To get the list out, you SELECT in the Supabase
-- SQL editor (which uses the service role and bypasses RLS) and export
-- as CSV. Imported addresses can then be moved into Substack / Buttondown /
-- wherever the actual sending happens.

create table if not exists subscribers (
  email       text primary key,
  created_at  timestamptz not null default now(),
  source      text  -- 'footer', 'post-save', etc. for funnel attribution
);

alter table subscribers enable row level security;

-- Anon INSERT, with a basic email-shape check at the DB layer so the form
-- can never persist obvious garbage even if client-side validation is
-- bypassed. PostgREST clients sending `Prefer: resolution=ignore-duplicates`
-- on the POST will get a silent 201 for re-submissions instead of a 409.
create policy "subscribers_anon_insert"
  on subscribers
  for insert
  to anon, authenticated
  with check (email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$');

-- No SELECT / UPDATE / DELETE policies; PostgREST will return 401 on those
-- routes for anon/authenticated, which is exactly what we want.
