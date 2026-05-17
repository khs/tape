"""
ACS 5-year estimates per CBSA (Metropolitan Statistical Area).

Unlike the CD pipeline (pipelines/census_acs_cd.py), which has to
crosswalk tract-level data into stable 118th-Congress districts,
the Census API exposes ACS data directly at the CBSA geography:

    geography = "metropolitan statistical area/micropolitan statistical area"

CBSA boundaries change infrequently (last major OMB revision was Bulletin
23-01, July 2023) so we can pull the contemporary-CBSA series directly
without a tract-aggregation step. Future redelineations will introduce
small comparability breaks; document those when they happen.

Series pulled (same indicators as the CD pipeline so charts can layer
trivially):
  * population (B01003_001E)
  * poverty_count (B17001_002E)
  * bachelors_plus (B15003_022E)
  * median_hh_income (B19013_001E)

Outputs (per metro × per series):
  * public/data/acs_metro/<series>_<CBSA>.json
  * src/content/sources/acs_metro/<series>_<CBSA>.yaml

Source-ID convention: ``acs_metro/<series>_<cbsa>`` (parsed by
src/lib/geographic-regions.ts → parseMetroSourceId).

Requires CENSUS_API_KEY env var; no-ops with a status message when unset.

Run with: ``CENSUS_API_KEY=<key> python pipelines/census_acs_metro.py``.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from common import write_timeseries

REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSWALK_DIR = REPO_ROOT / "pipelines" / "_crosswalks"
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "acs_metro"

ACS_VINTAGES = list(range(2010, 2023))


def acs_base(year: int) -> str:
    if year >= 2015:
        return f"https://api.census.gov/data/{year}/acs/acs5"
    return f"https://api.census.gov/data/{year}/acs5"


@dataclass
class AcsMetroVar:
    out_id: str
    var_code: str
    name_prefix: str
    unit: str
    decimals: int
    unit_class: str  # currency | count | rate | index | ratio
    fmt_style: str  # number | currency | percent
    fmt_currency: str | None  # e.g. "USD"
    fmt_notation: str | None  # e.g. "compact"


# Mirror the CD pipeline's series selection. Keep this list intentionally
# small at launch — Census API caps per-call vars and adding more rows
# inflates wall-time × ~387 metros.
INDICATORS: list[AcsMetroVar] = [
    AcsMetroVar(
        out_id="population",
        var_code="B01003_001E",
        name_prefix="Total population",
        unit="people",
        decimals=0,
        unit_class="count",
        fmt_style="number",
        fmt_currency=None,
        fmt_notation="compact",
    ),
    AcsMetroVar(
        out_id="poverty_count",
        var_code="B17001_002E",
        name_prefix="People in poverty",
        unit="people",
        decimals=0,
        unit_class="count",
        fmt_style="number",
        fmt_currency=None,
        fmt_notation="compact",
    ),
    AcsMetroVar(
        out_id="bachelors_plus",
        var_code="B15003_022E",
        name_prefix="Adults 25+ with bachelor's degree",
        unit="people",
        decimals=0,
        unit_class="count",
        fmt_style="number",
        fmt_currency=None,
        fmt_notation="compact",
    ),
    AcsMetroVar(
        out_id="median_hh_income",
        var_code="B19013_001E",
        name_prefix="Median household income",
        unit="USD",
        decimals=0,
        unit_class="currency",
        fmt_style="currency",
        fmt_currency="USD",
        fmt_notation=None,
    ),
]


def load_metro_codes(path: Path) -> dict[str, tuple[str, str]]:
    """Returns {cbsa_code: (short_name, full_name)}."""
    out: dict[str, tuple[str, str]] = {}
    if not path.exists():
        print(f"  CBSA crosswalk missing: {path}", file=sys.stderr)
        return out
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            code = (row.get("cbsa_code") or "").strip()
            if not code:
                continue
            out[code] = (
                (row.get("short_name") or "").strip(),
                (row.get("name") or "").strip(),
            )
    return out


def acs_fetch(year: int, var_codes: list[str], key: str) -> list[list[str]]:
    """
    One request for every CBSA at once. Returns the response as a list
    of rows (first row = headers). Empty list on failure.
    """
    vars_csv = ",".join(var_codes)
    geo = "metropolitan%20statistical%20area/micropolitan%20statistical%20area:*"
    url = (
        f"{acs_base(year)}?get=NAME,{vars_csv}"
        f"&for={geo}&key={key}"
    )
    try:
        out = subprocess.run(
            ["curl", "-s", "-S", "--max-time", "120", "-w", "%{http_code}", url],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    curl failed year={year}: {e}", file=sys.stderr)
        return []
    body = out.stdout
    code = body[-3:] if body[-3:].isdigit() else "???"
    payload = body[:-3] if body[-3:].isdigit() else body
    if code != "200":
        snippet = payload.strip()[:200]
        print(f"    HTTP {code} year={year}: {snippet}", file=sys.stderr)
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"    JSON parse year={year}: {e}", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def parse_value(s: str) -> float | None:
    """Census sentinel-negative values mean 'no data'."""
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    if v < -1_000_000:
        return None
    return v


def yaml_escape(s: str) -> str:
    if not s:
        return '""'
    if any(ch in s for ch in [":", "#", "&", "*", "!", "|", ">", "%", "@"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def write_source_yaml(var: AcsMetroVar, cbsa: str, short_name: str) -> bool:
    out = SOURCES_DIR / f"{var.out_id}_{cbsa}.yaml"
    if out.exists():
        return False
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    description = (
        f"{var.name_prefix} for the {short_name} metropolitan statistical "
        f"area (CBSA {cbsa}). From the American Community Survey 5-year "
        f"estimates. Released annually."
    )
    short_label = f"{short_name} {var.out_id.replace('_', ' ')}"
    name_full = f"{var.name_prefix} — {short_name}"
    lines = [
        f"name: {yaml_escape(name_full)}",
        f"shortName: {yaml_escape(short_label)}",
        f"description: {yaml_escape(description)}",
        "kind: timeseries",
        "pipeline: acs_metro",
        f"dataFile: data/acs_metro/{var.out_id}_{cbsa}.json",
        'supportedDeltas: ["5y", "10y"]',
        f'unit: "{var.unit}"',
        "formatting:",
        f"  style: {var.fmt_style}",
    ]
    if var.fmt_currency:
        lines.append(f"  currency: {var.fmt_currency}")
    lines.append(f"  decimals: {var.decimals}")
    if var.fmt_notation:
        lines.append(f"  notation: {var.fmt_notation}")
    lines.extend([
        "emphasis: change",
        "provenance:",
        "  provider: US Census Bureau (ACS 5-year)",
        f"  series: {var.out_id}_{cbsa}",
        f"  url: https://api.census.gov/data/2022/acs/acs5",
        "  license: Public domain (US government data)",
        f"unitClass: {var.unit_class}",
    ])
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    metros = load_metro_codes(CROSSWALK_DIR / "cbsa_metro.csv")
    if not metros:
        print("census_acs_metro: no metros loaded — aborting", file=sys.stderr)
        return 1

    if not key:
        print(
            "census_acs_metro: CENSUS_API_KEY not set. Writing source YAMLs "
            "only (no data files). Register a free key at "
            "https://api.census.gov/data/key_signup.html and re-run.",
            file=sys.stderr,
        )
        yaml_written = 0
        for var in INDICATORS:
            for cbsa, (short_name, _) in metros.items():
                if write_source_yaml(var, cbsa, short_name):
                    yaml_written += 1
        print(f"  wrote {yaml_written} new source YAMLs", flush=True)
        return 0

    # Accumulator: {(out_id, cbsa): [{t, v}, ...]}
    series_accum: dict[tuple[str, str], list[dict]] = defaultdict(list)
    var_codes = [v.var_code for v in INDICATORS]

    for year in ACS_VINTAGES:
        anchor = f"{year}-12-31"
        print(f"\nFetching ACS5 vintage {year}...", flush=True)
        rows = acs_fetch(year, var_codes, key)
        if not rows or len(rows) < 2:
            print(f"  no data for {year}", file=sys.stderr)
            continue
        headers = rows[0]
        try:
            geo_col = headers.index(
                "metropolitan statistical area/micropolitan statistical area"
            )
        except ValueError:
            print(f"  unexpected schema {year}: {headers}", file=sys.stderr)
            continue
        for row in rows[1:]:
            if len(row) < len(headers):
                continue
            cbsa = row[geo_col]
            if cbsa not in metros:
                # Skip micropolitan areas + any metro outside our curated list.
                continue
            for var in INDICATORS:
                try:
                    col = headers.index(var.var_code)
                except ValueError:
                    continue
                v = parse_value(row[col])
                if v is None:
                    continue
                series_accum[(var.out_id, cbsa)].append({"t": anchor, "v": v})

    json_written = 0
    for var in INDICATORS:
        for cbsa, (short_name, _) in metros.items():
            points = series_accum.get((var.out_id, cbsa))
            if not points:
                continue
            points.sort(key=lambda p: p["t"])
            if var.unit_class == "count":
                for p in points:
                    p["v"] = round(p["v"])
            write_timeseries(
                pipeline="acs_metro",
                series_id=f"{var.out_id}_{cbsa}",
                name=f"{var.name_prefix} — {short_name}",
                points=points,
                unit=var.unit,
            )
            json_written += 1
    print(f"\nWrote {json_written} metro × series JSON files", flush=True)

    yaml_written = 0
    for var in INDICATORS:
        for cbsa, (short_name, _) in metros.items():
            if write_source_yaml(var, cbsa, short_name):
                yaml_written += 1
    print(f"Wrote {yaml_written} new source YAMLs", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
