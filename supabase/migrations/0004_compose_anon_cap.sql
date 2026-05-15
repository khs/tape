-- Migration 0004: rate-limit anonymous composer actions
--
-- Threat model
-- -------------
-- A bot can hit /compose/ without signing in, cycle through millions of
-- dashboard compositions from one IP, and share each as a /custom/?d=...
-- URL. The URL encoding is purely client-side — base64 of JSON state in
-- a query param — so the "share" action itself is unstoppable: the
-- bot has the URL the moment it knows the encoding. What we CAN do is
-- gate the *composer UI* on meaningful units of work, so a real human
-- exploring the tool is fine while a script trying to use our UI as
-- a generator gets prompted to sign in.
--
-- "Meaningful unit of work" = adding a chart, or creating a derived
-- source. Title typing, description edits, and chart removes don't
-- count — those don't change what shows up in the rendered dashboard.
-- Removes intentionally do not refund budget (otherwise the bot's loop
-- is "add 20, remove 20, add 20 more").
--
-- Signed-in users are exempt: per-user saved_dashboards caps already
-- constrain them at write time, and we don't want to over-friction the
-- UI for real users. The bot-via-fresh-Google-account path still hits
-- the per-IP saved_dashboards INSERT cap from migration 0003 at write
-- time, so this isn't the only defense against that path.
--
-- Anonymous budget: 20 actions per IP per 24h. Empirically real-human
-- composer sessions add 5-10 charts; this clears human use by 2× and
-- caps bots that exceed in seconds. Shared IPs (libraries, offices)
-- might collectively hit 20 in a busy day — the prompt is non-blocking
-- ("sign in to keep editing"), so this is friction, not denial.
--
-- Run once in the Supabase SQL editor after migrations 0002 and 0003.

create or replace function public.compose_action_check(p_action text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  -- Authed users always pass. p_action is accepted but ignored for them.
  if auth.uid() is not null then return true; end if;

  -- Anonymous: one shared budget across action kinds, keyed by IP.
  -- p_action is included as a string parameter for future segmentation
  -- (telemetry on which action type triggers the cap most often) but
  -- doesn't change the limit. Same identifier means "add chart" and
  -- "create derived source" draw from the same 20-per-day budget,
  -- matching the spec.
  return public.check_rate_limit(
    'ip:' || public.client_ip(),
    'compose_anon_action',
    20,
    86400
  );
end;
$$;

grant execute on function public.compose_action_check(text) to anon, authenticated;
