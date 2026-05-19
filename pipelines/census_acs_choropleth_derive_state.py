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


def load_value_at(slug: str, st: str, vintage: str,
                  fallback_years: int = 0) -> tuple[float, str] | tuple[None, None]:
    """Read public/data/acs_state/<slug>_<st>.json and pull the value
    at the given vintage. Returns (value, actual_vintage) — typically
    actual_vintage == vintage, but if missing AND fallback_years > 0
    we scan up to that many years back for the most recent earlier
    value. Returns (None, None) if no value found in the fallback
    window. Bundled so callers know whether they got the exact
    vintage or a fallback (for the snapshot's metadata)."""
    path = STATE_DATA / f"{slug}_{st}.json"
    if not path.exists():
        return None, None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    target_year = int(vintage)
    candidates: dict[int, float] = {}
    for p in body.get("points", []):
        t = p.get("t", "")
        if not isinstance(t, str) or len(t) < 4:
            continue
        try:
            y = int(t[:4])
        except ValueError:
            continue
        v = p.get("v")
        if isinstance(v, (int, float)):
            candidates[y] = float(v)
    if target_year in candidates:
        return candidates[target_year], vintage
    if fallback_years > 0:
        for back in range(1, fallback_years + 1):
            y = target_year - back
            if y in candidates:
                return candidates[y], str(y)
    return None, None


def write_snapshot(out_id: str, vintage: str,
                   values: dict[str, float],
                   fallbacks: dict[str, str],
                   unit: str, decimals: int, value_label: str) -> Path:
    """Write a snapshot file. `fallbacks` records {state_fips: actual_year}
    for any state whose value came from an earlier-vintage fallback, so
    the renderer can surface that to the user later if it wants. Most
    entries will have actual_year == vintage and the dict will be small."""
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
    if fallbacks:
        body["fallbacks"] = dict(sorted(fallbacks.items()))
    path.write_text(json.dumps(body) + "\n", encoding="utf-8")
    return path


def derive_all() -> int:
    """Walk every (state, indicator, vintage) we want; write one
    snapshot file per (indicator, vintage). Up to 3-year fallback
    fills gaps from a recent earlier vintage so the choropleth has
    complete coverage — the dominant case being Connecticut 2022,
    where the tract→CD crosswalk's pre-Planning-Region county FIPS
    don't match the Census API's new PR-based tract GEOIDs and so
    the tract-aggregated path yields nothing. Fallback is recorded
    in the snapshot file's `fallbacks` block so the renderer / future
    UI can call it out.

    The numerator + all denominator series must come from the SAME
    actual_year — mixing 2022 numerator with 2021 denominator would
    produce a wrong ratio. So the year-resolution happens per-state,
    not per-series.
    """
    # Fallback window: 3 years. CT lacks 2022 for our derivation path
    # so the snapshot would otherwise skip CT; 2021 → 2022 drift on
    # poverty / income / education / foreign-born is small (~0.5pp on
    # rates, ~2-3% on dollar amounts) and well below the heatmap's
    # color-bucket resolution.
    FALLBACK = 3

    def resolve(st: str, vintage: str, codes: list[str]) -> tuple[dict[str, float] | None, str | None]:
        """Resolve a state to a (year-consistent) bundle of values for
        the requested series codes. Tries the exact vintage first; if
        ANY series is missing at that year, walks back up to FALLBACK
        years looking for a year where ALL series have data. Returns
        ({code: value}, actual_year) or (None, None) if no year in the
        window has the full bundle."""
        for back in range(0, FALLBACK + 1):
            year = str(int(vintage) - back)
            bundle: dict[str, float] = {}
            ok = True
            for code in codes:
                v, _ = load_value_at(code, st, year)
                if v is None:
                    ok = False
                    break
                bundle[code] = v
            if ok:
                return bundle, year
        return None, None

    written = 0
    for vintage in VINTAGES:
        # poverty_rate
        vals: dict[str, float] = {}
        fallbacks: dict[str, str] = {}
        for st, fips in STATE_FIPS.items():
            b, actual = resolve(st, vintage, ["poverty_count", "population"])
            if not b or actual is None:
                continue
            den = b["population"]
            if den <= 0:
                continue
            vals[fips] = 100.0 * b["poverty_count"] / den
            if actual != vintage:
                fallbacks[fips] = actual
        if vals:
            write_snapshot(
                "poverty_rate", vintage, vals, fallbacks, "%", 1,
                "% of population below poverty line",
            )
            written += 1

        # median_hh_income (direct)
        vals = {}; fallbacks = {}
        for st, fips in STATE_FIPS.items():
            b, actual = resolve(st, vintage, ["median_hh_income"])
            if not b or actual is None:
                continue
            vals[fips] = b["median_hh_income"]
            if actual != vintage:
                fallbacks[fips] = actual
        if vals:
            write_snapshot(
                "median_hh_income", vintage, vals, fallbacks, "USD", 0,
                "Median household income (USD)",
            )
            written += 1

        # bachelors_plus_pct (proxy 18+ denominator)
        vals = {}; fallbacks = {}
        for st, fips in STATE_FIPS.items():
            b, actual = resolve(
                st, vintage,
                ["bachelors_plus", "population", "population_under_18"],
            )
            if not b or actual is None:
                continue
            adults = b["population"] - b["population_under_18"]
            if adults <= 0:
                continue
            vals[fips] = 100.0 * b["bachelors_plus"] / adults
            if actual != vintage:
                fallbacks[fips] = actual
        if vals:
            write_snapshot(
                "bachelors_plus_pct", vintage, vals, fallbacks, "%", 1,
                "% of adults (18+) with bachelor's degree or higher",
            )
            written += 1

        # foreign_born_pct
        vals = {}; fallbacks = {}
        for st, fips in STATE_FIPS.items():
            b, actual = resolve(st, vintage, ["foreign_born", "population"])
            if not b or actual is None:
                continue
            den = b["population"]
            if den <= 0:
                continue
            vals[fips] = 100.0 * b["foreign_born"] / den
            if actual != vintage:
                fallbacks[fips] = actual
        if vals:
            write_snapshot(
                "foreign_born_pct", vintage, vals, fallbacks, "%", 1,
                "% foreign-born",
            )
            written += 1

    print(f"Wrote {written} snapshot file(s) under public/data/acs_state/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(derive_all())
