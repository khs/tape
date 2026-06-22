"""
Per-state Census TIGER -> TopoJSON generator.

Background
----------
The choropleth renderer takes a boundaryFile path per chart and joins
ACS values onto the topology by GEOID. We started with a multi-state
DMV tract bundle (VA + MD + DC) and a VA-only block-group file, but
the user has since asked for tract- AND BG-level coverage of every
state. Rather than ship one giant nation-wide topology (~50 MB for
tracts, ~250 MB for block groups, too heavy for client-side fetch),
we generate one file per (state, geo) pair. Each chart loads only
the topology it needs.

Source
------
US Census TIGER/Line shapefiles, one zip per state per geography:
  TRACT: https://www2.census.gov/geo/tiger/TIGER<Y>/TRACT/tl_<Y>_<FIPS>_tract.zip
  BG:    https://www2.census.gov/geo/tiger/TIGER<Y>/BG/tl_<Y>_<FIPS>_bg.zip

Output schema (matches the existing dmv-tracts-topo / va-block-groups
files):
  objects.{tracts|block_groups}.geometries[i] = {
    type: "Polygon" | "MultiPolygon",
    id: "<11-digit (tract) or 12-digit (BG) GEOID>",
    properties: { name: "Census Tract X.Y" or "Block Group N..." },
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
  python pipelines/build_state_tract_topo.py --state CA --geo tract
  python pipelines/build_state_tract_topo.py --state all --geo tract
  python pipelines/build_state_tract_topo.py --state all --geo block_group
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

# TIGER vintage. Bump when the user wants boundaries from a different
# vintage; the file naming convention is stable across years.
TIGER_YEAR = 2025
TIGER_ROOT = f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}"


def tiger_url(geo: str, fips: str) -> str:
    """Build the TIGER zip URL for a (geo, state) pair."""
    if geo == "tract":
        return f"{TIGER_ROOT}/TRACT/tl_{TIGER_YEAR}_{fips}_tract.zip"
    if geo == "block_group":
        # BG zips are under /BG/ with a "_bg" stem.
        return f"{TIGER_ROOT}/BG/tl_{TIGER_YEAR}_{fips}_bg.zip"
    raise ValueError(f"Unknown geo: {geo}")


def geo_layer_name(geo: str) -> str:
    """Topojson layer name the renderer looks for. tract -> 'tracts',
    block_group -> 'block_groups' (per ChartMap.astro)."""
    return {"tract": "tracts", "block_group": "block_groups"}[geo]


def geo_file_stem(geo: str) -> str:
    """Per-geo output-filename stem. Matches the existing files:
    <st>-tracts-topo.json and <st>-block-groups-topo.json."""
    return {"tract": "tracts", "block_group": "block-groups"}[geo]


def shapefile_stem(geo: str, fips: str) -> str:
    """Inner-shapefile name (varies by geo)."""
    return {
        "tract": f"tl_{TIGER_YEAR}_{fips}_tract",
        "block_group": f"tl_{TIGER_YEAR}_{fips}_bg",
    }[geo]

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


def _is_zip(path: Path) -> bool:
    """True if ``path`` is a real zip (PK signature + valid central dir).
    Census behind Cloudflare sometimes serves a 200 HTML 'not found' page
    for a valid-looking TIGER URL; urlretrieve would otherwise cache that
    HTML as a bogus .zip and every retry fails with 'File is not a zip
    file'. Observed live for tl_2025_50_bg.zip (2026-06)."""
    try:
        return zipfile.is_zipfile(path)
    except OSError:
        return False


def fetch_zip(geo: str, fips: str) -> Path:
    """Download a state's TIGER zip (tract or BG) into the local cache,
    validating it is actually a zip. On a non-zip response (a Cloudflare
    stale-HTML 200) retry once with a cache-buster query, which forces a
    CDN cache miss + origin fetch. Never leaves a non-zip in the cache, and
    self-heals an already-poisoned cache entry."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"{shapefile_stem(geo, fips)}.zip"
    if out.exists():
        if _is_zip(out):
            return out
        out.unlink()  # poisoned cache entry (cached HTML) — drop + refetch
    url = tiger_url(geo, fips)
    tmp = out.parent / (out.name + ".part")
    urls = (url, f"{url}?cb={fips}{geo}")
    for i, fetch_url in enumerate(urls):
        print(f"  fetching {fetch_url}", flush=True)
        urlretrieve(fetch_url, tmp)
        if _is_zip(tmp):
            tmp.replace(out)  # atomic promote: only a valid zip is cached
            return out
        tmp.unlink(missing_ok=True)
        if i + 1 < len(urls):
            print("  response was not a zip (stale CDN cache?); "
                  "retrying cache-busted", flush=True)
    raise RuntimeError(
        f"TIGER download for {shapefile_stem(geo, fips)} is not a zip even "
        f"after a cache-busted retry (Census/Cloudflare returned a non-zip "
        f"200 for {url})."
    )


def extract_shapefile(zip_path: Path, geo: str, fips: str) -> Path:
    """Extract the shapefile + supporting files (shx, dbf, prj, cpg)
    from the zip. mapshaper needs all of them in the same directory
    even if we pass only the .shp path."""
    stem = shapefile_stem(geo, fips)
    extract_dir = CACHE_DIR / stem
    shp = extract_dir / f"{stem}.shp"
    if not shp.exists():
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
    return shp


def make_topo(state_code: str, fips: str, geo: str,
              simplify_pct: int = 10, out_suffix: str = "") -> Path:
    """Convert one state's TIGER shapefile (tract OR block group) to
    TopoJSON in the schema the renderer expects.

    Mapshaper pipeline:
      1. read the shapefile
      2. simplify with `keep-shapes` so tiny polygons (small tracts /
         BGs) don't get reduced to zero-area
      3. drop every attribute except GEOID + NAMELSAD
      4. copy NAMELSAD into a `name` field; the renderer reads
         ``properties.name`` for the hover tooltip
      5. rename the layer (tracts | block_groups)
      6. emit topojson, promoting GEOID to geometry.id via id-field=GEOID
    """
    zip_path = fetch_zip(geo, fips)
    shp = extract_shapefile(zip_path, geo, fips)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / (
        f"{state_code.lower()}-{geo_file_stem(geo)}{out_suffix}-topo.json"
    )
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
        "-rename-layers", geo_layer_name(geo),
        # `id-field=GEOID` promotes the GEOID property to topojson's
        # top-level geometry.id. The renderer joins on geometry.id.
        "-o", "format=topojson", "id-field=GEOID", str(out_path),
    ]
    print(f"  mapshaper -> {out_path.relative_to(ROOT)}", flush=True)
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_path


def main(argv: list[str] | None = None) -> int:
    global TIGER_YEAR, TIGER_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--state", default="all",
        help="Two-letter state code, or 'all' to do every state + DC.",
    )
    ap.add_argument(
        "--geo", default="tract", choices=["tract", "block_group"],
        help=(
            "Geography level: 'tract' (11-digit GEOID, ~5k features per "
            "state) or 'block_group' (12-digit GEOID, ~5x more features "
            "per state). Output filename suffix differs accordingly: "
            "<st>-tracts-topo.json vs <st>-block-groups-topo.json."
        ),
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
    ap.add_argument(
        "--tiger-year", type=int, default=TIGER_YEAR,
        help=(
            "TIGER/Line vintage. Default 2025 (2020-census tract grid). Use "
            "a 2010-era year (e.g. 2019) to build the pre-2020 grid for ACS "
            "vintages 2019 and earlier, paired with --out-suffix -2010."
        ),
    )
    ap.add_argument(
        "--out-suffix", default="",
        help=("Inserted before '-topo.json' in the output filename, e.g. "
              "'-2010' gives <st>-tracts-2010-topo.json."),
    )
    args = ap.parse_args(argv)
    if args.tiger_year != TIGER_YEAR:
        TIGER_YEAR = args.tiger_year
        TIGER_ROOT = f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}"

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
        print(f"\n--- {code} (FIPS {fips}) [{args.geo}] ---", flush=True)
        try:
            path = make_topo(code, fips, args.geo, args.simplify,
                             out_suffix=args.out_suffix)
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
        f"\nWrote {written}/{len(targets)} state {args.geo} topojsons "
        f"(failed: {failed if failed else 'none'})"
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
