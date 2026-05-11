-- Fix-up for migrations/0001_subscribers.sql. The initial INSERT policy used a
-- regex with a POSIX [:space:] class inside the WITH CHECK clause; PostgreSQL
-- evaluated it as false for ordinary emails, so anon POSTs were rejected with
-- "new row violates row-level security policy" (code 42501).
--
-- Two changes:
--   1. Drop and recreate the policy with WITH CHECK (true). Email-shape
--      validation already happens client-side; if we want DB-level enforcement
--      later, a column-level CHECK constraint is the right place — see the
--      commented-out ALTER at the bottom of this file for a sketch.
--   2. Re-state the INSERT grant. In Supabase the `anon`/`authenticated` roles
--      get SELECT on public tables by default, but writes require an explicit
--      grant.
--
-- Run this once in the Supabase SQL editor.

drop policy if exists "subscribers_anon_insert" on subscribers;

create policy "subscribers_anon_insert"
  on subscribers
  for insert
  to anon, authenticated
  with check (true);

grant insert on subscribers to anon, authenticated;

-- Optional belt-and-suspenders for the future. Uncomment to enforce the
-- email shape at the column level (rejects malformed input even from
-- service-role inserts):
--
-- alter table subscribers
--   add constraint subscribers_email_shape
--   check (email ~ '^[^@]+@[^@]+\.[^@]+$');
