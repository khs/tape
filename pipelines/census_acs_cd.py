"""
Census American Community Survey (ACS) 5-year estimates, by congressional
district. Headline demographics for each of the 435 CDs (118th Congress
boundaries): median household income, total population, poverty,
educational attainment, unemployment.

Requires a Census Bureau API key (free, registers in ~30 seconds at
https://api.census.gov/data/key_signup.html). Set CENSUS_API_KEY in the
environment before running. CI: add as a GitHub Actions secret.

When CENSUS_API_KEY is unset, the pipeline no-ops with a clear status
message so the data-refresh workflow doesn't fail.

Run with: ``CENSUS_API_KEY=<your-key> python pipelines/census_acs_cd.py``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

from common import write_timeseries


# Latest available ACS 5-year. Released ~Dec of year+2 (so 2022 5-year
# released Dec 2023; current as of mid-2026).
ACS_YEAR = 2022
ACS_BASE = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"

# Indicator → ACS variable code + display metadata.
@dataclass
class AcsVar:
    out_id: str       # filename slug: data/acs_cd/<out_id>_<state>_<dist>.json
    var_code: str     # Census variable code (e.g. B19013_001E)
    name_prefix: str  # YAML "name" prefix
    unit: str
    decimals: int


INDICATORS = [
    AcsVar("median_hh_income", "B19013_001E",
           "Median household income", "USD", 0),
    AcsVar("population", "B01003_001E",
           "Total population", "people", 0),
    AcsVar("poverty_count", "B17001_002E",
           "People in poverty", "people", 0),
    AcsVar("bachelors_plus", "B15003_022E",
           "Adults 25+ with bachelor's degree", "people", 0),
]

# State FIPS codes for the 50 states + DC. Census doesn't return CD data
# for territories.
STATE_FIPS = [
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
    "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "44", "45", "46", "47", "48", "49", "50", "51", "53",
    "54", "55", "56",
]

# Mirror of US_STATES from usaspending.py — kept local for self-contained
# pipeline; the abbreviation forms the per-CD slug.
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


def fetch_indicator(var: AcsVar, state_fips: str, key: str) -> dict[str, float]:
    """
    Fetch one ACS variable for all congressional districts within one state.
    Returns {district_code: value}.
    """
    url = (
        f"{ACS_BASE}?get=NAME,{var.var_code}"
        f"&for=congressional%20district:*&in=state:{state_fips}&key={key}"
    )
    try:
        out = subprocess.run(
            ["curl", "-s", "-S", "--max-time", "60", url],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError:
        return {}
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list) or len(data) < 2:
        return {}
    # First row is headers: ['NAME', '<var_code>', 'state', 'congressional district']
    out_map: dict[str, float] = {}
    for row in data[1:]:
        if len(row) < 4:
            continue
        try:
            v = float(row[1])
        except (TypeError, ValueError):
            continue
        district = row[3]
        out_map[district] = v
    return out_map


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

    # ACS data is annual; we store one data point per (district, indicator).
    # Anchor at end-of-year-of-ACS-period for chronological sorting.
    anchor = f"{ACS_YEAR}-12-31"

    written = 0
    for var in INDICATORS:
        print(f"Fetching {var.var_code} ({var.out_id})...", flush=True)
        for fips in STATE_FIPS:
            data = fetch_indicator(var, fips, key)
            for district, value in data.items():
                abbr = STATE_ABBR.get(fips, fips)
                # At-large district encoding: Census returns "00" for at-large.
                if district == "00":
                    dist_slug = "al"
                else:
                    try:
                        dist_slug = f"{int(district):02d}"
                    except ValueError:
                        continue
                slug = f"{var.out_id}_{abbr}_{dist_slug}"
                # ACS 5-year is annual; one point per series for now.
                # Future runs will append new years.
                write_timeseries(
                    pipeline="acs_cd",
                    series_id=slug,
                    name=f"{var.name_prefix} — {abbr.upper()}-{dist_slug.upper()}",
                    points=[{"t": anchor, "v": value}],
                    unit=var.unit,
                )
                written += 1
    print(f"acs_cd: wrote {written} series", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
