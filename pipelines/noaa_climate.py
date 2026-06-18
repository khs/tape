"""
NOAA major-city climate pipeline (annual temperature + precipitation).

Source: NOAA NCEI Climate Data Online (CDO) v2 API, GSOY (Global Summary
of the Year) dataset. Auth: NOAA_API_KEY sent as the `token` HEADER.
Public domain (US government data).

WHY CITY-LEVEL (not state): CDO returns STATION-level observations. A
naive average of the stations in a state does NOT reproduce NOAA's
official area-weighted, homogenized statewide values (nClimDiv) — it
would be subtly wrong. So this pipeline tracks named long-record airport
stations for major metros, where the station IS the series — honest and
methodology-free. (State/division series, if ever wanted, should come
from NCEI nClimDiv / Climate-at-a-Glance, a different product.)

New-data-source checklist notes:
  - Authoritative label: NOAA station identity (GHCND:<id>) + datatype
    (TAVG/PRCP). Names constructed from (datatype concept + city);
    correct-by-construction. Station ids are pinned + were each verified
    to return TAVG before commit. Preflight: a station/datatype that
    returns no rows is skipped (logged), never written empty.
  - Identifier convention: noaa_climate/<indicator>_<city_slug>;
    provenance.series = "<datatype> / GHCND:<station>".
  - Units stored as NOAA "standard": TAVG in °F, PRCP in inches. Physical
    measures — stored raw, no rescale.

Run: python pipelines/noaa_climate.py            (all)
     python pipelines/noaa_climate.py temperature chicago
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from common import write_timeseries

HERE = Path(__file__).resolve().parent
SOURCES_DIR = HERE.parent / "src" / "content" / "sources" / "noaa_climate"
BASE = "https://www.ncei.noaa.gov/cdo-web/api/v2/data"


def _token() -> str:
    m = re.search(r"^NOAA_API_KEY=(.*)$", (HERE.parent / ".env").read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit("NOAA_API_KEY not found in .env")
    return m.group(1).strip().strip('"').strip("'")


@dataclass
class Indicator:
    datatype: str       # CDO datatypeid
    slug: str
    label: str
    short: str
    unit: str
    decimals: int
    desc: str


INDICATORS = [
    Indicator("TAVG", "temperature", "Average temperature", "Avg temp",
              "°F", 1,
              "Annual average temperature in degrees Fahrenheit, from NOAA's Global Summary of the Year."),
    Indicator("PRCP", "precipitation", "Total precipitation", "Precipitation",
              "inches", 1,
              "Annual total precipitation in inches, from NOAA's Global Summary of the Year."),
]

# (city display name, slug, GHCND station id, state abbr). Each station is a
# long-record metro airport, verified to return GSOY TAVG before commit.
CITIES: list[tuple[str, str, str, str]] = [
    ("Washington, DC", "washington_dc", "USW00013743", "DC"),
    ("New York", "new_york", "USW00094728", "NY"),
    ("Chicago", "chicago", "USW00094846", "IL"),
    ("Los Angeles", "los_angeles", "USW00023174", "CA"),
    ("Houston", "houston", "USW00012960", "TX"),
    ("Miami", "miami", "USW00012839", "FL"),
    ("Atlanta", "atlanta", "USW00013874", "GA"),
    ("Boston", "boston", "USW00014739", "MA"),
    ("Seattle", "seattle", "USW00024233", "WA"),
    ("Denver", "denver", "USW00003017", "CO"),
    ("Phoenix", "phoenix", "USW00023183", "AZ"),
    ("Dallas", "dallas", "USW00003927", "TX"),
    ("San Francisco", "san_francisco", "USW00023234", "CA"),
    ("Minneapolis", "minneapolis", "USW00014922", "MN"),
    ("Detroit", "detroit", "USW00094847", "MI"),
    ("Philadelphia", "philadelphia", "USW00013739", "PA"),
    ("San Diego", "san_diego", "USW00023188", "CA"),
    ("New Orleans", "new_orleans", "USW00012916", "LA"),
]

import datetime  # noqa: E402 — kept beside its only use (END_YEAR)

START_YEAR = 1950
# Through the current year. CDO returns only published years, so a
# not-yet-released recent year just yields no points. Was hardcoded 2024,
# which silently dropped 2025 GSOY data once NOAA published it.
END_YEAR = datetime.datetime.now(datetime.timezone.utc).year


def _get(url: str, tok: str) -> dict:
    for attempt in range(4):
        try:
            rq = urllib.request.Request(url, headers={"token": tok, "User-Agent": "tape/1.0"})
            return json.loads(urllib.request.urlopen(rq, timeout=45).read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(2 + attempt)
                continue
            if e.code == 400:
                return {"_range_error": True}
            raise
    return {}


def fetch_series(station: str, datatype: str, tok: str) -> list[dict]:
    """GSOY annual values for one station+datatype. Chunks by decade to
    stay under CDO's per-request date-range cap; paginates within a chunk."""
    points: dict[str, float] = {}
    y = START_YEAR
    while y <= END_YEAR:
        y2 = min(y + 9, END_YEAR)
        offset = 1
        while True:
            url = (
                f"{BASE}?datasetid=GSOY&datatypeid={datatype}"
                f"&stationid=GHCND:{station}&startdate={y}-01-01&enddate={y2}-12-31"
                f"&units=standard&limit=1000&offset={offset}"
            )
            data = _get(url, tok)
            res = data.get("results", [])
            for r in res:
                if r.get("datatype") == datatype and r.get("value") is not None:
                    points[r["date"][:4]] = float(r["value"])
            got = len(res)
            meta = (data.get("metadata") or {}).get("resultset", {})
            total = meta.get("count", got)
            if offset + 1000 > total or got == 0:
                break
            offset += 1000
            time.sleep(0.25)
        y = y2 + 1
        time.sleep(0.25)
    return [{"t": f"{yr}-01-01", "v": v} for yr, v in sorted(points.items())]


def yaml_for(ind: Indicator, city: str, slug: str, station: str, state: str) -> str:
    data_id = f"{ind.slug}_{slug}"
    return "\n".join([
        f'name: "{ind.label} — {city}"',
        f"shortName: {city} {ind.short}",
        f"description: {ind.desc} Recorded at the {city} metro long-record station (GHCND:{station}).",
        "kind: timeseries",
        "pipeline: noaa_climate",
        f"dataFile: data/noaa_climate/{data_id}.json",
        'supportedDeltas: ["10y", "30y", "50y"]',
        f'unit: "{ind.unit}"',
        "formatting:",
        "  style: number",
        f"  decimals: {ind.decimals}",
        "emphasis: change",
        "provenance:",
        "  provider: NOAA (NCEI Climate Data Online)",
        f"  series: {ind.datatype} / GHCND:{station}",
        f"  url: https://www.ncei.noaa.gov/cdo-web/datasets/GSOY/stations/GHCND:{station}/detail",
        "  license: Public domain (US government data)",
        "tags:",
        "  - climate",
        "  - us",
        "",
    ]) + "\n"


def main(argv: list[str] | None = None) -> int:
    filters = [a.lower() for a in (argv or [])[1:]]
    tok = _token()
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for ind in INDICATORS:
        for city, slug, station, state in CITIES:
            if filters and not any(f in ind.slug or f in slug for f in filters):
                continue
            points = fetch_series(station, ind.datatype, tok)
            if not points:
                print(f"  skip (no data): {ind.slug}_{slug}")
                skipped += 1
                continue
            write_timeseries(
                pipeline="noaa_climate",
                series_id=f"{ind.slug}_{slug}",
                name=f"{ind.label} — {city}",
                points=points,
                unit=ind.unit,
            )
            (SOURCES_DIR / f"{ind.slug}_{slug}.yaml").write_text(
                yaml_for(ind, city, slug, station, state), encoding="utf-8"
            )
            written += 1
        print(f"noaa_climate: {ind.slug} done")
    print(f"noaa_climate: wrote {written} series, skipped {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
