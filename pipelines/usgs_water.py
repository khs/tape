"""USGS water use — county compilations rolled up to US + state level.

USGS migrated water-use data off its old `nwis/water_use` RDB endpoint to
ScienceBase bulk CSVs, so this is NOT an API pipeline. The two source CSVs
are version-controlled under ``pipelines/_usgs_raw/`` (override with
``--src``); re-download from USGS when a newer vintage is published:

  usco2015v2.0.csv  (https://water.usgs.gov/watuse/data/data2015.html;
      Dieter et al. 2018, USGS data release 10.5066/F7TB15V5)
      2015 county withdrawals for all eight use categories, Mgal/d. The
      FIRST physical line is a citation; the real header is line 2. STATE
      is the postal code, FIPS the 5-digit county. Per-category TOTAL-
      withdrawal columns:
        PS-Wtotl public supply   DO-WFrTo self-supplied domestic
        IN-Wtotl self-supp. ind. IR-WFrTo irrigation
        LI-WFrTo livestock       AQ-Wtotl aquaculture
        MI-Wtotl mining          PT-Wtotl thermoelectric power

  AllCategories_TopCat_County_1985to2015.csv
      (https://www.sciencebase.gov/catalog/item/6197decad34eb622f692eea9)
      Per county x water-type (GW/SW), the TOTAL withdrawal ``TV<year>``
      for 1985/90/95/2000/05/10/15. Summing GW+SW gives the county total;
      this is the only file with a time series, so it powers the
      total-water-use TREND. (By-sector data is 2015 only.)

2015 is the most recent COMPLETE national compilation; a newer full
vintage is not yet published. Geographies: US total + 50 states + DC
(grouped by the STATE postal code). Units: Mgal/d (million gallons per
day), stored raw; extensive, so state sums reconstruct the US total
(unitClass "count"). License: public domain (US Geological Survey).

Emits BOTH data JSONs (public/data/usgs_water/) and source YAMLs
(src/content/sources/usgs_water/). Run:
    python pipelines/usgs_water.py
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import _env  # noqa: F401 — parity with sibling pipelines

from common import write_timeseries

PIPELINE = "usgs_water"
REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "pipelines" / "_usgs_raw"
YAML_DIR = REPO_ROOT / "src" / "content" / "sources" / PIPELINE

USCO_2015 = "usco2015v2.0.csv"
TOPCAT = "AllCategories_TopCat_County_1985to2015.csv"
UNIT = "Mgal/d"

# (slug, usco2015 total-withdrawal column, Title label, short word)
SECTORS: list[tuple[str, str, str, str]] = [
    ("public_supply", "PS-Wtotl", "Public-supply", "public-supply"),
    ("domestic", "DO-WFrTo", "Self-supplied domestic", "domestic"),
    ("industrial", "IN-Wtotl", "Self-supplied industrial", "industrial"),
    ("irrigation", "IR-WFrTo", "Irrigation", "irrigation"),
    ("livestock", "LI-WFrTo", "Livestock", "livestock"),
    ("aquaculture", "AQ-Wtotl", "Aquaculture", "aquaculture"),
    ("mining", "MI-Wtotl", "Mining", "mining"),
    ("thermoelectric", "PT-Wtotl", "Thermoelectric-power", "thermoelectric"),
]
TOTAL_COL = "TO-Wtotl"
TREND_YEARS = [1985, 1990, 1995, 2000, 2005, 2010, 2015]

STATE_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
# geo key -> (abbr-for-shortName, name-for-title, name-for-description)
GEOS = {"us": ("US", "United States", "the United States")}
for _ab, _nm in STATE_NAME.items():
    GEOS[_ab.lower()] = (_ab, _nm, _nm)


def _f(v: str | None) -> float:
    if v is None:
        return 0.0
    s = v.strip().replace(",", "")
    if not s or s in {"-", "N/A", "NA"}:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def read_usco2015(src: Path) -> list[dict[str, str]]:
    path = src / USCO_2015
    with path.open(encoding="utf-8-sig", newline="") as fh:
        first = fh.readline()
        if first.split(",", 1)[0].strip().upper() == "STATE":
            fh.seek(0)  # no citation line; rewind so the header is read
        reader = csv.reader(fh)
        header = [h.strip() for h in next(reader)]
        return [dict(zip(header, row)) for row in reader if row]


def parse_2015(src: Path):
    """county_fips5 -> {sector_slug: Mgal/d}, plus county->state postal."""
    county_state: dict[str, str] = {}
    county_vals: dict[str, dict[str, float]] = {}
    for r in read_usco2015(src):
        fips = (r.get("FIPS") or "").strip().zfill(5)
        st = (r.get("STATE") or "").strip().upper()
        if not fips or st not in STATE_NAME:
            continue
        county_state[fips] = st
        county_vals[fips] = {slug: _f(r.get(col)) for slug, col, _, _ in SECTORS}
    return county_state, county_vals


def parse_trend(src: Path) -> dict[str, dict[int, float]]:
    """county_fips5 -> {year: total Mgal/d} (GW + SW rows summed)."""
    out: dict[str, dict[int, float]] = {}
    with (src / TOPCAT).open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            fips = (r.get("Fips") or "").strip().zfill(5)
            if not fips:
                continue
            bucket = out.setdefault(fips, {})
            for y in TREND_YEARS:
                bucket[y] = bucket.get(y, 0.0) + _f(r.get(f"TV{y}"))
    return out


def rollup(per_county: dict[str, float], county_state: dict[str, str]):
    """{county: v} -> (us_total, {state_postal: total})."""
    us = 0.0
    by_state: dict[str, float] = {}
    for fips, v in per_county.items():
        us += v
        st = county_state.get(fips)
        if st:
            by_state[st] = by_state.get(st, 0.0) + v
    return us, by_state


def _yaml_str(s: str) -> str:
    """Single-quote a scalar, doubling any embedded single quotes."""
    return "'" + s.replace("'", "''") + "'"


def write_yaml(
    sid: str,
    name: str,
    short_name: str,
    description: str,
    geo_key: str,
    supported: list[str],
    emphasis: str,
    series_note: str,
    url: str,
) -> None:
    YAML_DIR.mkdir(parents=True, exist_ok=True)
    tags = ["water", "government"]
    if geo_key != "us":
        tags.append("us-state")
    tags.append("us")
    deltas = ", ".join(f'"{d}"' for d in supported)
    lines = [
        f"name: {_yaml_str(name)}",
        f"shortName: {_yaml_str(short_name)}",
        f"description: {_yaml_str(description)}",
        "kind: timeseries",
        f"pipeline: {PIPELINE}",
        f"dataFile: data/{PIPELINE}/{sid}.json",
        f"supportedDeltas: [{deltas}]",
        f'unit: "{UNIT}"',
        f"emphasis: {emphasis}",
        "formatting:",
        "  style: number",
        "  decimals: 0",
        '  suffix: " Mgal/d"',
        "provenance:",
        "  provider: U.S. Geological Survey",
        f"  series: {_yaml_str(series_note)}",
        f"  url: {url}",
        "  license: Public domain (US government data)",
        "tags:",
        *[f"  - {t}" for t in tags],
        "unitClass: count",
        "",
    ]
    (YAML_DIR / f"{sid}.yaml").write_text("\n".join(lines), encoding="utf-8")


SECTOR_URL = "https://water.usgs.gov/watuse/data/data2015.html"
TREND_URL = "https://www.sciencebase.gov/catalog/item/6197decad34eb622f692eea9"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="USGS water use → US + state")
    ap.add_argument("--src", default=str(RAW_DIR), help="dir with the USGS CSVs")
    args = ap.parse_args(argv)
    src = Path(args.src)
    if not (src / USCO_2015).exists():
        print(f"  missing {USCO_2015} in {src}", file=sys.stderr)
        return 1

    county_state, county_2015 = parse_2015(src)
    trend = parse_trend(src) if (src / TOPCAT).exists() else {}
    written = 0

    # ---- 2015 by-sector snapshots (single 2015 point) ----
    for slug, _col, label, short_word in SECTORS:
        per_county = {f: v[slug] for f, v in county_2015.items()}
        us, by_state = rollup(per_county, county_state)
        for geo_key, val in [("us", us)] + [(s.lower(), by_state.get(s, 0.0)) for s in STATE_NAME]:
            abbr, name_t, name_d = GEOS[geo_key]
            sid = f"{slug}_{geo_key}"
            write_timeseries(
                PIPELINE, sid, f"{label} water withdrawals — {name_t}",
                [{"t": "2015-01-01", "v": round(val, 1)}], unit=UNIT, merge=False,
            )
            write_yaml(
                sid,
                f"{label} water withdrawals — {name_t}",
                f"{abbr} {short_word} water",
                f"{label} water withdrawals for {name_d}, 2015, in million "
                f"gallons per day (Mgal/d). U.S. Geological Survey, Estimated "
                f"Use of Water in the United States.",
                geo_key, ["10y", "30y"], "level",
                f"USGS water use 2015; category={slug}; geo={geo_key}", SECTOR_URL,
            )
            written += 1

    # ---- Total-use trend 1985–2015 (multi-point) ----
    if trend:
        us_pts: dict[int, float] = {}
        st_pts: dict[str, dict[int, float]] = {}
        for fips, years in trend.items():
            st = county_state.get(fips)
            for y, v in years.items():
                us_pts[y] = us_pts.get(y, 0.0) + v
                if st:
                    d = st_pts.setdefault(st, {})
                    d[y] = d.get(y, 0.0) + v

        def to_points(d: dict[int, float]) -> list[dict]:
            return [{"t": f"{y}-01-01", "v": round(d[y], 1)} for y in sorted(d) if d.get(y)]

        for geo_key, d in [("us", us_pts)] + [(s.lower(), st_pts.get(s, {})) for s in STATE_NAME]:
            pts = to_points(d)
            if len(pts) < 2:
                continue
            abbr, name_t, name_d = GEOS[geo_key]
            sid = f"total_{geo_key}"
            write_timeseries(
                PIPELINE, sid, f"Total water withdrawals — {name_t}", pts,
                unit=UNIT, merge=False,
            )
            write_yaml(
                sid,
                f"Total water withdrawals — {name_t}",
                f"{abbr} water use",
                f"Total water withdrawals for {name_d}, 1985–2015 (compiled "
                f"every five years), in million gallons per day (Mgal/d). "
                f"U.S. Geological Survey, Estimated Use of Water in the "
                f"United States.",
                geo_key, ["5y", "10y", "30y"], "change",
                f"USGS water use 1985-2015 total; geo={geo_key}", TREND_URL,
            )
            written += 1

    us_total_2015 = sum(sum(v.values()) for v in county_2015.values())
    print(f"[usgs_water] wrote {written} series + YAMLs; counties={len(county_2015)}; "
          f"US 2015 sector sum = {us_total_2015:,.0f} Mgal/d "
          f"(USGS published total ~322,000 incl. territories)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
