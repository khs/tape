"""
FHFA House Price Index (all-transactions) per US metro area.

FHFA publishes a quarterly repeat-sales House Price Index (single-family
properties with conforming Fannie/Freddie mortgages). It is the public-domain
federal substitute for the proprietary Case-Shiller index, which Tape
deliberately excludes. The all-transactions metro file gives a per-CBSA NSA
index back to 1975.

One wrinkle: FHFA publishes the largest metros ONLY as metropolitan DIVISIONS,
not as a combined CBSA (e.g. there is no 31080 Los Angeles index, only 31084
LA-Long Beach-Glendale + 11244 Anaheim). For those we surface the PRINCIPAL
division (the one with the core city) under the parent CBSA id, noted in the
source description. See DIVISION_PRINCIPAL.

Source: keyless bulk CSV at
fhfa.gov/hpi/download/quarterly_datasets/hpi_at_metro.csv (no header; columns:
place_name, place_id, year, quarter, index_nsa, <qoq change>). We read the NSA
index (column 5); missing cells render as "-" and are skipped.

Outputs (per metro):
  * public/data/fhfa/hpi_<cbsa>.json
  * src/content/sources/fhfa/hpi_<cbsa>.yaml

Source-ID convention: ``fhfa/hpi_<cbsa>`` (parsed by
src/lib/geographic-regions.ts -> parseMetroSourceId).

Cadence: FHFA HPI is QUARTERLY. This is a manual bump-and-rerun pipeline (like
cms_nhe / bls_qcew / nhtsa_fars), NOT wired into the weekly refresh -- re-run it
after FHFA posts a new quarter (~8 weeks after quarter close). write_timeseries
merges, so a rerun only appends the new quarter; the skip-if-exists YAML emitter
leaves existing source YAMLs untouched.

Run with: ``python pipelines/fhfa.py``.
"""
from __future__ import annotations

import csv
import io
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from common import write_timeseries

REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSWALK = REPO_ROOT / "pipelines" / "_crosswalks" / "cbsa_metro.csv"
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "fhfa"
DATA_DIR = REPO_ROOT / "public" / "data" / "fhfa"

FHFA_URL = "https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_metro.csv"

# Metros FHFA publishes ONLY as metropolitan divisions (no combined-CBSA index).
# Map each to its PRINCIPAL division (the one containing the core city); we
# surface that under the parent CBSA. Division codes verified against the live
# hpi_at_metro.csv place_id list.
DIVISION_PRINCIPAL: dict[str, str] = {
    "12060": "12054",  # Atlanta -> Atlanta-Sandy Springs-Roswell
    "14460": "14454",  # Boston
    "16980": "16984",  # Chicago -> Chicago-Naperville-Schaumburg
    "19100": "19124",  # Dallas-Fort Worth -> Dallas-Plano-Irving
    "19820": "19804",  # Detroit -> Detroit-Dearborn-Livonia
    "31080": "31084",  # Los Angeles -> Los Angeles-Long Beach-Glendale
    "33100": "33124",  # Miami -> Miami-Miami Beach-Kendall
    "35620": "35614",  # New York -> New York-Jersey City-White Plains
    "37980": "37964",  # Philadelphia
    "41860": "41884",  # San Francisco -> San Francisco-San Mateo-Redwood City
    "42660": "42644",  # Seattle -> Seattle-Bellevue-Kent
    "45300": "45294",  # Tampa
    "47900": "47764",  # Washington -> Washington, DC-MD
}


@dataclass
class CbsaMetro:
    code: str
    short_name: str
    name: str


def load_metros(path: Path) -> list[CbsaMetro]:
    out: list[CbsaMetro] = []
    if not path.exists():
        print(f"  CBSA crosswalk missing: {path}", file=sys.stderr)
        return out
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("cbsa_code") or "").strip()
            if not code:
                continue
            out.append(CbsaMetro(
                code=code,
                short_name=(row.get("short_name") or "").strip(),
                name=(row.get("name") or "").strip(),
            ))
    return out


def metro_display_name(short_name: str, full_name: str) -> str:
    """Short name + the official CBSA title's state suffix (mirrors bls_metro)."""
    if "," in full_name:
        tail = full_name.split(",", 1)[1].strip()
        if tail:
            return f"{short_name}, {tail}"
    return short_name


def quarter_to_iso(year: int, quarter: int) -> str:
    # Mid-quarter stamp (month = quarter*3, day 15), matching the Q-handling in
    # pipelines/bls_metro.py so quarterly series align across providers.
    return f"{year:04d}-{quarter * 3:02d}-15"


def yaml_escape(s: str) -> str:
    if not s:
        return '""'
    if any(ch in s for ch in [":", "#", "&", "*", "!", "|", ">", "%", "@"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def fetch_place_data() -> dict[str, tuple[str, list[dict]]]:
    """place_id -> (place_name, ascending [{t, v}]) from the NSA index column."""
    req = urllib.request.Request(
        FHFA_URL,
        headers={"User-Agent": "tape-data-pipeline (keller.scholl@gmail.com)"},
    )
    raw = urllib.request.urlopen(req, timeout=180).read().decode("utf-8", "replace")
    by_place: dict[str, tuple[str, list[dict]]] = {}
    for row in csv.reader(io.StringIO(raw)):
        if len(row) < 5:
            continue
        name = row[0].strip()
        pid = row[1].strip()
        try:
            yr = int(row[2])
            q = int(row[3])
            v = float(row[4])
        except (ValueError, IndexError):
            continue  # missing cells render as "-"
        if not 1 <= q <= 4:
            continue
        entry = by_place.setdefault(pid, (name, []))
        entry[1].append({"t": quarter_to_iso(yr, q), "v": v})
    return by_place


def write_source_yaml(cbsa: str, display: str, place_id: str,
                      place_name: str, is_division: bool) -> bool:
    out = SOURCES_DIR / f"hpi_{cbsa}.yaml"
    if out.exists():
        return False
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    label = f"{display} — home price index (FHFA)"
    short = f"{display} home prices"
    desc = (
        f"FHFA all-transactions House Price Index for the {display} metro area "
        f"(CBSA {cbsa}). Repeat-sales index of single-family properties with "
        "conforming mortgages; not seasonally adjusted, quarterly. The "
        "public-domain federal substitute for the proprietary Case-Shiller index."
    )
    if is_division:
        clean = place_name.replace(" (MSAD)", "")
        desc += (
            f" FHFA publishes this metro only at the metropolitan-division level, "
            f"so values are its principal division, {clean} (FHFA area {place_id})."
        )
    lines = [
        f"name: {yaml_escape(label)}",
        f"shortName: {yaml_escape(short)}",
        f"description: {yaml_escape(desc)}",
        "kind: timeseries",
        "pipeline: fhfa",
        f"dataFile: data/fhfa/hpi_{cbsa}.json",
        'supportedDeltas: ["1y", "5y", "10y", "30y"]',
        'unit: "index"',
        "formatting:",
        "  style: number",
        "  decimals: 1",
        "emphasis: change",
        "provenance:",
        "  provider: U.S. Federal Housing Finance Agency (FHFA)",
        f'  series: "{place_id}"',  # quote: FHFA codes are numeric, schema wants a string
        "  url: https://www.fhfa.gov/data/hpi/datasets",
        "  license: Public domain (US government data)",
        "unitClass: index",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    metros = load_metros(CROSSWALK)
    if not metros:
        print("fhfa: no metros loaded — aborting", file=sys.stderr)
        return 1
    print("Fetching FHFA metro HPI CSV...", flush=True)
    by_place = fetch_place_data()
    print(f"  parsed {len(by_place)} FHFA places", flush=True)

    data_written = 0
    yaml_written = 0
    skipped = 0
    for m in metros:
        is_division = m.code not in by_place
        place_id = m.code if not is_division else DIVISION_PRINCIPAL.get(m.code, "")
        if not place_id or place_id not in by_place:
            skipped += 1
            continue
        place_name, points = by_place[place_id]
        if len(points) < 2:
            skipped += 1
            continue
        display = metro_display_name(m.short_name, m.name)
        write_timeseries(
            pipeline="fhfa",
            series_id=f"hpi_{m.code}",
            name=f"{display} — home price index (FHFA)",
            points=points,
            unit="index",
        )
        data_written += 1
        if (DATA_DIR / f"hpi_{m.code}.json").exists():
            if write_source_yaml(m.code, display, place_id, place_name, is_division):
                yaml_written += 1
    print(f"Wrote {data_written} metro HPI JSON files, {yaml_written} new YAMLs, "
          f"{skipped} metros skipped (no FHFA coverage)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
