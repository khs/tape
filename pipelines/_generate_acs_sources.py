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
    # Education attainment as shares. The raw degree counts stay (the
    # choropleth + state-derivation infra and the composer's total-
    # reconstruction need them) but are hidden:true so the picker shows
    # the denominator "Adults 25+" + the two shares instead. The shares
    # carry derivedFrom metadata so the composer can offer "× Adults 25+"
    # to rebuild a total and substitute the exact count source.
    {
        "out_id": "bachelors_plus",
        "name_prefix": "Adults 25+ with a bachelor's degree",
        "short_suffix": "bachelors plus",
        "unit": "people",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B15003",
        "agg": "sum",
        "extra_tags": [],
        "hidden": True,
    },
    {
        "out_id": "masters_plus",
        "name_prefix": "Adults 25+ with a master's degree",
        "short_suffix": "masters plus",
        "unit": "people",
        "unit_class": "count",
        "fmt_style": "number",
        "decimals": 0,
        "notation": "compact",
        "table": "B15003",
        "agg": "sum",
        "extra_tags": [],
        "hidden": True,
    },
    {
        "out_id": "adults_25plus",
        "name_prefix": "Adults 25+",
        "short_suffix": "adults 25+",
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
        "out_id": "pct_bachelors",
        "name_prefix": "Share of adults 25+ with a bachelor's degree",
        "short_suffix": "bachelor's degree share",
        "unit": "%",
        "unit_class": "rate",
        "fmt_style": "percent",
        "decimals": 1,
        "table": "B15003",
        "agg": "pct",
        "extra_tags": [],
        "numerator": "bachelors_plus",
        "denominator": "adults_25plus",
    },
    {
        "out_id": "pct_masters",
        "name_prefix": "Share of adults 25+ with a master's degree",
        "short_suffix": "master's degree share",
        "unit": "%",
        "unit_class": "rate",
        "fmt_style": "percent",
        "decimals": 1,
        "table": "B15003",
        "agg": "pct",
        "extra_tags": [],
        "numerator": "masters_plus",
        "denominator": "adults_25plus",
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
        "agg": "median_dist",
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
        "agg": "median_dist",
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
        "agg": "median_dist",
        "extra_tags": ["real-estate"],
    },
    # ----- v4 expansion: ratio components + new medians -----
    # Stable-geo rebuild (2026-06): everything here is crosswalk-
    # rebuilt from tract data (agg=sum / median_dist) EXCEPT Gini and
    # the class-of-worker pair — B19083 and C24080 have no tract-level
    # publication in any vintage, so those stay cd_level with the
    # boundary caveat.
    {
        "out_id": "gini_index", "name_prefix": "Income inequality (Gini index)",
        "short_suffix": "Gini index", "unit": "ratio",
        "unit_class": "ratio", "fmt_style": "number", "decimals": 3,
        "table": "B19083", "agg": "cd_level", "extra_tags": [],
    },
    {
        "out_id": "median_year_built",
        "name_prefix": "Median year housing structure built",
        "short_suffix": "median year built", "unit": "year",
        "unit_class": "ratio", "fmt_style": "number", "decimals": 0,
        "table": "B25035", "agg": "median_dist", "extra_tags": ["real-estate"],
    },
    {
        "out_id": "households_above_200k",
        "name_prefix": "Households with income $200k+",
        "short_suffix": "HHs $200k+", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B19001", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "households_total_income",
        "name_prefix": "Total households (income-table denominator)",
        "short_suffix": "HHs total (income)", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B19001", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "workers_wfh",
        "name_prefix": "Workers who work from home",
        "short_suffix": "WFH workers", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B08301", "agg": "sum",
        "extra_tags": ["labor"],
    },
    {
        "out_id": "workers_total_commute",
        "name_prefix": "Total workers (commute-table denominator)",
        "short_suffix": "workers total (commute)", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B08301", "agg": "sum",
        "extra_tags": ["labor"],
    },
    {
        "out_id": "households_no_vehicle",
        "name_prefix": "Households with no vehicle available",
        "short_suffix": "HHs no vehicle", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B08201", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "households_total_vehicle",
        "name_prefix": "Total households (vehicle-table denominator)",
        "short_suffix": "HHs total (vehicle)", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B08201", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "insurance_universe",
        "name_prefix": "Total population (insurance-table denominator)",
        "short_suffix": "pop. total (insurance)", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B27010", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "movers_last_year",
        "name_prefix": "People who moved in the last year",
        "short_suffix": "movers (last yr)", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B07003", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "mobility_universe",
        "name_prefix": "Total population (mobility-table denominator)",
        "short_suffix": "pop. total (mobility)", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B07003", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "born_same_state",
        "name_prefix": "Population born in current state of residence",
        "short_suffix": "born same state", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B05002", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "workers_manufacturing",
        "name_prefix": "Workers in manufacturing",
        "short_suffix": "mfg workers", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "C24070", "agg": "sum",
        "extra_tags": ["labor"],
    },
    {
        "out_id": "workers_total_industry",
        "name_prefix": "Total workers (industry-table denominator)",
        "short_suffix": "workers total (industry)", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "C24070", "agg": "sum",
        "extra_tags": ["labor"],
    },
    {
        "out_id": "workers_class_universe",
        "name_prefix": "Total workers (class-of-worker-table denominator)",
        "short_suffix": "workers total (class)", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "C24080", "agg": "cd_level",
        "extra_tags": ["labor"],
    },
    {
        "out_id": "households_below_25k",
        "name_prefix": "Households with income under $25k",
        "short_suffix": "HHs under $25k", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B19001", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "population_under_18",
        "name_prefix": "Population under 18",
        "short_suffix": "pop. under 18", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B01001", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "population_65_plus",
        "name_prefix": "Population 65 and older",
        "short_suffix": "pop. 65+", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B01001", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "people_uninsured",
        "name_prefix": "People without health insurance coverage",
        "short_suffix": "uninsured", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B27010", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "people_with_disability",
        "name_prefix": "People with a disability",
        "short_suffix": "with disability", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B18101", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "people_disability_universe",
        "name_prefix": "Civilian noninstitutionalized population (disability-table denominator)",
        "short_suffix": "pop. total (disability)", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B18101", "agg": "sum",
        "extra_tags": [],
    },
    {
        "out_id": "workers_government",
        "name_prefix": "Workers in government employment (federal + state + local)",
        "short_suffix": "govt workers", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "C24080", "agg": "cd_level_sum",
        "extra_tags": ["labor", "government"],
    },
    {
        "out_id": "median_commute_minutes",
        "name_prefix": "Median travel time to work",
        "short_suffix": "median commute", "unit": "minutes",
        "unit_class": "ratio", "fmt_style": "number", "decimals": 1,
        "table": "B08303", "agg": "median_dist",
        "extra_tags": [],
    },
]


# ----- Count → share conversions (#102) -----
# Mirrors the AGG_PCT entries in census_acs_cd.py. Each share links back to
# its count numerator + universe denominator via derivedFrom (scale 100,
# emitted by render_yaml), so the composer's rebuild chip can substitute the
# exact count ("× <denominator>"). The numerator counts are hidden from the
# picker (still emitted as data for reconstruction); the denominators stay
# user-facing. `contemporaneous`: False = rides stable 118th-Congress geo (a
# SUM-based numerator); True = rides each year's contemporaneous CD
# boundaries (a CD-level numerator) — only affects the description wording.
_PCT_CONVERSIONS = [
    # (out_id, numerator, denominator, name_prefix, short_suffix, contemporaneous)
    # Mirrors the AGG_PCT entries in census_acs_cd.py — keep the two lists in
    # sync. Since the stable-geo rebuild every shipped share rides tract-based
    # numerators AND denominators (contemporaneous=False across the board);
    # pct_government stays out — C24080 has no tract-level data, so its
    # would-be numerator still rides contemporaneous boundaries.
    ("pct_foreign_born", "foreign_born", "population",
     "Foreign-born share of population", "foreign-born share", False),
    ("pct_workers_wfh", "workers_wfh", "workers_total_commute",
     "Work-from-home share of workers", "work-from-home share", False),
    ("pct_no_vehicle", "households_no_vehicle", "households_total_vehicle",
     "Share of households with no vehicle", "no-vehicle share", False),
    ("pct_movers", "movers_last_year", "mobility_universe",
     "Share who moved in the past year", "recent-mover share", False),
    ("pct_disability", "people_with_disability", "people_disability_universe",
     "Share of people with a disability", "disability share", False),
    ("pct_uninsured", "people_uninsured", "insurance_universe",
     "Uninsured share of population", "uninsured share", False),
    ("pct_manufacturing", "workers_manufacturing", "workers_total_industry",
     "Manufacturing share of workers", "manufacturing share", False),
    ("pct_households_above_200k", "households_above_200k", "households_total_income",
     "Share of households earning $200k+", "$200k+ household share", False),
    ("pct_households_below_25k", "households_below_25k", "households_total_income",
     "Share of households earning under $25k", "under-$25k household share", False),
]
_pct_numerators = {num for _, num, _, _, _, _ in _PCT_CONVERSIONS}
for _oid, _num, _den, _np, _ss, _contemp in _PCT_CONVERSIONS:
    INDICATORS.append({
        "out_id": _oid,
        "name_prefix": _np,
        "short_suffix": _ss,
        "unit": "%",
        "unit_class": "rate",
        "fmt_style": "percent",
        "decimals": 1,
        "table": "",
        "agg": "pct",
        "extra_tags": [],
        "numerator": _num,
        "denominator": _den,
        "contemporaneous": _contemp,
    })
# Hide the numerator counts from the picker (still emitted as data so the
# rebuild chip can substitute them); the denominators stay visible.
for _ind in INDICATORS:
    if _ind["out_id"] in _pct_numerators:
        _ind["hidden"] = True


def slug_to_display(slug: str) -> str:
    """va_08 -> VA-08, ak_al -> AK-AL, dc_98 -> DC-98."""
    return slug.upper().replace("_", "-")


def description_for(ind: dict, slug: str) -> str:
    """Reader-facing description: what the series measures, where it comes
    from, and the one caveat that matters for interpretation (which
    district boundaries each year's figure uses). Deliberately free of
    derivation mechanics (no "recompute", crosswalks, bin counts, table
    cells) — that's implementation detail, not something a reader needs.

    Two boundary regimes:
      - "sum" / "median_dist" hold the geography constant at the 2023
        (118th Congress) district lines across all years.
      - everything else reports each year on the district lines that were
        in effect that year.
    """
    display = slug_to_display(slug)
    # A "pct" rides the geo basis of its numerator/denominator: a SUM-based
    # share (e.g. foreign-born / population) is stable-geo; a CD-level-based
    # share (e.g. work-from-home / total workers) reports on each year's
    # contemporaneous boundaries. The `contemporaneous` flag distinguishes.
    stable_geo = ind["agg"] in ("sum", "median_dist") or (
        ind["agg"] == "pct" and not ind.get("contemporaneous")
    )
    if stable_geo:
        return (
            f"{ind['name_prefix']} for {display}, on 2023 (118th Congress) "
            f"congressional-district boundaries held constant across years. "
            f"American Community Survey (ACS) 5-year estimates, released annually."
        )
    return (
        f"{ind['name_prefix']} for {display}. American Community Survey (ACS) "
        f"5-year estimates, released annually. Each year reflects the "
        f"congressional-district boundaries then in effect."
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
        # Quote units that aren't a plain word — e.g. "%", which YAML treats
        # as a reserved directive indicator and js-yaml (astro) rejects bare.
        f'unit: "{ind["unit"]}"' if not ind["unit"].isalnum() else f"unit: {ind['unit']}",
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
    if ind.get("hidden"):
        lines.append("hidden: true")
    # Rate series: link back to the count + universe it's derived from so
    # the composer can offer "× Adults 25+" and substitute the exact count.
    # Stored as a percent (num / denom * 100), hence scale: 100.
    if ind.get("numerator") and ind.get("denominator"):
        lines.append("derivedFrom:")
        lines.append(f"  numerator: acs_cd/{ind['numerator']}_{slug}")
        lines.append(f"  denominator: acs_cd/{ind['denominator']}_{slug}")
        lines.append("  scale: 100")
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
