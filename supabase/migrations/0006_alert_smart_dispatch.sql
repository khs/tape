-- 0006: smarter alert dispatch + acknowledge tracking.
--
-- Adds two columns that drive the dispatcher's retry + auto-pause
-- behavior (see pipelines/dispatch_alert_emails.py for the logic):
--
--   alert_triggers.notify_attempts
--     How many send attempts have run for this trigger. Incremented
--     on every failed dispatch; on the 5th failure the dispatcher
--     stamps a sentinel notified_at ('1970-01-01T00:00:00Z') to drop
--     the trigger from the retry queue and writes a final
--     notify_error so the UI can still surface it.
--
--   alert_rules.pause_reason
--     Human-readable text explaining WHY a rule was auto-paused —
--     populated by the dispatcher when a rule racks up 3+
--     permanently-failed triggers in a row (a strong signal that
--     the user's email setup is broken). Surfaces in /alerts/ next
--     to the rule so the user knows what to fix.
--
-- The pause_reason column augments the existing paused boolean —
-- paused=true with pause_reason=NULL is a manual pause; paused=true
-- with pause_reason set is an auto-pause. Resuming the rule (the
-- "Resume" button in /alerts/) clears both fields.

alter table public.alert_triggers
  add column if not exists notify_attempts integer not null default 0;

alter table public.alert_rules
  add column if not exists pause_reason text;

-- Index that supports "is this rule's recent delivery healthy?"
-- queries — the dispatcher reads the last N triggers per rule to
-- decide whether to auto-pause.
create index if not exists alert_triggers_rule_recent_idx
  on public.alert_triggers(rule_id, triggered_at desc);
