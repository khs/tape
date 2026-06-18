"""Connecticut CD backfill via direct congressional-district fetch.

Why: from the 2022 ACS on, Census publishes CT tracts under the new COG
"planning region" county FIPS (110-190); the tract2020->CD118 crosswalk
(old county FIPS 001-015) can't map them, so census_acs_cd.py freezes CT's
five CD series at 2021 (only gini_index, which is fetched directly at CD
geography, reaches the new vintages). CT did NOT redistrict — its 118th
districts are unchanged — so this fetches CT's 5 CDs DIRECTLY at
congressional-district geography for the crosswalk-broken vintages, writes
them into acs_cd, derives the percentage indicators, and re-derives CT's
acs_state from the now-complete CDs.

Runs AFTER census_acs_cd.py (which lays down CT 2010-2021) and
derive_acs_state_from_cd.py in the refresh; idempotent (merge=True appends).

Caveat: CT medians for the new vintages are Census's PUBLISHED CD medians
(exact for the stable 118th districts), whereas 2010-2021 are the
crosswalk bin-recompute approximation — a small method boundary at 2022,
the new points being the more accurate.

Run: python pipelines/census_acs_cd_ct_direct.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: F401  (loads .env -> CENSUS_API_KEY)
import census_acs_cd as cd
import derive_acs_state_from_cd as derive
from common import cached_get, write_timeseries

CT_FIPS = "09"
CT_DISTRICTS = ["01", "02", "03", "04", "05"]
CD_DATA = Path(__file__).resolve().parent.parent / "public" / "data" / "acs_cd"
# Vintages the crosswalk can't supply for CT (COG geography from 2022 on).
# Intersect with the pipeline's configured set so this auto-extends.
NEW_VINTAGES = [y for y in cd.ACS_VINTAGES if y >= 2022]
API = "https://api.census.gov/data/{year}/acs/acs5"
TTL = 30 * 24 * 3600


def _num(s: str | None):
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _var_by_id() -> dict[str, cd.AcsVar]:
    return {v.out_id: v for v in cd.INDICATORS}


def _is_median(v: cd.AcsVar) -> bool:
    return v.cd_basis == cd.CD_BASIS_TRACT_MEDIAN


def _fetch_codes() -> dict[str, list[str]]:
    """out_id -> list of Census var codes to fetch. Skips C24080 (class of
    worker), which Census doesn't publish at these geographies (it 400s the
    whole batch); skips AGG_PCT (computed from the fetched counts)."""
    out: dict[str, list[str]] = {}
    for v in cd.INDICATORS:
        codes = [v.var_code] if v.var_code else list(v.sum_codes)
        codes = [c for c in codes if c]
        if not codes or any("C24080" in c for c in codes):
            continue
        out[v.out_id] = codes
    return out


def _fetch_year(year: int, all_codes: list[str]) -> dict[str, dict[str, float | None]]:
    """{district: {var_code: value}} for CT's CDs at CD geography. The Census
    API caps `get` at 50 variables, so fetch in batches and merge."""
    key = os.environ.get("CENSUS_API_KEY", "")
    out: dict[str, dict[str, float | None]] = {d: {} for d in CT_DISTRICTS}
    BATCH = 45
    for i in range(0, len(all_codes), BATCH):
        chunk = all_codes[i:i + BATCH]
        get = ",".join(["NAME"] + chunk)
        url = (f"{API.format(year=year)}?get={get}"
               f"&for=congressional%20district:*&in=state:{CT_FIPS}&key={key}")
        rows = json.loads(cached_get(url, ttl_seconds=TTL))
        hdr = rows[0]
        cdi = hdr.index("congressional district")
        idx = {c: hdr.index(c) for c in chunk}
        for r in rows[1:]:
            dist = r[cdi]
            if dist == "ZZ" or dist not in CT_DISTRICTS:
                continue
            for c in chunk:
                out[dist][c] = _num(r[idx[c]])
    return out


def main() -> int:
    var_by_id = _var_by_id()
    fetch_codes = _fetch_codes()
    all_codes = sorted({c for codes in fetch_codes.values() for c in codes})
    print(f"CT direct fetch: {len(all_codes)} var codes x {len(NEW_VINTAGES)} "
          f"vintages {NEW_VINTAGES} x 5 CDs", flush=True)

    raw: dict[int, dict[str, dict[str, float | None]]] = {}
    for y in NEW_VINTAGES:
        raw[y] = _fetch_year(y, all_codes)

    # counts[year][dist][out_id] = computed value (median = published cell;
    # count = the cell, or sum of sum_codes for movers). Negatives are
    # Census "not available" placeholders -> dropped.
    counts: dict[int, dict[str, dict[str, float]]] = {}
    for y in NEW_VINTAGES:
        counts[y] = {}
        for dist in CT_DISTRICTS:
            vals = raw[y].get(dist, {})
            row: dict[str, float] = {}
            for out_id, codes in fetch_codes.items():
                parts = [vals.get(c) for c in codes]
                present = [p for p in parts if p is not None]
                if not present:
                    continue
                v = present[0] if len(codes) == 1 else sum(present)
                if v < 0:
                    continue
                row[out_id] = v
            counts[y][dist] = row

    written = 0
    # 1. Write the fetched counts + medians.
    for out_id, _codes in fetch_codes.items():
        var = var_by_id[out_id]
        for dist in CT_DISTRICTS:
            pts = []
            for y in NEW_VINTAGES:
                v = counts[y].get(dist, {}).get(out_id)
                if v is None:
                    continue
                v = round(v, var.decimals) if _is_median(var) else round(v)
                pts.append({"t": f"{y}-12-31", "v": v})
            if pts:
                write_timeseries(
                    "acs_cd", f"{out_id}_ct_{dist}",
                    f"{var.name_prefix} — CT-{dist}", pts,
                    unit=var.unit, merge=True)
                written += 1

    # 2. Compute + write the percentage indicators from the counts.
    for v in cd.INDICATORS:
        if v.agg != cd.AGG_PCT or not (v.numerator_id and v.denominator_id):
            continue
        for dist in CT_DISTRICTS:
            pts = []
            for y in NEW_VINTAGES:
                row = counts[y].get(dist, {})
                num = row.get(v.numerator_id)
                den = row.get(v.denominator_id)
                if num is None or not den or den <= 0:
                    continue
                pts.append({"t": f"{y}-12-31", "v": round(100 * num / den, v.decimals)})
            if pts:
                write_timeseries(
                    "acs_cd", f"{v.out_id}_ct_{dist}",
                    f"{v.name_prefix} — CT-{dist}", pts,
                    unit=v.unit, merge=True)
                written += 1

    print(f"  wrote/merged {written} CT acs_cd series", flush=True)

    # 3. Re-derive CT's acs_state from the now-complete CDs (reusing derive's
    # exact aggregation: counts sum, medians population-weighted).
    pop_lookup: dict[tuple[str, str], dict[str, float]] = {}
    for dist in CT_DISTRICTS:
        p = CD_DATA / f"population_ct_{dist}.json"
        pts = derive.load_points(p)
        if pts:
            pop_lookup[("ct", dist)] = {
                x["t"]: float(x["v"]) for x in pts
                if isinstance(x.get("t"), str) and isinstance(x.get("v"), (int, float))
            }
    state_written = 0
    for ind in derive.ALL_INDICATORS:
        is_med = ind in derive.MEDIAN_INDICATORS
        points = derive.aggregate_state(ind, "ct", CT_DISTRICTS, pop_lookup, is_med)
        if not points:
            continue
        write_timeseries(
            "acs_state", f"{ind['out_id']}_ct",
            f"{ind['name_prefix']} — CT", points,
            unit=ind["unit"], merge=False)
        state_written += 1
    print(f"  re-derived {state_written} CT acs_state series", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
