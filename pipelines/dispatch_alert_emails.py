"""
Alert-email dispatcher. Reads alert_triggers rows where notified_at
is null, looks up the owner's email via the Supabase admin API, and
sends a notification via the email provider chosen at runtime.

Decoupling fire-detection (pipelines/check_alerts.py) from email
delivery means a transient email-provider outage doesn't drop
triggers — they queue in alert_triggers.notified_at = NULL until
this script can dispatch them.

Provider selection (set ONE of these env vars):
  RESEND_API_KEY        Use Resend (https://resend.com)
  POSTMARK_API_KEY      Use Postmark (https://postmarkapp.com)

Common config:
  ALERTS_FROM_ADDRESS   The "From" email. Required. Must be on a
                        verified domain for the chosen provider.
  ALERTS_FROM_NAME      Display name for the From address. Defaults
                        to "Tape Alerts".
  SUPABASE_URL          + SUPABASE_SERVICE_ROLE_KEY for reading
                        triggers + listing user emails.

Idempotency: each successful send patches notified_at; a transient
failure stamps notify_error and leaves notified_at null so the next
run retries.

Email format: plain text + minimal HTML. The body reads as a one-
liner ("CPI YoY crossed above 4% on 2026-04-15 — observed 4.2%")
with a "Manage your alerts" link back to /alerts/. No batching: one
email per trigger so each alert is its own message in the user's
inbox (matches the "indicator alerts" mental model).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any


def env(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v if v else None


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
    """Resolve a Supabase auth user ID → email via the admin API. The
    admin endpoint requires the service-role key (which we already
    need to read alert_triggers)."""
    try:
        # /auth/v1/admin/users/<id>
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


def condition_phrase(condition: str, threshold: float) -> str:
    if condition == "gt": return f"> {threshold}"
    if condition == "gte": return f"≥ {threshold}"
    if condition == "lt": return f"< {threshold}"
    if condition == "lte": return f"≤ {threshold}"
    if condition == "crosses_above": return f"crossed above {threshold}"
    if condition == "crosses_below": return f"crossed below {threshold}"
    if condition == "change_above": return f"|Δ| > {threshold}"
    return f"{condition} {threshold}"


def build_message(trigger: dict[str, Any]) -> tuple[str, str, str]:
    """(subject, text, html). Plain HTML inside the html string; no
    external CSS — email clients strip <style> tags."""
    label = trigger.get("source_label", trigger.get("source_id", "Unknown"))
    cond = condition_phrase(
        trigger["condition"], float(trigger["threshold"])
    )
    observed = trigger["observed_value"]
    observed_t = trigger["observed_t"]
    subject = f"[Tape] {label} {cond}"
    text = (
        f"{label} {cond} on {observed_t} — observed {observed}.\n\n"
        f"Manage your alerts: https://tape.io/alerts/\n"
    )
    html = (
        f'<p style="font-family:Inter,sans-serif;font-size:14px;color:#1c1c1a;line-height:1.5;">'
        f'<strong>{label}</strong> {cond} on {observed_t} &mdash; observed <strong>{observed}</strong>.'
        f"</p>"
        f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#6f6c66;">'
        f'<a href="https://tape.io/alerts/" style="color:#1c1c1a;">Manage your alerts &rarr;</a>'
        f"</p>"
    )
    return (subject, text, html)


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

    try:
        rows = supabase_get(
            supabase_url,
            "/rest/v1/alert_triggers",
            service_key,
            {
                "notified_at": "is.null",
                "select": "*",
                "order": "triggered_at.asc",
                # Cap per-run to avoid burning through provider quota
                # in a single sweep when a big data refresh fires many
                # rules at once. Tune as needed.
                "limit": "100",
            },
        )
    except Exception as e:
        print(f"Failed to fetch pending triggers: {e}", file=sys.stderr)
        return 2

    if not isinstance(rows, list):
        print("alert_triggers response was not a list", file=sys.stderr)
        return 2

    email_cache: dict[str, str | None] = {}
    sent = 0
    failed = 0
    skipped = 0
    print(f"dispatch_alert_emails: {len(rows)} pending triggers")

    for row in rows:
        owner_id = row.get("owner_id")
        if not owner_id:
            skipped += 1
            continue
        if owner_id not in email_cache:
            email_cache[owner_id] = lookup_user_email(supabase_url, service_key, owner_id)
        to_addr = email_cache[owner_id]
        if not to_addr:
            # Couldn't resolve the user's email — mark with an error
            # so future runs don't keep retrying the lookup forever.
            try:
                supabase_patch(
                    supabase_url,
                    f"/rest/v1/alert_triggers?id=eq.{row['id']}",
                    service_key,
                    {"notify_error": "no email on file for owner"},
                )
            except Exception:
                pass
            skipped += 1
            continue
        subject, text, html = build_message(row)
        try:
            if resend_key:
                send_via_resend(resend_key, from_addr, to_addr, subject, text, html)
            else:
                send_via_postmark(postmark_key or "", from_addr, to_addr, subject, text, html)
            supabase_patch(
                supabase_url,
                f"/rest/v1/alert_triggers?id=eq.{row['id']}",
                service_key,
                {"notified_at": "now()", "notify_error": None},
            )
            sent += 1
        except Exception as e:
            err = str(e)[:300]
            try:
                supabase_patch(
                    supabase_url,
                    f"/rest/v1/alert_triggers?id=eq.{row['id']}",
                    service_key,
                    {"notify_error": err},
                )
            except Exception:
                pass
            print(f"  trigger {row.get('id')}: {err}", file=sys.stderr)
            failed += 1

    print(f"dispatch_alert_emails: sent={sent} failed={failed} skipped={skipped}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
