"""
Derive state-level choropleth snapshot files from existing acs_state
time-series data.

The Census API requires CENSUS_API_KEY to query directly, which lives
on the GitHub Actions runner but isn't always available locally. This
script avoids that hop by deriving the cross-sectional snapshots from
the per-state time series already on disk (census_acs_cd.py +
derive_acs_state_from_cd.py already populated them).

Indicators derived:
  poverty_rate          = poverty_count / population × 100
  median_hh_income      = direct copy from median_hh_income_<st>
  bachelors_plus_pct    = bachelors_plus / (population - population_under_18) × 100
                          (using 18+ as a proxy for the 25+ universe;
                           drift is small, ~3pp on the ratio)
  foreign_born_pct      = foreign_born / population × 100

Output format matches census_acs_choropleth.py exactly so the chart
renderer doesn't care how the file was produced.

Run with: python pipelines/census_acs_choropleth_derive_state.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
STATE_DATA = ROOT / "public" / "data" / "acs_state"
OUT_DIR = ROOT / "public" / "data" / "acs_state"

VINTAGES = [
    "2010", "2011", "2012", "2013", "2014", "2015", "2016",
    "2017", "2018", "2019", "2020", "2021", "2022",
]

# 50 states + DC, lowercase 2-letter (matches the file-name convention).
# State FIPS for output GEOIDs.
STATE_FIPS: dict[str, str] = {
    "al": "01", "ak": "02", "az": "04", "ar": "05", "ca": "06",
    "co": "08", "ct": "09", "de": "10", "dc": "11", "fl": "12",
    "ga": "13", "hi": "15", "id": "16", "il": "17", "in": "18",
    "ia": "19", "ks": "20", "ky": "21", "la": "22", "me": "23",
    "md": "24", "ma": "25", "mi": "26", "mn": "27", "ms": "28",
    "mo": "29", "mt": "30", "ne": "31", "nv": "32", "nh": "33",
    "nj": "34", "nm": "35", "ny": "36", "nc": "37", "nd": "38",
    "oh": "39", "ok": "40", "or": "41", "pa": "42", "ri": "44",
    "sc": "45", "sd": "46", "tn": "47", "tx": "48", "ut": "49",
    "vt": "50", "va": "51", "wa": "53", "wv": "54", "wi": "55",
    "wy": "56",
}


def load_value_at(slug: str, st: str, vintage: str) -> float | None:
    """Read public/data/acs_state/<slug>_<st>.json and pull the value
    at the given vintage (matches the year part of the ISO date).
    Returns None if file missing or vintage absent."""
    path = STATE_DATA / f"{slug}_{st}.json"
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for p in body.get("points", []):
        t = p.get("t", "")
        if isinstance(t, str) and t.startswith(vintage + "-"):
            v = p.get("v")
            if isinstance(v, (int, float)):
                return float(v)
    return None


def write_snapshot(out_id: str, vintage: str, values: dict[str, float],
                   unit: str, decimals: int, value_label: str) -> Path:
    path = OUT_DIR / f"{out_id}_{vintage}.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    body = {
        "geo": "state",
        "indicator": out_id,
        "vintage": vintage,
        "unit": unit,
        "decimals": decimals,
        "valueLabel": value_label,
        "lastUpdated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "values": {k: round(values[k], decimals + 2) for k in sorted(values)},
    }
    path.write_text(json.dumps(body) + "\n", encoding="utf-8")
    return path


def derive_all() -> int:
    written = 0
    for vintage in VINTAGES:
        # poverty_rate
        vals: dict[str, float] = {}
        for st, fips in STATE_FIPS.items():
            num = load_value_at("poverty_count", st, vintage)
            den = load_value_at("population", st, vintage)
            if num is None or den is None or den <= 0:
                continue
            vals[fips] = 100.0 * num / den
        if vals:
            write_snapshot(
                "poverty_rate", vintage, vals, "%", 1,
                "% of population below poverty line",
            )
            written += 1

        # median_hh_income (direct)
        vals = {}
        for st, fips in STATE_FIPS.items():
            v = load_value_at("median_hh_income", st, vintage)
            if v is None:
                continue
            vals[fips] = v
        if vals:
            write_snapshot(
                "median_hh_income", vintage, vals, "USD", 0,
                "Median household income (USD)",
            )
            written += 1

        # bachelors_plus_pct (proxy 18+ denominator)
        vals = {}
        for st, fips in STATE_FIPS.items():
            num = load_value_at("bachelors_plus", st, vintage)
            pop = load_value_at("population", st, vintage)
            under18 = load_value_at("population_under_18", st, vintage)
            if num is None or pop is None or under18 is None:
                continue
            adults = pop - under18
            if adults <= 0:
                continue
            vals[fips] = 100.0 * num / adults
        if vals:
            write_snapshot(
                "bachelors_plus_pct", vintage, vals, "%", 1,
                "% of adults (18+) with bachelor's degree or higher",
            )
            written += 1

        # foreign_born_pct
        vals = {}
        for st, fips in STATE_FIPS.items():
            num = load_value_at("foreign_born", st, vintage)
            den = load_value_at("population", st, vintage)
            if num is None or den is None or den <= 0:
                continue
            vals[fips] = 100.0 * num / den
        if vals:
            write_snapshot(
                "foreign_born_pct", vintage, vals, "%", 1,
                "% foreign-born",
            )
            written += 1

    print(f"Wrote {written} snapshot file(s) under public/data/acs_state/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(derive_all())
