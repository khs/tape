"""
Trim each source's full data JSON to its declared longest supportedDeltas
window plus a small buffer. Source YAMLs declare what windows the
charting code will ever render, so any history older than that is dead
weight on every page load.

Why this exists
---------------
Some sources (Yahoo equities like KO, XOM) carry 50+ years of daily
data — over 1MB per file. The dashboards using them top out at 10-year
windows, so 80% of the data has never been displayed. Multiply across
~6800 sources and the cumulative bandwidth waste on every page load
and every Vercel function fetch is real.

This script reads each source's YAML manifest to find its longest
declared supportedDelta, looks up the corresponding data file, and
rewrites it with only points falling within (longest_window * 1.1)
of the latest observation. The 10% buffer is for charts that compose
multiple sources where the closestSupported fallback picks a slightly-
larger window than declared.

Trimmed files keep the same JSON shape — only the `points` array is
shortened. No renderer code needs to change.

Pipeline ordering note: build_summaries.py runs BEFORE this script in
the refresh workflow, so summaries are computed from the full
(un-trimmed) data. If we trimmed first, sparks for windows beyond the
declared max would have fewer points than they could, defeating the
purpose.

Idempotent: re-running on already-trimmed files is a no-op. Run with
``python pipelines/trim_source_data.py``.
"""
from __future__ import annotations

import json
import sys
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "public" / "data"
SOURCES_ROOT = REPO_ROOT / "src" / "content" / "sources"

DELTA_DAYS = {
    "1w": 7,
    "1m": 30,
    "ytd": 366,
    "1y": 365,
    "5y": 365 * 5,
    "10y": 365 * 10,
    "30y": 365 * 30,
    "50y": 365 * 50,
}
BUFFER_FACTOR = 1.1  # keep 10% extra to be safe for cross-source charts


def trim_data_file(
    data_file: Path,
    longest_days: int,
) -> tuple[bool, int, int]:
    """
    Trim a single data file to the last `longest_days * BUFFER_FACTOR`
    days from its latest observation. Returns (changed, kept, dropped).
    """
    try:
        full = json.loads(data_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, 0, 0
    if full.get("kind") != "timeseries":
        return False, 0, 0
    points = full.get("points") or []
    if not points:
        return False, 0, 0
    try:
        latest_t = datetime.strptime(points[-1]["t"][:10], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except (KeyError, ValueError):
        return False, 0, 0
    cutoff = latest_t - timedelta(days=int(longest_days * BUFFER_FACTOR))
    cutoff_iso = cutoff.strftime("%Y-%m-%d")
    kept = [p for p in points if p["t"][:10] >= cutoff_iso]
    if len(kept) == len(points):
        return False, len(points), 0
    full["points"] = kept
    data_file.write_text(
        json.dumps(full, separators=(",", ":")),
        encoding="utf-8",
    )
    return True, len(kept), len(points) - len(kept)


def main() -> int:
    if not SOURCES_ROOT.exists() or not DATA_ROOT.exists():
        print(f"missing sources/data root", file=sys.stderr)
        return 1
    yaml_files = list(SOURCES_ROOT.rglob("*.yaml"))
    print(f"trim_source_data: scanning {len(yaml_files)} source manifests...")
    total_changed = 0
    total_kept = 0
    total_dropped = 0
    bytes_before = 0
    bytes_after = 0
    for yaml_path in yaml_files:
        try:
            manifest = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as e:
            print(f"  skip {yaml_path.name}: {e}", file=sys.stderr)
            continue
        if not isinstance(manifest, dict):
            continue
        data_file_rel = manifest.get("dataFile")
        supported = manifest.get("supportedDeltas") or []
        if not data_file_rel or not isinstance(supported, list):
            continue
        # Find longest supported window. We treat ytd as 1y for trimming
        # purposes — its actual span depends on today's date and we'd
        # rather over-keep than risk under-keeping.
        longest_days = max(
            (DELTA_DAYS.get(w, 0) for w in supported),
            default=0,
        )
        if longest_days <= 0:
            continue
        data_file = REPO_ROOT / "public" / data_file_rel
        if not data_file.exists():
            continue
        size_before = data_file.stat().st_size
        bytes_before += size_before
        changed, kept, dropped = trim_data_file(data_file, longest_days)
        size_after = data_file.stat().st_size
        bytes_after += size_after
        if changed:
            total_changed += 1
            total_kept += kept
            total_dropped += dropped
    print(
        f"trim_source_data: trimmed {total_changed} files; "
        f"kept {total_kept} points, dropped {total_dropped} points"
    )
    mb_before = bytes_before / (1024 * 1024)
    mb_after = bytes_after / (1024 * 1024)
    saved_pct = (1 - mb_after / mb_before) * 100 if mb_before > 0 else 0
    print(
        f"  data size: {mb_before:.1f} MB -> {mb_after:.1f} MB "
        f"({saved_pct:.1f}% saved)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
