"""
Aggregate per-CD ACS data files into per-state ACS data, so every series
the CD pipeline produces has a state-level equivalent without needing a
second Census API trip.

What this writes
----------------
For each of the 13 ACS indicators × 51 states (50 + DC):
  - public/data/acs_state/<series>_<st>.json (full timeseries)
  - public/data/acs_state/<series>_<st>.summary.json (built later by
    build_summaries.py)

Aggregation strategy
--------------------
Per indicator type:

  * Count-aggregable (population, poverty_count, foreign_born,
    bachelors_plus, masters_plus, owner_occupied, renter_occupied,
    veterans, broadband_households)
        state_value(t) = SUM over CDs of cd_value(t)
    Exact. The same arithmetic that defines the state total from its
    components. Identity copy for single-CD states.

  * Median-style (median_hh_income, median_age, median_home_value,
    median_gross_rent)
        state_value(t) = SUM(cd_value(t) * cd_population(t)) /
                         SUM(cd_population(t))
    Population-weighted average of the CD medians. NOT the true state
    median — Census recomputes that from raw distribution tables at
    state level. For single-CD states the weighted average == the CD's
    median (still exact). For multi-CD states this is a documented
    approximation, called out in the source YAML's description.

    To replace with API-fetched true state medians, run a follow-up
    pipeline (census_acs_state.py) when CENSUS_API_KEY is available.

Single-CD states (AK, DE, ND, SD, VT, WY) and DC
------------------------------------------------
census_acs_cd.py writes their state-level data JSONs directly into
public/data/acs_state/ (their CD-level YAMLs are retired, so there are
no acs_cd series to aggregate from and list_cds_per_state() never even
yields these states). This script therefore never writes DATA for them
— but it does emit their source YAMLs, one per indicator whose data
JSON is already on disk, so their catalog parity-matches the multi-CD
states. See emit_single_cd_state_yamls().

This script is idempotent: re-running it overwrites the JSONs but
doesn't touch source YAMLs that already exist. To regenerate YAMLs
after a description-text tweak, delete the relevant src/content/
sources/acs_state/<series>_<st>.yaml first.

Run with: ``python pipelines/derive_acs_state_from_cd.py``
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import _env  # noqa: F401 — loads .env (CENSUS_API_KEY) for the median fetch
from common import write_timeseries, utc_now_iso
from census_acs_cd import acs_fetch, STATE_ABBR

# States ARE a native Census median geography, so for these indicators we fetch
# the TRUE state-level median directly (var _001E) instead of the population-
# weighted average of CD medians (which is only an approximation). Keyed by
# out_id -> direct estimate variable. median_commute (B08303) has no direct
# median var (it's a travel-time distribution), so it stays a CD rollup.
TRUE_MEDIAN_VARS: dict[str, str] = {
    "median_hh_income": "B19013_001E",
    "median_age": "B01002_001E",
    "median_home_value": "B25077_001E",
    "median_gross_rent": "B25064_001E",
    "gini_index": "B19083_001E",
    "median_year_built": "B25035_001E",
}


def fetch_true_state_medians(
    years: range, key: str,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """{out_id: {state_abbr: [{t, v}]}} of true state medians from the Census
    API (one call per year per var, geo=state:*). Skips negative sentinels."""
    decimals = {ind["out_id"]: ind["decimals"] for ind in MEDIAN_INDICATORS}
    out: dict[str, dict[str, list[dict[str, Any]]]] = {
        oid: defaultdict(list) for oid in TRUE_MEDIAN_VARS
    }
    for year in years:
        for oid, var in TRUE_MEDIAN_VARS.items():
            rows = acs_fetch(year, [var], "state:*", key)
            if not rows or len(rows) < 2:
                continue
            hdr = rows[0]
            try:
                vi, fi = hdr.index(var), hdr.index("state")
            except ValueError:
                continue
            for r in rows[1:]:
                abbr = STATE_ABBR.get(r[fi])
                if not abbr or not r[vi]:
                    continue
                try:
                    v = float(r[vi])
                except ValueError:
                    continue
                if v <= 0:  # Census negative sentinels = missing / suppressed
                    continue
                out[oid][abbr].append(
                    {"t": f"{year}-12-31", "v": round(v, decimals[oid])}
                )
    for oid in out:
        for abbr in out[oid]:
            out[oid][abbr].sort(key=lambda p: p["t"])
    return out


ROOT = Path(__file__).resolve().parent.parent
CD_DATA = ROOT / "public" / "data" / "acs_cd"
STATE_DATA = ROOT / "public" / "data" / "acs_state"
STATE_SOURCES = ROOT / "src" / "content" / "sources" / "acs_state"


# Indicator definitions — mirrors _generate_acs_sources.py so the
# resulting YAMLs match the CD-level ones in style.
COUNT_INDICATORS: list[dict[str, Any]] = [
    {
        "out_id": "population", "name_prefix": "Total population",
        "short_suffix": "population", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B01003", "extra_tags": [],
    },
    {
        "out_id": "poverty_count", "name_prefix": "People in poverty",
        "short_suffix": "poverty count", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B17001", "extra_tags": [],
    },
    {
        "out_id": "foreign_born", "name_prefix": "Foreign-born population",
        "short_suffix": "foreign-born", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B05002", "extra_tags": [],
    },
    {
        "out_id": "bachelors_plus",
        "name_prefix": "Adults 25+ with bachelor's degree",
        "short_suffix": "bachelors plus", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B15003", "extra_tags": [],
    },
    {
        "out_id": "masters_plus",
        "name_prefix": "Adults 25+ with master's degree",
        "short_suffix": "masters plus", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B15003", "extra_tags": [],
    },
    {
        "out_id": "owner_occupied",
        "name_prefix": "Owner-occupied housing units",
        "short_suffix": "owner-occupied", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B25003",
        "extra_tags": ["real-estate"],
    },
    {
        "out_id": "renter_occupied",
        "name_prefix": "Renter-occupied housing units",
        "short_suffix": "renter-occupied", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B25003",
        "extra_tags": ["real-estate"],
    },
    {
        "out_id": "veterans",
        "name_prefix": "Civilian veteran population (18+)",
        "short_suffix": "veterans", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B21001", "extra_tags": [],
    },
    {
        "out_id": "broadband_households",
        "name_prefix": "Households with broadband internet",
        "short_suffix": "broadband", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B28002", "extra_tags": [],
    },
    # ----- v4 expansion: ratio-component counts -----
    {
        "out_id": "households_above_200k",
        "name_prefix": "Households with income $200k+",
        "short_suffix": "HHs $200k+", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B19001", "extra_tags": [],
    },
    {
        "out_id": "households_total_income",
        "name_prefix": "Total households (income-table denominator)",
        "short_suffix": "HHs total (income)", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B19001", "extra_tags": [],
    },
    {
        "out_id": "workers_wfh",
        "name_prefix": "Workers who work from home",
        "short_suffix": "WFH workers", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B08301", "extra_tags": ["labor"],
    },
    {
        "out_id": "workers_total_commute",
        "name_prefix": "Total workers (commute-table denominator)",
        "short_suffix": "workers total (commute)", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B08301", "extra_tags": ["labor"],
    },
    {
        "out_id": "households_no_vehicle",
        "name_prefix": "Households with no vehicle available",
        "short_suffix": "HHs no vehicle", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B08201", "extra_tags": [],
    },
    {
        "out_id": "households_total_vehicle",
        "name_prefix": "Total households (vehicle-table denominator)",
        "short_suffix": "HHs total (vehicle)", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B08201", "extra_tags": [],
    },
    {
        "out_id": "insurance_universe",
        "name_prefix": "Total population (insurance-table denominator)",
        "short_suffix": "pop. total (insurance)", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B27010", "extra_tags": [],
    },
    {
        "out_id": "movers_last_year",
        "name_prefix": "People who moved in the last year",
        "short_suffix": "movers (last yr)", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B07003", "extra_tags": [],
    },
    {
        "out_id": "mobility_universe",
        "name_prefix": "Total population (mobility-table denominator)",
        "short_suffix": "pop. total (mobility)", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B07003", "extra_tags": [],
    },
    {
        "out_id": "born_same_state",
        "name_prefix": "Population born in current state of residence",
        "short_suffix": "born same state", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B05002", "extra_tags": [],
    },
    {
        "out_id": "workers_manufacturing",
        "name_prefix": "Workers in manufacturing",
        "short_suffix": "mfg workers", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "C24070", "extra_tags": ["labor"],
    },
    {
        "out_id": "workers_total_industry",
        "name_prefix": "Total workers (industry-table denominator)",
        "short_suffix": "workers total (industry)", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "C24070", "extra_tags": ["labor"],
    },
    {
        "out_id": "workers_class_universe",
        "name_prefix": "Total workers (class-of-worker-table denominator)",
        "short_suffix": "workers total (class)", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "C24080", "extra_tags": ["labor"],
    },
    {
        "out_id": "households_below_25k",
        "name_prefix": "Households with income under $25k",
        "short_suffix": "HHs under $25k", "unit": "households",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B19001", "extra_tags": [],
    },
    {
        "out_id": "population_under_18",
        "name_prefix": "Population under 18",
        "short_suffix": "pop. under 18", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B01001", "extra_tags": [],
    },
    {
        "out_id": "population_65_plus",
        "name_prefix": "Population 65 and older",
        "short_suffix": "pop. 65+", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B01001", "extra_tags": [],
    },
    {
        "out_id": "people_uninsured",
        "name_prefix": "People without health insurance coverage",
        "short_suffix": "uninsured", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B27010", "extra_tags": [],
    },
    {
        "out_id": "people_with_disability",
        "name_prefix": "People with a disability",
        "short_suffix": "with disability", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B18101", "extra_tags": [],
    },
    {
        "out_id": "people_disability_universe",
        "name_prefix": "Civilian noninstitutionalized population (disability-table denominator)",
        "short_suffix": "pop. total (disability)", "unit": "people",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "B18101", "extra_tags": [],
    },
    {
        "out_id": "workers_government",
        "name_prefix": "Workers in government employment (federal + state + local)",
        "short_suffix": "govt workers", "unit": "workers",
        "unit_class": "count", "fmt_style": "number", "decimals": 0,
        "notation": "compact", "table": "C24080",
        "extra_tags": ["labor", "government"],
    },
]

MEDIAN_INDICATORS: list[dict[str, Any]] = [
    {
        "out_id": "median_hh_income",
        "name_prefix": "Median household income",
        "short_suffix": "median hh income", "unit": "USD",
        "unit_class": "currency", "fmt_style": "currency",
        "currency": "USD", "decimals": 0, "notation": "compact",
        "table": "B19013", "extra_tags": [],
    },
    {
        "out_id": "median_age", "name_prefix": "Median age",
        "short_suffix": "median age", "unit": "years",
        "unit_class": "ratio", "fmt_style": "number", "decimals": 1,
        "table": "B01002", "extra_tags": [],
    },
    {
        "out_id": "median_home_value",
        "name_prefix": "Median home value (owner-occupied)",
        "short_suffix": "median home value", "unit": "USD",
        "unit_class": "currency", "fmt_style": "currency",
        "currency": "USD", "decimals": 0, "notation": "compact",
        "table": "B25077", "extra_tags": ["real-estate"],
    },
    {
        "out_id": "median_gross_rent",
        "name_prefix": "Median gross rent",
        "short_suffix": "median gross rent", "unit": "USD",
        "unit_class": "currency", "fmt_style": "currency",
        "currency": "USD", "decimals": 0, "notation": "compact",
        "table": "B25064", "extra_tags": ["real-estate"],
    },
    # ----- v4 expansion: medians + Gini -----
    # Aggregated via population-weighted average across CDs at state
    # level — an approximation, not the true state value. Gini is
    # treated as a "median-style" indicator here because it doesn't
    # sum across CDs the way a count does.
    {
        "out_id": "gini_index",
        "name_prefix": "Income inequality (Gini index)",
        "short_suffix": "Gini index", "unit": "ratio",
        "unit_class": "ratio", "fmt_style": "number", "decimals": 3,
        "table": "B19083", "extra_tags": [],
    },
    {
        "out_id": "median_year_built",
        "name_prefix": "Median year housing structure built",
        "short_suffix": "median year built", "unit": "year",
        "unit_class": "ratio", "fmt_style": "number", "decimals": 0,
        "table": "B25035", "extra_tags": ["real-estate"],
    },
    {
        "out_id": "median_commute_minutes",
        "name_prefix": "Median travel time to work",
        "short_suffix": "median commute", "unit": "minutes",
        "unit_class": "ratio", "fmt_style": "number", "decimals": 1,
        "table": "B08303", "extra_tags": [],
    },
]

ALL_INDICATORS = COUNT_INDICATORS + MEDIAN_INDICATORS


# Single-CD states route their CD data directly to acs_state/ via
# census_acs_cd.py. Skip their DATA writes here so this script doesn't
# overwrite census_acs_cd.py's writes with an empty/single-point
# aggregate (there are no acs_cd JSONs to read for these states).
# Their source YAMLs, however, are emitted by this script — see
# emit_single_cd_state_yamls(). Nothing else generates them: their
# CD-level YAMLs are retired, so list_cds_per_state() doesn't yield
# these states and the main aggregation loop never visits them.
SINGLE_CD_STATES = frozenset({"ak", "de", "nd", "sd", "vt", "wy", "dc"})


_SLUG_RX = re.compile(r"^(?P<series>.+)_(?P<st>[a-z]{2})_(?P<dst>[a-z0-9]{2})$")


def list_cds_per_state() -> dict[str, list[str]]:
    """Walk acs_cd YAMLs to enumerate which districts exist per state.
    Pulls from sources/acs_cd so the count is stable regardless of
    whether any vintages happen to be missing for a given CD."""
    out: dict[str, set[str]] = defaultdict(set)
    src_root = ROOT / "src" / "content" / "sources" / "acs_cd"
    for p in src_root.glob("*.yaml"):
        m = _SLUG_RX.match(p.stem)
        if m:
            out[m.group("st")].add(m.group("dst"))
    return {st: sorted(ds) for st, ds in out.items()}


def load_points(path: Path) -> list[dict[str, Any]] | None:
    """Read a timeseries JSON's points array. Returns None on miss."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    points = data.get("points")
    if not isinstance(points, list):
        return None
    return points


def aggregate_state(
    indicator: dict[str, Any],
    state: str,
    districts: list[str],
    pop_lookup: dict[tuple[str, str], dict[str, float]],
    is_median: bool,
) -> list[dict[str, Any]]:
    """
    Aggregate a single indicator across one state's CDs.

      - Counts: state_value(t) = SUM cd_value(t)
      - Medians: weighted by CD population at same timestamp:
        state_value(t) = SUM(cd_value(t) * cd_pop(t)) / SUM(cd_pop(t))

    Skips timestamps where no CD has a value. For medians, skips
    timestamps with zero total weight (e.g. all CDs missing population
    for that vintage).
    """
    # Collect per-timestamp values across CDs.
    by_t: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for dst in districts:
        path = CD_DATA / f"{indicator['out_id']}_{state}_{dst}.json"
        points = load_points(path)
        if not points:
            continue
        for p in points:
            t = p.get("t")
            v = p.get("v")
            if isinstance(t, str) and isinstance(v, (int, float)):
                by_t[t].append((float(v), dst))

    out: list[dict[str, Any]] = []
    for t in sorted(by_t.keys()):
        entries = by_t[t]
        if not is_median:
            total = sum(v for v, _ in entries)
            out.append({"t": t, "v": round(total)})
            continue
        # Median branch: population-weighted average over the CDs
        # that have a value for this timestamp. If a CD has the
        # median but not the population for this t, skip its weight
        # (drops it from the average rather than weight it as 0).
        num = 0.0
        den = 0.0
        for v, dst in entries:
            w = pop_lookup.get((state, dst), {}).get(t)
            if w is None or w <= 0:
                continue
            num += v * w
            den += w
        if den > 0:
            out.append({"t": t, "v": round(num / den, indicator["decimals"])})
    return out


def description_for(indicator: dict[str, Any], state: str, n_cds: int) -> str:
    """One-sentence-ish description matching the CD-level YAML tone."""
    abbr = state.upper()
    name = indicator["name_prefix"]
    table = indicator["table"]
    if indicator in COUNT_INDICATORS:
        if n_cds == 1:
            return (
                f"{name} for {abbr} (statewide). From the American "
                f"Community Survey 5-year estimates (table {table}), "
                f"released annually. {abbr} has a single congressional "
                f"district, so this is identical to the district-level "
                f"series."
            )
        return (
            f"{name} for {abbr} (statewide). Aggregated from the "
            f"{n_cds} congressional-district series for this state "
            f"(118th-Congress boundaries) via direct sum. Underlying "
            f"source, American Community Survey 5-year estimates "
            f"(table {table}), released annually."
        )
    # Median branch.
    if n_cds == 1:
        return (
            f"{name} for {abbr} (statewide). From the American "
            f"Community Survey 5-year estimates (table {table}), "
            f"released annually. {abbr} has a single congressional "
            f"district, so this is identical to the district-level "
            f"series."
        )
    return (
        f"{name} for {abbr} (statewide), from the American Community "
        f"Survey 5-year estimates (table {table}), released annually."
    )


def render_yaml(indicator: dict[str, Any], state: str, n_cds: int) -> str:
    abbr = state.upper()
    name = f"{indicator['name_prefix']} — {abbr}"
    short = f"{abbr} {indicator['short_suffix']}"
    desc = description_for(indicator, state, n_cds)
    tags = ["government", "us"] + list(indicator.get("extra_tags", []))

    lines: list[str] = [
        f"name: {name}",
        f"shortName: {short}",
        f"description: {desc}",
        "kind: timeseries",
        "pipeline: derive_acs_state_from_cd",
        f"dataFile: data/acs_state/{indicator['out_id']}_{state}.json",
        'supportedDeltas: ["5y", "10y"]',
        f"unit: {indicator['unit']}",
        "formatting:",
        f"  style: {indicator['fmt_style']}",
    ]
    if indicator.get("currency"):
        lines.append(f"  currency: {indicator['currency']}")
    lines.append(f"  decimals: {indicator['decimals']}")
    if indicator.get("notation"):
        lines.append(f"  notation: {indicator['notation']}")
    lines.append("emphasis: change")
    lines.append("provenance:")
    lines.append("  provider: US Census Bureau (ACS 5-year)")
    lines.append(f"  series: {indicator['out_id']}_state")
    lines.append("  url: https://api.census.gov/data/2022/acs/acs5")
    lines.append("  license: Public domain (US government data)")
    lines.append("tags:")
    for tag in tags:
        lines.append(f"  - {tag}")
    if indicator.get("unit_class"):
        lines.append(f"unitClass: {indicator['unit_class']}")
    return "\n".join(lines) + "\n"


def emit_single_cd_state_yamls() -> tuple[int, int, int]:
    """
    Emit source YAMLs for the single-CD states (AK, DE, ND, SD, VT, WY)
    and DC.

    Their data JSONs are written straight into public/data/acs_state/
    by census_acs_cd.py (the CD-level YAMLs for these states are
    retired, so the aggregation loop above never visits them), but
    until this pass nothing emitted their source YAMLs — leaving the
    data orphaned and the states missing from the catalog for every
    indicator added after the original 13.

    Emits one YAML per indicator whose data JSON exists on disk with a
    non-empty points array (n_cds=1 wording: "identical to the
    district-level series"). Never writes data files, and never
    overwrites a YAML that already exists.

    Returns (written, skipped_existing, skipped_no_data).
    """
    STATE_SOURCES.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped_existing = 0
    skipped_no_data = 0
    for state in sorted(SINGLE_CD_STATES):
        for indicator in ALL_INDICATORS:
            data_path = STATE_DATA / f"{indicator['out_id']}_{state}.json"
            points = load_points(data_path)
            if not points:
                # No data on disk (e.g. workers_class_universe /
                # workers_government have no data for any state, and a
                # few legacy AGG_SUM indicators were never fetched for
                # DC). No data -> no YAML, same as the multi-CD loop.
                skipped_no_data += 1
                continue
            yaml_path = STATE_SOURCES / f"{indicator['out_id']}_{state}.yaml"
            if yaml_path.exists():
                skipped_existing += 1
                continue
            yaml_path.write_text(
                render_yaml(indicator, state, 1),
                encoding="utf-8",
            )
            written += 1
    return written, skipped_existing, skipped_no_data


def main() -> int:
    STATE_DATA.mkdir(parents=True, exist_ok=True)
    STATE_SOURCES.mkdir(parents=True, exist_ok=True)

    cds_per_state = list_cds_per_state()
    if not cds_per_state:
        print("No CD source YAMLs found; nothing to aggregate.", file=sys.stderr)
        return 1
    print(f"Aggregating {sum(len(d) for d in cds_per_state.values())} "
          f"CDs across {len(cds_per_state)} states/DC...", flush=True)

    # Build per-CD population lookup once, used for median weighting.
    # Keyed by (state, dst) -> {timestamp: population}.
    pop_lookup: dict[tuple[str, str], dict[str, float]] = {}
    for state, districts in cds_per_state.items():
        for dst in districts:
            path = CD_DATA / f"population_{state}_{dst}.json"
            points = load_points(path)
            if not points:
                continue
            by_t = {p["t"]: float(p["v"]) for p in points
                    if isinstance(p.get("t"), str) and isinstance(p.get("v"), (int, float))}
            pop_lookup[(state, dst)] = by_t

    # True state medians (direct Census state fetch) for indicators with a
    # native median var — replaces the CD population-weighted approximation.
    import os
    census_key = os.environ.get("CENSUS_API_KEY", "")
    true_medians = (
        fetch_true_state_medians(range(2010, 2025), census_key)
        if census_key
        else {}
    )
    if not census_key:
        print("WARNING: CENSUS_API_KEY unset; medians fall back to CD rollups.",
              file=sys.stderr)

    written_json = 0
    written_yaml = 0
    skipped_yaml = 0
    series_emitted_per_indicator: dict[str, int] = defaultdict(int)
    for indicator in ALL_INDICATORS:
        is_median = indicator in MEDIAN_INDICATORS
        for state, districts in cds_per_state.items():
            # Skip single-CD states — census_acs_cd.py already wrote
            # their state-level data directly (with full multi-vintage
            # coverage). Aggregating from non-existent acs_cd JSONs
            # would write an empty/single-point series and clobber it.
            if state in SINGLE_CD_STATES:
                continue
            # Prefer the true direct state median where Census publishes one;
            # otherwise aggregate from the CDs (counts; commute).
            true_series = true_medians.get(indicator["out_id"], {}).get(state)
            points = (
                true_series
                if true_series is not None
                else aggregate_state(indicator, state, districts, pop_lookup, is_median)
            )
            if not points:
                continue
            # Write data JSON via write_timeseries for consistency with the
            # other pipelines (gets the same "id/name/kind/lastUpdated"
            # envelope and atomic-write behavior).
            write_timeseries(
                pipeline="acs_state",
                series_id=f"{indicator['out_id']}_{state}",
                name=f"{indicator['name_prefix']} — {state.upper()}",
                points=points,
                unit=indicator["unit"],
            )
            written_json += 1
            series_emitted_per_indicator[indicator["out_id"]] += 1
            # Source YAML — only if absent (don't clobber hand-edits).
            yaml_path = STATE_SOURCES / f"{indicator['out_id']}_{state}.yaml"
            if yaml_path.exists():
                skipped_yaml += 1
                continue
            yaml_path.write_text(
                render_yaml(indicator, state, len(districts)),
                encoding="utf-8",
            )
            written_yaml += 1

    single_written, single_existing, single_no_data = emit_single_cd_state_yamls()

    print(f"\nWrote {written_json} state-level data JSONs.")
    print(f"Wrote {written_yaml} new source YAMLs ({skipped_yaml} already existed).")
    print(f"Single-CD states/DC: wrote {single_written} new source YAMLs "
          f"({single_existing} already existed, "
          f"{single_no_data} indicators had no data JSON).")
    print(f"\n{'indicator':<25}  {'series':>6}")
    print(f"{'-'*25}  {'-'*6}")
    for ind in ALL_INDICATORS:
        print(f"{ind['out_id']:<25}  {series_emitted_per_indicator.get(ind['out_id'], 0):>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
