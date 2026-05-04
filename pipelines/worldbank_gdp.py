"""
Fetch World Bank real GDP (constant 2015 USD, indicator NY.GDP.MKTP.KD) for the
countries on the World dashboard plus the world aggregate, then produce a
"country share of world real GDP" annual timeseries per country.

Run with: ``python pipelines/worldbank_gdp.py``.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from common import write_timeseries, DATA_ROOT


WB_URL = (
    "https://api.worldbank.org/v2/country/{code}/indicator/NY.GDP.MKTP.KD"
    "?format=json&per_page=200"
)


@dataclass
class CountrySpec:
    iso3: str  # World Bank country code
    label: str  # human-readable
    series_id: str  # matches the corresponding countries_relative id (e.g., "EWJ")


COUNTRIES: list[CountrySpec] = [
    CountrySpec("USA", "United States", "USA"),
    CountrySpec("JPN", "Japan", "EWJ"),
    CountrySpec("DEU", "Germany", "EWG"),
    CountrySpec("GBR", "United Kingdom", "EWU"),
    CountrySpec("BRA", "Brazil", "EWZ"),
    CountrySpec("CHN", "China", "FXI"),
    CountrySpec("IND", "India", "INDA"),
    CountrySpec("CAN", "Canada", "EWC"),
    CountrySpec("AUS", "Australia", "EWA"),
    CountrySpec("MEX", "Mexico", "EWW"),
    CountrySpec("KOR", "South Korea", "EWY"),
]
WORLD_CODE = "WLD"


def fetch_wb_series(code: str) -> dict[str, float]:
    """Return {year_iso: real_gdp_constant_2015_usd}."""
    url = WB_URL.format(code=code)
    result = subprocess.run(
        ["curl", "-sS", "--max-time", "60", url],
        capture_output=True,
        check=True,
        text=True,
    )
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Non-JSON response for {code}: {e}") from e
    if not isinstance(raw, list) or len(raw) < 2 or raw[1] is None:
        return {}
    out: dict[str, float] = {}
    for row in raw[1]:
        year = row.get("date")
        v = row.get("value")
        if year and v is not None:
            try:
                out[str(year)] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def main() -> int:
    print(f"Fetching World aggregate ({WORLD_CODE})...", flush=True)
    world = fetch_wb_series(WORLD_CODE)
    if not world:
        print("  (no data from WLD)", file=sys.stderr)
        return 2
    print(f"  {len(world)} years")

    for spec in COUNTRIES:
        print(f"Fetching {spec.iso3} ({spec.label})...", flush=True)
        country = fetch_wb_series(spec.iso3)
        if not country:
            print("  (no data)")
            continue

        # Compute share as percent for each year present in both series.
        years = sorted(set(country) & set(world))
        points = []
        for y in years:
            w = world[y]
            c = country[y]
            if w <= 0:
                continue
            pct = (c / w) * 100.0
            points.append({"t": f"{y}-12-31", "v": pct})

        # Forward-fill the latest observation to today so the plot reaches the
        # right edge of the window and delta computations have a "current" anchor.
        # Annual WB data lags by ~1 year; the flat extension is flagged in the
        # source description.
        if points:
            today = datetime.now(timezone.utc).date().isoformat()
            if points[-1]["t"] < today:
                points.append({"t": today, "v": points[-1]["v"]})

        out = write_timeseries(
            pipeline="worldbank_gdp",
            series_id=spec.series_id,
            name=f"{spec.label} real GDP share of world",
            points=points,
            unit="%",
        )
        if points:
            first = points[0]
            last = points[-1]
            print(
                f"  {len(points)} years, {first['v']:.2f}% ({first['t'][:4]}) -> {last['v']:.2f}% ({last['t'][:4]})"
            )
        print(f"  [{out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
