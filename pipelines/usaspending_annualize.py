"""
Partial-fiscal-year annualization for USAspending series (audit new-#2).

Both usaspending pipelines anchor each federal fiscal year at Sep 30 and
include the in-progress current FY, whose cumulative total is partial.
On a chart that reads as an artificial spending DROP — e.g. FY2026 (7
months reported) sitting well below FY2025 (full year).

Per Keller's decisions:
  - Annualize the open-FY point ONLY when it would otherwise be a
    level-drop below the prior full FY (annualizing a value that's
    already above the prior year would invent a spike).
  - Scale by ACTUAL data coverage, not the calendar: USAspending reports
    on a monthly submission schedule with a reveal lag, so we ask the
    API which fiscal month is the latest *revealed* one and annualize by
    12 / months_covered.
  - Mark the annualized point with an annotation ("FY2026 annualized
    (7 of 12 mo)") carried as the source's defaultAnnotations, so the
    existing chart-annotation mechanism shows it — no renderer change.

When the FY later closes, the pipeline refetches the full-year total and
overwrites the annualized estimate, and clear_stale_annotation() drops
the now-irrelevant note. So the annualization is transient by design.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

SUBMISSION_PERIODS_URL = (
    "https://api.usaspending.gov/api/v2/references/submission_periods/"
)


def fetch_coverage(today: datetime | None = None) -> tuple[int, int] | None:
    """
    Returns (open_fiscal_year, months_covered) for the current in-progress
    federal FY, where months_covered is 1..12 (Oct=1 .. Sep=12), or None
    if the API is unreachable. months_covered == 12 means the FY's final
    period has revealed (no annualization needed).
    """
    if today is None:
        today = datetime.now(timezone.utc)
    try:
        out = subprocess.run(
            ["curl", "-sS", "--max-time", "60", SUBMISSION_PERIODS_URL],
            capture_output=True, text=True, check=True,
        )
        periods = json.loads(out.stdout).get("available_periods", [])
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"  [annualize] coverage probe failed: {e}", file=sys.stderr)
        return None
    revealed = [
        p for p in periods
        if _parse(p.get("submission_reveal_date")) is not None
        and _parse(p["submission_reveal_date"]) <= today
    ]
    if not revealed:
        return None
    latest = max(
        revealed,
        key=lambda p: (p["submission_fiscal_year"], p["submission_fiscal_month"]),
    )
    return int(latest["submission_fiscal_year"]), int(latest["submission_fiscal_month"])


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def open_fy_anchor(open_fy: int) -> str:
    """ISO end-of-FY date the partial point is anchored at."""
    return f"{open_fy}-09-30"


def annualize_open_fy(
    points: list[dict],
    open_fy: int,
    months_covered: int,
) -> tuple[list[dict], dict | None]:
    """
    Given a series' ascending points, annualize the trailing open-FY point
    when (and only when) it is a level-drop below the prior full FY.

    Returns (points, annotation) where `points` is a NEW list (the trailing
    value scaled in place when triggered) and `annotation` is a
    {date,label,position} dict to stamp as a defaultAnnotation, or None
    when no annualization applied. Non-destructive: returns the input
    points unchanged (copied) when nothing triggers.
    """
    if months_covered < 1 or months_covered >= 12 or len(points) < 2:
        return list(points), None
    anchor = open_fy_anchor(open_fy)
    last, prior = points[-1], points[-2]
    if last.get("t") != anchor:
        return list(points), None
    if not isinstance(last.get("v"), (int, float)) or not isinstance(prior.get("v"), (int, float)):
        return list(points), None
    if last["v"] >= prior["v"]:
        # Already at/above the prior full year — annualizing would invent
        # a spike. Leave the partial point as-is (no drop to correct).
        return list(points), None
    factor = 12.0 / months_covered
    new_points = list(points[:-1]) + [{**last, "v": last["v"] * factor}]
    annotation = {
        "date": anchor,
        "label": f"FY{open_fy} annualized ({months_covered} of 12 mo)",
        "position": "above",
    }
    return new_points, annotation


# A single-line, flow-style defaultAnnotations entry the pipeline fully
# owns: easy to detect by prefix and replace/remove idempotently, so it
# never accumulates or goes stale. usaspending sources never carry a
# hand-authored defaultAnnotations, so managing this one line is safe.
_ANN_PREFIX = "defaultAnnotations:"


def set_yaml_default_annotation(yaml_path, annotation: dict | None) -> bool:
    """
    Idempotently set (or clear, when annotation is None) the managed
    defaultAnnotations line on a source YAML. Returns True if the file
    changed. Preserves every other byte — only the one managed line is
    added/updated/removed.
    """
    import os

    if not os.path.exists(yaml_path):
        return False
    with open(yaml_path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    # Strip any existing managed line (single flow-style line only).
    kept = [
        ln for ln in text.splitlines(keepends=True)
        if not ln.lstrip().startswith(_ANN_PREFIX)
    ]
    new_text = "".join(kept)
    if annotation is not None:
        if not new_text.endswith("\n"):
            new_text += "\n"
        # Flow style keeps it to one line; label is quoted (may contain
        # spaces/parens), date quoted, position bare.
        d, lbl, pos = annotation["date"], annotation["label"], annotation["position"]
        new_text += (
            f'{_ANN_PREFIX} [{{date: "{d}", label: "{lbl}", position: {pos}}}]\n'
        )
    if new_text == text:
        return False
    with open(yaml_path, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    return True


def _sources_dir() -> str:
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "src", "content", "sources", "usaspending")


def annualize_for_write(points: list[dict], series_id: str, coverage):
    """
    Pipeline entry point: annualize a series' points for the open FY (when
    it's a level-drop) and set/clear the matching source YAML's managed
    annotation to stay in sync. `coverage` is (open_fy, months) from
    fetch_coverage(), or None to no-op (e.g. probe failed — never block a
    refresh on it). Returns the points to hand to write_timeseries.

    Annualizes from the RAW freshly-fetched points every run, so it never
    double-scales (unlike the one-shot backfill).
    """
    import os
    if coverage is None:
        return points
    open_fy, months = coverage
    new_pts, annotation = annualize_open_fy(points, open_fy, months)
    set_yaml_default_annotation(os.path.join(_sources_dir(), f"{series_id}.yaml"), annotation)
    return new_pts


def managed_annotation_date(yaml_path) -> str | None:
    """The anchor date in the YAML's managed defaultAnnotations line, or
    None. Lets the backfill tell 'already annualized this FY' from 'raw',
    so it never double-scales on a re-run."""
    import os
    import re

    if not os.path.exists(yaml_path):
        return None
    with open(yaml_path, "r", encoding="utf-8") as f:
        for ln in f:
            if ln.lstrip().startswith(_ANN_PREFIX):
                m = re.search(r'date:\s*"(\d{4}-\d{2}-\d{2})"', ln)
                return m.group(1) if m else None
    return None


def _write_compact_json(path, payload) -> None:
    """Match the usaspending data files' compact, ascii-escaped, no-final-
    newline format so backfills produce a minimal diff."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(payload, f, separators=(",", ":"), ensure_ascii=True)


def backfill() -> int:
    """
    One-off: annualize the open-FY point in every existing usaspending data
    file that's a level-drop, and stamp the matching source YAML's
    defaultAnnotations. Idempotent — safe to re-run (it recomputes from the
    raw prior points each time? No: it reads stored points, so run ONCE per
    fetch; see the guard below). Future correctness lives in the pipelines.
    """
    import glob
    import os

    import build_summaries

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    sources_dir = os.path.join(root, "src", "content", "sources", "usaspending")
    data_dir = os.path.join(root, "public", "data", "usaspending")

    cov = fetch_coverage()
    if cov is None:
        print("backfill: coverage probe failed; aborting", file=sys.stderr)
        return 1
    open_fy, months = cov
    print(f"backfill: open FY{open_fy}, {months}/12 months covered")

    anchor = open_fy_anchor(open_fy)
    n_data, n_skip, n_clear = 0, 0, 0
    for yaml_path in sorted(glob.glob(os.path.join(sources_dir, "*.yaml"))):
        stem = os.path.splitext(os.path.basename(yaml_path))[0]
        data_path = os.path.join(data_dir, f"{stem}.json")
        if not os.path.exists(data_path):
            continue
        # Idempotency guard: if this YAML already carries a managed
        # annotation for the current open FY, its data file is already
        # annualized — skip so a re-run never scales the value twice.
        if managed_annotation_date(yaml_path) == anchor:
            n_skip += 1
            continue
        with open(data_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        new_pts, annotation = annualize_open_fy(payload.get("points", []), open_fy, months)
        if annotation is not None:
            payload["points"] = new_pts
            _write_compact_json(data_path, payload)
            # Regenerate the .summary.json so the precomputed "latest" the
            # app reads for tiles matches the annualized chart value.
            summary_path = data_path[:-5] + ".summary.json"
            if os.path.exists(summary_path):
                _write_compact_json(summary_path, build_summaries.build_summary(payload))
            set_yaml_default_annotation(yaml_path, annotation)
            n_data += 1
        elif managed_annotation_date(yaml_path) is not None:
            # No annualization now but a stale managed line (an older FY)
            # lingers — drop it.
            set_yaml_default_annotation(yaml_path, None)
            n_clear += 1
    print(f"backfill: annualized {n_data} data files (+annotations), "
          f"skipped {n_skip} already-done, cleared {n_clear} stale")
    return 0


if __name__ == "__main__":
    sys.exit(backfill())
