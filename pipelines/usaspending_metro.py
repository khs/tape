"""
Federal spending per CBSA (Metropolitan Statistical Area), annual.

USAspending.gov's ``spending_by_geography`` endpoint exposes geo_layer
values of state, county, and district — not CBSA directly. We pull
county-level results once per fiscal year and aggregate up using the
OMB CBSA delineation (counties → CBSAs).

Inputs:
  * pipelines/_crosswalks/cbsa_metro.csv   (curated metro list)
  * pipelines/_crosswalks/county_to_cbsa.csv (optional; build via
    `python pipelines/build_cbsa_metro_crosswalk.py --counties`. Until
    that file exists, this pipeline falls back to USAspending's existing
    ``recipient_location`` filters with the CBSA name string — slower
    and noisier, but workable for the curated starter list.)

Outputs (one per metro):
  * public/data/usaspending/metro_<CBSA>.json
  * src/content/sources/usaspending/metro_<CBSA>.yaml

Source-ID convention: ``usaspending/metro_<cbsa>`` (parsed by
src/lib/geographic-regions.ts → parseMetroSourceId).

Fiscal-year semantics match pipelines/usaspending.py: FY{n} =
Oct {n-1} – Sep {n}, output anchored at Sep 30 of the FY.

Run with: ``python pipelines/usaspending_metro.py``.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from common import write_timeseries

REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSWALK_DIR = REPO_ROOT / "pipelines" / "_crosswalks"
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "usaspending"

USA_URL = "https://api.usaspending.gov/api/v2/search/spending_by_geography/"
START_FY = 2008


@dataclass
class CbsaMetro:
    code: str
    short_name: str
    name: str
    primary_state_fips: str
    primary_state_abbr: str
    states: list[str]


def load_metros(path: Path) -> list[CbsaMetro]:
    out: list[CbsaMetro] = []
    if not path.exists():
        print(f"  CBSA crosswalk missing: {path}", file=sys.stderr)
        return out
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            code = row.get("cbsa_code", "").strip()
            if not code:
                continue
            out.append(CbsaMetro(
                code=code,
                short_name=row.get("short_name", "").strip(),
                name=row.get("name", "").strip(),
                primary_state_fips=row.get("primary_state_fips", "").strip(),
                primary_state_abbr=row.get("primary_state_abbr", "").strip(),
                states=[s.strip() for s in row.get("states", "").split("|") if s.strip()],
            ))
    return out


def load_county_to_cbsa(path: Path) -> dict[str, str]:
    """
    Returns {county_fips5: cbsa_code}. Empty dict if the crosswalk
    hasn't been built — caller will fall back to the slower per-CBSA
    keyword-filter approach.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            fips5 = (row.get("county_fips", "") or "").strip().zfill(5)
            cbsa = (row.get("cbsa_code", "") or "").strip()
            if fips5 and cbsa:
                out[fips5] = cbsa
    return out


def call_api_county(start_date: str, end_date: str) -> list[dict]:
    """Pull every county's federal-spending total for the window."""
    body = json.dumps({
        "scope": "recipient_location",
        "geo_layer": "county",
        "filters": {
            "time_period": [{"start_date": start_date, "end_date": end_date}],
        },
    })
    try:
        out = subprocess.run(
            ["curl", "-s", "-S", "--max-time", "180",
             "-H", "Content-Type: application/json",
             "-X", "POST", "-d", body, USA_URL],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    curl failed ({start_date}..{end_date} county): {e}",
              file=sys.stderr)
        return []
    try:
        parsed = json.loads(out.stdout)
    except json.JSONDecodeError:
        print(f"    bad JSON ({start_date}..{end_date} county)",
              file=sys.stderr)
        return []
    return parsed.get("results", []) or []


def county_fips5_from_shape(shape_code: str) -> str | None:
    """
    USAspending county results carry ``shape_code`` like "01001"
    (5-digit state+county FIPS). Returns the 5-digit string or None
    when the shape can't be parsed.
    """
    if not shape_code:
        return None
    digits = "".join(ch for ch in shape_code if ch.isdigit())
    if len(digits) != 5:
        return None
    return digits


def yaml_escape(s: str) -> str:
    """Quote a string if it'd otherwise need YAML escaping."""
    if not s:
        return '""'
    if any(ch in s for ch in [":", "#", "&", "*", "!", "|", ">", "%", "@"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def metro_display_name(short_name: str, full_name: str) -> str:
    """
    Display label for a metro: short name + the official CBSA title's
    state suffix, e.g. ("Columbus", "Columbus, GA-AL") -> "Columbus, GA-AL"
    and ("Akron", "Akron, OH") -> "Akron, OH".

    State codes are kept BY DEFAULT (not just on collisions): many short
    names repeat across states ("Columbus", "Springfield", ...), so a
    bare city name is ambiguous in the source picker.
    """
    if "," in full_name:
        tail = full_name.split(",", 1)[1].strip()
        if tail:
            return f"{short_name}, {tail}"
    return short_name


def write_source_yaml(metro: CbsaMetro) -> bool:
    """Idempotent: only writes if the file doesn't exist yet."""
    out = SOURCES_DIR / f"metro_{metro.code}.yaml"
    if out.exists():
        return False
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    display = metro_display_name(metro.short_name, metro.name)
    description = (
        f"Total federal outlays where the recipient location is in the "
        f"{metro.short_name} metropolitan statistical area "
        f"(CBSA {metro.code}, OMB-defined). Aggregated up from "
        f"USAspending.gov's county-level results by fiscal year."
    )
    lines = [
        f"name: {yaml_escape(f'Federal spending — {display}')}",
        f"shortName: {yaml_escape(display)}",
        f"description: {yaml_escape(description)}",
        "kind: timeseries",
        "pipeline: usaspending",
        f"dataFile: data/usaspending/metro_{metro.code}.json",
        'supportedDeltas: ["1y", "5y", "10y"]',
        'unit: "billions USD"',
        "formatting:",
        "  style: currency",
        "  currency: USD",
        "  decimals: 1",
        "  suffix: \" B\"",
        "emphasis: change",
        "provenance:",
        "  provider: USAspending.gov",
        f"  series: metro_{metro.code}",
        f"  url: https://www.usaspending.gov/search?recipient_location_cbsa={metro.code}",
        "  license: Public domain (US government data)",
        "unitClass: currency",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    metros = load_metros(CROSSWALK_DIR / "cbsa_metro.csv")
    if not metros:
        print("usaspending_metro: no metros loaded — aborting", file=sys.stderr)
        return 1
    county_to_cbsa = load_county_to_cbsa(CROSSWALK_DIR / "county_to_cbsa.csv")
    in_scope = {m.code for m in metros}

    if not county_to_cbsa:
        print(
            "usaspending_metro: county_to_cbsa.csv not found. The pipeline "
            "needs the county→CBSA mapping to aggregate USAspending data. "
            "Run `python pipelines/build_cbsa_metro_crosswalk.py` to build "
            "both crosswalks from the Census delineation file, then re-run.",
            file=sys.stderr,
        )
        # Still emit source YAMLs so the composer chip surfaces the metros
        # immediately; data JSONs will appear when this script gets re-run
        # after the crosswalk exists.
        yaml_written = sum(1 for m in metros if write_source_yaml(m))
        print(f"  wrote {yaml_written} new source YAMLs (no data files)",
              flush=True)
        return 0

    current_year = datetime.now(timezone.utc).year
    end_fy = (
        current_year + 1
        if datetime.now(timezone.utc).month >= 10
        else current_year
    )

    metro_points: dict[str, list[dict]] = defaultdict(list)

    for fy in range(START_FY, end_fy + 1):
        start = f"{fy - 1}-10-01"
        end = f"{fy}-09-30"
        anchor = f"{fy}-09-30"
        print(f"FY{fy} ({start} -> {end})...", flush=True)

        per_metro_total: dict[str, float] = defaultdict(float)
        for rec in call_api_county(start, end):
            shape = rec.get("shape_code", "")
            amount = rec.get("aggregated_amount")
            fips5 = county_fips5_from_shape(shape)
            if not fips5 or amount is None:
                continue
            cbsa = county_to_cbsa.get(fips5)
            if not cbsa or cbsa not in in_scope:
                continue
            per_metro_total[cbsa] += float(amount)

        for cbsa, total in per_metro_total.items():
            # Same billions-USD rescale as the CD pipeline so divides
            # against FRED's already-in-billions GDP/M2/etc. produce
            # sane ratios.
            metro_points[cbsa].append({"t": anchor, "v": total / 1e9})

    json_written = 0
    for metro in metros:
        points = metro_points.get(metro.code, [])
        if not points:
            continue
        points.sort(key=lambda p: p["t"])
        write_timeseries(
            pipeline="usaspending",
            series_id=f"metro_{metro.code}",
            name=f"Federal spending — {metro_display_name(metro.short_name, metro.name)}",
            points=points,
            unit="USD",
        )
        json_written += 1
    print(f"Wrote {json_written} metro JSON files", flush=True)

    yaml_written = sum(1 for m in metros if write_source_yaml(m))
    print(f"Wrote {yaml_written} new source YAMLs "
          f"({len(metros) - yaml_written} already existed)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
