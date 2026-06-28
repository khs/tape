"""
Bound each source's data file to a payload budget by DOWNSAMPLING old data,
without ever dropping the time span.

Why this exists / what changed
------------------------------
The old version TRUNCATED each file to its longest declared supportedDeltas
window (~50y). That made sense before the synthetic "max" / all-time pill
existed, but now every chart offers all-time — so truncation actively breaks it,
and it punished low-frequency series (a 125-point annual series is ~2KB, yet got
clipped to ~55 points, throwing away a century).

This version decouples retention (payload) from display (windows):
  • Series at or under BUDGET points are left untouched — full history, free.
    (All annual / monthly series fall here.)
  • Series over BUDGET keep the last RECENT_NATIVE_DAYS verbatim (so the dense
    short windows stay exact) and the OLDER portion is min/max (M4) decimated to
    fit the remaining budget. The full SPAN survives, so "max" works everywhere;
    only point DENSITY drops for old data, and extremes (spikes/crashes) are
    preserved by construction.

Where a file is decimated, we stamp `approximatedBefore: <cutoff>` onto the data
file AND its .summary.json, so the source page and single-source charts can warn
that data older than ~5 years may be approximated.

M4 reference: Jugel et al., "M4: A Visualization-Oriented Time Series Data
Aggregation" (VLDB 2014) — per bucket keep first, last, value-min, value-max.

Pipeline ordering: runs AFTER build_summaries.py (sparks are computed from full
data) and AFTER the fetch (which writes full history). Idempotent: a file already
at/under budget is left alone, and an existing approximated-flag is preserved.

Run with ``python pipelines/trim_source_data.py``.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "public" / "data"
SOURCES_ROOT = REPO_ROOT / "src" / "content" / "sources"

BUDGET = 2500            # target ceiling, points per file
RECENT_NATIVE_DAYS = 365 * 5  # keep the last ~5y verbatim (short windows stay exact)


def _parse(t: str) -> datetime:
    return datetime.strptime(t[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)


def m4_bucket(points: list[dict], out_budget: int) -> list[dict]:
    """Min/max (M4) decimate `points` to ~out_budget points, preserving extremes.

    Partition into out_budget//4 contiguous equal-count buckets; from each emit
    first, last, value-min, value-max (deduped, in time order). Flat buckets
    collapse to ~1 point; only volatile buckets cost the full 4.
    """
    n = len(points)
    if n <= out_budget or out_budget < 4:
        return points
    n_buckets = max(1, out_budget // 4)
    out: list[dict] = []
    for b in range(n_buckets):
        lo = b * n // n_buckets
        hi = (b + 1) * n // n_buckets
        bucket = points[lo:hi]
        if not bucket:
            continue
        picks = {
            id(bucket[0]): bucket[0],
            id(bucket[-1]): bucket[-1],
        }
        vmin = min(bucket, key=lambda p: p["v"])
        vmax = max(bucket, key=lambda p: p["v"])
        picks[id(vmin)] = vmin
        picks[id(vmax)] = vmax
        out.extend(sorted(picks.values(), key=lambda p: p["t"]))
    return out


def downsample_points(points: list[dict]) -> tuple[list[dict], str | None]:
    """Return (new_points, approximated_before_iso). approx is None if untouched."""
    if len(points) <= BUDGET:
        return points, None
    try:
        latest = _parse(points[-1]["t"])
    except (KeyError, ValueError):
        return points, None
    cutoff = latest - timedelta(days=RECENT_NATIVE_DAYS)
    cutoff_iso = cutoff.strftime("%Y-%m-%d")
    split = next((i for i, p in enumerate(points) if p["t"][:10] >= cutoff_iso), len(points))
    recent = points[split:]
    old = m4_bucket(points[:split], max(4, BUDGET - len(recent)))
    return old + recent, cutoff_iso


def _patch_summary(summary_file: Path, approx_before: str | None) -> None:
    """Mirror the approximated-flag onto the .summary.json (built earlier)."""
    if not summary_file.exists():
        return
    try:
        s = json.loads(summary_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    cur = s.get("approximatedBefore")
    if approx_before:
        if cur == approx_before:
            return
        s["approximatedBefore"] = approx_before
    else:
        if cur is None:
            return
        s.pop("approximatedBefore", None)
    summary_file.write_text(json.dumps(s, separators=(",", ":")), encoding="utf-8")


def downsample_file(data_file: Path) -> tuple[bool, int, int]:
    """Downsample one data file if over budget; stamp the flag. (changed, before, after)."""
    try:
        full = json.loads(data_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, 0, 0
    if full.get("kind") != "timeseries":
        return False, 0, 0
    points = full.get("points") or []
    if not points:
        return False, 0, 0

    new_points, approx_before = downsample_points(points)
    # Preserve a prior flag if a re-run sees an already-downsampled (now small) file.
    if approx_before is None and full.get("approximatedBefore"):
        approx_before = full["approximatedBefore"]

    changed = len(new_points) != len(points) or full.get("approximatedBefore") != approx_before
    if approx_before:
        full["approximatedBefore"] = approx_before
    else:
        full.pop("approximatedBefore", None)
    full["points"] = new_points
    if changed:
        data_file.write_text(json.dumps(full, separators=(",", ":")), encoding="utf-8")

    _patch_summary(data_file.with_name(data_file.stem + ".summary.json"), approx_before)
    return changed, len(points), len(new_points)


def main() -> int:
    if not SOURCES_ROOT.exists() or not DATA_ROOT.exists():
        print("missing sources/data root", file=sys.stderr)
        return 1
    yaml_files = list(SOURCES_ROOT.rglob("*.yaml"))
    print(f"trim_source_data: scanning {len(yaml_files)} source manifests...")
    changed_files = 0
    kept = 0
    dropped = 0
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
        if not data_file_rel:
            continue
        data_file = REPO_ROOT / "public" / data_file_rel
        if not data_file.exists():
            continue
        size_before = data_file.stat().st_size
        was_changed, before, after = downsample_file(data_file)
        bytes_before += size_before
        bytes_after += data_file.stat().st_size
        if was_changed:
            changed_files += 1
            kept += after
            dropped += before - after
    mb_before = bytes_before / (1024 * 1024)
    mb_after = bytes_after / (1024 * 1024)
    saved = (1 - mb_after / mb_before) * 100 if mb_before > 0 else 0
    print(
        f"trim_source_data: downsampled {changed_files} files; "
        f"kept {kept} points, dropped {dropped}"
    )
    print(f"  data size: {mb_before:.1f} MB -> {mb_after:.1f} MB ({saved:.1f}% saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
