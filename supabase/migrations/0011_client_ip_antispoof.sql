-- 0011: harden public.client_ip() against X-Forwarded-For spoofing.
--
-- Numbering note
-- --------------
-- This migration was originally authored as `0007_client_ip_antispoof.sql`,
-- colliding with `0007_alert_derived_spec.sql`. Because migrations here are
-- applied by hand in the Supabase SQL editor (no schema_migrations ledger, no
-- Supabase CLI ordering), a duplicate 0007 made the apply order ambiguous and
-- put this security fix at risk of being skipped as "the other 0007." It has
-- been renamed to the next free unique number (0011) so ordering is
-- unambiguous, and its single statement is idempotent (CREATE OR REPLACE), so
-- re-applying it -- e.g. if it was already run under the old 0007 name -- is a
-- harmless no-op. The other 0007 (alert_derived_spec) is left as-is.
--
-- What it fixes
-- -------------
-- The original (0002) returned split_part(x-forwarded-for, ',', 1) -- the
-- LEFTMOST hop, which the client fully controls: `curl -H 'X-Forwarded-For:
-- 9.9.9.9'` arrives as `9.9.9.9, <real-ip>`, so split_part(...,1) returns the
-- attacker's value. Rotating it per request gave each request a fresh per-IP
-- bucket, defeating the anon-compose (0004), subscribe (0002) and
-- saved_dashboards INSERT (0003) per-IP rate limits. The per-USER auth.uid()
-- tier and RLS ownership were never affected.
--
-- Fix: prefer cf-connecting-ip, set by the trusted Cloudflare edge and not
-- client-forgeable (Supabase forwards it -- see the 0002 comment). Fall back to
-- X-Forwarded-For only when it's absent, and take the RIGHTMOST hop (split_part
-- index -1, PG14+), i.e. the one the trusted proxy appended -- never the
-- client-controlled leftmost.
--
-- APPLY in the Supabase SQL editor (same as 0001-0010). No data migration; this
-- only redefines a STABLE helper, so existing rate_limit_events rows are fine.
-- CREATE OR REPLACE makes re-application idempotent.
create or replace function public.client_ip() returns text
language sql
stable
as $$
  select coalesce(
    nullif(current_setting('request.headers', true)::json->>'cf-connecting-ip', ''),
    nullif(trim(split_part(
      coalesce(current_setting('request.headers', true)::json->>'x-forwarded-for', ''),
      ',', -1
    )), ''),
    'unknown'
  );
$$;
