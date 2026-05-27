-- Migration 0007: derived-indicator alerts.
--
-- Lets a user define an alert on a COMBINATION of two existing
-- sources (e.g. "CPI YoY / 10-year Treasury yield crossed 0.3") via
-- a single alert_rules row. The combination is stored as a JSON spec
-- in `derived_spec`; the evaluator computes A op B at each timestamp
-- and compares against threshold.
--
-- Why one column instead of a separate user_derived_indicators
-- table: the simpler the schema, the fewer migration steps to ship
-- and the fewer integrity rules to think about. A user who wants the
-- same derivation across multiple alerts can copy-paste the spec;
-- when that becomes painful we promote to a real table. For now,
-- one-off + alert-scoped is the right shape.
--
-- derived_spec shape (validated client-side; trust enforced by RLS
-- ownership):
--   { "a": "<source-id>", "op": "divide" | "sum" | "diff", "b": "<source-id>" }
--
-- Rows without derived_spec behave EXACTLY as before — evaluator
-- reads source_id's data file directly. Rows with derived_spec
-- ignore source_id for data resolution (source_id stays populated
-- as "derived:adhoc" or similar sentinel for UI display + the
-- alert_triggers FK).
--
-- Run once in the Supabase SQL editor.

alter table public.alert_rules
  add column if not exists derived_spec jsonb;

-- Document the column for anyone reading the schema later.
comment on column public.alert_rules.derived_spec is
  'Optional derivation spec for combination alerts: { a, op: "divide" | "sum" | "diff", b }. NULL means a normal single-source alert.';

-- Optional sanity-check constraint. Rejects malformed specs at write
-- time (e.g. missing op, op not in the allowed set). NULL is allowed
-- (and is the dominant case for legacy rules).
alter table public.alert_rules
  drop constraint if exists alert_rules_derived_spec_shape;
alter table public.alert_rules
  add constraint alert_rules_derived_spec_shape
  check (
    derived_spec is null
    or (
      jsonb_typeof(derived_spec) = 'object'
      and derived_spec ? 'a'
      and derived_spec ? 'b'
      and derived_spec ? 'op'
      and (derived_spec ->> 'op') in ('divide', 'sum', 'diff')
    )
  );
