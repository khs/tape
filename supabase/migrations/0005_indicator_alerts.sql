-- Indicator alerts — threshold-based notification rules + a triggered-
-- event log per user.
--
-- A user picks a source (e.g. fred/cpi_yoy) and sets a condition
-- (>= 4%, crosses below 0%, etc.). After each data refresh, the
-- pipelines/check_alerts.py job walks every active rule, evaluates
-- it against the source's latest observation, and inserts a row
-- into alert_triggers when the condition fires. Email delivery is
-- out of scope for this migration — the trigger log is the audit
-- surface; an email-sending job hooks alert_triggers when ready.
--
-- Rule conditions (text column, kept lowercase + underscore):
--   gt              current_value >  threshold
--   gte             current_value >= threshold
--   lt              current_value <  threshold
--   lte             current_value <= threshold
--   crosses_above   last_value_seen <= threshold AND current_value > threshold
--   crosses_below   last_value_seen >= threshold AND current_value < threshold
--   change_above    abs(current_value - last_value_seen) > threshold
--                   (absolute change between consecutive observations)

create table if not exists public.alert_rules (
  id                  uuid primary key default gen_random_uuid(),
  owner_id            uuid not null references auth.users(id) on delete cascade,
  source_id           text not null,
  -- Denormalized for display so the alerts UI doesn't have to fetch
  -- the source's YAML on every render. Refreshed by the client when
  -- the rule is updated; never read by the evaluation pipeline.
  source_label        text not null,
  condition           text not null
                        check (condition in (
                          'gt', 'gte', 'lt', 'lte',
                          'crosses_above', 'crosses_below', 'change_above'
                        )),
  threshold           numeric not null,
  -- Optional human label so the user can give the rule a name
  -- ("Watch for inflation > 4%"). Falls back to a generated label
  -- ("fred/cpi_yoy gte 4.0") when blank.
  label               text,
  -- Last raw value seen by the evaluator. Required to detect
  -- crosses_above / crosses_below transitions; also useful for
  -- change_above. Nullable on first evaluation (the rule has
  -- never been checked).
  last_value_seen     numeric,
  -- Last as-of date of the source data when the rule was checked.
  -- Used by the evaluator to skip rules whose source hasn't been
  -- refreshed since the previous run.
  last_value_t        date,
  -- When the condition most recently fired. Null = never fired.
  last_triggered_at   timestamptz,
  paused              boolean not null default false,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create index if not exists alert_rules_owner_idx
  on public.alert_rules(owner_id, updated_at desc);
create index if not exists alert_rules_source_idx
  on public.alert_rules(source_id) where paused = false;

alter table public.alert_rules enable row level security;

drop policy if exists "alert_rules_select_own" on public.alert_rules;
create policy "alert_rules_select_own"
  on public.alert_rules
  for select
  using (auth.uid() = owner_id);

drop policy if exists "alert_rules_insert_own" on public.alert_rules;
create policy "alert_rules_insert_own"
  on public.alert_rules
  for insert
  with check (auth.uid() is not null and auth.uid() = owner_id);

drop policy if exists "alert_rules_update_own" on public.alert_rules;
create policy "alert_rules_update_own"
  on public.alert_rules
  for update
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

drop policy if exists "alert_rules_delete_own" on public.alert_rules;
create policy "alert_rules_delete_own"
  on public.alert_rules
  for delete
  using (auth.uid() = owner_id);

drop trigger if exists alert_rules_touch on public.alert_rules;
create trigger alert_rules_touch
  before update on public.alert_rules
  for each row execute function public.touch_updated_at();


-- Trigger log: every time a rule fires, we insert a row here. This is
-- the audit surface the user sees on /alerts/. An out-of-band job can
-- watch this table and dispatch emails when the user wires that up.

create table if not exists public.alert_triggers (
  id              uuid primary key default gen_random_uuid(),
  rule_id         uuid not null references public.alert_rules(id) on delete cascade,
  owner_id        uuid not null references auth.users(id) on delete cascade,
  -- Snapshot of the rule + observed value at fire time. The rule
  -- itself can be edited after a trigger fires; the snapshot keeps
  -- the historical record intact.
  source_id       text not null,
  source_label    text not null,
  condition       text not null,
  threshold       numeric not null,
  observed_value  numeric not null,
  observed_t      date not null,
  triggered_at    timestamptz not null default now(),
  -- Boolean: has the user opened / acknowledged this trigger? UI
  -- defaults unread on first display; a click marks read.
  acknowledged    boolean not null default false,
  -- Email dispatch state. pipelines/dispatch_alert_emails.py walks
  -- this table looking for rows where notified_at is null and an
  -- email_address is resolvable, calls the email provider, and
  -- stamps notified_at on success. Decoupling fire from email send
  -- means a transient email-provider outage doesn't lose triggers —
  -- they sit in the queue until delivery.
  notified_at     timestamptz,
  notify_error    text
);

create index if not exists alert_triggers_owner_idx
  on public.alert_triggers(owner_id, triggered_at desc);
create index if not exists alert_triggers_rule_idx
  on public.alert_triggers(rule_id, triggered_at desc);

alter table public.alert_triggers enable row level security;

drop policy if exists "alert_triggers_select_own" on public.alert_triggers;
create policy "alert_triggers_select_own"
  on public.alert_triggers
  for select
  using (auth.uid() = owner_id);

-- INSERTs come from the server-side evaluator running with the
-- Supabase service role; no client-side insert policy is needed.
-- (When the evaluator switches to running through an RPC under a
-- user's auth context, add an insert policy then.)

drop policy if exists "alert_triggers_update_own" on public.alert_triggers;
create policy "alert_triggers_update_own"
  on public.alert_triggers
  for update
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

drop policy if exists "alert_triggers_delete_own" on public.alert_triggers;
create policy "alert_triggers_delete_own"
  on public.alert_triggers
  for delete
  using (auth.uid() = owner_id);
