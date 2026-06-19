"""
BLS Quarterly Census of Employment and Wages (QCEW) — DC-metro jobs + wages.

QCEW is the near-census of jobs covered by unemployment insurance (~95% of
US employment), tabulated from employers' UI filings. Unlike the CES/LAUS
survey programs that bls_metro.py taps, QCEW gives a near-complete COUNT at
fine geography (county / metro), with average wages — the right cut for the
federal-economy story across the DC jurisdictions.

Data access — QCEW Open Data Access:
    https://data.bls.gov/cew/data/api/<YEAR>/<QTR>/area/<AREA>.csv
where QTR is 1-4 or 'a' (annual averages). This endpoint is SEPARATE from
the registered BLS Public Data API (api.bls.gov/publicAPI): it needs NO key
and is NOT subject to the 25-queries/day quota. One CSV per (year, area)
returns every own/industry/aggregation row for that area-year; we read the
"all industries" (industry_code 10, size 0) rows for the ownership sectors
we want.

Codes (verified against live 2024 data):
  * own_code 0 = Total Covered (all ownerships)   -> covered employment + wage
  * own_code 1 = Federal Government               -> federal employment
  * industry_code 10 = "Total, all industries"
  * agglvl differs by geography (county 70/71/72; MSA 40/41/42) so we select
    by (own_code, industry_code, size_code), NOT agglvl.
Fields used: annual_avg_emplvl (jobs), annual_avg_wkly_wage (USD).

Areas: the Washington-Arlington-Alexandria MSA (QCEW area C4790) plus its
core jurisdictions. County area codes are 5-digit FIPS; the MSA code is
"C" + the first four digits of the CBSA code (47900 -> C4790).

Outputs (nested under the existing "bls" provider, qcew_ prefix):
  * public/data/bls/qcew_<metric>_<slug>.json
  * src/content/sources/bls/qcew_<metric>_<slug>.yaml

Cadence: QCEW publishes annual averages once a year (the full year ~9 months
after it closes). Like cms_nhe, this is a manual bump-and-rerun, not a weekly
refresh — re-run when BLS posts a new annual year:
    python pipelines/bls_qcew.py
Optional argv filter: pass area slugs to fetch a subset, e.g.
    python pipelines/bls_qcew.py dc montgomery_md
"""
from __future__ import annotations

import csv
import io
import sys
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from common import write_timeseries

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "bls"
DATA_DIR = REPO_ROOT / "public" / "data" / "bls"

QCEW_URL = "https://data.bls.gov/cew/data/api/{year}/a/area/{area}.csv"
# Pre-2014 history: the Open Data Access "api" CSV slices cover 2014-present
# only (pre-2014 returns HTTP 404). Older years live in the bulk per-year
# "singlefile" annual zips. We backfill those to 2001 — the first NAICS year,
# so the (own_code, industry_code 10, size_code 0) selection is identical to
# the 2014+ data. 1990-2000 is SIC-based with a different industry hierarchy
# (no NAICS "10" total), so it's deliberately out of scope.
SINGLEFILE_URL = (
    "https://data.bls.gov/cew/data/files/{year}/csv/{year}_annual_singlefile.zip"
)
BULK_START = 2001  # first NAICS singlefile year
# Bump the upper bound as BLS posts each new annual year (~September of the
# following year).
YEARS = list(range(BULK_START, 2025))  # 2001..2024 inclusive
BULK_YEARS = frozenset(range(BULK_START, 2014))  # 2001..2013 via singlefile zips
# Immutable historical zips — cache under the shared gitignored pipeline cache
# so manual re-runs don't re-download ~750 MB.
CACHE_DIR = REPO_ROOT / "pipelines" / "_cache" / "qcew"


@dataclass(frozen=True)
class Area:
    area_fips: str  # QCEW area code (county FIPS, or C#### for the MSA)
    slug: str       # out_id slug
    display: str    # chart label (common name)
    short: str      # ticker-style short


@dataclass(frozen=True)
class Metric:
    key: str            # out_id metric segment
    own_code: str       # QCEW ownership code
    field: str          # CSV column to read
    label: str          # appended after the area name in the source name
    short_label: str    # appended after the area short in shortName
    unit: str
    unit_class: str
    style: str          # formatting.style
    decimals: int


AREAS = [
    Area("C4790", "dc_metro", "Washington DC metro area", "DC metro"),
    Area("11001", "dc", "District of Columbia", "DC"),
    Area("24031", "montgomery_md", "Montgomery County, MD", "Montgomery, MD"),
    Area("24033", "prince_georges_md", "Prince George's County, MD", "Prince George's, MD"),
    Area("51059", "fairfax_va", "Fairfax County, VA", "Fairfax, VA"),
    Area("51013", "arlington_va", "Arlington County, VA", "Arlington, VA"),
    Area("51510", "alexandria_va", "Alexandria, VA", "Alexandria, VA"),
    Area("51107", "loudoun_va", "Loudoun County, VA", "Loudoun, VA"),
    Area("51153", "prince_william_va", "Prince William County, VA", "Prince William, VA"),
]

METRICS = [
    Metric("employment", "0", "annual_avg_emplvl", "covered employment",
           "covered jobs", "jobs", "count", "number", 0),
    Metric("avg_weekly_wage", "0", "annual_avg_wkly_wage", "average weekly wage",
           "avg weekly wage", "USD", "currency", "currency", 0),
    Metric("federal_employment", "1", "annual_avg_emplvl", "federal government employment",
           "federal jobs", "jobs", "count", "number", 0),
]


def out_id(metric: Metric, area: Area) -> str:
    return f"qcew_{metric.key}_{area.slug}"


def fetch_area_year(area: str, year: int) -> list[dict[str, str]] | None:
    """Return the parsed CSV rows for one (area, year), or None on a miss
    (404 for a year the area lacks, or a transient error)."""
    url = QCEW_URL.format(year=year, area=area)
    req = urllib.request.Request(
        url, headers={"User-Agent": "tape-data-pipeline (github.com/khs/tape)"}
    )
    try:
        raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — log + skip, don't abort the run
        print(f"  {area} {year}: fetch miss ({type(e).__name__})", file=sys.stderr)
        return None
    return list(csv.DictReader(io.StringIO(raw)))


def _download_singlefile(year: int) -> bytes | None:
    """Fetch one year's QCEW annual singlefile zip, caching the (immutable)
    bytes under pipelines/_cache/qcew so re-runs are free. Returns None on a
    download error (the year is then skipped, not fatal)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{year}_annual_singlefile.zip"
    if cached.exists():
        return cached.read_bytes()
    url = SINGLEFILE_URL.format(year=year)
    req = urllib.request.Request(
        url, headers={"User-Agent": "tape-data-pipeline (github.com/khs/tape)"}
    )
    try:
        raw = urllib.request.urlopen(req, timeout=300).read()
    except Exception as e:  # noqa: BLE001 — log + skip the year, don't abort
        print(f"  singlefile {year}: download miss ({type(e).__name__})", file=sys.stderr)
        return None
    cached.write_bytes(raw)
    return raw


def prefetch_bulk(
    area_fipses: set[str], years: list[int]
) -> dict[tuple[str, int], list[dict[str, str]]]:
    """Download each bulk year's singlefile zip ONCE and pull just the rows our
    areas need (the all-industries totals for the ownership sectors we read),
    keyed by (area_fips, year). One ~40-75 MB zip per year is streamed, not
    held; only the handful of matching rows are retained."""
    out: dict[tuple[str, int], list[dict[str, str]]] = {}
    for year in years:
        raw = _download_singlefile(year)
        if raw is None:
            continue
        kept = 0
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as fh:
                rdr = csv.DictReader(io.TextIOWrapper(fh, "utf-8"))
                for r in rdr:
                    # Match the same slice extract() reads: all-industries
                    # total (industry 10, size 0) for our areas + ownerships.
                    if (
                        r.get("area_fips") in area_fipses
                        and r.get("industry_code") == "10"
                        and r.get("size_code") == "0"
                    ):
                        out.setdefault((r["area_fips"], year), []).append(r)
                        kept += 1
        print(f"  singlefile {year}: kept {kept} rows for {len(area_fipses)} areas",
              flush=True)
        time.sleep(0.05)
    return out


def extract(rows: list[dict[str, str]], metric: Metric) -> float | None:
    """Pull the all-industries value for one ownership sector. Selects by
    (own, industry 10, size 0); agglvl varies by geography so isn't pinned.
    Returns None when the cell is suppressed/absent (value <= 0)."""
    for r in rows:
        if (
            r.get("own_code") == metric.own_code
            and r.get("industry_code") == "10"
            and r.get("size_code") == "0"
        ):
            try:
                v = float(r.get(metric.field, ""))
            except (TypeError, ValueError):
                return None
            return v if v > 0 else None
    return None


def yaml_escape(s: str) -> str:
    if not s:
        return '""'
    if any(ch in s for ch in [":", "#", "&", "*", "!", "|", ">", "%", "@", "'"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def write_source_yaml(metric: Metric, area: Area, first: int, last: int) -> None:
    out = SOURCES_DIR / f"{out_id(metric, area)}.yaml"
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{area.display} — {metric.label}"
    short = f"{area.short} {metric.short_label}"
    place = area.display if area.slug != "dc_metro" else "the Washington DC metro area"
    if metric.key == "employment":
        desc = (
            f"Average annual employment covered by unemployment insurance in "
            f"{place}, across all industries and ownership sectors. From the "
            f"BLS Quarterly Census of Employment and Wages (QCEW), which counts "
            f"about 95 percent of US jobs. Annual averages, {first} to {last}."
        )
        tags = ["labor", "us"]
    elif metric.key == "avg_weekly_wage":
        desc = (
            f"Average weekly wage across all covered employment in {place}, "
            f"total annual wages divided by average employment. From the BLS "
            f"Quarterly Census of Employment and Wages (QCEW). Annual, "
            f"{first} to {last}."
        )
        tags = ["labor", "us"]
    else:  # federal_employment
        desc = (
            f"Federal government employment covered by unemployment insurance "
            f"in {place}, all agencies and industries. From the BLS Quarterly "
            f"Census of Employment and Wages (QCEW). Annual averages, "
            f"{first} to {last}."
        )
        tags = ["labor", "government", "us"]
    lines = [
        f"name: {yaml_escape(name)}",
        f"shortName: {yaml_escape(short)}",
        f"description: {yaml_escape(desc)}",
        "kind: timeseries",
        "pipeline: bls",
        f"dataFile: data/bls/{out_id(metric, area)}.json",
        'supportedDeltas: ["1y", "5y", "10y", "30y"]',
        f'unit: "{metric.unit}"',
        "emphasis: level",
        "formatting:",
        f"  style: {metric.style}",
    ]
    if metric.style == "currency":
        lines.append("  currency: USD")
    lines += [
        f"  decimals: {metric.decimals}",
        "provenance:",
        "  provider: BLS (QCEW)",
        f"  series: {area.area_fips} own={metric.own_code} NAICS 10 (all industries), annual avg",
        "  url: https://www.bls.gov/cew/",
        "  license: Public domain (US government data)",
        f"unitClass: {metric.unit_class}",
        "tags:",
    ]
    lines += [f"  - {t}" for t in tags]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    areas = AREAS
    if argv:
        wanted = set(argv)
        areas = [a for a in AREAS if a.slug in wanted]
        if not areas:
            print(f"No areas match {argv}; valid slugs: "
                  f"{', '.join(a.slug for a in AREAS)}", file=sys.stderr)
            return 1

    # Pre-2014 (NAICS) years come from the bulk singlefile zips, downloaded
    # once + cached + scanned for all areas together; 2014+ from the per-area
    # Open Data Access CSV. Prefetch the bulk slice up front.
    bulk = prefetch_bulk(
        {a.area_fips for a in areas},
        sorted(y for y in YEARS if y in BULK_YEARS),
    )

    json_written = 0
    yaml_written = 0
    for area in areas:
        # Accumulate per-metric points across all years for this area, in
        # ascending year order (YEARS is sorted), so the written series is too.
        series: dict[str, list[dict]] = {out_id(m, area): [] for m in METRICS}
        for year in YEARS:
            if year in BULK_YEARS:
                rows = bulk.get((area.area_fips, year))
            else:
                rows = fetch_area_year(area.area_fips, year)
                time.sleep(0.05)  # be polite to data.bls.gov
            if not rows:
                continue
            for metric in METRICS:
                v = extract(rows, metric)
                if v is None:
                    continue
                series[out_id(metric, area)].append({"t": f"{year}-12-31", "v": v})

        for metric in METRICS:
            oid = out_id(metric, area)
            points = series[oid]
            if len(points) < 2:
                if points:
                    print(f"  {oid}: only {len(points)} point(s) — skipping",
                          file=sys.stderr)
                continue
            name = f"{area.display} — {metric.label}"
            write_timeseries(
                pipeline="bls",
                series_id=oid,
                name=name,
                points=points,
                unit=metric.unit,
                merge=False,
            )
            json_written += 1
            first = int(points[0]["t"][:4])
            last = int(points[-1]["t"][:4])
            write_source_yaml(metric, area, first, last)
            yaml_written += 1
            print(f"  {oid}: {len(points)} pts {first}-{last} "
                  f"(latest {points[-1]['v']:,.0f})", flush=True)

    print(f"\nWrote {json_written} QCEW JSON files + {yaml_written} source YAMLs",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
