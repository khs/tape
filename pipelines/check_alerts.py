"""
Indicator-alert evaluator. Runs after each data refresh: walks every
active alert_rules row, evaluates its condition against the source's
latest observation, and inserts an alert_triggers row when the
condition fires.

Schema lives in supabase/migrations/0005_indicator_alerts.sql.

Conditions:
  gt              current > threshold
  gte             current >= threshold
  lt              current < threshold
  lte             current <= threshold
  crosses_above   prev <= threshold AND current > threshold
  crosses_below   prev >= threshold AND current < threshold
  change_above    abs(current - prev) > threshold

Idempotency: the evaluator stamps `last_value_t` on every rule it
checks. A rule whose source's latest observation date == the rule's
last_value_t is skipped (already evaluated for this vintage). So
running the evaluator twice between data refreshes produces zero new
triggers.

Email delivery: out of scope here. This script writes to
alert_triggers; an out-of-band job (or the user's own infrastructure)
watches that table and dispatches notifications.

Environment:
  SUPABASE_URL                — required
  SUPABASE_SERVICE_ROLE_KEY   — required. Read alert_rules + insert
                                alert_triggers + update last_value_*
                                on rules. Service-role bypasses RLS;
                                evaluator runs server-side, not as
                                any user.

The script returns 0 on success, 1 on partial failure (some rules
errored but others completed), 2 on hard failure (Supabase auth /
connectivity died).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "public" / "data"
SOURCES_ROOT = ROOT / "src" / "content" / "sources"

# Source IDs come from the alert_rules table which any authed user
# can write to (RLS only enforces owner_id == auth.uid()). The
# evaluator runs under the service role so it could be tricked into
# reading arbitrary YAML / JSON via a malicious source_id like
# "../../../etc/passwd". Validate against a strict character class
# before touching the filesystem.
SAFE_SOURCE_ID = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_./-]*$")

# Auto-load .env from the repo root when python-dotenv is available.
# Lets the user keep SUPABASE_SERVICE_ROLE_KEY (+ email-provider keys)
# in a single .env file alongside the other API keys, sourced by the
# local data-refresh runner OR picked up automatically here on
# direct CLI invocation. CI workflows pass these via `env:` blocks
# from GitHub Secrets — load_dotenv() finds no .env there and is a
# no-op. Soft-imports so the script still runs in minimal envs
# without the dotenv dep.
try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(dotenv_path=ROOT / ".env", override=False)
except ImportError:
    pass


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


def supabase_post(url: str, path: str, key: str, body: Any) -> None:
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
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


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


def load_latest_observation(source_id: str) -> tuple[str, float] | None:
    """Read the source's data file and return (latest_t, latest_v).
    Source IDs look like ``fred/cpi_yoy`` → that maps to
    ``public/data/fred/CPIAUCSL_PC1.json`` via the source YAML's
    dataFile. We DON'T parse YAML here; instead, ride on the
    convention that source IDs match YAML filenames + look up the
    YAML to find dataFile.

    Returns None when the source can't be resolved or has no points.
    """
    # Reject anything that doesn't look like a source ID. Without
    # this guard a malicious authed user could write source_id =
    # "../../../etc/passwd" into alert_rules and the service-role
    # evaluator would happily read arbitrary YAML.
    if not source_id or not SAFE_SOURCE_ID.match(source_id):
        return None
    yaml_path = SOURCES_ROOT / f"{source_id}.yaml"
    # Belt-and-suspenders: even with the regex guard, ensure the
    # resolved path is INSIDE the sources directory (a YAML file
    # could symlink elsewhere; on most filesystems this still
    # constrains the read).
    try:
        yaml_path.resolve().relative_to(SOURCES_ROOT.resolve())
    except ValueError:
        return None
    if not yaml_path.exists():
        return None
    # Tiny YAML extractor — pull `dataFile:` from the YAML without
    # importing pyyaml. The dataFile line is canonical "dataFile: path".
    data_file: str | None = None
    for line in yaml_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("dataFile:"):
            data_file = stripped.split(":", 1)[1].strip().strip("\"'")
            break
    if not data_file:
        return None
    # dataFile is YAML-author-controlled; we trust it but still
    # ensure the resolved path stays under the repo. A malformed
    # YAML pointing to /etc/passwd would otherwise read it.
    json_path = ROOT / data_file
    try:
        json_path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return None
    if not json_path.exists():
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    # Source data files are dict-shaped (points + metadata). A list
    # at root would crash the .get() call; guard it explicitly.
    if not isinstance(payload, dict):
        return None
    points = payload.get("points")
    if not isinstance(points, list) or not points:
        return None
    last = points[-1]
    if not isinstance(last, dict):
        return None
    t = last.get("t")
    v = last.get("v")
    if not isinstance(t, str) or not isinstance(v, (int, float)):
        return None
    return (t, float(v))


def evaluate_condition(
    condition: str,
    threshold: float,
    current: float,
    prev: float | None,
) -> bool:
    """True when the rule's condition fires for (current, prev)."""
    if condition == "gt":
        return current > threshold
    if condition == "gte":
        return current >= threshold
    if condition == "lt":
        return current < threshold
    if condition == "lte":
        return current <= threshold
    if condition == "crosses_above":
        return prev is not None and prev <= threshold and current > threshold
    if condition == "crosses_below":
        return prev is not None and prev >= threshold and current < threshold
    if condition == "change_above":
        return prev is not None and abs(current - prev) > threshold
    return False


def main() -> int:
    supabase_url = env("SUPABASE_URL") or env("PUBLIC_SUPABASE_URL")
    service_key = env("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        print(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. "
            "Set both before running check_alerts.py.",
            file=sys.stderr,
        )
        return 2

    # Pull every active rule. Supabase REST paginates at 1000 rows by
    # default — when we exceed that, paginate properly.
    try:
        rules = supabase_get(
            supabase_url,
            "/rest/v1/alert_rules",
            service_key,
            {"paused": "eq.false", "select": "*", "order": "id.asc"},
        )
    except Exception as e:
        print(f"Failed to fetch alert_rules: {e}", file=sys.stderr)
        return 2
    if not isinstance(rules, list):
        print("alert_rules response was not a list", file=sys.stderr)
        return 2

    fired = 0
    skipped = 0
    errors = 0
    print(f"check_alerts: {len(rules)} active rules to evaluate")

    for rule in rules:
        try:
            rule_id = rule["id"]
            source_id = rule["source_id"]
            condition = rule["condition"]
            threshold = float(rule["threshold"])
            last_t_seen = rule.get("last_value_t")
            last_v_seen = rule.get("last_value_seen")
            owner_id = rule["owner_id"]

            obs = load_latest_observation(source_id)
            if obs is None:
                skipped += 1
                continue
            (latest_t, latest_v) = obs

            # Idempotency: skip rules whose source hasn't moved since
            # the last evaluation. Sidesteps re-firing on a no-op data
            # refresh that happened to bump file mtimes.
            if last_t_seen == latest_t:
                skipped += 1
                continue

            prev_v = float(last_v_seen) if isinstance(last_v_seen, (int, float)) else None
            triggered = evaluate_condition(condition, threshold, latest_v, prev_v)

            if triggered:
                # Insert trigger snapshot. Service-role auth bypasses
                # RLS; the row's owner_id is set explicitly so
                # downstream queries (and the owner's /alerts/ page)
                # see the right rows.
                supabase_post(
                    supabase_url,
                    "/rest/v1/alert_triggers",
                    service_key,
                    {
                        "rule_id": rule_id,
                        "owner_id": owner_id,
                        "source_id": source_id,
                        "source_label": rule.get("source_label", source_id),
                        "condition": condition,
                        "threshold": threshold,
                        "observed_value": latest_v,
                        "observed_t": latest_t,
                    },
                )
                fired += 1

            # Update last_value_* on the rule even when not triggered —
            # crosses_above / crosses_below need the prior value to
            # detect the transition next time around.
            supabase_patch(
                supabase_url,
                f"/rest/v1/alert_rules?id=eq.{rule_id}",
                service_key,
                {
                    "last_value_seen": latest_v,
                    "last_value_t": latest_t,
                    **({"last_triggered_at": "now()"} if triggered else {}),
                },
            )
        except Exception as e:
            print(f"  rule {rule.get('id', '?')}: error {e}", file=sys.stderr)
            errors += 1

    print(
        f"check_alerts: fired={fired} skipped={skipped} errors={errors}"
    )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
