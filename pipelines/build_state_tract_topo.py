"""
Per-state tract TopoJSON generator.

Background
----------
The choropleth renderer takes a boundaryFile path per chart and joins
ACS values onto the topology by 11-digit GEOID. We started with a
multi-state DMV bundle (VA + MD + DC) but the user has since asked for
tract-level coverage of every state. Rather than ship one giant
nation-wide topology (~50 MB, too heavy for client-side fetch), we
generate one file per state, each ~100 KB - 3 MB depending on tract
count. Each chart loads only the topology it needs.

Source
------
US Census TIGER/Line tract shapefiles, one zip per state:
  https://www2.census.gov/geo/tiger/TIGER<YEAR>/TRACT/tl_<YEAR>_<FIPS>_tract.zip

Output schema (matches the bundled dmv-tracts-topo.json):
  objects.tracts.geometries[i] = {
    type: "Polygon" | "MultiPolygon",
    id: "<11-digit GEOID>",
    properties: { name: "Census Tract X.Y" },
    arcs: [...]
  }

License: TIGER/Line files are public domain.

Tools
-----
Requires `mapshaper` on PATH:
  npm install -g mapshaper

Cache
-----
Source zips + extracted shapefiles cached at
``pipelines/_tract_topo_cache/`` (gitignored). Re-running for a state
that's already been fetched skips the download.

Run
---
  python pipelines/build_state_tract_topo.py --state CA
  python pipelines/build_state_tract_topo.py --state all
  python pipelines/build_state_tract_topo.py --state DE --simplify 30
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "public" / "maps"
CACHE_DIR = ROOT / "pipelines" / "_tract_topo_cache"

# TIGER vintage. Bump when the user wants tract boundaries from a
# different vintage; the file naming convention is stable.
TIGER_YEAR = 2024
TIGER_BASE = f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}/TRACT"

# 50 states + DC, matching pipelines/census_acs_choropleth.py.
STATE_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56",
}


def fetch_zip(fips: str) -> Path:
    """Download a state's TIGER tract zip into the local cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"tl_{TIGER_YEAR}_{fips}_tract.zip"
    if not out.exists():
        url = f"{TIGER_BASE}/tl_{TIGER_YEAR}_{fips}_tract.zip"
        print(f"  fetching {url}", flush=True)
        urlretrieve(url, out)
    return out


def extract_shapefile(zip_path: Path, fips: str) -> Path:
    """Extract the shapefile + supporting files (shx, dbf, prj, cpg)
    from the zip. mapshaper needs all of them in the same directory
    even if we pass only the .shp path."""
    extract_dir = CACHE_DIR / f"tl_{TIGER_YEAR}_{fips}_tract"
    shp = extract_dir / f"tl_{TIGER_YEAR}_{fips}_tract.shp"
    if not shp.exists():
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
    return shp


def make_topo(state_code: str, fips: str, simplify_pct: int = 10) -> Path:
    """Convert one state's TIGER tract shapefile to TopoJSON.

    Mapshaper pipeline:
      1. read the shapefile
      2. simplify with `keep-shapes` so tiny polygons (small tracts)
         don't get reduced to zero-area
      3. drop every attribute except GEOID + NAMELSAD
      4. promote GEOID to the geometry's `id` field and copy NAMELSAD
         to ``properties.name`` to match the existing
         ``dmv-tracts-topo.json`` schema
      5. rename the layer to "tracts" (renderer looks for this name)
      6. emit topojson
    """
    zip_path = fetch_zip(fips)
    shp = extract_shapefile(zip_path, fips)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{state_code.lower()}-tracts-topo.json"
    # On Windows, the npm-installed `mapshaper` is a Unix shim with no
    # .exe/.cmd association; subprocess.run can't launch it directly.
    # shutil.which resolves to mapshaper.cmd on Windows and the plain
    # binary on Linux/macOS.
    mapshaper_bin = shutil.which("mapshaper") or shutil.which("mapshaper.cmd")
    if not mapshaper_bin:
        raise FileNotFoundError(
            "mapshaper not on PATH. Install with: npm install -g mapshaper"
        )
    cmd = [
        mapshaper_bin, str(shp),
        "-simplify", f"{simplify_pct}%", "keep-shapes",
        "-filter-fields", "GEOID,NAMELSAD",
        "-each", "name = NAMELSAD",
        "-filter-fields", "GEOID,name",
        "-rename-layers", "tracts",
        # `id-field=GEOID` promotes the GEOID property to topojson's
        # top-level geometry.id, then drops it from properties. The
        # renderer joins on geometry.id, so this is the shape we need.
        "-o", "format=topojson", "id-field=GEOID", str(out_path),
    ]
    print(f"  mapshaper -> {out_path.relative_to(ROOT)}", flush=True)
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--state", default="all",
        help="Two-letter state code, or 'all' to do every state + DC.",
    )
    ap.add_argument(
        "--simplify", type=int, default=10,
        help=(
            "Percent of polygon vertices to keep after Douglas-Peucker "
            "simplification (1-100). Default 10 — small files, still "
            "visually accurate at typical zoom levels. Bump to 25-30 "
            "for sharper boundaries at high zoom."
        ),
    )
    args = ap.parse_args(argv)

    if args.state.lower() == "all":
        targets = list(STATE_FIPS.items())
    else:
        code = args.state.upper()
        if code not in STATE_FIPS:
            print(f"Unknown state: {code}", file=sys.stderr)
            return 2
        targets = [(code, STATE_FIPS[code])]

    written = 0
    failed: list[str] = []
    for code, fips in targets:
        print(f"\n--- {code} (FIPS {fips}) ---", flush=True)
        try:
            path = make_topo(code, fips, args.simplify)
            size_kb = path.stat().st_size / 1024
            print(f"  ok: {size_kb:.0f} KB", flush=True)
            written += 1
        except subprocess.CalledProcessError as e:
            print(
                f"  mapshaper failed (rc={e.returncode}): "
                f"{(e.stderr or '').strip()[:300]}",
                file=sys.stderr,
            )
            failed.append(code)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            failed.append(code)

    print(
        f"\nWrote {written}/{len(targets)} state tract topojsons "
        f"(failed: {failed if failed else 'none'})"
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
