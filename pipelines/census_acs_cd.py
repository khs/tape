"""
Census American Community Survey (ACS) 5-year estimates, aggregated to
stable-geography (118th-Congress) congressional districts across all
~13 published vintages.

Pipeline architecture:

  1. Read pre-built crosswalks (pipelines/_crosswalks/) that map 2010
     and 2020 tract GEOIDs to 118th-Congress districts with population
     weights. These were produced by build_crosswalks.py from Census
     BAFs and t10t20 relationship files; they're stable until the
     119th Congress takes effect.

  2. For each ACS vintage (2010-2022), fetch tract-level ACS data.
     Vintages 2010-2021 use 2010 tract boundaries; vintage 2022+ uses
     2020 tract boundaries. We auto-select the right crosswalk.

  3. Aggregate by 118th CD using the crosswalk weights:
        - Counts (population, poverty, foreign-born, etc.) sum cleanly:
          CD_total = sum(tract_value × tract_weight) across tracts.
        - Median household income is recomputed from the B19001
          household-income-distribution table (16 income bins per
          tract): sum bin counts across CD-assigned tracts, then
          compute the weighted-median income from the aggregated
          distribution. This gives a true CD-level median on stable
          geography.
        - Other medians (age, home value, rent) are taken at the
          contemporaneous CD level (i.e. vintage-boundary data with
          the historical caveat) — implementing those via
          distribution would be straightforward but isn't necessary
          for the headline use case yet.

  4. Write per-CD time series JSON files.

Requires CENSUS_API_KEY env var (free registration). When unset, the
pipeline no-ops with a clear status message.

Run with: ``CENSUS_API_KEY=<key> python pipelines/census_acs_cd.py``.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from common import write_timeseries


REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSWALK_DIR = REPO_ROOT / "pipelines" / "_crosswalks"

# Vintages we pull. Each is published as its own /data/<year>/acs/acs5
# endpoint. Range starts at 2010 (the earliest ACS5 with CD-level data)
# and goes to 2022 (the latest released as of mid-2026). Extending to
# new vintages is one-line additions when they release each December.
ACS_VINTAGES = list(range(2010, 2023))

# The boundary at which ACS switched from 2010-decennial tract
# definitions to 2020-decennial tract definitions. Set empirically:
# ACS 2022 (covering 2018-2022) was the first vintage released using
# 2020-boundary tract IDs. Earlier vintages use 2010-boundary tracts.
TRACT2020_FIRST_VINTAGE = 2022

# Census's URL path changed mid-decade:
#   2010-2014 ACS5: /data/{year}/acs5/     (no /acs/ subfolder)
#   2015+   ACS5: /data/{year}/acs/acs5/  (current)
# Both paths still exist on Census's side, but each only serves its own
# era. Hitting the wrong path returns 404, which our `acs_fetch` treats
# as empty data — historically that meant pre-2015 vintages silently
# disappeared. Pick per year.
def acs_base(year: int) -> str:
    if year >= 2015:
        return f"https://api.census.gov/data/{year}/acs/acs5"
    return f"https://api.census.gov/data/{year}/acs5"


# ---------------------------------------------------------------------
# Indicator definitions
# ---------------------------------------------------------------------

# Aggregation strategy per indicator. "sum" works at the tract level
# (counts add cleanly across crosswalk-weighted tracts). "cd_level"
# fetches contemporaneous CD-level data, no aggregation — the boundary
# changes across redistricting cycles. "median_from_distribution" fetches
# the income-bin distribution and reassembles the median on aggregated
# geography (only used for B19013 currently).
AGG_SUM = "sum"
AGG_CD_LEVEL = "cd_level"
AGG_MEDIAN_DIST = "median_from_distribution"


@dataclass
class AcsVar:
    out_id: str
    var_code: str           # primary variable code (Census table cell)
    name_prefix: str
    unit: str
    decimals: int
    agg: str                # one of AGG_*
    # For median_from_distribution agg, list of (var_code, lower, upper)
    # describing each income bin. Lower/upper are dollar bounds; the
    # top bin's upper is typically open-ended (we use a synthetic 2x
    # lower bound as an interpolation cap).
    bins: list[tuple[str, float, float]] = field(default_factory=list)


# B19001 = Household Income in the Past 12 Months. Cells 002-017 are
# the 16 income bins; 001 is the total household count. Bounds in 2020
# dollars per ACS specification.
B19001_BINS = [
    ("B19001_002E",      0,  9_999),
    ("B19001_003E", 10_000, 14_999),
    ("B19001_004E", 15_000, 19_999),
    ("B19001_005E", 20_000, 24_999),
    ("B19001_006E", 25_000, 29_999),
    ("B19001_007E", 30_000, 34_999),
    ("B19001_008E", 35_000, 39_999),
    ("B19001_009E", 40_000, 44_999),
    ("B19001_010E", 45_000, 49_999),
    ("B19001_011E", 50_000, 59_999),
    ("B19001_012E", 60_000, 74_999),
    ("B19001_013E", 75_000, 99_999),
    ("B19001_014E", 100_000, 124_999),
    ("B19001_015E", 125_000, 149_999),
    ("B19001_016E", 150_000, 199_999),
    # Top bin is "200,000 or more". For weighted-median interpolation
    # we cap at 2x the lower bound (a Pareto-distribution-style
    # convention used by Census's own median estimates). True top-bin
    # median is unbounded; this is best-available approximation.
    ("B19001_017E", 200_000, 400_000),
]


INDICATORS = [
    # Count indicators — aggregated via crosswalk sum.
    AcsVar("population", "B01003_001E",
           "Total population", "people", 0, AGG_SUM),
    AcsVar("poverty_count", "B17001_002E",
           "People in poverty", "people", 0, AGG_SUM),
    AcsVar("foreign_born", "B05002_013E",
           "Foreign-born population", "people", 0, AGG_SUM),
    AcsVar("bachelors_plus", "B15003_022E",
           "Adults 25+ with bachelor's degree", "people", 0, AGG_SUM),
    AcsVar("masters_plus", "B15003_023E",
           "Adults 25+ with master's degree", "people", 0, AGG_SUM),
    AcsVar("owner_occupied", "B25003_002E",
           "Owner-occupied housing units", "households", 0, AGG_SUM),
    AcsVar("renter_occupied", "B25003_003E",
           "Renter-occupied housing units", "households", 0, AGG_SUM),
    AcsVar("veterans", "B21001_002E",
           "Civilian veteran population (18+)", "people", 0, AGG_SUM),
    AcsVar("broadband_households", "B28002_004E",
           "Households with broadband internet", "households", 0, AGG_SUM),
    # Median from distribution — uses B19001 income bins, recomputed
    # at CD level on stable geography.
    AcsVar("median_hh_income", "B19013_001E",
           "Median household income", "USD", 0, AGG_MEDIAN_DIST,
           bins=B19001_BINS),
    # Medians on contemporaneous-CD geography. Documented caveat.
    AcsVar("median_age", "B01002_001E",
           "Median age", "years", 1, AGG_CD_LEVEL),
    AcsVar("median_home_value", "B25077_001E",
           "Median home value (owner-occupied)", "USD", 0, AGG_CD_LEVEL),
    AcsVar("median_gross_rent", "B25064_001E",
           "Median gross rent", "USD", 0, AGG_CD_LEVEL),
]


# State FIPS for the 50 states + DC.
STATE_FIPS = [
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
    "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "44", "45", "46", "47", "48", "49", "50", "51", "53",
    "54", "55", "56",
]
STATE_ABBR = {
    "01": "al", "02": "ak", "04": "az", "05": "ar", "06": "ca", "08": "co",
    "09": "ct", "10": "de", "11": "dc", "12": "fl", "13": "ga", "15": "hi",
    "16": "id", "17": "il", "18": "in", "19": "ia", "20": "ks", "21": "ky",
    "22": "la", "23": "me", "24": "md", "25": "ma", "26": "mi", "27": "mn",
    "28": "ms", "29": "mo", "30": "mt", "31": "ne", "32": "nv", "33": "nh",
    "34": "nj", "35": "nm", "36": "ny", "37": "nc", "38": "nd", "39": "oh",
    "40": "ok", "41": "or", "42": "pa", "44": "ri", "45": "sc", "46": "sd",
    "47": "tn", "48": "tx", "49": "ut", "50": "vt", "51": "va", "53": "wa",
    "54": "wv", "55": "wi", "56": "wy",
}


# ---------------------------------------------------------------------
# Crosswalks
# ---------------------------------------------------------------------

def load_crosswalk(path: Path) -> dict[str, list[tuple[str, str, float]]]:
    """
    Returns {tract_geoid: [(state_fips, cd, weight), ...]}.
    Tracts that straddle CD boundaries appear with multiple entries.
    """
    out: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    if not path.exists():
        print(f"  crosswalk not found: {path}", file=sys.stderr)
        return out
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            tract = row.get("tract_geoid", "")
            state = row.get("state_fips", "")
            cd = row.get("cd_district", "")
            try:
                weight = float(row.get("weight", "0"))
            except ValueError:
                continue
            if tract and state and cd:
                out[tract].append((state, cd, weight))
    return out


def cd_slug(state_fips: str, cd: str) -> str | None:
    """Convert (state_fips, cd_code) to our slug pattern: 'va_08' or 'mt_al'."""
    abbr = STATE_ABBR.get(state_fips)
    if not abbr:
        return None
    if cd == "00":
        return f"{abbr}_al"
    try:
        return f"{abbr}_{int(cd):02d}"
    except ValueError:
        return None


# ---------------------------------------------------------------------
# ACS API
# ---------------------------------------------------------------------

def acs_fetch(year: int, var_codes: list[str], geo: str, key: str) -> list[list[str]]:
    """
    Fire one Census API request. Returns list of rows (first row = headers).
    Empty list on failure. Logs non-empty error responses so silent
    failures (404 because of wrong URL path, "geography not supported"
    because of wrong filter shape, etc.) are visible in workflow output.
    """
    vars_csv = ",".join(var_codes)
    url = (
        f"{acs_base(year)}?get=NAME,{vars_csv}"
        f"&for={geo}&key={key}"
    )
    try:
        out = subprocess.run(
            ["curl", "-s", "-S", "--max-time", "120", "-w", "%{http_code}", url],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    curl failed for year={year} geo={geo!r}: {e}", file=sys.stderr)
        return []
    # `-w "%{http_code}"` appends the HTTP code at the very end of stdout.
    body = out.stdout
    code = body[-3:] if body[-3:].isdigit() else "???"
    payload = body[:-3] if body[-3:].isdigit() else body
    if code != "200":
        # First non-200 per year is loud; subsequent ones (same state
        # variants etc.) we trust the per-loop logging already covers.
        if len(payload) < 500:
            snippet = payload.strip()[:200]
        else:
            snippet = payload.strip()[:200] + "..."
        print(f"    HTTP {code} for year={year} geo={geo!r}: {snippet}", file=sys.stderr)
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error year={year} geo={geo!r}: {e}", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def parse_value(s: str) -> float | None:
    """Parse a Census value, treating sentinel-negatives as missing."""
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    if v < -1_000_000:
        return None
    return v


# ---------------------------------------------------------------------
# Median-from-bins
# ---------------------------------------------------------------------

def weighted_median_from_bins(
    bins: list[tuple[str, float, float]],
    counts: dict[str, float],
) -> float | None:
    """
    Given bins as (var_code, lower, upper) and a counts dict mapping
    var_code -> count, return the linearly-interpolated median.
    Returns None if total count is zero.
    """
    total = sum(counts.get(code, 0) for code, _, _ in bins)
    if total <= 0:
        return None
    target = total / 2.0
    cum = 0.0
    for code, lower, upper in bins:
        c = counts.get(code, 0)
        if c <= 0:
            continue
        if cum + c >= target:
            # Median falls within this bin. Linear interpolation:
            # median = lower + (target - cum) / c * (upper - lower)
            fraction = (target - cum) / c
            return lower + fraction * (upper - lower)
        cum += c
    return None


# ---------------------------------------------------------------------
# Per-vintage fetch
# ---------------------------------------------------------------------

def fetch_vintage_tract(
    year: int,
    var_codes: list[str],
    state_fips: str,
    key: str,
) -> dict[str, dict[str, float]]:
    """
    Tract-level fetch for one state, one vintage. Returns
    {tract_geoid_11: {var_code: value}}.

    Geography hierarchy: `tract:* in=state:XX county:*`. The wildcard
    county is supported universally across ACS vintages back to 2010.
    Earlier code used `tract:* in=state:XX` (no county), which the
    modern API accepts but the pre-2015 API rejects — that's why our
    pre-2017 vintages came back empty before this fix.
    """
    geo = f"tract:*&in=state:{state_fips}%20county:*"
    rows = acs_fetch(year, var_codes, geo, key)
    if not rows or len(rows) < 2:
        return {}
    headers = rows[0]
    try:
        state_col = headers.index("state")
        county_col = headers.index("county")
        tract_col = headers.index("tract")
    except ValueError:
        return {}
    out: dict[str, dict[str, float]] = {}
    for row in rows[1:]:
        if len(row) < len(headers):
            continue
        state = row[state_col]
        county = row[county_col]
        tract = row[tract_col]
        geoid = f"{state:>2}{county:>3}{tract:>6}"
        per_var: dict[str, float] = {}
        for code in var_codes:
            try:
                col = headers.index(code)
            except ValueError:
                continue
            v = parse_value(row[col])
            if v is not None:
                per_var[code] = v
        if per_var:
            out[geoid] = per_var
    return out


def fetch_vintage_cd_level(
    year: int,
    var_codes: list[str],
    key: str,
) -> dict[tuple[str, str], dict[str, float]]:
    """
    CD-level fetch (no aggregation) for one vintage. Returns
    {(state_fips, cd): {var_code: value}}. Used for medians we don't
    recompute via distribution.
    """
    rows = acs_fetch(year, var_codes, "congressional%20district:*", key)
    if not rows or len(rows) < 2:
        return {}
    headers = rows[0]
    try:
        state_col = headers.index("state")
        dist_col = headers.index("congressional district")
    except ValueError:
        return {}
    out: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows[1:]:
        if len(row) < len(headers):
            continue
        state = row[state_col]
        cd = row[dist_col]
        per_var: dict[str, float] = {}
        for code in var_codes:
            try:
                col = headers.index(code)
            except ValueError:
                continue
            v = parse_value(row[col])
            if v is not None:
                per_var[code] = v
        if per_var:
            out[(state, cd)] = per_var
    return out


# ---------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------

def main() -> int:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        print(
            "census_acs_cd.py: CENSUS_API_KEY not set. Skipping. "
            "Register a free key at https://api.census.gov/data/key_signup.html "
            "and set the env var.",
            file=sys.stderr,
        )
        return 0

    cw_2020 = load_crosswalk(CROSSWALK_DIR / "tract2020_to_cd118.csv")
    cw_2010 = load_crosswalk(CROSSWALK_DIR / "tract2010_to_cd118.csv")
    print(f"Loaded crosswalks: tract2020={len(cw_2020):,} tracts, "
          f"tract2010={len(cw_2010):,} tracts", flush=True)

    # Variable lists for the API calls
    sum_indicators = [v for v in INDICATORS if v.agg == AGG_SUM]
    sum_codes = [v.var_code for v in sum_indicators]
    median_dist_indicators = [v for v in INDICATORS if v.agg == AGG_MEDIAN_DIST]
    median_cd_indicators = [v for v in INDICATORS if v.agg == AGG_CD_LEVEL]
    median_cd_codes = [v.var_code for v in median_cd_indicators]

    # Accumulator: {(out_id, cd_slug): [{t, v}, ...]}
    series_accum: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for year in ACS_VINTAGES:
        anchor = f"{year}-12-31"
        cw = cw_2020 if year >= TRACT2020_FIRST_VINTAGE else cw_2010
        print(f"\nFetching ACS5 vintage {year} (using "
              f"{'tract2020' if year >= TRACT2020_FIRST_VINTAGE else 'tract2010'} crosswalk)...",
              flush=True)

        # Per-CD accumulator for this vintage: {cd_slug: {out_id: value}}
        cd_values: dict[str, dict[str, float]] = defaultdict(dict)
        # Per-CD bin sums for the median-distribution indicators:
        # {cd_slug: {out_id: {bin_code: count_sum}}}
        cd_bins: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

        for fips in STATE_FIPS:
            # Build the variable list for the tract-level call.
            tract_codes = list(sum_codes)
            for v in median_dist_indicators:
                tract_codes += [code for code, _, _ in v.bins]
            # Census limits ~50 vars per call. With 9 sum + 16 income
            # bins = 25 vars, we fit in one call. Add a guard so future
            # expansion still works.
            if len(tract_codes) > 48:
                # Split. (Future: chunk into multiple calls.)
                tract_codes = tract_codes[:48]
            tract_data = fetch_vintage_tract(year, tract_codes, fips, key)
            if not tract_data:
                continue

            for tract_geoid, per_var in tract_data.items():
                cd_assignments = cw.get(tract_geoid, [])
                if not cd_assignments:
                    continue
                for (cd_state, cd, weight) in cd_assignments:
                    slug = cd_slug(cd_state, cd)
                    if not slug:
                        continue
                    # Sum-aggregated indicators: add tract_value * weight
                    for v in sum_indicators:
                        val = per_var.get(v.var_code)
                        if val is None:
                            continue
                        cd_values[slug][v.out_id] = cd_values[slug].get(v.out_id, 0) + val * weight
                    # Distribution-bin counts: sum each bin
                    for v in median_dist_indicators:
                        for code, _, _ in v.bins:
                            val = per_var.get(code)
                            if val is None:
                                continue
                            cd_bins[slug][v.out_id][code] += val * weight

        # Compute medians from accumulated distributions
        for slug, by_indicator in cd_bins.items():
            for v in median_dist_indicators:
                bins_data = by_indicator.get(v.out_id, {})
                med = weighted_median_from_bins(v.bins, bins_data)
                if med is not None:
                    cd_values[slug][v.out_id] = med

        # CD-level medians (no crosswalk; contemporaneous boundaries)
        if median_cd_codes:
            cd_level_data = fetch_vintage_cd_level(year, median_cd_codes, key)
            for (state_fips, cd_raw), per_var in cd_level_data.items():
                slug = cd_slug(state_fips, cd_raw)
                if not slug:
                    continue
                for v in median_cd_indicators:
                    val = per_var.get(v.var_code)
                    if val is not None:
                        cd_values[slug][v.out_id] = val

        # Emit accumulated values into the main series accumulator
        for slug, values in cd_values.items():
            for out_id, value in values.items():
                series_accum[(out_id, slug)].append({"t": anchor, "v": value})

    # Write per-(indicator, CD) time series JSON files
    written = 0
    for (out_id, slug), points in series_accum.items():
        if not points:
            continue
        points.sort(key=lambda p: p["t"])
        # Round counts to integers, keep medians at the indicator's decimal precision.
        var = next((v for v in INDICATORS if v.out_id == out_id), None)
        if var and var.agg == AGG_SUM:
            for p in points:
                p["v"] = round(p["v"])
        name_prefix = var.name_prefix if var else out_id
        unit = var.unit if var else "value"
        series_id = f"{out_id}_{slug}"
        write_timeseries(
            pipeline="acs_cd",
            series_id=series_id,
            name=f"{name_prefix} — {slug.upper().replace('_', '-')}",
            points=points,
            unit=unit,
        )
        written += 1
    print(f"\nacs_cd: wrote {written} stable-geo series across "
          f"{len(ACS_VINTAGES)} vintages", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
