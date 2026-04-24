-- Legible Markets v1.1 — saved dashboards
--
-- Users come from Supabase Auth (auth.users). We don't mirror a local users
-- table; Supabase's built-in table is fine.
--
-- Policies enforce:
--   * any authenticated user can insert their own rows
--   * anyone (even anon) can SELECT a row iff visibility = 'public'
--   * only the owner can UPDATE or DELETE their rows
--
-- The default for new rows is visibility = 'public' (the user-approved
-- "public-link-only by default; opt-in to private" policy). Switching to
-- 'private' makes it readable only by the owner.

create table if not exists public.saved_dashboards (
  id          uuid primary key default gen_random_uuid(),
  slug        text not null unique,
  owner_id    uuid not null references auth.users(id) on delete cascade,
  title       text not null default 'Untitled dashboard',
  state_json  jsonb not null,
  visibility  text not null default 'public'
                check (visibility in ('public', 'private')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists saved_dashboards_owner_idx
  on public.saved_dashboards(owner_id, updated_at desc);

-- RLS
alter table public.saved_dashboards enable row level security;

-- SELECT: anyone can read a public row; owner can always read their own.
drop policy if exists "read_public_or_own" on public.saved_dashboards;
create policy "read_public_or_own"
  on public.saved_dashboards
  for select
  using (
    visibility = 'public'
    or (auth.uid() is not null and auth.uid() = owner_id)
  );

-- INSERT: authenticated users inserting rows as themselves.
drop policy if exists "insert_own" on public.saved_dashboards;
create policy "insert_own"
  on public.saved_dashboards
  for insert
  with check (auth.uid() is not null and auth.uid() = owner_id);

-- UPDATE: only the owner.
drop policy if exists "update_own" on public.saved_dashboards;
create policy "update_own"
  on public.saved_dashboards
  for update
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

-- DELETE: only the owner.
drop policy if exists "delete_own" on public.saved_dashboards;
create policy "delete_own"
  on public.saved_dashboards
  for delete
  using (auth.uid() = owner_id);

-- Bump updated_at on UPDATE.
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists saved_dashboards_touch on public.saved_dashboards;
create trigger saved_dashboards_touch
  before update on public.saved_dashboards
  for each row execute function public.touch_updated_at();
