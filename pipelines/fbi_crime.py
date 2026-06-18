"""
FBI Crime Data Explorer (CDE) pipeline — state + national crime rates.

Source: the FBI CDE "summarized" API (the backend the public CDE site
itself calls), keyless:
  https://cde.ucr.cjis.gov/LATEST/summarized/{geo}/{offense}
    ?from=MM-YYYY&to=MM-YYYY&type=counts
Public domain (FBI UCR/NIBRS). The legacy `/estimates/` path was retired;
the live CDE frontend uses `/summarized/`. The official api.data.gov
proxy (api.usa.gov/crime/fbi/cde/...) mirrors these paths and accepts
DATAGOV_API_KEY, BUT it returns 503 intermittently and is too flaky for a
reliable refresh — so we hit the CDE backend directly (no key needed;
low request volume, polite delay). DATAGOV_API_KEY stays in .env for
other api.data.gov sources.

What we emit: annual VIOLENT-crime and PROPERTY-crime RATE per 100,000
population, per state (+ DC + national). The API returns monthly offense
COUNTS (`offenses.actuals`) and annual `populations.population`; we sum
the 12 monthly counts for each COMPLETE year and divide by that year's
population × 100,000. Rate (not raw count) is the cross-state-comparable
metric.

New-data-source checklist notes:
  - Authoritative label: CDE offense groups (V = Violent, P = Property)
    from /lookup/offenses. Names constructed from (offense + geo);
    correct-by-construction. Preflight: only complete years (12 monthly
    values) are emitted, so partial/lagging current years don't ship as
    understated points; a geo/offense returning nothing is skipped.
  - Identifier: fbi_crime/<offense_slug>_<geo_slug>;
    provenance.series = "summarized/<geo>/<V|P> / rate per 100k".
  - Units: rate per 100,000 — a derived intensity, stored raw.

SECURITY: the proxy URL embeds the key — never log the URL/response, ids
and counts only. Retries on 429/503 (api.data.gov is occasionally flaky).

Run: python pipelines/fbi_crime.py            (all)
     python pipelines/fbi_crime.py violent texas
"""
from __future__ import annotations

import datetime
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
SOURCES_DIR = HERE.parent / "src" / "content" / "sources" / "fbi_crime"
BASE = "https://cde.ucr.cjis.gov/LATEST/summarized"
# TO runs through the current year; the CDE API returns only published
# months, so a not-yet-released year is harmless (no hardcoded cap to go
# stale — was pinned at 12-2024, which would have blocked 2025 data).
FROM, TO = "01-1985", f"12-{datetime.datetime.now(datetime.timezone.utc).year}"


@dataclass
class Offense:
    code: str       # CDE aggregate offense code
    slug: str
    label: str      # "<label> — <geo>"
    short: str
    desc: str


OFFENSES = [
    # Murder first, on purpose: the homicide rate is the most reliable
    # crime statistic — least distorted by reporting practices and
    # definitional drift that can swamp the other categories.
    Offense("HOM", "murder", "Murder rate", "Murder",
            "Reported murders and nonnegligent manslaughters per 100,000 population per year, from the FBI's Crime Data Explorer. The most reliable crime measure — homicide is consistently reported, so it's the least subject to the reporting artifacts that affect other categories. Multiply by a population series to recover the total count."),
    Offense("V", "violent_crime", "Violent crime rate", "Violent crime",
            "Reported violent-crime offenses (homicide, rape, robbery, aggravated assault) per 100,000 population per year, from the FBI's Crime Data Explorer."),
    Offense("P", "property_crime", "Property crime rate", "Property crime",
            "Reported property-crime offenses (burglary, larceny-theft, motor-vehicle theft, arson) per 100,000 population per year, from the FBI's Crime Data Explorer."),
]

# geo: (display, slug, cde_path_segment). national uses /summarized/national/.
GEOS: list[tuple[str, str, str]] = [
    ("United States", "united_states", "national"),
]
GEOS += [
    (name, slug, f"state/{abbr}") for name, slug, abbr in [
        ("Alabama", "alabama", "AL"), ("Alaska", "alaska", "AK"), ("Arizona", "arizona", "AZ"),
        ("Arkansas", "arkansas", "AR"), ("California", "california", "CA"), ("Colorado", "colorado", "CO"),
        ("Connecticut", "connecticut", "CT"), ("Delaware", "delaware", "DE"), ("District of Columbia", "district_of_columbia", "DC"),
        ("Florida", "florida", "FL"), ("Georgia", "georgia", "GA"), ("Hawaii", "hawaii", "HI"),
        ("Idaho", "idaho", "ID"), ("Illinois", "illinois", "IL"), ("Indiana", "indiana", "IN"),
        ("Iowa", "iowa", "IA"), ("Kansas", "kansas", "KS"), ("Kentucky", "kentucky", "KY"),
        ("Louisiana", "louisiana", "LA"), ("Maine", "maine", "ME"), ("Maryland", "maryland", "MD"),
        ("Massachusetts", "massachusetts", "MA"), ("Michigan", "michigan", "MI"), ("Minnesota", "minnesota", "MN"),
        ("Mississippi", "mississippi", "MS"), ("Missouri", "missouri", "MO"), ("Montana", "montana", "MT"),
        ("Nebraska", "nebraska", "NE"), ("Nevada", "nevada", "NV"), ("New Hampshire", "new_hampshire", "NH"),
        ("New Jersey", "new_jersey", "NJ"), ("New Mexico", "new_mexico", "NM"), ("New York", "new_york", "NY"),
        ("North Carolina", "north_carolina", "NC"), ("North Dakota", "north_dakota", "ND"), ("Ohio", "ohio", "OH"),
        ("Oklahoma", "oklahoma", "OK"), ("Oregon", "oregon", "OR"), ("Pennsylvania", "pennsylvania", "PA"),
        ("Rhode Island", "rhode_island", "RI"), ("South Carolina", "south_carolina", "SC"), ("South Dakota", "south_dakota", "SD"),
        ("Tennessee", "tennessee", "TN"), ("Texas", "texas", "TX"), ("Utah", "utah", "UT"),
        ("Vermont", "vermont", "VT"), ("Virginia", "virginia", "VA"), ("Washington", "washington", "WA"),
        ("West Virginia", "west_virginia", "WV"), ("Wisconsin", "wisconsin", "WI"), ("Wyoming", "wyoming", "WY"),
    ]
]


def _get(url: str) -> dict:
    for attempt in range(5):
        try:
            rq = urllib.request.Request(url, headers={"User-Agent": "tape/1.0"})
            return json.loads(urllib.request.urlopen(rq, timeout=50).read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 4:
                time.sleep(2 + 2 * attempt)
                continue
            raise
    return {}


def annual_rate_points(geo_path: str, code: str) -> list[dict]:
    url = f"{BASE}/{geo_path}/{code}?from={FROM}&to={TO}&type=counts"
    data = _get(url)
    offenses = (data.get("offenses") or {}).get("actuals") or {}
    # the offense-count series is "<GeoName> Offenses" (NOT "<GeoName> Clearances")
    series = None
    geoname = None
    for name, vals in offenses.items():
        if "clearance" not in name.lower():
            series = vals
            geoname = re.sub(r"\s+Offenses$", "", name)
            break
    if not series:
        return []
    # populations.population is nested by geo-name → {MM-YYYY: pop}; pick the
    # matching series, else the sole non-"United States" entry (state case).
    pops = (data.get("populations") or {}).get("population") or {}
    popser = pops.get(geoname)
    if popser is None and pops:
        nonus = [v for k, v in pops.items() if k != "United States"]
        popser = nonus[0] if (geoname != "United States" and nonus) else pops.get("United States")
    popser = popser or {}
    # sum monthly counts per year; keep only complete (12-month) years
    by_year: dict[str, list[float]] = {}
    for mk, v in series.items():
        m = re.match(r"^(\d{2})-(\d{4})$", mk)
        if not m or v is None:
            continue
        by_year.setdefault(m.group(2), []).append(float(v))
    points = []
    for yr, months in sorted(by_year.items()):
        if len(months) < 12:
            continue  # incomplete/partial year — don't ship an understated point
        count = sum(months)
        p = popser.get(f"01-{yr}") or popser.get(yr)
        if not p:
            continue
        try:
            rate = count / float(p) * 100000.0
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        points.append({"t": f"{yr}-01-01", "v": round(rate, 2)})
    return points


def yaml_for(off: Offense, geo: str, slug: str, path: str) -> str:
    data_id = f"{off.slug}_{slug}"
    return "\n".join([
        f'name: "{off.label} — {geo}"',
        f"shortName: {geo} {off.short}",
        f"description: {off.desc} Values for {geo}.",
        "kind: timeseries",
        "pipeline: fbi_crime",
        f"dataFile: data/fbi_crime/{data_id}.json",
        'supportedDeltas: ["10y", "30y", "50y"]',
        'unit: "per 100k"',
        "formatting:",
        "  style: number",
        "  decimals: 1",
        "emphasis: change",
        "provenance:",
        "  provider: FBI (Crime Data Explorer)",
        f"  series: summarized/{path}/{off.code} / rate per 100k",
        "  url: https://cde.ucr.cjis.gov/",
        "  license: Public domain (US government data)",
        "tags:",
        "  - crime",
        "  - us",
        "",
    ]) + "\n"


def main(argv: list[str] | None = None) -> int:
    filters = [a.lower() for a in (argv or [])[1:]]
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for off in OFFENSES:
        for geo, slug, path in GEOS:
            if filters and not any(f in off.slug or f in slug for f in filters):
                continue
            points = annual_rate_points(path, off.code)
            if not points:
                print(f"  skip (no complete-year data): {off.slug}_{slug}")
                skipped += 1
                continue
            write_timeseries(
                pipeline="fbi_crime",
                series_id=f"{off.slug}_{slug}",
                name=f"{off.label} — {geo}",
                points=points,
                unit="per 100k",
            )
            (SOURCES_DIR / f"{off.slug}_{slug}.yaml").write_text(
                yaml_for(off, geo, slug, path), encoding="utf-8"
            )
            written += 1
            time.sleep(0.2)
        print(f"fbi_crime: {off.slug} done")
    print(f"fbi_crime: wrote {written} series, skipped {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
