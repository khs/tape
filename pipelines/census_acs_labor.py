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

Source YAMLs are emitted INLINE (one per written series, right after the
data file) into src/content/sources/acs_labor/ — overwrite-always; the dir
is pipeline-owned. This replaced the one-shot _scaffold_acs_labor.py
(Plan 7). Suppression is handled for free: a (state, race) cell the API
suppresses never produces points, so it never gets a data file OR a YAML.

Run: `python pipelines/census_acs_labor.py` (needs CENSUS_API_KEY).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import _env  # noqa: F401 — loads .env so CENSUS_API_KEY is available locally

from common import cached_get, write_timeseries

PIPELINE = "acs_labor"
API_TMPL = "https://api.census.gov/data/{year}/acs/acs1/subject"
# ACS 1-year vintages. 2020 omitted (no standard 1-year release).
# Append the new vintage each year (ACS 1-year releases ~September).
YEARS = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]

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

# --- Source-YAML emission (inline; Plan 7) --------------------------------
# One YAML per written series, emitted right after its data file, so
# YAML<->data parity holds by construction (suppressed (state, race) cells
# never get either). Overwrite-always: the dir is pipeline-owned —
# name/description fixes belong in these templates. Per-state IDs
# (`state_<race>_<st>`) are recognized by parseStateSourceId and gated
# behind the composer's state chip; the national `us_<race>` series stay
# default-visible and carry the labor/macro tags.
REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_DIR = REPO_ROOT / "src" / "content" / "sources" / PIPELINE

RACE_LABEL = {suffix: label for suffix, _code, label in RACES}
RACE_CODE = {suffix: code for suffix, code, _label in RACES}
STATE_NAME_LC = {abbr.lower(): name for abbr, name in STATES.values()}

# Short race tag for the chip/card shortName.
SHORT_RACE = {
    "total": "all", "white": "White", "black": "Black", "aian": "AIAN",
    "asian": "Asian", "nhpi": "NHPI", "otherrace": "other race",
    "multi": "2+ races", "hispanic": "Hispanic",
}
TABLE_URL = "https://data.census.gov/table/ACSST1Y2023.S2301"


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def write_yaml(sid: str, suffix: str, geo: str) -> None:
    label = RACE_LABEL[suffix]
    if geo == "us":
        if suffix == "total":
            name = "Unemployment rate — all workers (US)"
            desc_scope = "all workers (ages 16+) nationally"
        else:
            name = f"Unemployment rate — {label} (US)"
            desc_scope = f"{label} workers (ages 16+) nationally"
        short = f"{SHORT_RACE[suffix]} unemployment (US)"
        tags = ["labor", "macro", "us"]
    else:
        sname = STATE_NAME_LC[geo]
        if suffix == "total":
            name = f"{sname} unemployment rate — all workers"
            desc_scope = f"all workers (ages 16+) in {sname}"
        else:
            name = f"{sname} unemployment rate — {label}"
            desc_scope = f"{label} workers (ages 16+) in {sname}"
        short = f"{geo.upper()} {SHORT_RACE[suffix]} unemp"
        tags = ["labor", "macro", "us-state", "us"]
    desc = (
        f"Unemployment rate among {desc_scope}, Census American Community "
        f"Survey 1-year estimates (Subject Table S2301). ACS is a rolling "
        f"annual survey, so this differs from the monthly BLS state "
        f"unemployment rate."
    )
    lines = [
        f"name: {_q(name)}",
        f"shortName: {_q(short)}",
        f"description: {_q(desc)}",
        "kind: timeseries",
        f"pipeline: {PIPELINE}",
        f"dataFile: data/{PIPELINE}/{sid}.json",
        'supportedDeltas: ["1y", "5y"]',
        'unit: "%"',
        "emphasis: level",
        "formatting:",
        "  style: percent",
        "  decimals: 1",
        "provenance:",
        "  provider: U.S. Census Bureau, American Community Survey (ACS 1-year)",
        f"  series: {RACE_CODE[suffix]} (ACS 1-year Subject Table S2301)",
        f"  url: {TABLE_URL}",
        "  license: Public domain (US government data)",
        "tags:",
    ]
    for t in tags:
        lines.append(f"  - {t}")
    lines.append("unitClass: rate")
    (YAML_DIR / f"{sid}.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


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
    YAML_DIR.mkdir(parents=True, exist_ok=True)
    for (geo, suffix), pts in series.items():
        pts.sort(key=lambda p: p["t"])
        sid = f"us_{suffix}" if geo == "us" else f"state_{suffix}_{geo}"
        # display name lives in the inline YAML; the data file `name` is a
        # fallback only.
        write_timeseries(PIPELINE, sid, sid, pts, unit="%")
        write_yaml(sid, suffix, geo)
        written += 1

    print(f"acs_labor: wrote {written} series "
          f"({len(YEARS)} years, {len(RACES)} race groups).")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
