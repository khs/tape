"""
Census Building Permits Survey (BPS) — residential permits per US metro.

New privately-owned housing units authorized by building permits, by CBSA:
total units plus the single-family (1-unit) and multifamily (5+ unit) splits.
A leading indicator of housing supply. Annual.

Census reorganized the BPS metro files with the Jan-2024 CBSA redefinition:
  * <=2023: "Metro (ending 2023)/ma<YYYY>a.txt"
  * 2024+:  "CBSA (beginning Jan 2024)/cbsa<YYYY>a.txt"
Both are the SAME comma-delimited layout (verified): two header rows + a blank,
then rows of
  Survey, CSA, CBSA, flag, CBSA_Name, [Bldgs,Units,Value]x{1-unit, 2-units,
  3-4 units, 5+ units}, then the same four "rep" (reported, not imputed) blocks.
We read the Units columns: 1-unit=col6, 2-units=col9, 3-4=col12, 5+=col15. Rows
whose CBSA isn't a 5-digit code in our crosswalk (e.g. the pre-2004 old metro
codes) are skipped, so the join is definition-safe. No Census API exposes BPS
metro tables; the flat files are canonical.

Outputs (per metro x series):
  * public/data/census_bps/<series>_<cbsa>.json
  * src/content/sources/census_bps/<series>_<cbsa>.yaml
Series: permits_total, permits_single_family, permits_multifamily.

Source-ID convention: census_bps/<series>_<cbsa> (parsed by
src/lib/geographic-regions.ts -> parseMetroSourceId).

Cadence: ANNUAL. Manual bump-and-rerun; the current-era loop auto-discovers new
cbsa<YYYY>a.txt files up to CURRENT_MAX, so a rerun picks up the new year.

Run: python pipelines/census_bps.py
"""
from __future__ import annotations

import csv
import io
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from common import write_timeseries

REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSWALK = REPO_ROOT / "pipelines" / "_crosswalks" / "cbsa_metro.csv"
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "census_bps"
DATA_DIR = REPO_ROOT / "public" / "data" / "census_bps"
UA = {"User-Agent": "tape-data-pipeline (keller.scholl@gmail.com)"}
METRO_BASE = "https://www2.census.gov/econ/bps/Metro%20(ending%202023)/"
CBSA_BASE = "https://www2.census.gov/econ/bps/CBSA%20(beginning%20Jan%202024)/"
HIST_YEARS = range(2004, 2024)   # ma<Y>a.txt — CBSA-coded era (CBSAs defined 2003)
CURRENT_MAX = 2030               # try cbsa<Y>a.txt for 2024..CURRENT_MAX, skip 404

# Units columns (0-indexed) in the comma-delimited annual file.
COL_CBSA, COL_1UNIT, COL_2UNIT, COL_34UNIT, COL_5PLUS = 2, 6, 9, 12, 15

# (slug, label, short, description-fragment)
SERIES = [
    ("permits_total", "Building permits, total units", "building permits",
     "All structure types (1-unit, 2-unit, 3-4 unit, 5+ unit)."),
    ("permits_single_family", "Building permits, single-family", "1-unit permits",
     "Single-family (1-unit) structures only."),
    ("permits_multifamily", "Building permits, multifamily (5+ units)", "5+ unit permits",
     "Multifamily structures of 5 or more units."),
]


@dataclass
class Metro:
    code: str
    short_name: str
    name: str


def load_metros() -> list[Metro]:
    out: list[Metro] = []
    with CROSSWALK.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("cbsa_code") or "").strip()
            if code:
                out.append(Metro(code, (row.get("short_name") or "").strip(),
                                 (row.get("name") or "").strip()))
    return out


def metro_display_name(short_name: str, full_name: str) -> str:
    if "," in full_name:
        tail = full_name.split(",", 1)[1].strip()
        if tail:
            return f"{short_name}, {tail}"
    return short_name


def yaml_escape(s: str) -> str:
    if not s:
        return '""'
    if any(c in s for c in [":", "#", "&", "*", "!", "|", ">", "%", "@"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def fetch_year(year: int) -> str | None:
    url = (f"{METRO_BASE}ma{year}a.txt" if year < 2024
           else f"{CBSA_BASE}cbsa{year}a.txt")
    try:
        return urllib.request.urlopen(
            urllib.request.Request(url, headers=UA), timeout=90
        ).read().decode("latin-1", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _to_int(s: str) -> int:
    try:
        return int((s or "").strip())
    except ValueError:
        return 0


def parse_year(text: str) -> dict[str, tuple[int, int, int]]:
    """{cbsa: (total_units, single_family, multifamily)} for one annual file."""
    out: dict[str, tuple[int, int, int]] = {}
    for r in list(csv.reader(io.StringIO(text)))[3:]:  # skip 2 headers + 1 blank
        if len(r) <= COL_5PLUS:
            continue
        cbsa = (r[COL_CBSA] or "").strip()
        if not (cbsa.isdigit() and len(cbsa) == 5):
            continue
        u1, u5 = _to_int(r[COL_1UNIT]), _to_int(r[COL_5PLUS])
        total = u1 + _to_int(r[COL_2UNIT]) + _to_int(r[COL_34UNIT]) + u5
        out[cbsa] = (total, u1, u5)
    return out


def write_yaml(out_id: str, cbsa: str, display: str, label: str,
               short: str, frag: str) -> bool:
    out = SOURCES_DIR / f"{out_id}.yaml"
    if out.exists():
        return False
    desc = (f"New privately-owned housing units authorized by building permits in "
            f"the {display} metro area (CBSA {cbsa}). {frag} Annual count, from the "
            "US Census Bureau Building Permits Survey (spliced across the 2024 CBSA "
            "redefinition).")
    lines = [
        f"name: {yaml_escape(f'{label} — {display}')}",
        f"shortName: {yaml_escape(f'{display} {short}')}",
        f"description: {yaml_escape(desc)}",
        "kind: timeseries",
        "pipeline: census_bps",
        f"dataFile: data/census_bps/{out_id}.json",
        'supportedDeltas: ["1y", "5y", "10y", "30y"]',
        'unit: "units"',
        "formatting:",
        "  style: number",
        "  decimals: 0",
        "  notation: compact",
        "emphasis: change",
        "provenance:",
        "  provider: U.S. Census Bureau (Building Permits Survey)",
        f'  series: "BPS CBSA {cbsa} / {out_id.rsplit("_", 1)[0]}"',
        "  url: https://www.census.gov/construction/bps/",
        "  license: Public domain (US government data)",
        "unitClass: count",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    metros = load_metros()
    # cbsa -> series_idx -> year -> value
    acc: dict[str, dict[int, dict[int, int]]] = {}
    fetched = 0
    for y in list(HIST_YEARS) + list(range(2024, CURRENT_MAX + 1)):
        text = fetch_year(y)
        if text is None:
            continue
        fetched += 1
        for cbsa, triple in parse_year(text).items():
            d = acc.setdefault(cbsa, {})
            for idx, val in enumerate(triple):
                d.setdefault(idx, {})[y] = val
    print(f"Fetched {fetched} annual files", flush=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    data_written = yaml_written = 0
    for m in metros:
        by_idx = acc.get(m.code)
        if not by_idx:
            continue
        display = metro_display_name(m.short_name, m.name)
        for idx, (slug, label, short, frag) in enumerate(SERIES):
            yv = by_idx.get(idx, {})
            points = [{"t": f"{y}-01-01", "v": float(yv[y])} for y in sorted(yv)]
            if len(points) < 2:
                continue
            out_id = f"{slug}_{m.code}"
            write_timeseries(pipeline="census_bps", series_id=out_id,
                             name=f"{label} — {display}", points=points, unit="units")
            data_written += 1
            if (DATA_DIR / f"{out_id}.json").exists():
                if write_yaml(out_id, m.code, display, label, short, frag):
                    yaml_written += 1
    print(f"Wrote {data_written} data + {yaml_written} YAMLs", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
