"""
BEA (Bureau of Economic Analysis) Regional accounts pipeline.

Source: https://apps.bea.gov/api/data  (Regional dataset). Requires
BEA_API_KEY in .env. Public domain (US government data).

Why this exists: BEA's regional GDP + personal income by STATE (and
per-capita income, which BEA computes directly) are the headline
sub-national economic series. They are not carried in our FRED set at
this breadth, and BEA is the authoritative publisher.

New-data-source checklist notes (docs/new-data-source-checklist.md):
  - Authoritative label: BEA's own Regional table concepts (SAGDP2 =
    "GDP by state", SAINC1 = "personal income summary"). Names are
    constructed here from (table concept + GeoName); correct-by-
    construction with a preflight on BEAAPI.Error + a UNIT_MULT sanity
    check (the cdc_health / owid_co2 pattern). No separate label-audit
    endpoint exists.
  - Identifier convention: bea/<indicator_slug>_<state_slug>;
    provenance.series = "<TableName> line <LineCode> / <GeoFips>".
  - Canonical units: BEA returns currency in millions/thousands of $
    (UNIT_MULT = power of 10). We convert aggregates to canonical
    BILLIONS via value * 10**UNIT_MULT / 1e9. Per-capita income is a
    dollar level, stored raw.

SECURITY: the fetch URL embeds the API key, and BEA echoes UserID in its
response. NEVER print the URL or the raw response — log only series ids
and counts. No shared cache (would persist key-bearing URLs to disk).

Run: python pipelines/bea.py            (all)
     python pipelines/bea.py gdp texas   (filter by indicator/state slug substrings)
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from common import write_timeseries

HERE = Path(__file__).resolve().parent
SOURCES_DIR = HERE.parent / "src" / "content" / "sources" / "bea"
API = "https://apps.bea.gov/api/data"


def _load_key() -> str:
    env = HERE.parent / ".env"
    if env.exists():
        m = re.search(r"^BEA_API_KEY=(.*)$", env.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit("BEA_API_KEY not found in .env")


@dataclass
class Indicator:
    table: str          # BEA Regional TableName
    line: str           # LineCode
    slug: str           # indicator slug fragment
    label: str          # human label ("<label> — <state>")
    short: str
    unit: str
    style: str          # currency | number | ...
    decimals: int
    unit_class: str | None
    to_billions: bool   # True: aggregate $ → canonical billions; False: store raw (per-capita)
    suffix: str | None
    desc: str


INDICATORS: list[Indicator] = [
    Indicator("SAGDP2", "1", "gdp", "GDP (nominal)", "GDP",
              "billions USD", "currency", 1, "currency", True, "B",
              "Gross domestic product by state in current dollars, annual, all-industry total (BEA Regional table SAGDP2)."),
    Indicator("SAGDP9", "1", "real_gdp", "Real GDP (chained 2017 $)", "Real GDP",
              "billions USD", "currency", 1, "currency", True, "B",
              "Inflation-adjusted gross domestic product by state, chained 2017 dollars, annual, all-industry total (BEA Regional table SAGDP9)."),
    Indicator("SAINC1", "1", "personal_income", "Personal income", "Personal income",
              "billions USD", "currency", 1, "currency", True, "B",
              "Total personal income by state, annual (BEA Regional table SAINC1)."),
    Indicator("SAINC1", "3", "pc_personal_income", "Per-capita personal income", "Per-capita income",
              "USD", "currency", 0, "currency", False, None,
              "Personal income per resident by state, annual (BEA Regional table SAINC1, per-capita line)."),
]

# GeoNames we keep (50 states + DC + US). BEA's GeoFIPS=STATE response also
# includes 8 BEA regions (New England, Mideast, …) which we drop for the
# first cut. slug = lowercased GeoName with spaces → underscores.
US_NAME = "United States"
STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "District of Columbia", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
    "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
    "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
}
KEEP = STATES | {US_NAME}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def fetch(table: str, line: str, key: str) -> list[dict]:
    params = {
        "UserID": key, "method": "GetData", "datasetname": "Regional",
        "TableName": table, "LineCode": line, "GeoFIPS": "STATE",
        "Year": "ALL", "ResultFormat": "JSON",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    rq = urllib.request.Request(url, headers={"User-Agent": "tape/1.0"})
    data = json.loads(urllib.request.urlopen(rq, timeout=60).read())
    api = data.get("BEAAPI", {})
    err = api.get("Error") or api.get("Results", {}).get("Error") if isinstance(api.get("Results"), dict) else api.get("Error")
    if err:
        # NB: never include url/response (key-bearing). Surface the message only.
        raise SystemExit(f"BEA error for {table} line {line}: {err}")
    return api.get("Results", {}).get("Data", [])


def supported_deltas() -> list[str]:
    return ["5y", "10y", "30y", "50y"]


def yaml_for(ind: Indicator, geoname: str, slug: str, geofips: str) -> str:
    data_id = f"{ind.slug}_{slug}"
    lines = [
        f'name: "{ind.label} — {geoname}"',
        f"shortName: {geoname} {ind.short}",
        f"description: {ind.desc} Values for {geoname}.",
        "kind: timeseries",
        "pipeline: bea",
        f"dataFile: data/bea/{data_id}.json",
        'supportedDeltas: ["5y", "10y", "30y", "50y"]',
        f'unit: "{ind.unit}"',
        "formatting:",
        f"  style: {ind.style}",
        f"  decimals: {ind.decimals}",
    ]
    if ind.suffix:
        lines.append(f'  suffix: "{ind.suffix}"')
    lines += [
        "emphasis: change",
        "provenance:",
        "  provider: BEA (Bureau of Economic Analysis)",
        f"  series: {ind.table} line {ind.line} / {geofips}",
        f"  url: https://apps.bea.gov/regional/",
        "  license: Public domain (US government data)",
        "tags:",
        "  - macro",
        "  - us",
        "  - us-state",
    ]
    if ind.unit_class:
        lines.append(f"unitClass: {ind.unit_class}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    filters = [a.lower() for a in (argv or [])[1:]]
    key = _load_key()
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for ind in INDICATORS:
        rows = fetch(ind.table, ind.line, key)
        if not rows:
            raise SystemExit(f"BEA returned no rows for {ind.table} line {ind.line}")
        # group by GeoName
        by_geo: dict[str, list[dict]] = {}
        fips_of: dict[str, str] = {}
        for r in rows:
            g = r.get("GeoName", "")
            if g not in KEEP:
                continue
            by_geo.setdefault(g, []).append(r)
            fips_of[g] = r.get("GeoFips", "")
        for geoname, grows in by_geo.items():
            slug = slugify(geoname)
            if filters and not any(f in ind.slug or f in slug for f in filters):
                continue
            points = []
            for r in grows:
                yr = r.get("TimePeriod", "")
                raw = (r.get("DataValue") or "").replace(",", "")
                mult = r.get("UNIT_MULT", "0")
                if not yr or not re.fullmatch(r"-?\d+(\.\d+)?", raw):
                    continue  # skip (NA)/(D) disclosure-suppressed
                try:
                    dollars = float(raw) * (10 ** int(mult))
                except (TypeError, ValueError):
                    continue
                v = dollars / 1e9 if ind.to_billions else dollars
                points.append({"t": f"{yr}-01-01", "v": v})
            if not points:
                continue
            write_timeseries(
                pipeline="bea",
                series_id=f"{ind.slug}_{slug}",
                name=f"{ind.label} — {geoname}",
                points=points,
                unit=ind.unit,
            )
            (SOURCES_DIR / f"{ind.slug}_{slug}.yaml").write_text(
                yaml_for(ind, geoname, slug, fips_of[geoname]), encoding="utf-8"
            )
            written += 1
        print(f"bea: {ind.table} line {ind.line} -> {ind.slug} done")
    print(f"bea: wrote {written} series (data + YAML).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
