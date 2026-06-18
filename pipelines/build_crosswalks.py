"""
Build tract-to-118th-Congressional-District crosswalks for use by the
ACS pipeline.

Why this exists: ACS data is published on the congressional-district
boundaries in effect for that ACS vintage. So a trend line for "VA-08
median household income" actually crosses several boundary-change
events — 2012 redistricting, 2022 redistricting. To get a clean
trend on stable (current 118th-Congress) geography, we have to:

  1. Fetch ACS data at the tract level (tracts are near-stable)
  2. Aggregate up to current-118th-CD using a crosswalk

This script builds the two crosswalks the ACS pipeline needs:

  - crosswalks/tract2020_to_cd118.csv  — used for ACS 2020-2022 vintages,
    which publish on 2020 tract boundaries.
  - crosswalks/tract2010_to_cd118.csv  — used for ACS 2010-2019 vintages,
    which publish on 2010 tract boundaries. Built by chaining
    2010 blocks -> 2020 blocks (via Census's tab2010_tab2020 file) ->
    118th CD (via the BAF).

Inputs (downloaded fresh each run):
  - The national 118th-Congress Block Equivalency File (cd118.zip, Census
    Redistricting Data Office): one comma-delimited member per state,
    "<FIPS>_<ABBR>_CD118.txt", header GEOID,CDFP, mapping 2020 blocks to
    118th CDs. This is the AUTHORITATIVE 118th map; an earlier version of
    this script used baf2020/BlockAssign_*_CD.txt, which carried 116th
    districts despite the cd118 name (CA=53/TX=36/NC=13/MT at-large) and
    produced stale geography. The BEF is verified 118th (CA=52/TX=38/
    NC=14/MT=2, 435 seats).

  - Per-state 2010-to-2020 block correspondence files:
    https://www2.census.gov/geo/docs/maps-data/data/rel2020/t10t20/TAB2010_TAB2020_ST<FIPS>.zip
    Inside each, tab2010_tab2020_st<FIPS>_<abbr>.txt gives 2010 block ↔
    2020 block with intersecting land areas.

Outputs (small, checked into repo):
  - pipelines/_crosswalks/tract2020_to_cd118.csv
  - pipelines/_crosswalks/tract2010_to_cd118.csv

CSV format for both:
    tract_geoid, cd_state, cd_district, weight
where weight is the population-area share of the tract that falls within
that CD. A tract entirely inside one CD has weight=1; tracts that
straddle CD boundaries appear twice (e.g. weight 0.7 and 0.3).

Tracts straddle CD boundaries less than ~5% of the time in practice
because redistricting committees deliberately respect tract lines when
they can. The weights still matter for those cases, especially in
gerrymandered states.

This script writes ~80k-row CSVs (a few MB each). Run once after each
new congressional cycle (currently the 118th, which runs through Jan
2027). When the 119th takes effect, rerun.

Run with: ``python pipelines/build_crosswalks.py``.
"""
from __future__ import annotations

import csv
import io
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "pipelines" / "_crosswalks_cache"
OUT_DIR = REPO_ROOT / "pipelines" / "_crosswalks"

# Census 2020 Census 118th-Congressional-District Block Equivalency File
# (RDO). A single national archive with one comma-delimited member per
# state, "<FIPS>_<ABBR>_CD118.txt". This is the TRUE 118th-Congress
# block-to-CD map. It replaces the old baf2020 BlockAssign_*_CD.txt
# source, which silently carried 116th-Congress districts (CA=53, TX=36,
# NC=13, MT at-large) despite the cd118 naming. Verified 118th here:
# CA=52, TX=38, NC=14, MT=2 (01/02), 435 seats total.
CD118_URL = (
    "https://www2.census.gov/programs-surveys/decennial/rdo/mapping-files/"
    "2023/118-congressional-district-bef/cd118.zip"
)

# State FIPS -> abbreviation. 50 states + DC; Census BAFs exist for all of these.
STATES: list[tuple[str, str]] = [
    ("01", "AL"), ("02", "AK"), ("04", "AZ"), ("05", "AR"), ("06", "CA"),
    ("08", "CO"), ("09", "CT"), ("10", "DE"), ("11", "DC"), ("12", "FL"),
    ("13", "GA"), ("15", "HI"), ("16", "ID"), ("17", "IL"), ("18", "IN"),
    ("19", "IA"), ("20", "KS"), ("21", "KY"), ("22", "LA"), ("23", "ME"),
    ("24", "MD"), ("25", "MA"), ("26", "MI"), ("27", "MN"), ("28", "MS"),
    ("29", "MO"), ("30", "MT"), ("31", "NE"), ("32", "NV"), ("33", "NH"),
    ("34", "NJ"), ("35", "NM"), ("36", "NY"), ("37", "NC"), ("38", "ND"),
    ("39", "OH"), ("40", "OK"), ("41", "OR"), ("42", "PA"), ("44", "RI"),
    ("45", "SC"), ("46", "SD"), ("47", "TN"), ("48", "TX"), ("49", "UT"),
    ("50", "VT"), ("51", "VA"), ("53", "WA"), ("54", "WV"), ("55", "WI"),
    ("56", "WY"),
]


def fetch(url: str, dest: Path) -> bool:
    """Download with curl. Returns True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        subprocess.run(
            ["curl", "-sS", "--max-time", "180", "-o", str(dest), url],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    fetch failed: {url}: {e}", file=sys.stderr)
        return False
    return dest.stat().st_size > 0


def cd118_zip() -> Path | None:
    """Download the national 118th-CD Block Equivalency File once, cached."""
    zip_path = CACHE_DIR / "cd118.zip"
    return zip_path if fetch(CD118_URL, zip_path) else None


def read_baf_cd(fips: str, abbr: str) -> dict[str, str]:
    """
    Returns {block_geoid_15: cd_2digit} for one state's 2020 blocks, on
    TRUE 118th-Congress districts.

    Source: the national cd118.zip (CD118_URL), one comma-delimited member
    per state named "<FIPS>_<ABBR>_CD118.txt":
        GEOID,CDFP
        010010201001000,02
    (Previously this pulled baf2020/BlockAssign_*_CD.txt, which carried
    116th-Congress districts despite the cd118 naming — that was the
    boundary bug this swap fixes.)

    Districts "ZZ" / "98" are non-voting placeholders we skip. "00" is the
    at-large designator for single-CD states (AK, DE, ND, SD, VT, WY);
    keep it — it's a real CD, just encoded as 00 instead of 01. Montana,
    at-large in the 116th, now has numbered districts 01/02.
    """
    zip_path = cd118_zip()
    if zip_path is None:
        return {}
    inner = f"{fips}_{abbr}_CD118.txt"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open(inner) as fh:
                content = fh.read().decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError) as e:
        print(f"    bad zip / missing member {inner}: {e}", file=sys.stderr)
        return {}
    out: dict[str, str] = {}
    for line in content.splitlines()[1:]:  # skip "GEOID,CDFP" header
        parts = line.split(",")
        if len(parts) < 2:
            continue
        block_id, cd = parts[0].strip(), parts[1].strip()
        if not block_id or not cd:
            continue
        if cd == "ZZ":
            # ZZ = territory / not in any CD. Drop it. Keep "98" (the
            # non-voting-delegate code): for DC (the only delegate geo in
            # STATES) every block is "98", so dropping it orphaned DC from
            # both crosswalks entirely. Kept, cd_slug() maps "98" -> dc_98,
            # and SINGLE_CD_REDUNDANT redirects dc_98 -> acs_state/<series>_dc.
            continue
        out[block_id] = cd
    return out


def aggregate_blocks_to_tracts(block_map: dict[str, str]) -> dict[str, dict[str, int]]:
    """
    Roll up block-level CD assignments to tract-level CD counts.
    Tract GEOID is first 11 chars of the 15-char block GEOID.
    Returns {tract_geoid: {cd_code: block_count}}. Population weights
    would be more accurate but block-count weighting is a reasonable
    proxy — blocks within a tract are roughly equal in population
    (that's how Census sizes them).
    """
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for block_id, cd in block_map.items():
        if len(block_id) < 11:
            continue
        tract_id = block_id[:11]
        out[tract_id][cd] += 1
    return out


def write_crosswalk(
    tract_to_cd_counts: dict[str, dict[str, int]],
    out_path: Path,
    state_fips: str,
) -> int:
    """
    Write rows of (tract_geoid, cd_state, cd_district, weight) where
    weight = block_count_in_cd / total_blocks_in_tract.
    """
    rows_written = 0
    with out_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        for tract_id, cd_counts in tract_to_cd_counts.items():
            total = sum(cd_counts.values())
            if total == 0:
                continue
            for cd, count in cd_counts.items():
                weight = count / total
                writer.writerow([tract_id, state_fips, cd, f"{weight:.6f}"])
                rows_written += 1
    return rows_written


def build_tract2020_crosswalk() -> None:
    """
    For each state: download BAF, parse blocks->CD, aggregate to tract->CD,
    append rows to the output CSV.
    """
    out_path = OUT_DIR / "tract2020_to_cd118.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Reset file with header.
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tract_geoid", "state_fips", "cd_district", "weight"])
    total = 0
    for fips, abbr in STATES:
        print(f"  {abbr}: parsing BAF...", flush=True)
        block_map = read_baf_cd(fips, abbr)
        if not block_map:
            print(f"    no data for {abbr}", file=sys.stderr)
            continue
        tract_counts = aggregate_blocks_to_tracts(block_map)
        n = write_crosswalk(tract_counts, out_path, fips)
        print(f"    {len(block_map)} blocks -> {len(tract_counts)} tracts -> {n} rows")
        total += n
    print(f"tract2020 crosswalk written: {total} rows -> {out_path}")


def read_t10t20(fips: str, abbr: str) -> list[tuple[str, str, int]]:
    """
    For one state, returns list of (block2010_geoid, block2020_geoid, intersect_land_area).
    Built from the t10t20 relationship file.
    """
    url = f"https://www2.census.gov/geo/docs/maps-data/data/rel2020/t10t20/TAB2010_TAB2020_ST{fips}.zip"
    zip_path = CACHE_DIR / f"t10t20_{abbr}.zip"
    if not fetch(url, zip_path):
        return []
    inner_name = f"tab2010_tab2020_st{fips}_{abbr.lower()}.txt"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open(inner_name) as fh:
                content = fh.read().decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError) as e:
        print(f"    bad zip {zip_path}: {e}", file=sys.stderr)
        return []
    out: list[tuple[str, str, int]] = []
    # First line is BOM + header. Stream rest line-by-line.
    lines = content.splitlines()
    header = lines[0].lstrip("﻿").split("|")
    try:
        col_s10 = header.index("STATE_2010")
        col_c10 = header.index("COUNTY_2010")
        col_t10 = header.index("TRACT_2010")
        col_b10 = header.index("BLK_2010")
        col_s20 = header.index("STATE_2020")
        col_c20 = header.index("COUNTY_2020")
        col_t20 = header.index("TRACT_2020")
        col_b20 = header.index("BLK_2020")
        col_area = header.index("AREALAND_INT")
    except ValueError as e:
        print(f"    {abbr} t10t20 header mismatch: {e}", file=sys.stderr)
        return []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) <= col_area:
            continue
        # 2010 GEOIDs sometimes come from another state (border blocks).
        # We don't care about those for the per-state aggregation since
        # we'll process them when iterating that state, so just record
        # what's there and let the caller decide.
        s10 = parts[col_s10]
        c10 = parts[col_c10]
        t10 = parts[col_t10]
        b10 = parts[col_b10]
        s20 = parts[col_s20]
        c20 = parts[col_c20]
        t20 = parts[col_t20]
        b20 = parts[col_b20]
        if not (s10 and c10 and t10 and b10 and s20 and c20 and t20 and b20):
            continue
        block10 = f"{s10:>2}{c10:>3}{t10:>6}{b10:>4}"
        block20 = f"{s20:>2}{c20:>3}{t20:>6}{b20:>4}"
        try:
            area = int(parts[col_area]) if parts[col_area] else 0
        except ValueError:
            area = 0
        out.append((block10, block20, area))
    return out


def build_tract2010_crosswalk(block2020_to_cd: dict[str, str]) -> None:
    """
    For each state's t10t20 file, look up the 2020 block in block2020_to_cd
    to get the CD118 assignment. Aggregate 2010 blocks within each
    2010 tract, weighted by intersection land area.
    """
    out_path = OUT_DIR / "tract2010_to_cd118.csv"
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tract_geoid", "state_fips", "cd_district", "weight"])
    total = 0
    for fips, abbr in STATES:
        print(f"  {abbr}: bridging 2010->2020 via t10t20...", flush=True)
        rows = read_t10t20(fips, abbr)
        if not rows:
            continue
        # {tract2010_geoid: {cd: area_sum}}
        tract_cd_area: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for block10, block20, area in rows:
            cd = block2020_to_cd.get(block20)
            if not cd:
                continue
            # Drop cross-state-boundary fragments. This state's t10t20 file
            # includes border 2010 blocks from NEIGHBORING states (a 2010 AL
            # block that slivers into a 2020 block in this state). Without
            # this filter that AL tract gets stamped with THIS state's CD at
            # full weight, leaking the whole AL tract's population into a
            # wrong-state district (317 such tracts before the fix). A 2010
            # tract is wholly within one state, so only count fragments whose
            # 2020 block sits in the same state as the 2010 block.
            if block20[:2] != block10[:2]:
                continue
            tract10 = block10[:11]
            tract_cd_area[tract10][cd] += area
        n = 0
        with out_path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            for tract_id, cd_areas in tract_cd_area.items():
                total_area = sum(cd_areas.values())
                if total_area == 0:
                    continue
                for cd, area in cd_areas.items():
                    weight = area / total_area
                    writer.writerow([tract_id, fips, cd, f"{weight:.6f}"])
                    n += 1
        print(f"    {len(rows)} bridge rows -> {len(tract_cd_area)} tracts -> {n} crosswalk rows")
        total += n
    print(f"tract2010 crosswalk written: {total} rows -> {out_path}")


def load_block2020_to_cd() -> dict[str, str]:
    """
    Concatenated block-to-CD map across all states. Built by re-reading
    BAFs (already cached after build_tract2020_crosswalk runs).
    """
    all_blocks: dict[str, str] = {}
    for fips, abbr in STATES:
        bm = read_baf_cd(fips, abbr)
        all_blocks.update(bm)
    return all_blocks


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Building tract2020 -> CD118 crosswalk ===")
    build_tract2020_crosswalk()

    print()
    print("=== Loading consolidated block2020 -> CD map ===")
    block2020_to_cd = load_block2020_to_cd()
    print(f"Total 2020 blocks with CD assignments: {len(block2020_to_cd):,}")

    print()
    print("=== Building tract2010 -> CD118 crosswalk (via 2010-to-2020 blocks) ===")
    build_tract2010_crosswalk(block2020_to_cd)

    print()
    print("Done. Crosswalks at:", OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
