#!/usr/bin/env python3
"""Emit the cross-language summary-parity fixture.

Tape computes per-window sparks + priors TWICE, in two languages:
  • Python  — pipelines/build_summaries.py:build_summary (offline, writes
    every source's .summary.json)
  • TypeScript — src/lib/load-data.ts:computeSummaryFromPoints (runtime, for
    derived / op'd charts that have no precomputed .summary.json)

If the two ever drift — a different window day-count, a different prior
boundary rule, JS Math.round (half-up) vs Python round (banker's) on a spark
index — a derived chart's tile would silently disagree with the same source's
standalone tile. This script runs the REAL Python implementation on a set of
synthetic edge-case series and records its output as a fixture; the TS side
(src/lib/summary-parity.test.ts) recomputes from the same inputs and asserts a
byte-for-byte match.

Run it (and commit the result) whenever build_summaries.py changes:

    python pipelines/emit_summary_parity_fixture.py

CI regenerates it and `git diff --exit-code`s the output, so a Python-side
change that isn't mirrored in TS (or vice-versa) fails the build.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_summaries import DELTA_WINDOWS, build_summary  # noqa: E402

OUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "src", "lib", "__fixtures__", "summary-parity.json",
)


def _daily(start: str, n: int, step_days: int, fn) -> list[dict]:
    """n points spaced step_days apart from `start`, value = fn(i)."""
    d0 = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return [
        {"t": (d0 + timedelta(days=i * step_days)).strftime("%Y-%m-%d"), "v": fn(i)}
        for i in range(n)
    ]


def _cases() -> list[dict]:
    # Deterministic, no randomness. Each exercises a distinct edge of the
    # prior / spark logic across every window.
    return [
        # Long daily series: every short window downsamples to 30; long windows
        # reach back far enough for priors.
        {"name": "daily_3y", "points": _daily("2021-06-01", 1100, 1, lambda i: round(100 + i * 0.37, 4))},
        # Just over the spark cap in the widest window → 31 pts → downsample.
        {"name": "daily_31", "points": _daily("2024-01-01", 31, 1, lambda i: i * 2)},
        # Exactly the spark cap → returned whole, no sampling.
        {"name": "daily_30", "points": _daily("2024-02-01", 30, 1, lambda i: i)},
        # Short series: most windows have no prior (series too young).
        {"name": "short_5", "points": _daily("2024-12-01", 5, 1, lambda i: 10 - i)},
        # Monthly over a decade: priors land on month boundaries, not exact day.
        {"name": "monthly_10y", "points": _daily("2014-01-15", 130, 30, lambda i: round((i % 12) * 1.5 - 3, 4))},
        # Signed values (an election-margin-shaped series).
        {"name": "signed_margins", "points": _daily("2016-11-01", 400, 7, lambda i: round(((i * 7) % 41) - 20, 4))},
        # Latest point mid-year → exercises the YTD Jan-1 anchor.
        {"name": "ytd_midyear", "points": _daily("2023-09-10", 300, 1, lambda i: round(50 + i * 0.1, 4))},
        # Single point: latest only, no priors, spark of length 1.
        {"name": "single", "points": _daily("2025-03-03", 1, 1, lambda i: 42)},
    ]


def main() -> int:
    cases = []
    for c in _cases():
        full = {"id": c["name"], "name": c["name"], "kind": "timeseries",
                "unit": "n", "lastUpdated": "2025-01-01", "points": c["points"]}
        summary = build_summary(full)
        assert summary is not None, c["name"]
        # Only the cross-language computed parts; id/name/unit are TS-side concerns.
        cases.append({
            "name": c["name"],
            "input": {"points": c["points"]},
            "expected": {
                "latest": summary["latest"],
                "priors": summary["priors"],
                "sparks": summary["sparks"],
            },
        })
    payload = {
        "_generator": "pipelines/emit_summary_parity_fixture.py",
        "windows": DELTA_WINDOWS,
        "sparkPoints": 30,
        "cases": cases,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    print(f"wrote {len(cases)} cases -> {os.path.relpath(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
