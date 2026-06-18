"""
Derive state-level choropleth snapshot files from existing acs_state
time-series data.

The Census API requires CENSUS_API_KEY to query directly, which lives
on the GitHub Actions runner but isn't always available locally. This
script avoids that hop by deriving the cross-sectional snapshots from
the per-state time series already on disk (census_acs_cd.py +
derive_acs_state_from_cd.py already populated them).

Output format matches census_acs_choropleth.py exactly so the chart
renderer doesn't care how the file was produced.

The indicator set was expanded in May 2026 from the original 4
(poverty_rate, median_hh_income, bachelors_plus_pct, foreign_born_pct)
to a comprehensive list covering every ACS-state series we have a
denominator and a meaningful interpretation for. Composer Maps tab
exposes the broader list at state geography only — county / tract /
block-group still ship the 4 originals because those snapshots come
straight from the API (census_acs_choropleth.py) and adding 16 × 13
vintages × 3,140 counties etc. would balloon the API budget.

Adult-share denominator note: the ACS bachelors / masters / veterans
universes are technically 25+ (education) and 18+ civilian (veterans),
but we don't pull those series at the state level. Using
(population - population_under_18) as a proxy for "adults" is the
same approximation the existing bachelors_plus_pct derivation has
been using since v4; the drift is small (~3pp on the ratio) and
consistent across vintages, so apples-to-apples comparisons hold.

Run with: python pipelines/census_acs_choropleth_derive_state.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DATA = ROOT / "public" / "data" / "acs_state"
OUT_DIR = ROOT / "public" / "data" / "acs_state"

VINTAGES = [
    "2010", "2011", "2012", "2013", "2014", "2015", "2016",
    "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024",
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


@dataclass
class IndicatorSpec:
    """One derived indicator's wiring.

    The numerator + all denominator series must come from the SAME
    actual_year (mixing 2022 numerator with 2021 denominator would
    produce a wrong ratio). The resolve() helper enforces this by
    fetching all `series` codes from one year-bundle.

    `formula(values_at_year)` -> float | None.  Returning None
    suppresses the state for that vintage (e.g. zero-denominator).
    """
    out_id: str
    series: list[str]
    formula: callable
    unit: str
    decimals: int
    value_label: str


def load_value_at(slug: str, st: str, vintage: str) -> float | None:
    """Read public/data/acs_state/<slug>_<st>.json and pull the value
    at the given vintage. Returns None if the file is missing, the
    JSON is malformed, or the point isn't published for that year."""
    path = STATE_DATA / f"{slug}_{st}.json"
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    target_year = int(vintage)
    for p in body.get("points", []):
        t = p.get("t", "")
        if not isinstance(t, str) or len(t) < 4:
            continue
        try:
            y = int(t[:4])
        except ValueError:
            continue
        if y != target_year:
            continue
        v = p.get("v")
        if isinstance(v, (int, float)):
            return float(v)
    return None


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


# Build the indicator spec table once. Each entry is consumed by the
# main loop below; adding a new state-level choropleth indicator means
# appending one entry here AND making sure the Maps-tab dropdown in
# src/pages/compose.astro lists it (the dropdown is hand-curated so
# the order can be opinionated).
def _pct(num: str, den_series: list[str], den_fn) -> callable:
    """Build a percent-of-denominator formula. `den_fn` takes the
    values dict and returns the denominator (so callers can express
    'population - population_under_18' inline)."""
    def f(v: dict[str, float]) -> float | None:
        d = den_fn(v)
        if d is None or d <= 0:
            return None
        return 100.0 * v[num] / d
    return f


def _direct(code: str) -> callable:
    def f(v: dict[str, float]) -> float | None:
        return v.get(code)
    return f


INDICATORS: list[IndicatorSpec] = [
    # ---- Original 4 (do NOT remove or rename — Maps tab default
    # selection lands on poverty_rate; choropleth chart YAMLs and any
    # saved dashboards reference these IDs verbatim).
    IndicatorSpec(
        "poverty_rate",
        ["poverty_count", "population"],
        _pct("poverty_count", [], lambda v: v["population"]),
        "%", 1, "% of population below poverty line",
    ),
    IndicatorSpec(
        "median_hh_income",
        ["median_hh_income"],
        _direct("median_hh_income"),
        "USD", 0, "Median household income (USD)",
    ),
    IndicatorSpec(
        "bachelors_plus_pct",
        ["bachelors_plus", "population", "population_under_18"],
        _pct("bachelors_plus", [], lambda v: v["population"] - v["population_under_18"]),
        "%", 1, "% of adults (18+) with bachelor's degree or higher",
    ),
    IndicatorSpec(
        "foreign_born_pct",
        ["foreign_born", "population"],
        _pct("foreign_born", [], lambda v: v["population"]),
        "%", 1, "% foreign-born",
    ),

    # ---- Education
    IndicatorSpec(
        "masters_plus_pct",
        ["masters_plus", "population", "population_under_18"],
        _pct("masters_plus", [], lambda v: v["population"] - v["population_under_18"]),
        "%", 1, "% of adults (18+) with master's degree or higher",
    ),

    # ---- Housing tenure + access
    IndicatorSpec(
        "owner_occupied_pct",
        ["owner_occupied", "renter_occupied"],
        _pct("owner_occupied", [], lambda v: v["owner_occupied"] + v["renter_occupied"]),
        "%", 1, "% of occupied housing units that are owner-occupied",
    ),
    IndicatorSpec(
        "broadband_households_pct",
        ["broadband_households", "owner_occupied", "renter_occupied"],
        _pct("broadband_households", [], lambda v: v["owner_occupied"] + v["renter_occupied"]),
        "%", 1, "% of households with a broadband internet subscription",
    ),
    IndicatorSpec(
        "median_gross_rent",
        ["median_gross_rent"],
        _direct("median_gross_rent"),
        "USD/mo", 0, "Median gross rent (USD/month)",
    ),
    IndicatorSpec(
        "median_home_value",
        ["median_home_value"],
        _direct("median_home_value"),
        "USD", 0, "Median value, owner-occupied homes (USD)",
    ),

    # ---- Transportation + commuting
    IndicatorSpec(
        "households_no_vehicle_pct",
        ["households_no_vehicle", "households_total_vehicle"],
        _pct("households_no_vehicle", [], lambda v: v["households_total_vehicle"]),
        "%", 1, "% of households with no vehicle available",
    ),
    IndicatorSpec(
        "workers_wfh_pct",
        ["workers_wfh", "workers_total_commute"],
        _pct("workers_wfh", [], lambda v: v["workers_total_commute"]),
        "%", 1, "% of workers who work from home",
    ),
    IndicatorSpec(
        "median_commute_minutes",
        ["median_commute_minutes"],
        _direct("median_commute_minutes"),
        "min", 1, "Median one-way commute (minutes)",
    ),

    # ---- Population shares
    IndicatorSpec(
        "population_65_plus_pct",
        ["population_65_plus", "population"],
        _pct("population_65_plus", [], lambda v: v["population"]),
        "%", 1, "% of population aged 65 and older",
    ),
    IndicatorSpec(
        "population_under_18_pct",
        ["population_under_18", "population"],
        _pct("population_under_18", [], lambda v: v["population"]),
        "%", 1, "% of population under 18",
    ),
    IndicatorSpec(
        "median_age",
        ["median_age"],
        _direct("median_age"),
        "years", 1, "Median age (years)",
    ),

    # ---- Mobility / migration
    IndicatorSpec(
        "movers_last_year_pct",
        ["movers_last_year", "mobility_universe"],
        _pct("movers_last_year", [], lambda v: v["mobility_universe"]),
        "%", 1, "% of population (1+) who moved in the past year",
    ),
    IndicatorSpec(
        "born_same_state_pct",
        ["born_same_state", "population"],
        _pct("born_same_state", [], lambda v: v["population"]),
        "%", 1, "% of population born in current state of residence",
    ),

    # ---- Social
    IndicatorSpec(
        "people_with_disability_pct",
        ["people_with_disability", "people_disability_universe"],
        _pct("people_with_disability", [], lambda v: v["people_disability_universe"]),
        "%", 1, "% of population with a disability",
    ),
    IndicatorSpec(
        "veterans_pct",
        ["veterans", "population", "population_under_18"],
        _pct("veterans", [], lambda v: v["population"] - v["population_under_18"]),
        "%", 1, "% of adults (18+) who are civilian veterans",
    ),

    # ---- Scale (raw count). Useful as a base layer + log-scale toggle
    # already lives in the Maps tab; the choropleth will look more like
    # a population heatmap than an actionable indicator, but it's a
    # natural anchor to compare against.
    IndicatorSpec(
        "population",
        ["population"],
        _direct("population"),
        "count", 0, "Total population (people)",
    ),
]


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
                v = load_value_at(code, st, year)
                if v is None:
                    ok = False
                    break
                bundle[code] = v
            if ok:
                return bundle, year
        return None, None

    written = 0
    skipped: dict[str, list[str]] = {}  # ind -> list of vintages that produced empty
    for spec in INDICATORS:
        for vintage in VINTAGES:
            vals: dict[str, float] = {}
            fallbacks: dict[str, str] = {}
            for st, fips in STATE_FIPS.items():
                b, actual = resolve(st, vintage, spec.series)
                if not b or actual is None:
                    continue
                try:
                    out = spec.formula(b)
                except (KeyError, ZeroDivisionError, TypeError):
                    out = None
                if out is None:
                    continue
                vals[fips] = float(out)
                if actual != vintage:
                    fallbacks[fips] = actual
            if vals:
                write_snapshot(
                    spec.out_id, vintage, vals, fallbacks,
                    spec.unit, spec.decimals, spec.value_label,
                )
                written += 1
            else:
                skipped.setdefault(spec.out_id, []).append(vintage)

    print(f"Wrote {written} snapshot file(s) under public/data/acs_state/.")
    if skipped:
        # Surface skipped (indicator, vintage) pairs — usually means the
        # underlying ACS series wasn't published that year (e.g. broadband
        # subscription data started ~2013). Not an error.
        for ind, vs in sorted(skipped.items()):
            print(f"  no data: {ind} for vintages {','.join(vs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(derive_all())
