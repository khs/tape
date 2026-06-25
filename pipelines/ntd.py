"""
FTA National Transit Database (NTD) — monthly transit ridership per US metro.

Monthly Unlinked Passenger Trips (UPT, i.e. boardings) summed across every
transit agency whose primary urbanized area maps to the metro. The COVID
ridership collapse + recovery is the headline story (NY: 368M trips Apr-2019
-> 45M Apr-2020 -> 317M Apr-2025).

Source: FTA "Complete Monthly Ridership (with adjustments and estimates)" on
data.transportation.gov (Socrata dataset 8bui-9xvu), keyless. We aggregate
sum(upt) by (uace_cd, date) SERVER-SIDE, then map the Census urbanized area
(UZA) to a CBSA by name (first city token + state). IMPORTANT: a UZA is the
dense urbanized core, not the full CBSA, so this is urbanized-area transit
ridership keyed to the metro (flagged in the source description), not a strict
CBSA aggregate.

Outputs (per metro):
  * public/data/ntd/ridership_<cbsa>.json
  * src/content/sources/ntd/ridership_<cbsa>.yaml

Source-ID convention: ntd/ridership_<cbsa> (parsed by
src/lib/geographic-regions.ts -> parseMetroSourceId).

Cadence: monthly (~1-2 month lag). Runs monthly in refresh-demographics.yml
(re-fetches all each run).

Run: python pipelines/ntd.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from common import write_timeseries

REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSWALK = REPO_ROOT / "pipelines" / "_crosswalks" / "cbsa_metro.csv"
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "ntd"
DATA_DIR = REPO_ROOT / "public" / "data" / "ntd"
RESOURCE = "https://data.transportation.gov/resource/8bui-9xvu.json"
UA = {"User-Agent": "tape-data-pipeline (keller.scholl@gmail.com)"}


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


def _first_token(name: str) -> str:
    city = name.split(",")[0]
    parts = re.split(r"--|-|/", city)
    return parts[0].strip().lower() if parts else ""


def _states(name: str) -> set[str]:
    m = re.search(r",\s*([A-Z]{2}(?:[-]{1,2}[A-Z]{2})*)", name)
    return set(re.findall(r"[A-Z]{2}", m.group(1))) if m else set()


def _socrata(params: dict) -> list[dict]:
    url = RESOURCE + "?" + urllib.parse.urlencode(params)
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=180).read())


def build_uza_cbsa_map(metros: list[Metro]) -> dict[str, str]:
    """uace_cd -> cbsa, by first-city-token + state name match."""
    by_token: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
    for m in metros:
        by_token[_first_token(m.name)].append((m.code, _states(m.name)))
    uzas = _socrata({"$select": "uace_cd,uza_name", "$group": "uace_cd,uza_name",
                     "$limit": 5000})
    out: dict[str, str] = {}
    for z in uzas:
        nm = z.get("uza_name") or ""
        code = z.get("uace_cd") or ""
        cands = by_token.get(_first_token(nm), [])
        if not (code and cands):
            continue
        st = _states(nm)
        pick = next((c for c, cst in cands if (st & cst) or not st), cands[0][0])
        out[code] = pick
    return out


def fetch_monthly() -> list[dict]:
    """All (uace_cd, date, sum(upt)) rows, paginated."""
    rows: list[dict] = []
    offset, page = 0, 50000
    while True:
        batch = _socrata({"$select": "uace_cd,date,sum(upt) as upt",
                          "$group": "uace_cd,date", "$order": "uace_cd,date",
                          "$limit": page, "$offset": offset})
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return rows


def write_yaml(cbsa: str, display: str) -> bool:
    out = SOURCES_DIR / f"ridership_{cbsa}.yaml"
    if out.exists():
        return False
    desc = (f"Monthly public-transit ridership (unlinked passenger trips, all "
            f"modes) for the {display} urbanized area, summed across the transit "
            "agencies the FTA National Transit Database assigns to that area, then "
            f"keyed to CBSA {cbsa}. The urbanized area is the dense core, not the "
            "full metro. Captures the post-2020 ridership collapse and recovery.")
    lines = [
        f'name: "Transit ridership — {display}"',
        f'shortName: "{display} transit ridership"',
        f'description: "{desc}"',
        "kind: timeseries",
        "pipeline: ntd",
        f"dataFile: data/ntd/ridership_{cbsa}.json",
        'supportedDeltas: ["1m", "1y", "5y", "10y"]',
        'unit: "trips"',
        "formatting:",
        "  style: number",
        "  decimals: 0",
        "  notation: compact",
        "emphasis: change",
        "provenance:",
        "  provider: U.S. DOT Federal Transit Administration (National Transit Database)",
        f'  series: "NTD monthly UPT / UZA -> CBSA {cbsa}"',
        "  url: https://www.transit.dot.gov/ntd/data-product/monthly-module-adjusted-data-release",
        "  license: Public domain (US government data)",
        "unitClass: count",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    metros = load_metros()
    uza2cbsa = build_uza_cbsa_map(metros)
    print(f"Mapped {len(uza2cbsa)} UZAs to CBSAs", flush=True)
    rows = fetch_monthly()
    print(f"Fetched {len(rows)} UZA-month aggregate rows", flush=True)
    acc: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        cbsa = uza2cbsa.get(r.get("uace_cd") or "")
        if not cbsa:
            continue
        try:
            v = int(float(r.get("upt") or 0))
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue
        acc[cbsa][(r.get("date") or "")[:10]] += v
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    data_written = yaml_written = 0
    by_code = {m.code: m for m in metros}
    for cbsa, months in acc.items():
        m = by_code.get(cbsa)
        if not m:
            continue
        points = [{"t": mo, "v": float(months[mo])} for mo in sorted(months) if mo]
        if len(points) < 2:
            continue
        display = metro_display_name(m.short_name, m.name)
        write_timeseries(pipeline="ntd", series_id=f"ridership_{cbsa}",
                         name=f"Transit ridership — {display}", points=points,
                         unit="trips")
        data_written += 1
        if (DATA_DIR / f"ridership_{cbsa}.json").exists():
            if write_yaml(cbsa, display):
                yaml_written += 1
    print(f"Wrote {data_written} metro ridership series + {yaml_written} YAMLs",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
