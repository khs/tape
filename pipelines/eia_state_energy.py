"""
State-level electricity net generation by fuel — EIA API v2,
route electricity/electric-power-operational-data.

Per state (+ US total), annual, broken out by the major generation
fuels: total, natural gas, coal, nuclear, wind, solar, hydro. This is
the canonical "where does this state's power come from" series.

Query shape (data[0]=generation, sectorid=99 "All Sectors"):
  /v2/electricity/electric-power-operational-data/data/
    ?frequency=annual&data[0]=generation
    &facets[sectorid][]=99&facets[location][]=TX&start=2001
We fetch ALL fuels for a state in one call and keep the curated set.

API notes:
  - The EIA v2 bracket params (data[0], facets[x][]) trip curl's URL
    globbing — pass curl -g if probing by hand. Python requests (what
    cached_get uses) encodes them fine.
  - Units come back as "thousand megawatthours"; we store TWh
    (thousand MWh / 1000) so state totals read as ~5-550 and the US
    total ~4300. unitClass "count" (additive extensive quantity:
    sum of states/fuels reconstructs larger totals).
  - sectorid=99 (All Sectors) so industrial / commercial self-
    generation is included, not just electric utilities.
  - Some (state, fuel) cells are absent (no solar in early years, no
    hydro in flat states); those are simply skipped.

Run: `python pipelines/eia_state_energy.py` (needs EIA_API_KEY).
"""
from __future__ import annotations

import os
import sys

import _env  # noqa: F401 — loads .env so EIA_API_KEY is available locally

from common import cached_get

# write_timeseries imported lazily inside run() is unnecessary; import here.
from common import write_timeseries

PIPELINE = "eia_state_energy"
BASE = "https://api.eia.gov/v2/electricity/electric-power-operational-data/data/"

# 50 states + DC. EIA uses 2-letter postal codes for the location facet.
STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
]
STATE_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

# (suffix, EIA fueltypeid, friendly label). ALL = total net generation.
# Keep in lockstep with pipelines/_scaffold_eia_state_energy.py.
FUELS = [
    ("all",     "ALL", "total net generation"),
    ("gas",     "NG",  "natural gas"),
    ("coal",    "COW", "coal"),
    ("nuclear", "NUC", "nuclear"),
    ("wind",    "WND", "wind"),
    ("solar",   "SUN", "solar"),
    ("hydro",   "HYC", "conventional hydroelectric"),
]
WANTED = {code for _suffix, code, _label in FUELS}
CODE_SUFFIX = {code: suffix for suffix, code, _label in FUELS}


def fetch_geo(location: str, api_key: str) -> list[dict]:
    params = {
        "api_key": api_key,
        "frequency": "annual",
        "data[0]": "generation",
        "facets[sectorid][]": "99",
        "facets[location][]": location,
        "start": "2001",
        "length": "5000",
    }
    import json
    body = cached_get(BASE, ttl_seconds=24 * 3600, params=params).strip()
    if not body:
        return []
    try:
        return json.loads(body).get("response", {}).get("data", []) or []
    except (json.JSONDecodeError, AttributeError):
        return []


def points_by_fuel(rows: list[dict]) -> dict[str, list[dict]]:
    """{fuel_suffix: [{t, v}]}. generation (thousand MWh) -> TWh."""
    out: dict[str, list[dict]] = {}
    for r in rows:
        code = r.get("fueltypeid")
        if code not in WANTED:
            continue
        raw = r.get("generation")
        period = r.get("period")
        if raw is None or period is None:
            continue
        try:
            twh = float(raw) / 1000.0
        except (TypeError, ValueError):
            continue
        out.setdefault(CODE_SUFFIX[code], []).append(
            {"t": f"{period}-12-31", "v": twh}
        )
    for suffix in out:
        out[suffix].sort(key=lambda p: p["t"])
    return out


def run() -> int:
    api_key = os.environ.get("EIA_API_KEY")
    if not api_key:
        print("ERROR: EIA_API_KEY required.", file=sys.stderr)
        return 2

    written = 0
    empties: list[str] = []

    def emit(geo_key: str, rows: list[dict]):
        nonlocal written
        by_fuel = points_by_fuel(rows)
        for suffix, _code, _label in FUELS:
            pts = by_fuel.get(suffix, [])
            sid = f"us_{suffix}" if geo_key == "us" else f"state_{suffix}_{geo_key}"
            if len(pts) < 2:  # need >=2 points to render a chart
                empties.append(sid)
                continue
            write_timeseries(PIPELINE, sid, sid, pts, unit="TWh")
            written += 1

    emit("us", fetch_geo("US", api_key))
    for abbr in STATES:
        emit(abbr.lower(), fetch_geo(abbr, api_key))

    print(f"eia_state_energy: wrote {written} series.")
    if empties:
        print(f"  {len(empties)} skipped (<2 points): {', '.join(empties[:8])}"
              + (" ..." if len(empties) > 8 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
