"""
National-level (us:1) ACS time series for every indicator that
census_acs_cd.py fetches per congressional district.

What this writes
----------------
For each indicator in census_acs_cd.INDICATORS, one time-series file:
    public/data/acs_national/<indicator>_us.json
covering ACS_VINTAGES (2010-2022 currently).

Why a separate pipeline
-----------------------
The CD pipeline does substantial tract-level aggregation + crosswalk
work that's not needed at the national level — at us:1 geography the
Census API returns one row per vintage and the published value IS the
national value. So this script is simpler: one API call per
indicator-chunk per vintage, store the value.

Reuses the INDICATORS list, AcsVar dataclass, and AGG_* constants
from census_acs_cd.py so adding an indicator to the CD pipeline
automatically extends national coverage.

Requires CENSUS_API_KEY env var. Run from project root with:
    CENSUS_API_KEY=<key> python pipelines/census_acs_national.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from census_acs_cd import (
    INDICATORS,
    ACS_VINTAGES,
    AGG_SUM,
    AGG_CD_LEVEL,
    AGG_CD_LEVEL_SUM,
    AGG_MEDIAN_DIST,
    AGG_MEDIAN_CD_DIST,
    acs_base,
    parse_value,
    weighted_median_from_bins,
)
from common import write_timeseries


REPO_ROOT = Path(__file__).resolve().parent.parent


def acs_fetch_us(year: int, var_codes: list[str], key: str) -> dict[str, float]:
    """
    Fire a single Census API request for us:1 geography. Returns a
    {var_code: value} dict for the single national row. Returns empty
    on failure. Mirrors the error-logging behavior of census_acs_cd's
    acs_fetch so silent failures show up in workflow logs.
    """
    vars_csv = ",".join(var_codes)
    url = f"{acs_base(year)}?get=NAME,{vars_csv}&for=us:1&key={key}"
    try:
        out = subprocess.run(
            ["curl", "-s", "-S", "--max-time", "120", "-w", "%{http_code}", url],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    curl failed for year={year}: {e}", file=sys.stderr)
        return {}
    body = out.stdout
    code = body[-3:] if body[-3:].isdigit() else "???"
    payload = body[:-3] if body[-3:].isdigit() else body
    if code != "200":
        snippet = payload.strip()[:200]
        print(f"    HTTP {code} for year={year}: {snippet}", file=sys.stderr)
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error year={year}: {e}", file=sys.stderr)
        return {}
    if not isinstance(data, list) or len(data) < 2:
        return {}
    headers, row = data[0], data[1]
    out_dict: dict[str, float] = {}
    for code in var_codes:
        try:
            col = headers.index(code)
        except ValueError:
            continue
        v = parse_value(row[col])
        if v is not None:
            out_dict[code] = v
    return out_dict


def main() -> int:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        print(
            "census_acs_national.py: CENSUS_API_KEY not set. Skipping.",
            file=sys.stderr,
        )
        return 0

    # Build the master variable list across all indicators. Deduped.
    needed_codes: set[str] = set()
    for v in INDICATORS:
        if v.agg in (AGG_SUM, AGG_CD_LEVEL):
            if v.var_code:
                needed_codes.add(v.var_code)
        elif v.agg == AGG_CD_LEVEL_SUM:
            needed_codes.update(v.sum_codes)
        elif v.agg == AGG_MEDIAN_DIST:
            # Existing CD pipeline uses tract-bin aggregation, but at the
            # national level the published median (var_code) is exact —
            # fetch the median value directly.
            if v.var_code:
                needed_codes.add(v.var_code)
        elif v.agg == AGG_MEDIAN_CD_DIST:
            needed_codes.update(code for code, _, _ in v.bins)
    var_list = sorted(needed_codes)
    print(
        f"census_acs_national: fetching {len(var_list)} variables across "
        f"{len(ACS_VINTAGES)} vintages...",
        flush=True,
    )

    # Accumulator: {out_id: [{t, v}, ...]}
    series_accum: dict[str, list[dict]] = defaultdict(list)
    for year in ACS_VINTAGES:
        anchor = f"{year}-12-31"
        # Chunk into <=45-var calls to stay under the API's per-call cap.
        merged: dict[str, float] = {}
        for chunk_start in range(0, len(var_list), 45):
            chunk = var_list[chunk_start:chunk_start + 45]
            merged.update(acs_fetch_us(year, chunk, key))
        if not merged:
            print(f"  vintage {year}: no data returned", file=sys.stderr)
            continue
        # Apply per-indicator aggregation.
        for v in INDICATORS:
            value: float | None = None
            if v.agg in (AGG_SUM, AGG_CD_LEVEL, AGG_MEDIAN_DIST):
                # All three behave identically at national level: just
                # pull the published value out of the response.
                value = merged.get(v.var_code) if v.var_code else None
            elif v.agg == AGG_CD_LEVEL_SUM:
                parts = [merged.get(c) for c in v.sum_codes]
                present = [p for p in parts if p is not None]
                if present:
                    value = sum(present)
            elif v.agg == AGG_MEDIAN_CD_DIST:
                bins_data = {
                    code: merged[code]
                    for code, _, _ in v.bins
                    if code in merged
                }
                value = weighted_median_from_bins(v.bins, bins_data)
            if value is None:
                continue
            # Counts: round to integers; everything else: indicator-declared precision.
            if v.agg in (AGG_SUM, AGG_CD_LEVEL_SUM):
                value = round(value)
            elif v.decimals > 0:
                value = round(value, v.decimals)
            series_accum[v.out_id].append({"t": anchor, "v": value})

    # Write per-indicator time series under the new acs_national pipeline.
    written = 0
    for out_id, points in series_accum.items():
        if not points:
            continue
        points.sort(key=lambda p: p["t"])
        var = next((v for v in INDICATORS if v.out_id == out_id), None)
        if var is None:
            continue
        write_timeseries(
            pipeline="acs_national",
            series_id=f"{out_id}_us",
            name=f"{var.name_prefix} — US",
            points=points,
            unit=var.unit,
        )
        written += 1
    print(
        f"census_acs_national: wrote {written} national time series across "
        f"{len(ACS_VINTAGES)} vintages.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
