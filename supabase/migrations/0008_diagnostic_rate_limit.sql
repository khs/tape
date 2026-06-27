-- Migration 0008: per-IP rate limit for the admin diagnostic endpoint
--
-- Why this exists
-- ----------------
-- POST /api/diagnostic verifies the caller's Supabase JWT (sb.auth.getUser)
-- BEFORE it can check whether the user is admin — it has to, because the admin
-- rule keys off the token's email. That ordering is unavoidable, but it means
-- an anonymous attacker spraying random bearer tokens forces one auth-server
-- round-trip + DB read PER request, burning free-tier Supabase auth quota long
-- before the 403 fires. (Classic authn-before-authz drain.)
--
-- Fix: an IP rate-limit gate the endpoint calls BEFORE auth.getUser(). It reuses
-- the shared public.check_rate_limit() infra from migration 0002.
--
-- Why a dedicated wrapper instead of granting check_rate_limit to anon:
-- check_rate_limit takes (identifier, endpoint, max, window) — exposing it
-- directly to anon would let any caller write arbitrary identifier/endpoint
-- rows into rate_limit_events. This wrapper hardcodes the endpoint + budget and
-- only accepts an IP string, so the blast radius is exactly one bucket.
--
-- The endpoint extracts the client IP itself (Astro clientAddress, set by the
-- Vercel adapter) and passes it in, because when the Vercel function calls
-- Supabase the IP that PostgREST sees is the function's egress IP, not the end
-- user's — so the SQL-side public.client_ip() helper can't be used here.
--
-- The endpoint FAILS OPEN if this function is absent (it logs + continues), so
-- deploying the endpoint code before this migration is applied is safe; the
-- rate limit simply starts enforcing once this runs.
--
-- Run once in the Supabase SQL editor.

create or replace function public.diagnostic_rate_limit(p_ip text)
returns boolean
language sql
security definer
set search_path = public
as $$
  -- 10 requests / 60s / IP. Generous for the admin (a diagnostic post is a
  -- deliberate button click, not a loop) while capping token-spray to 10
  -- auth.getUser() calls per minute per source IP. Returns true if allowed.
  select public.check_rate_limit(
    'ip:' || coalesce(nullif(p_ip, ''), 'unknown'),
    'diagnostic_minute',
    10,
    60
  );
$$;

-- Allow anon + authenticated invocation. Without this PostgREST returns 401
-- and the endpoint's fail-open path would silently disable the limit.
grant execute on function public.diagnostic_rate_limit(text) to anon, authenticated;
