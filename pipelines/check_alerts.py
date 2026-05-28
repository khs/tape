"""
Indicator-alert evaluator. Runs after each data refresh: walks every
active alert_rules row, evaluates its condition against every source
observation that has landed since the rule's last run, and inserts an
alert_triggers row when the condition fires.

Schema lives in supabase/migrations/0005_indicator_alerts.sql.

Conditions (current = an observation, prev = the one before it):
  gt / gte / lt / lte   level checks (current vs threshold). Fire on
                        ANY qualifying observation, so they re-fire
                        while a series stays past the threshold —
                        which is most series. The /alerts/ UI warns
                        about this and defaults to the crosses_* ops.
  crosses_above   prev <= threshold AND current > threshold   edge:
  crosses_below   prev >= threshold AND current < threshold   fires
                  once on the crossing, and re-arms when an observation
                  comes back to the other side of the threshold.
  change_above    abs(current - prev) > threshold

Windowed evaluation: the refresh runs WEEKLY but many series publish
DAILY, so ~5-7 new observations land between runs. We walk ALL of them
in chronological order (rolling `prev` seeded by the rule's
last_value_seen) rather than only comparing the two endpoints —
otherwise a crossing that happened (and maybe reverted) mid-week would
be missed. See fire_in_window. The crosses_* "going below re-arms the
indicator" behavior falls out of the rolling prev: once an observation
lands on the far side, the next crossing fires again.

Idempotency: the evaluator stamps `last_value_t` (the latest
observation's date) on every rule, and each run's window is everything
strictly after it. A rule whose source's latest observation date ==
last_value_t is skipped (no new data). So running the evaluator twice
between refreshes produces zero new triggers.

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


def _load_points(source_id: str) -> list[dict[str, Any]] | None:
    """Load the full points[] array for a source ID, or None if the
    source can't be resolved. Used by the derived-indicator path so
    we can align timestamps between A and B before computing A op B.
    Same source-id sanitization + path-confinement as
    load_latest_observation."""
    if not source_id or not SAFE_SOURCE_ID.match(source_id):
        return None
    yaml_path = SOURCES_ROOT / f"{source_id}.yaml"
    try:
        yaml_path.resolve().relative_to(SOURCES_ROOT.resolve())
    except ValueError:
        return None
    if not yaml_path.exists():
        return None
    data_file: str | None = None
    for line in yaml_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("dataFile:"):
            data_file = stripped.split(":", 1)[1].strip().strip("\"'")
            break
    if not data_file:
        return None
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
    if not isinstance(payload, dict):
        return None
    points = payload.get("points")
    if not isinstance(points, list) or not points:
        return None
    return points


def load_observations(source_id: str) -> list[tuple[str, float]] | None:
    """Full chronological [(t, v)] series for a regular source ID.
    Same source-id sanitization + path confinement as
    load_latest_observation (rides on _load_points). Returns None when
    the source is unresolvable or has no usable points."""
    pts = _load_points(source_id)
    if not pts:
        return None
    out: list[tuple[str, float]] = []
    for p in pts:
        if not isinstance(p, dict):
            continue
        t = p.get("t")
        v = p.get("v")
        if isinstance(t, str) and isinstance(v, (int, float)):
            out.append((t, float(v)))
    return out or None


def load_derived_observations(
    spec: dict[str, Any],
) -> list[tuple[str, float]] | None:
    """Compute the full derived series A op B, aligned by date.

    Alignment: align A and B by date. For each date present in BOTH
    series, compute the operation. Return the latest such (t, v).
    If A's latest is 2024-06-15 and B's latest is 2024-05-30, the
    derived series latest is 2024-05-30 (the most recent date both
    series have data for). This matches the composer's combineTwo
    semantics — a derived chart only plots where both inputs exist.

    Divide-by-zero returns None for that timestamp (skipped).

    Returns None if either source is unresolvable or the alignment
    leaves the derived series empty.
    """
    a_id = spec.get("a") if isinstance(spec, dict) else None
    b_id = spec.get("b") if isinstance(spec, dict) else None
    op = spec.get("op") if isinstance(spec, dict) else None
    if not isinstance(a_id, str) or not isinstance(b_id, str):
        return None
    if op not in ("divide", "sum", "diff"):
        return None
    pts_a = _load_points(a_id)
    pts_b = _load_points(b_id)
    if pts_a is None or pts_b is None:
        return None
    # Build a date -> value map for B so the alignment is O(N+M)
    # instead of O(N*M).
    b_by_t: dict[str, float] = {}
    for p in pts_b:
        if not isinstance(p, dict):
            continue
        t = p.get("t")
        v = p.get("v")
        if isinstance(t, str) and isinstance(v, (int, float)):
            b_by_t[t] = float(v)
    # Walk A in order; emit (t, derived_v) when B has the same t.
    derived: list[tuple[str, float]] = []
    for p in pts_a:
        if not isinstance(p, dict):
            continue
        t = p.get("t")
        v = p.get("v")
        if not isinstance(t, str) or not isinstance(v, (int, float)):
            continue
        if t not in b_by_t:
            continue
        b_v = b_by_t[t]
        if op == "divide":
            if b_v == 0:
                continue
            derived.append((t, float(v) / b_v))
        elif op == "sum":
            derived.append((t, float(v) + b_v))
        elif op == "diff":
            derived.append((t, float(v) - b_v))
    if not derived:
        return None
    # A's points are chronological per the pipeline contract and the
    # alignment preserves that, so `derived` is already ordered.
    return derived


def load_derived_latest_observation(
    spec: dict[str, Any],
) -> tuple[str, float] | None:
    """Latest observation of the derived series — thin wrapper around
    load_derived_observations, kept for callers/tests that only want
    the endpoint."""
    obs = load_derived_observations(spec)
    return obs[-1] if obs else None


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


def fire_in_window(
    condition: str,
    threshold: float,
    new_obs: list[tuple[str, float]],
    anchor_prev: float | None,
) -> tuple[str, float] | None:
    """Walk the new observations in chronological order, applying the
    per-pair condition with a rolling ``prev`` seeded by ``anchor_prev``
    (the rule's last_value_seen). Returns the (t, v) of the LAST
    observation in the window that fired, or None if none did.

    The rolling prev is what makes the multi-observation window correct:
    a crosses_* transition (or a change_above step) that happens BETWEEN
    two points inside the window is detected — and crosses_* even
    re-arms within the window (dip below, then cross up again, all since
    the last run → fires). Level conditions ignore prev, so they fire on
    any window point that meets the threshold. Reporting the LAST firing
    point gives the most recent crossing / qualifying value for the
    trigger snapshot."""
    prev = anchor_prev
    last_fire: tuple[str, float] | None = None
    for (t, v) in new_obs:
        if evaluate_condition(condition, threshold, v, prev):
            last_fire = (t, v)
        prev = v
    return last_fire


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
            derived_spec = rule.get("derived_spec")

            # Derived-indicator alerts: load BOTH sub-sources, align by
            # date, compute A op B. The source_id stays populated as a
            # display sentinel (typically "derived:adhoc") but isn't
            # used for data resolution when derived_spec is present.
            if isinstance(derived_spec, dict) and derived_spec:
                series = load_derived_observations(derived_spec)
            else:
                series = load_observations(source_id)
            if not series:
                skipped += 1
                continue
            (latest_t, latest_v) = series[-1]

            # Idempotency: skip rules whose source hasn't moved since
            # the last evaluation. Sidesteps re-firing on a no-op data
            # refresh that happened to bump file mtimes.
            if last_t_seen == latest_t:
                skipped += 1
                continue

            prev_v = float(last_v_seen) if isinstance(last_v_seen, (int, float)) else None

            # Windowed evaluation. The refresh runs WEEKLY but many
            # series publish DAILY, so several new observations land
            # between runs. Evaluate EVERY observation that arrived
            # since last_value_t — not just the latest-vs-last-seen
            # endpoints — so a crosses_* transition that happened
            # mid-window is caught and a level condition fires off a
            # point that actually met the threshold. The rolling prev is
            # seeded with last_value_seen (the prior run's final point).
            # First run (no last_value_t): baseline against the latest
            # point only, so we don't replay crossings that predate the
            # rule.
            if last_t_seen is None:
                window = [(latest_t, latest_v)]
            else:
                window = [(t, v) for (t, v) in series if t > last_t_seen]
            fire = fire_in_window(condition, threshold, window, prev_v)
            triggered = fire is not None

            if triggered:
                # Insert trigger snapshot. Service-role auth bypasses
                # RLS; the row's owner_id is set explicitly so
                # downstream queries (and the owner's /alerts/ page)
                # see the right rows. observed_* is the WINDOW point that
                # fired (e.g. the mid-week crossing), not necessarily the
                # latest observation.
                (obs_t, obs_v) = fire
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
                        "observed_value": obs_v,
                        "observed_t": obs_t,
                    },
                )
                fired += 1

            # Advance last_value_* to the LATEST observation even when
            # not triggered — the next run's window is everything after
            # last_value_t, and crosses_* / change_above use
            # last_value_seen as the rolling-prev seed.
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
