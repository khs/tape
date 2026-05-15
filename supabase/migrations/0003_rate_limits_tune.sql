-- Migration 0003: tune rate limits
--
-- Two changes informed by the first review:
--
--   1. Drop the DELETE rate-limit trigger and its function.
--      If a user is deleting their own dashboards aggressively — even
--      programmatically — that's their right; RLS already enforces they
--      can only touch their own rows. Friction here is annoying without
--      protecting anything we care about, and "Enterprise Support removes
--      this limit" isn't a real upsell for a delete loop.
--
--   2. Add a PER-IP tier to saved_dashboards INSERT (alongside the
--      existing per-user tier). The per-user limit doesn't help against
--      a bot spinning up dozens of fresh Google accounts; the per-IP
--      tier raises the cost of that path. Limits sized for shared-IP
--      tolerance (libraries, offices, NAT'd networks): legitimate
--      multi-user-from-one-IP traffic fits inside the budget; a single
--      attacker with one IP and many accounts hits the wall fast.
--
-- Run once in the Supabase SQL editor after migration 0002.

-- ----------------------------------------------------------------
-- 1. Drop delete rate-limit trigger + function
-- ----------------------------------------------------------------

drop trigger if exists saved_dashboards_rl_delete on public.saved_dashboards;
drop function if exists public.saved_dashboards_rate_limit_delete();

-- ----------------------------------------------------------------
-- 2. Re-define INSERT trigger function with per-IP tier added
-- ----------------------------------------------------------------
--
-- Per-user limits (unchanged from 0002):
--   60s →  3    1h → 15    24h → 50
--
-- Per-IP limits (new):
--   1h  → 25
--   24h → 100
--
-- Per-IP is intentionally generous: tuned so a small NAT'd group of
-- legitimate users (e.g. 5 people in a library each making a few
-- dashboards) fits inside the budget. A solo bot with one IP and many
-- accounts hits the wall fast; a bot with rotating residential proxies
-- defeats per-IP entirely, but then the per-user cap is doing the work.
-- This is a belt-and-suspenders layer, not the primary defense.

create or replace function public.saved_dashboards_rate_limit_insert()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user text := 'user:' || coalesce(auth.uid()::text, 'anon');
  v_ip   text := 'ip:'   || public.client_ip();
begin
  -- Per-user tier (catches one signed-in account looping).
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

  -- Per-IP tier (catches one IP spinning up many fresh Google accounts).
  -- Deliberately more generous than per-user so legitimate shared-IP
  -- traffic isn't the false-positive case.
  if not public.check_rate_limit(v_ip, 'dash_insert_ip_hour', 25, 3600) then
    raise exception 'Too many dashboards from this network in the last hour. Try again later, or email keller.scholl@gmail.com if this is a shared address.'
      using errcode = 'P0001';
  end if;
  if not public.check_rate_limit(v_ip, 'dash_insert_ip_day', 100, 86400) then
    raise exception 'Too many dashboards from this network today. Try again tomorrow, or email keller.scholl@gmail.com if this is a shared address.'
      using errcode = 'P0001';
  end if;

  return new;
end;
$$;
