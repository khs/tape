"""
Generate compact tile-summary JSON files alongside every full source data
JSON in public/data/.

Why this exists
---------------
Each chart tile only needs a small slice of its source data:
  - the latest value
  - the prior value at each supported delta window (1w, 1m, ytd, 1y, ...)
  - a downsampled sparkline for each window

The full timeseries — often 800-13,000 points per source — is only needed
when the user clicks the tile to open the expanded chart dialog. Bundling
the full series into every dashboard's HTML payload is the bottleneck on
both page weight (3MB+ per dashboard) and Vercel bandwidth, neither of
which scale well as the user base grows.

Generating <id>.summary.json sibling files lets the page payload
include just summaries (~7-10KB each); the dialog click lazy-fetches
the full <id>.json from the static-assets CDN on demand.

What's in a summary
-------------------
{
  "id": "POPTHM",
  "name": "US population, all persons (monthly)",
  "kind": "timeseries",
  "unit": "thousands",
  "lastUpdated": "2026-04-15T...",
  "latest": { "t": "2026-04-01", "v": 339213.4 },
  "priors": {
    "1w":  { "t": "2026-03-25", "v": 339100 },
    "1m":  { "t": "2026-03-01", "v": 339050 },
    "ytd": { "t": "2026-01-01", "v": 338700 },
    "1y":  { "t": "2025-04-01", "v": 336500 },
    "5y":  { "t": "2021-04-01", "v": 332800 },
    "10y": { "t": "2016-04-01", "v": 323700 },
    "30y": { "t": "1996-04-01", "v": 267800 },
    "50y": { "t": "1976-04-01", "v": 218000 }
  },
  "sparks": {
    "1w":  [...~30 points downsampled to the 1w range...],
    "1m":  [...],
    ...
    "50y": [...]
  }
}

Windows are computed for the full DELTA_WINDOWS set regardless of the
source's declared supportedDeltas; the renderer picks the subset it
needs. Each spark is uniformly downsampled to at most SPARK_POINTS
points within the window's range. Sparser windows return fewer points.

Idempotent: running it twice produces identical files. Safe to run as
the last step of the refresh-data workflow or as part of any local
backfill.

Run with: ``python pipelines/build_summaries.py``.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "public" / "data"

# Window definitions mirror src/lib/deltas.ts. Days-per-window for the
# fixed-length windows; "ytd" is computed against Jan 1 of the latest-
# point's year, so it doesn't have a fixed days value.
DELTA_WINDOWS = ["1w", "1m", "ytd", "1y", "5y", "10y", "30y", "50y"]
DELTA_DAYS = {
    "1w": 7,
    "1m": 30,
    "ytd": None,  # computed dynamically per-point
    "1y": 365,
    "5y": 365 * 5,
    "10y": 365 * 10,
    "30y": 365 * 30,
    "50y": 365 * 50,
}

# Target spark length. 30 points renders cleanly in a ~200px-wide tile
# sparkline and keeps each spark payload tiny.
SPARK_POINTS = 30


def parse_t(t: str) -> datetime:
    """Parse 'YYYY-MM-DD' (the canonical TS in our data files)."""
    # Some series use full ISO; just take the date prefix.
    return datetime.strptime(t[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)


def window_start(latest_t: datetime, window: str) -> datetime:
    """Compute the start timestamp for a window anchored at latest_t."""
    if window == "ytd":
        return datetime(latest_t.year, 1, 1, tzinfo=timezone.utc)
    days = DELTA_DAYS[window]
    return latest_t - timedelta(days=days)


def find_prior(
    points: list[dict[str, Any]],
    parsed_times: list[datetime],
    latest_t: datetime,
    window: str,
) -> dict[str, Any] | None:
    """
    Closest point at or before (latest_t - window) — matches the
    findPriorPoint logic in src/lib/load-data.ts.
    """
    target = window_start(latest_t, window)
    # Series doesn't extend back far enough? Return None.
    if parsed_times[0] > target:
        return None
    # Linear walk; for ~thousands of points this is fast enough. Could
    # binary-search but the build runs offline.
    best_idx = 0
    for i, t in enumerate(parsed_times):
        if t <= target:
            best_idx = i
        else:
            break
    return points[best_idx]


def downsample(
    points: list[dict[str, Any]],
    parsed_times: list[datetime],
    latest_t: datetime,
    window: str,
    n: int,
) -> list[dict[str, Any]]:
    """
    Return up to `n` points evenly sampled from the slice of `points`
    within the window's range. Uniform sampling — simple, lossy on
    spikes but visually fine for sparkline-scale rendering.
    """
    target = window_start(latest_t, window)
    # Find slice [start_idx, end_idx) where points fall in [target, latest_t].
    start_idx = 0
    for i, t in enumerate(parsed_times):
        if t >= target:
            start_idx = i
            break
    else:
        return []
    end_idx = len(points)  # latest is included
    sliced = points[start_idx:end_idx]
    if len(sliced) <= n:
        return sliced
    # Even sampling: take indices floor(i * (len-1) / (n-1)) for i in 0..n-1.
    indices = [round(i * (len(sliced) - 1) / (n - 1)) for i in range(n)]
    return [sliced[i] for i in indices]


def build_summary(full: dict[str, Any]) -> dict[str, Any] | None:
    """Returns the summary dict, or None if the source isn't a timeseries / is empty."""
    if full.get("kind") != "timeseries":
        return None
    points = full.get("points") or []
    if not points:
        return None
    # Parse timestamps once; we use them for both prior-finding and spark slicing.
    try:
        parsed_times = [parse_t(p["t"]) for p in points]
    except (KeyError, ValueError):
        return None
    latest_t = parsed_times[-1]
    latest = points[-1]
    priors: dict[str, Any] = {}
    sparks: dict[str, list[dict[str, Any]]] = {}
    for window in DELTA_WINDOWS:
        prior = find_prior(points, parsed_times, latest_t, window)
        if prior is not None and prior is not latest:
            priors[window] = prior
        spark = downsample(points, parsed_times, latest_t, window, SPARK_POINTS)
        if spark:
            sparks[window] = spark
    return {
        "id": full.get("id"),
        "name": full.get("name"),
        "kind": "timeseries",
        "unit": full.get("unit"),
        "lastUpdated": full.get("lastUpdated"),
        "latest": latest,
        "priors": priors,
        "sparks": sparks,
    }


def main() -> int:
    if not DATA_ROOT.exists():
        print(f"no public/data/ at {DATA_ROOT}", file=sys.stderr)
        return 1
    written = 0
    skipped = 0
    for full_path in sorted(DATA_ROOT.rglob("*.json")):
        # Skip summaries we generated previously, and anything inside
        # _archive (those are historical snapshots — re-summarizing
        # them would balloon the count).
        if full_path.name.endswith(".summary.json"):
            continue
        if "_archive" in full_path.parts:
            continue
        try:
            full = json.loads(full_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"  skip {full_path.relative_to(DATA_ROOT)}: {e}", file=sys.stderr)
            skipped += 1
            continue
        summary = build_summary(full)
        if summary is None:
            skipped += 1
            continue
        summary_path = full_path.with_name(full_path.stem + ".summary.json")
        # Compact-write so on-the-wire size stays small even before gzip.
        summary_path.write_text(
            json.dumps(summary, separators=(",", ":")),
            encoding="utf-8",
        )
        written += 1
    print(f"build_summaries: {written} written, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
