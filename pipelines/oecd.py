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


@dataclass
class OECDSpec:
    """One indicator to fetch across all G7 countries."""

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
    ),
    OECDSpec(
        pipeline_id="cpi_yoy",
        dataflow="OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
        name_prefix="CPI inflation (YoY)",
        unit="%",
        trailing_dots=7,
        filter_fn=_headline_cpi,
    ),
]


def fetch_indicator(spec: OECDSpec, country: str) -> list[dict]:
    """
    Fetch one indicator for one country. Returns a list of points sorted
    chronologically.
    """
    # Key: country + N empty wildcards (dimensions are dataflow-specific).
    key = country + "." * spec.trailing_dots
    url = (
        f"{OECD_BASE}/{spec.dataflow}/{key}"
        f"?format=csvfilewithlabels&dimensionAtObservation=AllDimensions"
    )
    print(f"  fetching {country}...", flush=True)
    # OECD's response is small enough (~50KB / country) that curl is fine.
    try:
        result = subprocess.run(
            ["curl", "-s", "-S", "--max-time", "180", url],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    curl failed for {country}: {e}", file=sys.stderr)
        return []
    body = result.stdout
    if body.strip().startswith("NoResultsFound") or "<?xml" in body[:200]:
        print(f"    no data for {country}", file=sys.stderr)
        return []

    reader = csv.DictReader(StringIO(body))
    rows = [r for r in reader if spec.filter_fn(r)]
    points: list[dict] = []
    for r in rows:
        t = r.get("TIME_PERIOD", "")
        v = r.get("OBS_VALUE", "")
        if not t or not v:
            continue
        try:
            v_f = float(v)
        except ValueError:
            continue
        # Normalize "YYYY-MM" to ISO date (first of month).
        if len(t) == 7 and t[4] == "-":
            t = t + "-01"
        points.append({"t": t, "v": v_f})
    points.sort(key=lambda p: p["t"])
    return points


def main() -> int:
    print("OECD pipeline: fetching G7 unemployment rates...", flush=True)
    total_written = 0
    for spec in SPECS:
        for iso, label in G7_COUNTRIES.items():
            points = fetch_indicator(spec, iso)
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
