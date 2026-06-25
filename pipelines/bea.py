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

Run: python pipelines/bea.py            (state indicators)
     python pipelines/bea.py gdp texas   (filter by indicator/state slug substrings)
     python pipelines/bea.py county      (county per-capita-income choropleth)
     python pipelines/bea.py metro       (metro personal income, summed from counties)

Cadence: BEA Regional income is ANNUAL (~Nov release). All three passes
(state / metro / county) run monthly in refresh-demographics.yml; needs the
BEA_API_KEY repo secret (read from the env, with a .env fallback for local runs).
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from common import strip_footnote_marker, write_timeseries

HERE = Path(__file__).resolve().parent
SOURCES_DIR = HERE.parent / "src" / "content" / "sources" / "bea"
CROSSWALK_DIR = HERE / "_crosswalks"
API = "https://apps.bea.gov/api/data"


def _load_key() -> str:
    # Prefer the environment (CI secret) so the monthly refresh works without a
    # .env file; fall back to .env for local runs.
    key = os.environ.get("BEA_API_KEY", "").strip()
    if key:
        return key
    env = HERE.parent / ".env"
    if env.exists():
        m = re.search(r"^BEA_API_KEY=(.*)$", env.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit("BEA_API_KEY not found in env or .env")


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
    to_billions: bool   # True: aggregate $ → canonical billions; False: store raw (per-capita / counts)
    suffix: str | None
    desc: str
    notation: str | None = None  # e.g. "compact" so 25.6M jobs reads cleanly


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
    # Employment by place of work, BEA's broadest jobs count: it adds the
    # self-employed (proprietors) and farm to the establishment-survey
    # payroll concept, so total runs well above the BLS CES payroll count.
    # (SAEMP25N, the old by-industry employment table, was retired from
    # BEA's Regional API; SAINC4's major-component lines are the live
    # source for total / wage-salary / proprietors employment.) Counts are
    # raw jobs (UNIT_MULT 0), so to_billions=False.
    Indicator("SAINC4", "7010", "total_employment", "Total employment", "total employment",
              "jobs", "number", 0, "count", False, None,
              "Total employment by place of work (wage-and-salary jobs plus proprietors, all industries including farm) by state, annual (BEA Regional table SAINC4, line 7010).",
              notation="compact"),
    Indicator("SAINC4", "7020", "wage_salary_employment", "Wage and salary employment", "wage/salary jobs",
              "jobs", "number", 0, "count", False, None,
              "Wage-and-salary employment by place of work, by state, annual (BEA Regional table SAINC4, line 7020).",
              notation="compact"),
    Indicator("SAINC4", "7040", "proprietors_employment", "Proprietors employment", "proprietor jobs",
              "jobs", "number", 0, "count", False, None,
              "Proprietors (self-employed) employment by place of work, by state, annual (BEA Regional table SAINC4, line 7040).",
              notation="compact"),
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


def points_from_rows(ind: Indicator, rows: list[dict]) -> list[dict]:
    """Build the points list for one geo from BEA Data rows: skip
    (NA)/(D) suppressions, convert units, dedupe by year (later row
    wins, mirroring common._merge_points_by_t's restatement rule), and
    ALWAYS return points sorted ascending by t.

    The explicit sort is load-bearing: BEA's API row order is not a
    contract, and common.write_timeseries only sorts when it merges
    with an existing on-disk file. A fresh write (new series, or a
    prior file lost/corrupted — see the refresh-race restore in git
    history) used to pass API row order straight to disk, which is how
    personal_income_virginia shipped as 2014→2025 followed by
    1959→2013 and its tile served a stale 2013 "latest"."""
    by_t: dict[str, dict] = {}
    for r in rows:
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
        if v <= 0:
            # BEA returns 0 for not-yet-published years (SAINC4 employment
            # lags its income lines by a year, so the latest year is a 0
            # placeholder) and for combined-area sentinels. No state-level
            # GDP / income / employment level is genuinely <= 0, so treat
            # these as missing rather than shipping a bogus 0 as "latest".
            continue
        by_t[f"{yr}-01-01"] = {"t": f"{yr}-01-01", "v": v}
    return [by_t[t] for t in sorted(by_t)]


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
    if ind.notation:
        lines.append(f"  notation: {ind.notation}")
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
    ]
    # The US-total row (geofips 00000) is NATIONAL data, not a state — it must
    # NOT carry the us-state geo tag (which would hide it behind the state
    # picker chip AND, since its id slugs the full name `united_states`,
    # parseStateSourceId can't place it, so it'd fall into the unreachable
    # `misc` bucket). Only the actual state rows get us-state.
    if geofips != "00000":
        lines.append("  - us-state")
    if ind.unit_class:
        lines.append(f"unitClass: {ind.unit_class}")
    return "\n".join(lines) + "\n"


def fetch_county_year(line: str, year: str, key: str) -> list[dict]:
    params = {
        "UserID": key, "method": "GetData", "datasetname": "Regional",
        "TableName": "CAINC1", "LineCode": line, "GeoFIPS": "COUNTY",
        "Year": year, "ResultFormat": "JSON",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    data = json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "tape/1.0"}), timeout=90).read())
    api = data.get("BEAAPI", {})
    if api.get("Error"):
        raise SystemExit(f"BEA error CAINC1/county/{year}: {api['Error']}")
    return api.get("Results", {}).get("Data", [])


def county_choropleth(key: str) -> int:
    """Write per-vintage county per-capita-income choropleth data files
    (CAINC1 line 3) to public/data/acs_county/ — the county-geo choropleth
    store the renderer reads (joined to the county topojson by FIPS).
    Not per-county time-series sources: county data on this site is
    choropleth-primary."""
    import datetime
    out_dir = HERE.parent / "public" / "data" / "acs_county"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    written = 0
    for year in [str(y) for y in range(2014, 2024)]:
        rows = fetch_county_year("3", year, key)
        values: dict[str, float] = {}
        for r in rows:
            fips = (r.get("GeoFips") or "").strip()
            raw = (r.get("DataValue") or "").replace(",", "")
            # real counties only: 5-digit FIPS, drop state (XX000) + US (00000)
            if not re.fullmatch(r"\d{5}", fips) or fips.endswith("000"):
                continue
            if not re.fullmatch(r"-?\d+(\.\d+)?", raw):
                continue
            mult = int(r.get("UNIT_MULT") or 0)  # per-capita income → 0 (raw $)
            v = round(float(raw) * (10 ** mult))
            if v <= 0:  # BEA reports combined-area placeholders as 0/NA — drop
                continue
            values[fips] = v
        if not values:
            continue
        payload = {
            "geo": "county", "indicator": "bea_per_capita_income", "vintage": year,
            "unit": "$", "decimals": 0,
            "valueLabel": "Per-capita personal income ($)",
            "lastUpdated": stamp, "values": values,
        }
        (out_dir / f"bea_per_capita_income_{year}.json").write_text(
            json.dumps(payload), encoding="utf-8")
        written += 1
        print(f"  bea county choropleth {year}: {len(values)} counties")
    print(f"bea county choropleth: wrote {written} vintages.")
    return 0


# ---- Metro (CBSA) personal income, summed from component counties ----
# BEA discontinued its standalone metropolitan-area income/GDP tables with the
# 2024 release (GeoFIPS=MSA and per-CBSA codes now error 101), so a metro total
# must be summed from CAINC1 COUNTY rows via the county->CBSA crosswalk. We emit
# total personal income (sum) and per-capita income (sum income / sum pop).

def _load_county_to_cbsa() -> dict[str, str]:
    out: dict[str, str] = {}
    with (CROSSWALK_DIR / "county_to_cbsa.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            fips = (row.get("county_fips") or "").strip()
            cbsa = (row.get("cbsa_code") or "").strip()
            if fips and cbsa:
                out[fips] = cbsa
    return out


def _load_cbsa_names() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    with (CROSSWALK_DIR / "cbsa_metro.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("cbsa_code") or "").strip()
            if code:
                out[code] = ((row.get("short_name") or "").strip(),
                             (row.get("name") or "").strip())
    return out


def _metro_display(short_name: str, full_name: str) -> str:
    if "," in full_name:
        tail = full_name.split(",", 1)[1].strip()
        if tail:
            return f"{short_name}, {tail}"
    return short_name


def _metro_yaml(series_slug: str, cbsa: str, display: str, label: str, short: str,
                unit: str, decimals: int, desc: str, line: str) -> str:
    return "\n".join([
        f'name: "{label} — {display}"',
        f'shortName: "{display} {short}"',
        f'description: "{desc}"',
        "kind: timeseries",
        "pipeline: bea",
        f"dataFile: data/bea/{series_slug}_{cbsa}.json",
        'supportedDeltas: ["5y", "10y", "30y", "50y"]',
        f'unit: "{unit}"',
        "formatting:",
        "  style: currency",
        f"  decimals: {decimals}",
        "emphasis: change",
        "provenance:",
        "  provider: BEA (Bureau of Economic Analysis)",
        f'  series: "CAINC1 line {line} / metro {cbsa} (sum of counties)"',
        "  url: https://apps.bea.gov/regional/",
        "  license: Public domain (US government data)",
        "unitClass: currency",
    ]) + "\n"


def _accumulate(rows: list[dict], c2c: dict[str, str],
                target: dict[str, dict[str, float]]) -> None:
    for r in rows:
        cbsa = c2c.get((r.get("GeoFips") or "").strip())
        if not cbsa:
            continue
        raw = (r.get("DataValue") or "").replace(",", "")
        yr = r.get("TimePeriod", "")
        if not yr or not re.fullmatch(r"-?\d+(\.\d+)?", raw):
            continue  # skip (NA)/(D) suppressions
        val = float(raw) * (10 ** int(r.get("UNIT_MULT") or 0))
        target.setdefault(cbsa, {}).setdefault(yr, 0.0)
        target[cbsa][yr] += val


def metro_income(key: str) -> int:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    c2c = _load_county_to_cbsa()
    names = _load_cbsa_names()
    income: dict[str, dict[str, float]] = {}   # cbsa -> year -> $ (dollars)
    pop: dict[str, dict[str, float]] = {}       # cbsa -> year -> persons
    _accumulate(fetch_county_year("1", "ALL", key), c2c, income)  # personal income
    _accumulate(fetch_county_year("2", "ALL", key), c2c, pop)     # population
    written = 0
    for cbsa, (short_name, full_name) in names.items():
        inc_y = income.get(cbsa, {})
        pop_y = pop.get(cbsa, {})
        if not inc_y:
            continue
        display = _metro_display(short_name, full_name)
        pi = [{"t": f"{y}-01-01", "v": inc_y[y] / 1e9}
              for y in sorted(inc_y) if inc_y[y] > 0]
        if len(pi) >= 2:
            write_timeseries(pipeline="bea", series_id=f"personal_income_{cbsa}",
                             name=f"Personal income — {display}", points=pi,
                             unit="billions USD")
            (SOURCES_DIR / f"personal_income_{cbsa}.yaml").write_text(
                _metro_yaml("personal_income", cbsa, display, "Personal income",
                            "personal income", "billions USD", 1,
                            f"Total personal income for the {display} metro area "
                            f"(CBSA {cbsa}), summed from BEA component-county data "
                            "(BEA discontinued its standalone metro income tables in "
                            "2024). Annual, BEA Regional table CAINC1.", "1"),
                encoding="utf-8")
            written += 1
        pc = [{"t": f"{y}-01-01", "v": inc_y[y] / pop_y[y]}
              for y in sorted(set(inc_y) & set(pop_y))
              if pop_y.get(y, 0) > 0 and inc_y[y] > 0]
        if len(pc) >= 2:
            write_timeseries(pipeline="bea", series_id=f"pc_personal_income_{cbsa}",
                             name=f"Per-capita personal income — {display}", points=pc,
                             unit="USD")
            (SOURCES_DIR / f"pc_personal_income_{cbsa}.yaml").write_text(
                _metro_yaml("pc_personal_income", cbsa, display,
                            "Per-capita personal income", "per-capita income", "USD", 0,
                            f"Per-capita personal income for the {display} metro area "
                            f"(CBSA {cbsa}): total personal income divided by population, "
                            "both summed from BEA component counties. Annual, CAINC1.",
                            "1/2"),
                encoding="utf-8")
            written += 1
    print(f"bea metro: wrote {written} metro series (data + YAML).")
    return 0


def main(argv: list[str] | None = None) -> int:
    filters = [a.lower() for a in (argv or [])[1:]]
    key = _load_key()
    if filters and filters[0] in ("county", "choropleth"):
        return county_choropleth(key)
    if filters and filters[0] in ("metro", "msa"):
        return metro_income(key)
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
            # BEA footnotes some geos in some tables (e.g. SAINC4 returns
            # "Alaska *" / "Hawaii *"); strip the trailing marker so they
            # match KEEP instead of being silently dropped.
            g = strip_footnote_marker(r.get("GeoName", ""))
            if g not in KEEP:
                continue
            by_geo.setdefault(g, []).append(r)
            fips_of[g] = r.get("GeoFips", "")
        for geoname, grows in by_geo.items():
            slug = slugify(geoname)
            if filters and not any(f in ind.slug or f in slug for f in filters):
                continue
            points = points_from_rows(ind, grows)
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
