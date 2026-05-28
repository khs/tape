"""
Unemployment rate by race / Hispanic origin, per state + US — Census
ACS 1-year Subject Table S2301 ("Employment Status"), column C04
("Unemployment rate").

Why ACS, not FRED/BLS: state-by-race unemployment isn't on FRED, and
BLS only publishes it in the annual Geographic Profile HTML tables. ACS
serves the same concept through a clean keyed API we're already wired
for. The methodology differs from the BLS LAUS/CPS headline (ACS is a
rolling annual survey, not the monthly household survey), so sources are
labeled ACS — don't expect them to match the BLS state unemployment rate
exactly.

S2301 layout: C04 is the "Unemployment rate" column; C04_001 is the
16-and-over total, C04_012..019 are the RACE AND HISPANIC OR LATINO
ORIGIN rows. acs1 covers every area with population >= 65k, so all 50
states + DC qualify.

API notes (cost real time if forgotten):
  - The variable CODES (S2301_C04_0NNE) are stable across 2015-2023
    (verified at both endpoints); only the label TEXT format drifted
    (the "Estimate" / "Unemployment rate" segment order swapped), so the
    companion audit matches labels flexibly. Codes are hardcoded here.
  - Suppressed / not-available cells come back as -999999999; we keep
    only plausible rates (0 <= v <= 100).
  - `for=state:*` returns 52 rows (50 states + DC + Puerto Rico 72); we
    map FIPS through STATES (50 + DC) and silently drop anything else.
  - ACS 1-year 2020 was never released (COVID nonresponse); skipped.

Units: the rate is already a percentage number (5.5 means 5.5%); unit
"%", stored verbatim (format style "percent" appends % without scaling).

Run: `python pipelines/census_acs_labor.py` (needs CENSUS_API_KEY).
"""
from __future__ import annotations

import json
import os
import sys

import _env  # noqa: F401 — loads .env so CENSUS_API_KEY is available locally

from common import cached_get, write_timeseries

PIPELINE = "acs_labor"
API_TMPL = "https://api.census.gov/data/{year}/acs/acs1/subject"
# ACS 1-year vintages. 2020 omitted (no standard 1-year release).
YEARS = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023]

# FIPS -> (abbr, name). 50 states + DC (ACS 1-year covers DC).
STATES: dict[str, tuple[str, str]] = {
    "01": ("AL", "Alabama"), "02": ("AK", "Alaska"), "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"), "06": ("CA", "California"), "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"), "10": ("DE", "Delaware"),
    "11": ("DC", "District of Columbia"), "12": ("FL", "Florida"),
    "13": ("GA", "Georgia"), "15": ("HI", "Hawaii"), "16": ("ID", "Idaho"),
    "17": ("IL", "Illinois"), "18": ("IN", "Indiana"), "19": ("IA", "Iowa"),
    "20": ("KS", "Kansas"), "21": ("KY", "Kentucky"), "22": ("LA", "Louisiana"),
    "23": ("ME", "Maine"), "24": ("MD", "Maryland"), "25": ("MA", "Massachusetts"),
    "26": ("MI", "Michigan"), "27": ("MN", "Minnesota"), "28": ("MS", "Mississippi"),
    "29": ("MO", "Missouri"), "30": ("MT", "Montana"), "31": ("NE", "Nebraska"),
    "32": ("NV", "Nevada"), "33": ("NH", "New Hampshire"), "34": ("NJ", "New Jersey"),
    "35": ("NM", "New Mexico"), "36": ("NY", "New York"), "37": ("NC", "North Carolina"),
    "38": ("ND", "North Dakota"), "39": ("OH", "Ohio"), "40": ("OK", "Oklahoma"),
    "41": ("OR", "Oregon"), "42": ("PA", "Pennsylvania"), "44": ("RI", "Rhode Island"),
    "45": ("SC", "South Carolina"), "46": ("SD", "South Dakota"), "47": ("TN", "Tennessee"),
    "48": ("TX", "Texas"), "49": ("UT", "Utah"), "50": ("VT", "Vermont"),
    "51": ("VA", "Virginia"), "53": ("WA", "Washington"), "54": ("WV", "West Virginia"),
    "55": ("WI", "Wisconsin"), "56": ("WY", "Wyoming"),
}

# (suffix, S2301 variable code, friendly race label). C04 is the
# "Unemployment rate" column. Keep in lockstep with scripts/audit_acs_labor.py.
RACES: list[tuple[str, str, str]] = [
    ("total",     "S2301_C04_001E", "all workers"),
    ("white",     "S2301_C04_012E", "White"),
    ("black",     "S2301_C04_013E", "Black or African American"),
    ("aian",      "S2301_C04_014E", "American Indian and Alaska Native"),
    ("asian",     "S2301_C04_015E", "Asian"),
    ("nhpi",      "S2301_C04_016E", "Native Hawaiian and Other Pacific Islander"),
    ("otherrace", "S2301_C04_017E", "some other race"),
    ("multi",     "S2301_C04_018E", "two or more races"),
    ("hispanic",  "S2301_C04_019E", "Hispanic or Latino origin (of any race)"),
]
CODES = [code for _suffix, code, _label in RACES]


def fetch_year(year: int, for_clause: str, api_key: str) -> list[list[str]]:
    url = API_TMPL.format(year=year)
    params = {"get": "NAME," + ",".join(CODES), "for": for_clause, "key": api_key}
    body = cached_get(url, ttl_seconds=24 * 3600, params=params).strip()
    if not body:
        return []
    try:
        rows = json.loads(body)
    except json.JSONDecodeError:
        return []
    return rows if isinstance(rows, list) and rows else []


def valid_rate(raw: str) -> float | None:
    """ACS suppresses unavailable cells with -999999999; real rates are
    0..100."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 100.0 else None


def run() -> int:
    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        print("ERROR: CENSUS_API_KEY required (ACS subject tables are key-gated).",
              file=sys.stderr)
        return 2

    # (geo_key, race_suffix) -> [{t, v}]
    series: dict[tuple[str, str], list[dict]] = {}

    def absorb(rows: list[list[str]], year: int, geo_of):
        if not rows:
            return
        hdr = rows[0]
        try:
            idx = {c: hdr.index(c) for c in CODES}
        except ValueError:
            return
        for r in rows[1:]:
            geo = geo_of(r)
            if geo is None:
                continue
            for suffix, code, _label in RACES:
                v = valid_rate(r[idx[code]])
                if v is None:
                    continue
                series.setdefault((geo, suffix), []).append(
                    {"t": f"{year}-07-01", "v": v}
                )

    for year in YEARS:
        # National.
        absorb(fetch_year(year, "us:1", api_key), year, lambda r: "us")
        # All states in one call; map FIPS -> abbr, drop PR / unknowns.
        def geo_of_state(r):
            fips = r[-1]
            ent = STATES.get(fips)
            return ent[0].lower() if ent else None
        absorb(fetch_year(year, "state:*", api_key), year, geo_of_state)

    written = 0
    for (geo, suffix), pts in series.items():
        pts.sort(key=lambda p: p["t"])
        sid = f"us_{suffix}" if geo == "us" else f"state_{suffix}_{geo}"
        # name set by the scaffolder's YAML; the data file `name` is a
        # fallback only.
        write_timeseries(PIPELINE, sid, sid, pts, unit="%")
        written += 1

    print(f"acs_labor: wrote {written} series "
          f"({len(YEARS)} years, {len(RACES)} race groups).")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
