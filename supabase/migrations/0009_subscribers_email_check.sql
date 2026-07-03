-- Migration 0009: DB-level email-shape CHECK on public.subscribers
--
-- Why this exists
-- ----------------
-- Subscribes flow through the public.subscribe() RPC (migration 0002), which is
-- SECURITY DEFINER and therefore runs as the function owner, bypassing RLS. The
-- client form (src/components/EmailSignup.astro) validates the address shape and
-- trims + lowercases before sending, but nothing at the DB layer stops a garbage
-- value from being persisted if that client check is bypassed (a direct RPC call,
-- a future code path, etc.). This adds the belt-and-suspenders column CHECK that
-- migrations/0002_subscribers_fix_policy.sql sketched but left commented out.
--
-- The regex mirrors the client-side EMAIL_RE: one-or-more non-@ chars, an @, more
-- non-@ chars, a dot, and a TLD. It is a shape check, not full RFC 5321 — just
-- enough to reject obvious junk. Written in plain POSIX ERE so PostgreSQL's ~
-- operator accepts it directly.
--
-- Added NOT VALID so the constraint enforces immediately on every new INSERT /
-- UPDATE without scanning (or failing on) any pre-existing rows. New writes,
-- including the SECURITY DEFINER RPC insert, are checked from the moment this
-- runs.
--
-- Run once in the Supabase SQL editor.

alter table public.subscribers
  add constraint subscribers_email_shape
  check (email ~ '^[^@]+@[^@]+\.[^@]+$')
  not valid;
