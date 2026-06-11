"""
OECD cross-country comparison pipeline.

Fetches harmonized unemployment rates for G7 countries from OECD's SDMX
REST API. OECD's edge over FRED + World Bank: the same methodology is
applied across countries, so cross-country comparisons aren't mixing
apples and oranges from different national statistics offices.

Endpoint pattern (OECD's new Data Explorer / SDMX REST):
    https://sdmx.oecd.org/public/rest/data/<dataflow>/<key>?format=csvfilewithlabels

The `<key>` is dot-separated dimension values in dataset-defined order.
Empty slots are wildcards. For DF_IALFS_UNE_M (monthly unemployment),
dimensions are: REF_AREA, FREQ, MEASURE, UNIT_MEASURE, TRANSFORMATION,
ADJUSTMENT, SEX, AGE, ACTIVITY.

We fetch with mostly-wildcard keys (country list + all-else-blank) then
filter in Python for the headline series (seasonally-adjusted, 15+,
both sexes, total). Keeps us robust to OECD tweaking the exact slot
encoding without breaking us.

Run with: ``python pipelines/oecd.py``.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from dataclasses import dataclass
from io import StringIO

from common import write_timeseries


OECD_BASE = "https://sdmx.oecd.org/public/rest/data"

# Order matters here — we use the dict keys as both display names and
# the YAML source IDs. Stick to ISO-3 codes that OECD recognizes.
G7_COUNTRIES = {
    "USA": "United States",
    "CAN": "Canada",
    "GBR": "United Kingdom",
    "FRA": "France",
    "DEU": "Germany",
    "ITA": "Italy",
    "JPN": "Japan",
}

# All current OECD members (as of late 2025). For G7-tagged specs we use
# G7_COUNTRIES above; for broader specs (gov finance, etc.) we use this.
OECD_MEMBERS = {
    "AUS": "Australia",
    "AUT": "Austria",
    "BEL": "Belgium",
    "CAN": "Canada",
    "CHL": "Chile",
    "COL": "Colombia",
    "CRI": "Costa Rica",
    "CZE": "Czech Republic",
    "DNK": "Denmark",
    "EST": "Estonia",
    "FIN": "Finland",
    "FRA": "France",
    "DEU": "Germany",
    "GRC": "Greece",
    "HUN": "Hungary",
    "ISL": "Iceland",
    "IRL": "Ireland",
    "ISR": "Israel",
    "ITA": "Italy",
    "JPN": "Japan",
    "KOR": "South Korea",
    "LVA": "Latvia",
    "LTU": "Lithuania",
    "LUX": "Luxembourg",
    "MEX": "Mexico",
    "NLD": "Netherlands",
    "NZL": "New Zealand",
    "NOR": "Norway",
    "POL": "Poland",
    "PRT": "Portugal",
    "SVK": "Slovak Republic",
    "SVN": "Slovenia",
    "ESP": "Spain",
    "SWE": "Sweden",
    "CHE": "Switzerland",
    "TUR": "Türkiye",
    "GBR": "United Kingdom",
    "USA": "United States",
}


@dataclass
class OECDSpec:
    """One indicator to fetch across a set of countries."""

    pipeline_id: str  # `unemployment_rate` -> file `<country>_<id>.json`
    dataflow: str  # SDMX dataflow ID
    name_prefix: str  # used in the YAML manifest's `name` field
    unit: str
    # Number of dimensions in the dataflow key (sans the country dimension).
    # Used to build the wildcard key as "<country>" + "." * trailing_dots.
    trailing_dots: int
    # Filter function: given a CSV row dict, return True iff this row is
    # the headline series we want. OECD returns many decompositions
    # (by sex, age, seasonal adjustment) and we just want the one
    # comparable across countries.
    filter_fn: callable  # noqa: A003
    # Which country set to fetch. Defaults to G7 for the original cross-
    # country comparison charts. Broader gov-finance specs use OECD_MEMBERS.
    countries: dict[str, str] = None  # type: ignore[assignment]
    # Optional: server-side key suffix to pre-filter dimensions. When the
    # raw "wildcard all dimensions" key returns megabytes of data (e.g.
    # SHA health expenditure with every financing-scheme × function combo),
    # narrowing the key with explicit values reduces the response to ~1%
    # of its size. Each empty position remains a wildcard.
    key_suffix: str | None = None


def _drop_quarterly(row: dict) -> bool:
    """OECD monthly endpoints return quarterly aggregates too; drop them."""
    tp = row.get("TIME_PERIOD", "")
    return not (tp.endswith(("Q1", "Q2", "Q3", "Q4")))


def _headline_unemployment(row: dict) -> bool:
    """
    Headline harmonized unemployment: seasonally-adjusted, both sexes,
    15 and over, all activities, monthly.
    """
    return (
        row.get("ADJUSTMENT") == "Y"
        and row.get("SEX") == "_T"
        and row.get("AGE") == "Y_GE15"
        and row.get("ACTIVITY") == "_Z"
        and _drop_quarterly(row)
    )


def _gov_debt_pct_gdp(row: dict) -> bool:
    """OECD EO general government gross financial liabilities, % of GDP."""
    return row.get("MEASURE") == "GGFLQ" and not row.get("TIME_PERIOD", "").endswith(
        ("Q1", "Q2", "Q3", "Q4")
    )


def _gov_deficit_pct_gdp(row: dict) -> bool:
    """OECD EO general government net lending, % of GDP. Negative = deficit."""
    return row.get("MEASURE") == "NLGQ" and not row.get("TIME_PERIOD", "").endswith(
        ("Q1", "Q2", "Q3", "Q4")
    )


def _life_expectancy_at_birth(row: dict) -> bool:
    """OECD Health Stats: life expectancy at age 0, both sexes, total."""
    return (
        row.get("MEASURE") == "LFEXP"
        and row.get("AGE") == "Y0"
        and row.get("SEX") == "_T"
    )


def _health_spending_pct_gdp(row: dict) -> bool:
    """
    OECD SHA: total current expenditure on health as % of GDP. All-totals
    across financing scheme, function, mode, provider (the maximally
    aggregated headline figure).
    """
    return (
        row.get("MEASURE") == "EXP_HEALTH"
        and row.get("UNIT_MEASURE") == "PT_B1GQ"
        and row.get("FINANCING_SCHEME") == "_T"
        and row.get("FUNCTION") == "_T"
        and row.get("MODE_PROVISION") == "_T"
        and row.get("PROVIDER") == "_T"
    )


def _headline_cpi(row: dict) -> bool:
    """
    Headline CPI year-over-year inflation: national methodology, total
    basket, not seasonally adjusted, monthly. The "GY" transformation
    code is "growth rate over 1 year" — the percentage point comparison
    everyone reports as "the inflation rate."
    """
    return (
        row.get("METHODOLOGY") == "N"
        and row.get("MEASURE") == "CPI"
        and row.get("EXPENDITURE") == "_T"
        and row.get("ADJUSTMENT") == "N"
        and row.get("TRANSFORMATION") == "GY"
        and _drop_quarterly(row)
    )


SPECS: list[OECDSpec] = [
    OECDSpec(
        pipeline_id="unemployment_rate",
        dataflow="OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0",
        name_prefix="Unemployment rate",
        unit="%",
        trailing_dots=8,
        filter_fn=_headline_unemployment,
        countries=G7_COUNTRIES,
    ),
    OECDSpec(
        pipeline_id="cpi_yoy",
        dataflow="OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
        name_prefix="CPI inflation (YoY)",
        unit="%",
        trailing_dots=7,
        filter_fn=_headline_cpi,
        countries=G7_COUNTRIES,
    ),
    OECDSpec(
        pipeline_id="gov_debt_pct_gdp",
        dataflow="OECD.ECO.MAD,DSD_EO@DF_EO,1.0",
        name_prefix="Government gross debt, % of GDP",
        unit="% of GDP",
        trailing_dots=3,
        filter_fn=_gov_debt_pct_gdp,
        countries=OECD_MEMBERS,
    ),
    OECDSpec(
        pipeline_id="gov_deficit_pct_gdp",
        dataflow="OECD.ECO.MAD,DSD_EO@DF_EO,1.0",
        name_prefix="Government net lending, % of GDP",
        unit="% of GDP",
        trailing_dots=3,
        filter_fn=_gov_deficit_pct_gdp,
        countries=OECD_MEMBERS,
    ),
    OECDSpec(
        pipeline_id="life_expectancy",
        dataflow="OECD.ELS.HD,DSD_HEALTH_STAT@DF_LE,1.0",
        name_prefix="Life expectancy at birth",
        unit="years",
        trailing_dots=12,
        filter_fn=_life_expectancy_at_birth,
        countries=OECD_MEMBERS,
    ),
    OECDSpec(
        pipeline_id="health_spending_pct_gdp",
        dataflow="OECD.ELS.HD,DSD_SHA@DF_SHA,1.0",
        name_prefix="Health expenditure, % of GDP",
        unit="% of GDP",
        trailing_dots=11,
        filter_fn=_health_spending_pct_gdp,
        countries=OECD_MEMBERS,
        # Server-side narrowing. Dimensions in DF_SHA order (after REF_AREA):
        # FREQ.MEASURE.UNIT.FIN_SCHEME.FIN_SCHEME_REV.FUNCTION.MODE.PROVIDER.
        # FACTOR.ASSET_TYPE.PRICE_BASE. We pin MEASURE/UNIT/the four totals;
        # everything else wildcards. Without this, the wildcarded response
        # is megabytes per country and times out.
        key_suffix="." + ".".join([
            "A",          # FREQ: annual
            "EXP_HEALTH", # MEASURE: total expenditure
            "PT_B1GQ",    # UNIT: % of GDP
            "_T",         # FINANCING_SCHEME: total
            "",           # FINANCING_SCHEME_REV: wildcard
            "_T",         # FUNCTION: total
            "_T",         # MODE_PROVISION: total
            "_T",         # PROVIDER: total
            "",           # FACTOR_PROVISION: wildcard
            "",           # ASSET_TYPE: wildcard
            "",           # PRICE_BASE: wildcard
        ]),
    ),
]


def fetch_indicator(spec: OECDSpec) -> dict[str, list[dict]]:
    """
    Fetch one indicator across all countries in spec.countries in a single
    request. Returns {iso_code: [{t, v}, ...]} keyed by country.

    Batching all countries into one call instead of one-at-a-time matters:
    OECD's public API rate-limits per-IP and 38 countries × 2-4 indicators
    of one-at-a-time calls saturates it. The "+"-separated key syntax
    pulls every country's data in a single request.
    """
    countries = spec.countries if spec.countries else G7_COUNTRIES
    country_key = "+".join(countries.keys())
    if spec.key_suffix is not None:
        # Caller specified an explicit key — use it verbatim. Drops the
        # response size when wildcarding would return way too much.
        key = country_key + spec.key_suffix
    else:
        key = country_key + "." * spec.trailing_dots
    url = (
        f"{OECD_BASE}/{spec.dataflow}/{key}"
        f"?format=csvfilewithlabels&dimensionAtObservation=AllDimensions"
    )
    print(
        f"  fetching {spec.pipeline_id} for {len(countries)} countries...",
        flush=True,
    )
    try:
        result = subprocess.run(
            ["curl", "-s", "-S", "--max-time", "300", url],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    curl failed: {e}", file=sys.stderr)
        return {}
    body = result.stdout
    if body.strip().startswith("NoResultsFound") or "<?xml" in body[:200]:
        print(f"    no data returned", file=sys.stderr)
        return {}
    if body.startswith("You have exceeded"):
        print(
            "    OECD API rate-limited us. Wait an hour and re-run, or "
            "request a higher quota.",
            file=sys.stderr,
        )
        return {}

    reader = csv.DictReader(StringIO(body))
    by_country: dict[str, list[dict]] = {}
    for r in reader:
        if not spec.filter_fn(r):
            continue
        iso = r.get("REF_AREA", "")
        if iso not in countries:
            continue
        t = r.get("TIME_PERIOD", "")
        v = r.get("OBS_VALUE", "")
        if not t or not v:
            continue
        try:
            v_f = float(v)
        except ValueError:
            continue
        # Normalize to ISO dates so every point sorts/parses uniformly
        # and aligns with other providers on a combined chart:
        #   "YYYY-MM" -> first of month
        #   "YYYY"    -> Jan 1 (matches FRED's annual convention, the
        #                app's dominant provider; also what JS
        #                Date.parse("YYYY") already yields, so no point
        #                moves — it just makes the date explicit).
        if len(t) == 7 and t[4] == "-":
            t = t + "-01"
        elif len(t) == 4 and t.isdigit():
            t = t + "-01-01"
        by_country.setdefault(iso, []).append({"t": t, "v": v_f})
    for pts in by_country.values():
        pts.sort(key=lambda p: p["t"])
    return by_country


def main() -> int:
    print("OECD pipeline: fetching indicators...", flush=True)
    total_written = 0
    for spec in SPECS:
        countries = spec.countries if spec.countries else G7_COUNTRIES
        by_country = fetch_indicator(spec)
        for iso, label in countries.items():
            points = by_country.get(iso, [])
            if not points:
                continue
            series_id = f"{iso.lower()}_{spec.pipeline_id}"
            write_timeseries(
                pipeline="oecd",
                series_id=series_id,
                name=f"{spec.name_prefix} — {label}",
                points=points,
                unit=spec.unit,
            )
            print(f"    {series_id}: {len(points)} points", flush=True)
            total_written += 1
    print(f"OECD pipeline: wrote {total_written} series", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
