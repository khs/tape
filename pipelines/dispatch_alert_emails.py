"""
Alert-email dispatcher with batching + retry cap + auto-pause.

Walks pending alert_triggers rows (notified_at IS NULL), groups them
by owner, sends ONE digest email per owner per run via Resend or
Postmark, and stamps notified_at on success. Triggers that fail
repeatedly get a sentinel notified_at to drop them from the queue;
rules that produce too many failed triggers in a row get auto-paused
with a pause_reason so the owner can see why their notifications
stopped.

Schema columns this script reads + writes:
  alert_triggers.notified_at         null = pending; now() = delivered;
                                     '1970-01-01T00:00:00Z' = dropped
                                     after retry cap exhausted
  alert_triggers.notify_attempts     count of dispatch attempts
  alert_triggers.notify_error        most recent failure message
  alert_rules.paused                 true = won't fire new triggers
  alert_rules.pause_reason           human text for AUTO-pause; NULL
                                     for manual pause (or not paused)

Provider selection (set ONE):
  RESEND_API_KEY        Resend (https://resend.com)
  POSTMARK_API_KEY      Postmark (https://postmarkapp.com)

Common config:
  SUPABASE_URL                + SUPABASE_SERVICE_ROLE_KEY for reading
                              triggers + listing user emails + patching
                              state.
  ALERTS_FROM_ADDRESS         required. Verified-domain sender.
  ALERTS_FROM_NAME            display name; defaults to "Tape Alerts".
  ALERT_MAX_ATTEMPTS          max delivery attempts before sentinel
                              drop. Default 5.
  ALERT_AUTOPAUSE_THRESHOLD   how many permanently-failed triggers in
                              a rule's last N before auto-pause.
                              Default 3.
  ALERT_AUTOPAUSE_WINDOW      look back this many triggers per rule
                              when checking auto-pause. Default 5.
  ALERTS_MANAGE_URL           URL printed in every email pointing the
                              user back to the alerts management page.
                              Defaults to https://tape.io/alerts/
                              (aspirational); override to the actual
                              prod URL until the custom domain is
                              live.

Soft-imports python-dotenv at the top so a local invocation reads
.env automatically. CI passes env via secrets — load_dotenv() is a
no-op then.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(
        dotenv_path=Path(__file__).resolve().parent.parent / ".env",
        override=False,
    )
except ImportError:
    pass


# Sentinel that takes a trigger out of the retry queue without
# pretending it was successfully delivered. The Unix epoch is far
# enough in the past that no real delivery could have stamped this
# value — easy to scan in the trigger feed and filter out of
# "successfully delivered" queries.
SENTINEL_DROPPED = "1970-01-01T00:00:00Z"


def env(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v if v else None


def env_int(name: str, default: int) -> int:
    raw = env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Tunables. Read once at module import. The defaults are the
# "reasonable behavior for a small-scale alert system" values; bump
# via env var if you want tighter / looser thresholds.
MAX_ATTEMPTS = env_int("ALERT_MAX_ATTEMPTS", 5)
AUTOPAUSE_THRESHOLD = env_int("ALERT_AUTOPAUSE_THRESHOLD", 3)
AUTOPAUSE_WINDOW = env_int("ALERT_AUTOPAUSE_WINDOW", 5)


# --------------------------------------------------------------------
# Supabase HTTP helpers
# --------------------------------------------------------------------

def supabase_get(url: str, path: str, key: str, params: dict[str, str]) -> Any:
    full = f"{url.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        full,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def supabase_patch(url: str, path: str, key: str, body: Any) -> None:
    full = f"{url.rstrip('/')}{path}"
    req = urllib.request.Request(
        full,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def lookup_user_email(supabase_url: str, key: str, user_id: str) -> str | None:
    try:
        full = f"{supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}"
        req = urllib.request.Request(
            full,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            row = json.loads(resp.read())
        email = row.get("email")
        return email if isinstance(email, str) and email else None
    except Exception as e:
        print(f"  user lookup failed for {user_id}: {e}", file=sys.stderr)
        return None


# --------------------------------------------------------------------
# Message building
# --------------------------------------------------------------------

def condition_phrase(condition: str, threshold: float) -> str:
    """Render the alert's condition + threshold as a short prose
    fragment used in subjects, bullet lines, and the inline UI."""
    if condition == "gt":
        return f"> {threshold}"
    if condition == "gte":
        return f"≥ {threshold}"
    if condition == "lt":
        return f"< {threshold}"
    if condition == "lte":
        return f"≤ {threshold}"
    if condition == "crosses_above":
        return f"crossed above {threshold}"
    if condition == "crosses_below":
        return f"crossed below {threshold}"
    if condition == "change_above":
        return f"|Δ| > {threshold}"
    return f"{condition} {threshold}"


def build_batch_message(
    triggers: list[dict[str, Any]],
    manage_url: str = "https://tape.io/alerts/",
) -> tuple[str, str, str]:
    """Render a list of triggers as one email — (subject, text, html).

    Subject conventions:
      1 trigger : [Tape] <Source label> <condition>
      2+        : [Tape] N alerts: <first label>, and N-1 more

    Body lists each trigger on its own line, in the order they
    triggered (newest fires last to match a chronological reading).
    Empty input is a programming error and raises rather than
    emitting a blank message.
    """
    if not triggers:
        raise ValueError("build_batch_message: triggers list must be non-empty")
    # Newest-last reading order — the dispatcher sorts pending by
    # triggered_at ASC, so this preserves it.
    n = len(triggers)
    first_label = _one_line(
        str(triggers[0].get("source_label", triggers[0].get("source_id", "Unknown")))
    )
    first_phrase = condition_phrase(
        triggers[0]["condition"], float(triggers[0]["threshold"])
    )
    if n == 1:
        subject = f"[Tape] {first_label} {first_phrase}"
    else:
        subject = f"[Tape] {n} alerts: {first_label} {first_phrase}, and {n - 1} more"

    # Text body
    text_lines: list[str] = []
    text_lines.append(
        f"You have {n} pending Tape alert{'s' if n != 1 else ''}."
        if n != 1
        else "You have a pending Tape alert."
    )
    text_lines.append("")
    for t in triggers:
        label = _one_line(str(t.get("source_label", t.get("source_id", "Unknown"))))
        phrase = condition_phrase(t["condition"], float(t["threshold"]))
        obs = t["observed_value"]
        obs_t = t["observed_t"]
        text_lines.append(
            f"- {label} {phrase} on {obs_t}, observed {obs}."
        )
    text_lines.append("")
    text_lines.append(f"Manage your alerts: {manage_url}")
    text = "\n".join(text_lines) + "\n"

    # HTML body. Inline styles (no <style> block) — email clients
    # strip <style>; inline is the only reliable formatting path.
    items_html = "".join(
        (
            f'<li style="margin: 0 0 6px;">'
            f'<strong>{escape_html(_one_line(str(t.get("source_label", t.get("source_id", "Unknown")))))}</strong> '
            f'{escape_html(condition_phrase(t["condition"], float(t["threshold"])))} '
            f'on {escape_html(t["observed_t"])}, '
            f'observed <strong>{escape_html(str(t["observed_value"]))}</strong>.'
            f'</li>'
        )
        for t in triggers
    )
    headline = (
        f"You have {n} pending Tape alert{'s' if n != 1 else ''}."
        if n != 1
        else "You have a pending Tape alert."
    )
    html = (
        f'<div style="font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif; color: #1c1c1a;">'
        f'<p style="font-size: 14px; line-height: 1.5; margin: 0 0 12px;">{escape_html(headline)}</p>'
        f'<ul style="font-size: 14px; line-height: 1.55; padding-left: 18px; margin: 0 0 14px;">{items_html}</ul>'
        f'<p style="font-size: 12px; color: #6f6c66; margin: 0;">'
        f'<a href="{escape_html(manage_url)}" style="color: #1c1c1a;">Manage your alerts &rarr;</a>'
        f"</p>"
        f"</div>"
    )
    return (subject, text, html)


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _one_line(s: str) -> str:
    """Flatten a label to a single line: replace CR/LF and any other
    control char with a space, then collapse whitespace. Defense in depth
    (OWASP A05) — a source label must never inject an email header (the
    Subject) or break the plain-text body. Labels come from the source
    catalog today, not free user input, but sanitize anyway so a future
    free-text field can't smuggle a newline into a header.
    """
    flattened = "".join(" " if (ch < " " or ch == "\x7f") else ch for ch in s)
    return " ".join(flattened.split())


# --------------------------------------------------------------------
# Provider sends
# --------------------------------------------------------------------

def send_via_resend(
    api_key: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    text: str,
    html: str,
) -> None:
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({
            "from": from_addr,
            "to": [to_addr],
            "subject": subject,
            "text": text,
            "html": html,
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def send_via_postmark(
    api_key: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    text: str,
    html: str,
) -> None:
    req = urllib.request.Request(
        "https://api.postmarkapp.com/email",
        data=json.dumps({
            "From": from_addr,
            "To": to_addr,
            "Subject": subject,
            "TextBody": text,
            "HtmlBody": html,
            "MessageStream": "outbound",
        }).encode("utf-8"),
        headers={
            "X-Postmark-Server-Token": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


# --------------------------------------------------------------------
# Auto-pause helpers
# --------------------------------------------------------------------

def should_auto_pause_rule(
    recent_attempts: list[int],
    recent_notified_at: list[str | None],
    *,
    threshold: int = AUTOPAUSE_THRESHOLD,
    sentinel: str = SENTINEL_DROPPED,
) -> bool:
    """Decide whether a rule has racked up enough permanently-failed
    triggers in its recent history to warrant an auto-pause.

    Inputs (parallel arrays):
      recent_attempts     notify_attempts on each of the rule's
                          last N triggers (newest first)
      recent_notified_at  notified_at on each of those triggers
                          (newest first). NULL = still pending;
                          sentinel = permanently failed; any other
                          ISO timestamp = successfully delivered.

    Returns True when at least `threshold` of the recent triggers
    are sentinel-stamped (= dropped after retry cap). Pure function
    so it's trivially testable.
    """
    if len(recent_attempts) != len(recent_notified_at):
        # Defensive — caller bug. Don't auto-pause on inconsistent
        # input; let a human eyeball it.
        return False
    sentinel_count = sum(
        1 for ts in recent_notified_at if ts == sentinel
    )
    return sentinel_count >= threshold


# --------------------------------------------------------------------
# Main dispatch loop
# --------------------------------------------------------------------

def main() -> int:
    supabase_url = env("SUPABASE_URL") or env("PUBLIC_SUPABASE_URL")
    service_key = env("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        print(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.",
            file=sys.stderr,
        )
        return 2

    resend_key = env("RESEND_API_KEY")
    postmark_key = env("POSTMARK_API_KEY")
    if not resend_key and not postmark_key:
        print(
            "No email provider configured. Set RESEND_API_KEY or "
            "POSTMARK_API_KEY to dispatch.",
            file=sys.stderr,
        )
        return 2
    from_addr_raw = env("ALERTS_FROM_ADDRESS")
    if not from_addr_raw:
        print(
            "ALERTS_FROM_ADDRESS is required (must be on a verified "
            "sending domain for the email provider).",
            file=sys.stderr,
        )
        return 2
    from_name = env("ALERTS_FROM_NAME") or "Tape Alerts"
    from_addr = f"{from_name} <{from_addr_raw}>"
    manage_url = env("ALERTS_MANAGE_URL") or "https://tape.io/alerts/"

    try:
        rows = supabase_get(
            supabase_url,
            "/rest/v1/alert_triggers",
            service_key,
            {
                "notified_at": "is.null",
                "select": "*",
                "order": "triggered_at.asc",
                # 500 per run is a soft cap. Once batched into one
                # email per owner the per-provider call count drops
                # dramatically; this exists to bound a runaway-loop
                # blast radius rather than provider quota.
                "limit": "500",
            },
        )
    except Exception as e:
        print(f"Failed to fetch pending triggers: {e}", file=sys.stderr)
        return 2

    if not isinstance(rows, list):
        print("alert_triggers response was not a list", file=sys.stderr)
        return 2

    # Group pending triggers by owner_id. Each owner gets ONE email
    # per run containing every owed trigger.
    by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        owner_id = row.get("owner_id")
        if not owner_id:
            continue
        by_owner[owner_id].append(row)

    email_cache: dict[str, str | None] = {}
    sent_emails = 0
    sent_triggers = 0
    failed_emails = 0
    skipped_triggers = 0
    auto_paused_rules: set[str] = set()
    print(
        f"dispatch_alert_emails: {len(rows)} pending triggers across "
        f"{len(by_owner)} owners"
    )

    for owner_id, triggers in by_owner.items():
        # Look up the owner's email once per run, even when their
        # batch has 50 triggers. Falsy = couldn't resolve.
        if owner_id not in email_cache:
            email_cache[owner_id] = lookup_user_email(
                supabase_url, service_key, owner_id
            )
        to_addr = email_cache[owner_id]
        if not to_addr:
            # Terminal failure — no email on file for this owner.
            # Stamp every trigger with the sentinel + error so we
            # don't keep retrying the admin-API lookup forever.
            for t in triggers:
                try:
                    supabase_patch(
                        supabase_url,
                        f"/rest/v1/alert_triggers?id=eq.{t['id']}",
                        service_key,
                        {
                            "notified_at": SENTINEL_DROPPED,
                            "notify_error": "no email on file for owner",
                            "notify_attempts": int(t.get("notify_attempts", 0)) + 1,
                        },
                    )
                except Exception:
                    pass
            skipped_triggers += len(triggers)
            continue

        # Build + send the batch email.
        try:
            subject, text, html = build_batch_message(triggers, manage_url=manage_url)
        except Exception as e:
            # build_batch_message is unlikely to fail in practice but
            # the catch lets one corrupt trigger row not poison the
            # whole owner's batch.
            print(
                f"  owner {owner_id}: message-build error: {e}",
                file=sys.stderr,
            )
            failed_emails += 1
            continue

        try:
            if resend_key:
                send_via_resend(resend_key, from_addr, to_addr, subject, text, html)
            else:
                send_via_postmark(
                    postmark_key or "", from_addr, to_addr, subject, text, html
                )
            # Success — stamp every trigger in the batch.
            for t in triggers:
                supabase_patch(
                    supabase_url,
                    f"/rest/v1/alert_triggers?id=eq.{t['id']}",
                    service_key,
                    {
                        "notified_at": "now()",
                        "notify_error": None,
                        "notify_attempts": int(t.get("notify_attempts", 0)) + 1,
                    },
                )
            sent_emails += 1
            sent_triggers += len(triggers)
        except Exception as e:
            err = str(e)[:300]
            # Per-trigger retry bookkeeping. Each failed delivery
            # bumps notify_attempts; once a trigger hits
            # MAX_ATTEMPTS we drop it with the sentinel + write a
            # terminal notify_error so the UI can show it.
            for t in triggers:
                new_attempts = int(t.get("notify_attempts", 0)) + 1
                terminal = new_attempts >= MAX_ATTEMPTS
                try:
                    supabase_patch(
                        supabase_url,
                        f"/rest/v1/alert_triggers?id=eq.{t['id']}",
                        service_key,
                        {
                            "notify_error": err,
                            "notify_attempts": new_attempts,
                            **(
                                {"notified_at": SENTINEL_DROPPED}
                                if terminal
                                else {}
                            ),
                        },
                    )
                    if terminal:
                        # Check if the rule should now auto-pause.
                        maybe_auto_pause_rule(
                            supabase_url,
                            service_key,
                            t.get("rule_id"),
                            err,
                            auto_paused_rules,
                        )
                except Exception:
                    pass
            failed_emails += 1
            print(f"  owner {owner_id}: {err}", file=sys.stderr)

    print(
        f"dispatch_alert_emails: sent_emails={sent_emails} "
        f"sent_triggers={sent_triggers} failed_emails={failed_emails} "
        f"skipped_triggers={skipped_triggers} "
        f"auto_paused_rules={len(auto_paused_rules)}"
    )
    return 0 if failed_emails == 0 else 1


def maybe_auto_pause_rule(
    supabase_url: str,
    service_key: str,
    rule_id: str | None,
    last_error: str,
    auto_paused_set: set[str],
) -> None:
    """When a trigger gets dropped after the retry cap, check whether
    enough of the rule's recent triggers were also dropped. If so,
    auto-pause the rule + write a pause_reason so the owner sees why
    delivery stopped.

    Idempotent across a single dispatcher run via auto_paused_set —
    a rule that auto-pauses won't get re-paused on the same run if
    another trigger from the same rule also exhausts retries.
    """
    if not rule_id:
        return
    if rule_id in auto_paused_set:
        return
    try:
        recent = supabase_get(
            supabase_url,
            "/rest/v1/alert_triggers",
            service_key,
            {
                "rule_id": f"eq.{rule_id}",
                "select": "notify_attempts,notified_at",
                "order": "triggered_at.desc",
                "limit": str(AUTOPAUSE_WINDOW),
            },
        )
        if not isinstance(recent, list):
            return
        attempts = [int(r.get("notify_attempts", 0)) for r in recent]
        notified = [r.get("notified_at") for r in recent]
        if not should_auto_pause_rule(attempts, notified):
            return
        reason = (
            f"Auto-paused after {AUTOPAUSE_THRESHOLD}+ delivery failures. "
            f"Last error: {last_error[:160]}. "
            f"Resume from /alerts/ after fixing the email setup."
        )
        supabase_patch(
            supabase_url,
            f"/rest/v1/alert_rules?id=eq.{rule_id}",
            service_key,
            {"paused": True, "pause_reason": reason},
        )
        auto_paused_set.add(rule_id)
        print(f"  rule {rule_id}: auto-paused — {reason[:80]}")
    except Exception as e:
        print(
            f"  rule {rule_id}: auto-pause check failed: {e}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    sys.exit(main())
