-- Migration 0010: rate-limit hardening
--
-- Three independent hardening changes, all forward-only (this file uses
-- CREATE OR REPLACE / REVOKE / GRANT / idempotent CREATE, so it never edits an
-- already-applied migration body):
--
--   (a) Bound the cleanup DELETE inside public.check_rate_limit(). The 0002
--       definition ran an UNCONDITIONAL full-table DELETE (everything older
--       than 24h) on EVERY call. Under load that is a repeated full-range
--       delete + the autovacuum churn behind it, on the hot path of the one
--       function every rate-limited endpoint calls several times per request.
--       Here the DELETE is scoped to the CURRENT (identifier, endpoint) bucket
--       and to rows already outside the window being checked. That touches only
--       the handful of rows this call already ignores, rides the existing
--       (identifier, endpoint, created_at desc) index, and leaves the visible
--       count -- and therefore the rate-limit decision -- byte-for-byte
--       identical to 0002.
--
--   (b) Lock down EXECUTE on public.check_rate_limit(). It is a generic writer
--       (arbitrary identifier/endpoint into rate_limit_events); it should never
--       be callable directly by untrusted PostgREST roles. Every legitimate
--       caller reaches it INSIDE a SECURITY DEFINER wrapper or trigger
--       (subscribe, compose_action_check, diagnostic_rate_limit, the
--       saved_dashboards triggers), and those inner calls run with the
--       definer's rights -- so revoking the anon/PUBLIC grant does not break any
--       existing path. See the note at the REVOKE below.
--
--   (c) Cap alert_rules rows per user (mirrors the intent of the per-user
--       saved-dashboard limits) via a BEFORE INSERT trigger that raises once a
--       user already owns the ceiling number of rules.
--
-- Run once in the Supabase SQL editor (same as 0001-0009). No data migration.

-- ----------------------------------------------------------------
-- (a) Bounded-cleanup check_rate_limit()
-- ----------------------------------------------------------------
--
-- Reproduces the 0002 signature, return type, SECURITY DEFINER, search_path,
-- and rate-limit semantics EXACTLY. The ONLY change is the cleanup DELETE:
--
--   0002:  delete every row older than 24h, table-wide, every call.
--   here:  delete only rows for THIS (p_identifier, p_endpoint) that already
--          fall before v_cutoff, i.e. rows this call is about to exclude from
--          its own count anyway.
--
-- Why this is semantics-preserving: v_count only ever considers rows with
-- created_at >= v_cutoff for this exact bucket. Rows with created_at < v_cutoff
-- for this bucket are, by construction, already outside the window and cannot
-- re-enter a future count for the same (identifier, endpoint) window. Removing
-- them changes no allow/deny outcome for any endpoint. The insert-then-return
-- ordering (record the attempt regardless of allow/deny) is unchanged, so
-- persistent offenders still extend their own timeout.
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
  -- Bounded cleanup: prune only this bucket's rows that are already older than
  -- the window being checked. Scoped to (identifier, endpoint) so it rides the
  -- rate_limit_events_lookup_idx prefix and never scans the whole table. Rows
  -- pruned here are exactly the ones excluded from v_count below, so the
  -- rate-limit decision is unchanged versus the 0002 full-range delete.
  delete from public.rate_limit_events
   where identifier = p_identifier
     and endpoint   = p_endpoint
     and created_at < v_cutoff;

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
-- (b) Restrict who can EXECUTE check_rate_limit directly
-- ----------------------------------------------------------------
--
-- check_rate_limit is a raw writer: given any (identifier, endpoint) it inserts
-- a rate_limit_events row. Exposing it to PostgREST's anon/authenticated roles
-- would let any caller forge arbitrary buckets (poison a victim's identifier,
-- or spray junk endpoints to bloat the table). It must only be reachable
-- through the hardcoded-budget wrappers.
--
-- Safe to revoke: every real caller is a SECURITY DEFINER routine owned by the
-- migration runner (public.subscribe, public.compose_action_check,
-- public.diagnostic_rate_limit, and the saved_dashboards_rate_limit_* triggers).
-- Inside a SECURITY DEFINER function, nested calls execute with the DEFINER's
-- privileges, not the invoking role's, so those paths do not depend on the
-- anon/authenticated grant. No application code calls check_rate_limit directly
-- (verified against src/: the only reference is a comment in
-- src/pages/api/diagnostic.ts). The diagnostic rate-limit path itself goes
-- through diagnostic_rate_limit, whose own grant is untouched by this file.
revoke execute on function public.check_rate_limit(text, text, int, int)
  from public;
revoke execute on function public.check_rate_limit(text, text, int, int)
  from anon;
revoke execute on function public.check_rate_limit(text, text, int, int)
  from authenticated;

-- Grant EXECUTE to the trusted server-side role only. service_role is the
-- Supabase key used by out-of-band jobs (the alert evaluator, admin tooling)
-- that legitimately need to record rate-limit attempts directly.
grant execute on function public.check_rate_limit(text, text, int, int)
  to service_role;

-- ----------------------------------------------------------------
-- (c) Per-user cap on alert_rules
-- ----------------------------------------------------------------
--
-- Bound how many alert rules one account can create. Mirrors the per-user
-- limiting intent applied to the composer/saved_dashboards write surfaces: a
-- BEFORE INSERT trigger that raises once the owner is at the ceiling. 100 rules
-- is far past any real user's alert set while capping a runaway insert loop.
--
-- Keyed off owner_id (the column set by the alert_rules_insert_own RLS policy
-- to auth.uid()), so it counts the inserting user's existing rules. SECURITY
-- DEFINER + a pinned search_path so the count runs regardless of the caller's
-- role/search_path.
create or replace function public.alert_rules_enforce_user_cap()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count int;
begin
  select count(*) into v_count
    from public.alert_rules
   where owner_id = new.owner_id;

  if v_count >= 100 then
    raise exception 'Alert-rule limit reached (100 per account). Delete an existing alert, or email keller.scholl@gmail.com for higher limits.'
      using errcode = 'P0001';
  end if;

  return new;
end;
$$;

drop trigger if exists alert_rules_user_cap on public.alert_rules;
create trigger alert_rules_user_cap
  before insert on public.alert_rules
  for each row execute function public.alert_rules_enforce_user_cap();
