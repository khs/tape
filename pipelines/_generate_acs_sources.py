"""
Generate source-metadata YAML files for ACS congressional-district data.

The pipeline at pipelines/census_acs_cd.py produces JSON data files for
13 ACS indicators across ~435 congressional districts, dropped into
public/data/acs_cd/. The Astro content layer requires a matching source
YAML in src/content/sources/acs_cd/ for each one to be discoverable by
the composer library and renderable by chart manifests.

This script scans the data directory and fills in any missing source
YAMLs, mirroring the format and conventions of the hand-written examples
(population_va_08.yaml et al.).

Idempotent: never overwrites existing YAMLs. Re-run after adding a new
indicator to census_acs_cd.py's INDICATORS list, or after a fresh data
fetch that produces new CDs (e.g. mid-decade redistricting).

Run with:  python pipelines/_generate_acs_sources.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "public" / "data" / "acs_cd"
SOURCES_DIR = ROOT / "src" / "content" / "sources" / "acs_cd"


# Indicator metadata. Mirrors the INDICATORS list in census_acs_cd.py
# with the extra YAML-specific fields (name, formatting, tags, table
# code). Keep aligned with the pipeline when adding new indicators.
#
# agg semantics — must match census_acs_cd.py:
#   "sum"          tract-aggregated counts on 118th-Congress stable geography
#   "median_dist"  median recomputed from a distribution table on stable geo
#   "cd_level"     contemporaneous-CD-boundary fetch (no stable-geo aggregation)
#
# extra_tags is appended to the universal ["government", "us"] base.
INDICATORS = [
    {
        "out_id": "population",
        "name_prefix": "Total population",
        "short_suffix": "population",
        "unit": "people",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B01003",
        "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "poverty_count",
        "name_prefix": "People in poverty",
        "short_suffix": "poverty count",
        "unit": "people",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B17001",
        "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "foreign_born",
        "name_prefix": "Foreign-born population",
        "short_suffix": "foreign-born",
        "unit": "people",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B05002",
        "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "bachelors_plus",
        "name_prefix": "Adults 25+ with bachelor's degree",
        "short_suffix": "bachelors plus",
        "unit": "people",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B15003",
        "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "masters_plus",
        "name_prefix": "Adults 25+ with master's degree",
        "short_suffix": "masters plus",
        "unit": "people",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B15003",
        "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "owner_occupied",
        "name_prefix": "Owner-occupied housing units",
        "short_suffix": "owner-occupied",
        "unit": "households",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B25003",
        "agg": "sum",
        "extra_tags": ["real-estate"],
    },
    {
        "out_id": "renter_occupied",
        "name_prefix": "Renter-occupied housing units",
        "short_suffix": "renter-occupied",
        "unit": "households",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B25003",
        "agg": "sum",
        "extra_tags": ["real-estate"],
    },
    {
        "out_id": "veterans",
        "name_prefix": "Civilian veteran population (18+)",
        "short_suffix": "veterans",
        "unit": "people",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B21001",
        "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "broadband_households",
        "name_prefix": "Households with broadband internet",
        "short_suffix": "broadband households",
        "unit": "households",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B28002",
        "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "median_hh_income",
        "name_prefix": "Median household income",
        "short_suffix": "median hh income",
        "unit": "USD",
        "unit_class": "currency",
        "fmt_style": "currency",
        "currency": "USD",
        "decimals": 0,
        "notation": "compact",
        "table": "B19013",
        "agg": "median_dist",
        "extra_tags": [],
    },
    {
        "out_id": "median_age",
        "name_prefix": "Median age",
        "short_suffix": "median age",
        "unit": "years",
        # No unitClass — "years" doesn't cleanly fit any of the
        # composer's classes (currency/count/rate/index/ratio).
        "unit_class": None,
        "fmt_style": "number",
        "decimals": 1,
        # Standard notation reads better for two-digit ages than compact.
        "notation": None,
        "table": "B01002",
        "agg": "cd_level",
        "extra_tags": [],
    },
    {
        "out_id": "median_home_value",
        "name_prefix": "Median home value (owner-occupied)",
        "short_suffix": "median home value",
        "unit": "USD",
        "unit_class": "currency",
        "fmt_style": "currency",
        "currency": "USD",
        "decimals": 0,
        "notation": "compact",
        "table": "B25077",
        "agg": "cd_level",
        "extra_tags": ["real-estate"],
    },
    {
        "out_id": "median_gross_rent",
        "name_prefix": "Median gross rent",
        "short_suffix": "median gross rent",
        "unit": "USD",
        "unit_class": "currency",
        "fmt_style": "currency",
        "currency": "USD",
        "decimals": 0,
        "notation": "compact",
        "table": "B25064",
        "agg": "cd_level",
        "extra_tags": ["real-estate"],
    },
]


def slug_to_display(slug: str) -> str:
    """va_08 -> VA-08, ak_al -> AK-AL, dc_98 -> DC-98."""
    return slug.upper().replace("_", "-")


def description_for(ind: dict, slug: str) -> str:
    """One-sentence-ish description matching the existing hand-written tone."""
    display = slug_to_display(slug)
    table = ind["table"]
    if ind["agg"] == "sum":
        return (
            f"{ind['name_prefix']} for {display} (118th Congress boundaries). "
            f"From the American Community Survey 5-year estimates "
            f"(table {table}). Released annually."
        )
    if ind["agg"] == "median_dist":
        return (
            f"{ind['name_prefix']} for {display} (118th Congress boundaries). "
            f"Recomputed at CD level by aggregating the {table} household-income-"
            f"distribution bin counts across tracts assigned to {display} via the "
            f"2020-tract crosswalk, then taking the weighted median. American "
            f"Community Survey 5-year estimates, released annually."
        )
    # cd_level
    return (
        f"{ind['name_prefix']} for {display}, from the American Community Survey "
        f"5-year estimates (table {table}). Released annually. Each data point "
        f"uses contemporaneous-CD boundaries — the geographic area called "
        f'"{display}" reflects whichever district lines were in effect for that '
        f"ACS vintage — pending a stable-geo distribution-based recompute."
    )


def render_yaml(ind: dict, slug: str) -> str:
    display = slug_to_display(slug)
    name = f"{ind['name_prefix']} — {display}"
    short = f"{display} {ind['short_suffix']}"
    desc = description_for(ind, slug)
    tags = ["government", "us"] + ind["extra_tags"]

    lines: list[str] = [
        f"name: {name}",
        f"shortName: {short}",
        f"description: {desc}",
        "kind: timeseries",
        "pipeline: acs_cd",
        f"dataFile: data/acs_cd/{ind['out_id']}_{slug}.json",
        'supportedDeltas: ["5y", "10y"]',
        f"unit: {ind['unit']}",
        "formatting:",
        f"  style: {ind['fmt_style']}",
    ]
    if ind.get("currency"):
        lines.append(f"  currency: {ind['currency']}")
    lines.append(f"  decimals: {ind['decimals']}")
    if ind.get("notation"):
        lines.append(f"  notation: {ind['notation']}")
    lines.append("emphasis: change")
    lines.append("provenance:")
    lines.append("  provider: US Census Bureau (ACS 5-year)")
    lines.append(f"  series: {ind['out_id']}")
    lines.append("  url: https://api.census.gov/data/2022/acs/acs5")
    lines.append("  license: Public domain (US government data)")
    lines.append("tags:")
    for tag in tags:
        lines.append(f"  - {tag}")
    if ind.get("unit_class"):
        lines.append(f"unitClass: {ind['unit_class']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    per_indicator: dict[str, tuple[int, int]] = {}
    for ind in INDICATORS:
        w = s = 0
        for data_file in sorted(DATA_DIR.glob(f"{ind['out_id']}_*.json")):
            # Skip the .summary.json sidecar files (Glob picks them up
            # because they also end in .json).
            if data_file.name.endswith(".summary.json"):
                continue
            slug = data_file.stem[len(ind["out_id"]) + 1 :]
            yaml_path = SOURCES_DIR / f"{ind['out_id']}_{slug}.yaml"
            if yaml_path.exists():
                s += 1
                continue
            yaml_path.write_text(render_yaml(ind, slug), encoding="utf-8")
            w += 1
        per_indicator[ind["out_id"]] = (w, s)
        written += w
        skipped += s

    print(f"Wrote {written} new source YAMLs ({skipped} already existed).")
    print()
    print(f"{'indicator':<25}  {'wrote':>6}  {'skipped':>8}")
    print(f"{'-' * 25}  {'-' * 6}  {'-' * 8}")
    for out_id, (w, s) in per_indicator.items():
        print(f"{out_id:<25}  {w:>6}  {s:>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
