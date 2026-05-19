"""
Generate source-metadata YAML files for Zillow data.

Mirrors the shape of pipelines/_generate_acs_sources.py: scans the
zillow data directory and writes a YAML for each (index, geo) pair
that doesn't already have one. Idempotent — never overwrites.

Run after pipelines/zillow.py adds new data files (e.g. you extend
the metro list, or Zillow ships a new index family).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "public" / "data" / "zillow"
SRC_DIR = ROOT / "src" / "content" / "sources" / "zillow"

# Friendly metro labels for the description field.
METRO_LABELS: dict[str, str] = {
    "national": "United States",
    "nyc": "New York, NY",
    "la": "Los Angeles, CA",
    "chicago": "Chicago, IL",
    "dallas": "Dallas, TX",
    "houston": "Houston, TX",
    "dc": "Washington, DC",
    "philadelphia": "Philadelphia, PA",
    "miami": "Miami, FL",
    "atlanta": "Atlanta, GA",
    "boston": "Boston, MA",
    "sf": "San Francisco, CA",
    "seattle": "Seattle, WA",
}

# Index families: (key, human label, unit, formatting style, tags).
INDEX_FAMILIES: dict[str, dict] = {
    "zhvi": {
        "human_label": "Zillow Home Value Index",
        "short_label": "ZHVI",
        "unit": "USD",
        "style": "currency",
        "decimals": 0,
        "notation": "compact",
        "tags": ["real-estate", "housing"],
        "describe": (
            "Zillow Home Value Index (ZHVI) — typical home value (35th–65th "
            "percentile band, single-family + condo, smoothed seasonally "
            "adjusted). Monthly back to January 2000. Zillow's most-cited "
            "house-price series and an alternative to the Case-Shiller "
            "index — broader geographic coverage (every ZIP code), faster "
            "release cadence, less smoothed at the local level."
        ),
    },
    "zori": {
        "human_label": "Zillow Observed Rent Index",
        "short_label": "ZORI",
        "unit": "USD/mo",
        "style": "currency",
        "decimals": 0,
        "notation": "compact",
        "tags": ["real-estate", "housing", "inflation"],
        "describe": (
            "Zillow Observed Rent Index (ZORI) — typical observed market-"
            "rate rent across a region, repeat-rent index weighted to the "
            "rental housing stock. Monthly back to January 2015. Catches "
            "asking-rent changes ~12 months earlier than CPI Shelter, "
            "which uses contract rent + a slow-rolling renewal weight."
        ),
    },
}


def main() -> int:
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for data_file in sorted(DATA_DIR.glob("*.json")):
        # Skip summary siblings.
        if data_file.name.endswith(".summary.json"):
            continue
        stem = data_file.stem  # e.g. zhvi_national, zori_dc
        # Split on the first underscore to get index family + geo slug.
        if "_" not in stem:
            continue
        index_key, geo_slug = stem.split("_", 1)
        if index_key not in INDEX_FAMILIES:
            continue
        if geo_slug not in METRO_LABELS:
            continue
        family = INDEX_FAMILIES[index_key]
        out_path = SRC_DIR / f"{stem}.yaml"
        if out_path.exists():
            continue

        # Read the data file for the canonical "name" field that the
        # pipeline already wrote into the JSON.
        data = json.loads(data_file.read_text(encoding="utf-8"))
        canonical_name = data.get("name", f"{family['human_label']} — {METRO_LABELS[geo_slug]}")

        # Pick supportedDeltas based on data length. ZHVI back to 2000
        # supports up to 30y; ZORI back to 2015 supports up to 10y.
        if index_key == "zhvi":
            deltas = '["1m", "ytd", "1y", "5y", "10y", "30y"]'
        else:
            deltas = '["1m", "ytd", "1y", "5y", "10y"]'

        geo_label = METRO_LABELS[geo_slug]
        is_national = geo_slug == "national"
        short_name = (
            f"{geo_label.split(',')[0]} {family['short_label']}"
            if not is_national
            else f"US {family['short_label']}"
        )

        body = f"""name: {canonical_name}
shortName: {short_name}
description: |
  {family['describe'].replace(chr(10), chr(10) + '  ')}
kind: timeseries
pipeline: zillow
dataFile: data/zillow/{stem}.json
supportedDeltas: {deltas}
unit: "{family['unit']}"
formatting:
  style: {family['style']}
  currency: USD
  decimals: {family['decimals']}
  notation: {family['notation']}
emphasis: change
provenance:
  provider: Zillow Research
  series: {index_key.upper()} ({geo_label})
  url: https://www.zillow.com/research/data/
  license: Free for public use (consumers, media, analysts, academics, policymakers)
tags:
"""
        for t in family["tags"]:
            body += f"  - {t}\n"
        # Add a geo tag for non-national.
        if not is_national:
            body += f"  - {geo_slug}\n"
        body += "unitClass: currency\n"

        out_path.write_text(body, encoding="utf-8")
        written += 1
        print(f"  wrote {out_path.relative_to(ROOT)}")
    print(f"Generated {written} Zillow source YAMLs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
