-- Migration 0002: rate-limit infrastructure + apply to public write surfaces
--
-- Why this exists
-- ----------------
-- Pre-this-migration there was no application-layer rate limiting on the
-- three writable endpoints:
--
--   1. public.subscribe RPC      — anonymous email signup form
--   2. public.saved_dashboards   — INSERT (save composer state)
--   3. public.saved_dashboards   — UPDATE / DELETE (rename, retitle, delete)
--
-- Supabase RLS protects ownership: only the row's owner can update or delete
-- their dashboards. But nothing previously stopped a logged-in user from
-- running an INSERT loop, or a script kiddie from spamming the email form.
-- One bad afternoon could fill the subscribers table or burn through free-
-- tier Supabase quota.
--
-- Design
-- ------
--   * One generic table (rate_limit_events) accounting for every limit-able
--     attempt across every endpoint.
--   * One generic check_rate_limit(identifier, endpoint, max, window_seconds)
--     function that returns true/false and ALWAYS records the attempt — so
--     bots that keep hammering after the cooldown only extend their own
--     timeout.
--   * Limits applied per IP (anon endpoints) or per auth.uid() (signed-in
--     endpoints). Tiered: short window catches bot loops, longer window
--     catches slow-drip bots.
--   * Error messages on rate-limit failure point at keller.scholl@gmail.com
--     for Enterprise Support — legitimate edge cases for hitting these
--     limits are basically nil, and any real human who does is the kind
--     of high-engagement user worth a personal reply.
--
-- Run once in the Supabase SQL editor.

-- ----------------------------------------------------------------
-- 1. Rate-limit accounting table
-- ----------------------------------------------------------------

create table if not exists public.rate_limit_events (
  id          uuid primary key default gen_random_uuid(),
  identifier  text not null,                -- 'ip:1.2.3.4' or 'user:<uuid>'
  endpoint    text not null,                -- e.g. 'subscribe_hour', 'dash_insert_day'
  created_at  timestamptz not null default now()
);

-- Only query pattern is (identifier, endpoint, recent created_at). DESC index
-- lets the LIMIT-style prefix scan terminate fast.
create index if not exists rate_limit_events_lookup_idx
  on public.rate_limit_events (identifier, endpoint, created_at desc);

-- Cleanup index for the periodic prune inside check_rate_limit().
create index if not exists rate_limit_events_created_at_idx
  on public.rate_limit_events (created_at);

-- RLS off: only SECURITY DEFINER functions touch this table; clients can't
-- read or write it directly. Locking it with RLS would add overhead with no
-- security gain.
alter table public.rate_limit_events disable row level security;
revoke all on public.rate_limit_events from anon, authenticated;

-- ----------------------------------------------------------------
-- 2. Helpers
-- ----------------------------------------------------------------

-- Extract the client IP from the PostgREST request. Supabase forwards both
-- the X-Forwarded-For chain and the Cloudflare CF-Connecting-IP header. XFF
-- can be multi-valued (proxy chain); the first hop is the original client.
-- Returns 'unknown' if neither header is present — those requests bucket
-- together, which is fine: weird traffic deserves combined accounting.
create or replace function public.client_ip() returns text
language sql
stable
as $$
  select coalesce(
    nullif(split_part(
      coalesce(current_setting('request.headers', true)::json->>'x-forwarded-for', ''),
      ',', 1
    ), ''),
    nullif(current_setting('request.headers', true)::json->>'cf-connecting-ip', ''),
    'unknown'
  );
$$;

-- Generic rate-limit check. Returns true if the call is allowed under the
-- given (max, window_seconds) budget, false if exceeded. The attempt is
-- ALWAYS recorded — bots that keep hammering after a deny only extend
-- their own cooldown rather than resetting it.
--
-- Old events are pruned opportunistically on each call (24h cap, since no
-- production endpoint cares about anything older). Cheap with the
-- created_at index; no separate vacuum job required.
create or replace function public.check_rate_limit(
  p_identifier      text,
  p_endpoint        text,
  p_max_per_window  int,
  p_window_seconds  int
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count  int;
  v_cutoff timestamptz := now() - make_interval(secs => p_window_seconds);
begin
  -- Sweep anything older than 24h. Every endpoint we care about has a
  -- window <= 24h, so older rows are dead weight.
  delete from public.rate_limit_events
   where created_at < now() - interval '24 hours';

  select count(*) into v_count
    from public.rate_limit_events
   where identifier = p_identifier
     and endpoint   = p_endpoint
     and created_at >= v_cutoff;

  -- Record regardless of allow/deny so persistent offenders extend their
  -- own timeout instead of resetting it.
  insert into public.rate_limit_events (identifier, endpoint)
       values (p_identifier, p_endpoint);

  return v_count < p_max_per_window;
end;
$$;

-- ----------------------------------------------------------------
-- 3. Wrap public.subscribe with strict per-IP limits
-- ----------------------------------------------------------------
--
-- Humans submit once, occasionally twice on bounce. Bots spray. Tiered:
--
--   * 60s window, 1 attempt   — catches double-click + tight bot loops
--   * 1h window,  3 attempts  — catches "tried 5 emails to see which works"
--   * 24h window, 5 attempts  — bot floor; humans don't hit this
--
-- Same exception code (P0001 — raise_exception) for all three so the
-- client can branch on the message rather than the code.

create or replace function public.subscribe(
  p_email   text,
  p_source  text
) returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_ip text := public.client_ip();
begin
  if not public.check_rate_limit('ip:' || v_ip, 'subscribe_minute', 1, 60) then
    raise exception 'Too many requests — try again in a minute. If you need help, email keller.scholl@gmail.com.'
      using errcode = 'P0001';
  end if;
  if not public.check_rate_limit('ip:' || v_ip, 'subscribe_hour', 3, 3600) then
    raise exception 'Signup limit reached. Email keller.scholl@gmail.com if you need higher-volume access.'
      using errcode = 'P0001';
  end if;
  if not public.check_rate_limit('ip:' || v_ip, 'subscribe_day', 5, 86400) then
    raise exception 'Daily signup limit reached. Enterprise Support removes these limits — keller.scholl@gmail.com.'
      using errcode = 'P0001';
  end if;

  -- Original write semantics: insert + ignore-conflict on the email PK.
  insert into public.subscribers (email, source)
       values (p_email, p_source)
  on conflict (email) do nothing;
end;
$$;

-- Allow anon + authenticated invocation. Without this PostgREST returns 401.
grant execute on function public.subscribe(text, text) to anon, authenticated;

-- ----------------------------------------------------------------
-- 4. saved_dashboards rate-limit triggers (per-user, auth.uid()-keyed)
-- ----------------------------------------------------------------
--
-- INSERT (save): the easiest abuse vector (fork-and-save loop).
-- UPDATE (rename / retitle / visibility / state edit): middling — the
--   composer may auto-save on edits, so limits are more generous.
-- DELETE: rare; modest limits.

create or replace function public.saved_dashboards_rate_limit_insert()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user text := 'user:' || coalesce(auth.uid()::text, 'anon');
begin
  if not public.check_rate_limit(v_user, 'dash_insert_min', 3, 60) then
    raise exception 'Saving too quickly — wait a few seconds. Email keller.scholl@gmail.com if you need higher limits.'
      using errcode = 'P0001';
  end if;
  if not public.check_rate_limit(v_user, 'dash_insert_hour', 15, 3600) then
    raise exception 'Hourly save limit reached. Enterprise Support removes these limits — keller.scholl@gmail.com.'
      using errcode = 'P0001';
  end if;
  if not public.check_rate_limit(v_user, 'dash_insert_day', 50, 86400) then
    raise exception 'Daily save limit reached. Enterprise Support removes these limits — keller.scholl@gmail.com.'
      using errcode = 'P0001';
  end if;
  return new;
end;
$$;

create or replace function public.saved_dashboards_rate_limit_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user text := 'user:' || coalesce(auth.uid()::text, 'anon');
begin
  if not public.check_rate_limit(v_user, 'dash_update_min', 10, 60) then
    raise exception 'Editing too quickly — wait a few seconds. Email keller.scholl@gmail.com if you need higher limits.'
      using errcode = 'P0001';
  end if;
  if not public.check_rate_limit(v_user, 'dash_update_hour', 100, 3600) then
    raise exception 'Hourly edit limit reached. Enterprise Support removes these limits — keller.scholl@gmail.com.'
      using errcode = 'P0001';
  end if;
  if not public.check_rate_limit(v_user, 'dash_update_day', 300, 86400) then
    raise exception 'Daily edit limit reached. Enterprise Support removes these limits — keller.scholl@gmail.com.'
      using errcode = 'P0001';
  end if;
  return new;
end;
$$;

create or replace function public.saved_dashboards_rate_limit_delete()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user text := 'user:' || coalesce(auth.uid()::text, 'anon');
begin
  if not public.check_rate_limit(v_user, 'dash_delete_min', 5, 60) then
    raise exception 'Deleting too quickly — wait a few seconds.'
      using errcode = 'P0001';
  end if;
  if not public.check_rate_limit(v_user, 'dash_delete_hour', 30, 3600) then
    raise exception 'Hourly delete limit reached. Email keller.scholl@gmail.com if this is a mistake.'
      using errcode = 'P0001';
  end if;
  return old;
end;
$$;

drop trigger if exists saved_dashboards_rl_insert on public.saved_dashboards;
create trigger saved_dashboards_rl_insert
  before insert on public.saved_dashboards
  for each row execute function public.saved_dashboards_rate_limit_insert();

drop trigger if exists saved_dashboards_rl_update on public.saved_dashboards;
create trigger saved_dashboards_rl_update
  before update on public.saved_dashboards
  for each row execute function public.saved_dashboards_rate_limit_update();

drop trigger if exists saved_dashboards_rl_delete on public.saved_dashboards;
create trigger saved_dashboards_rl_delete
  before delete on public.saved_dashboards
  for each row execute function public.saved_dashboards_rate_limit_delete();

-- ----------------------------------------------------------------
-- Tuning notes for future-Keller
-- ----------------------------------------------------------------
--
-- If a legitimate user reports hitting a limit, two ways to relieve:
--
--   1. Bump the per-tier number in the function definition. Cheap, no
--      schema change. (Re-running this file would overwrite their changes,
--      so put the bumped values in a follow-up migration file rather than
--      editing this one in place.)
--
--   2. Whitelist their user_id or IP by inserting a sentinel into a
--      future `rate_limit_overrides` table and short-circuiting at the
--      top of check_rate_limit. Add that table here once the first real
--      user case shows up — premature otherwise.
--
-- The PostgREST error body for raise_exception looks like:
--   {"code":"P0001","message":"Daily signup limit reached. ...","hint":null,"details":null}
-- Clients should display message verbatim; that's the Enterprise upsell.
