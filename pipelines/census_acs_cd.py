"""
Census American Community Survey (ACS) 5-year estimates, aggregated to
stable-geography (118th-Congress) congressional districts across all
~13 published vintages.

Pipeline architecture:

  1. Read pre-built crosswalks (pipelines/_crosswalks/) that map 2010
     and 2020 tract GEOIDs to 118th-Congress districts with population
     weights. These were produced by build_crosswalks.py from Census
     BAFs and t10t20 relationship files; they're stable until the
     119th Congress takes effect.

  2. For each ACS vintage (2010-2022), fetch tract-level ACS data.
     Vintages 2010-2021 use 2010 tract boundaries; vintage 2022+ uses
     2020 tract boundaries. We auto-select the right crosswalk.

  3. Aggregate by 118th CD using the crosswalk weights:
        - Counts (population, poverty, foreign-born, WFH workers,
          uninsured, movers, etc.) sum cleanly:
          CD_total = sum(tract_value × tract_weight) across tracts.
        - Medians (household income, age, home value, gross rent,
          year built, commute) are recomputed from each table's
          distribution bins at tract level: sum bin counts across
          CD-assigned tracts, then interpolate the weighted median
          from the aggregated distribution. True CD-level medians on
          stable geography; values are bin-interpolated, so they
          differ slightly from Census's published (microdata-based)
          medians. Bin schemas changed across vintages for home
          value / rent / year built — handled by per-vintage bin
          schedules.
        - The ONLY remaining contemporaneous-CD indicators are the
          ones Census doesn't publish at tract level in any vintage:
          gini_index (B19083, microdata-only) and the class-of-worker
          pair (C24080: workers_government + its universe). Those
          ride vintage boundaries, with the documented caveat.

  4. Write per-CD time series JSON files.

Requires CENSUS_API_KEY env var (free registration). When unset, the
pipeline no-ops with a clear status message.

Run with: ``CENSUS_API_KEY=<key> python pipelines/census_acs_cd.py``.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import _env  # noqa: F401 — load .env so CENSUS_API_KEY is available locally
from _cache import cache_get, cache_put
from common import write_timeseries


REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSWALK_DIR = REPO_ROOT / "pipelines" / "_crosswalks"


# ---------------------------------------------------------------------
# Cache policy
# ---------------------------------------------------------------------
# ACS5 vintages don't revise once published. The per-(year, state)
# tract pull is the dominant cost — 13 vintages × 51 states = 663 API
# calls per fresh run. Caching turns that into a one-time bulk fetch,
# with subsequent runs only re-fetching the most-recent vintage(s)
# where revisions are theoretically possible during the release
# window.
#
#   - vintage >= 2 years old: effectively permanent cache (the
#     underlying data genuinely never changes; cache invalidation is
#     "rm -rf pipelines/_cache/acs_cd_tract").
#   - vintage in the most recent 2 years: 30-day cache window
#     (Census sometimes issues corrections within months of release).
#
# Cache keys embed a hash of the variable-list so a future spec
# expansion that requests new cells auto-invalidates stale caches.
# A `--force-refetch` flag is intentionally NOT added here — operators
# who really need to bypass cache should delete the cache directory.

_CACHE_BUCKET_TRACT = "acs_cd_tract"
_CACHE_BUCKET_DISTRICT = "acs_cd_district"


def _cache_max_age_days(year: int) -> float:
    """Immutable vintages get permanent storage; recent vintages get
    a 30-day TTL to pick up the rare upstream correction."""
    current_year = datetime.now().year
    if current_year - year >= 2:
        return 365.0 * 100  # effectively permanent
    return 30.0


def _vars_hash(var_codes: list[str]) -> str:
    """Stable 10-char hash over the (sorted) variable set. Embedded in
    cache keys so a different var-list yields a different cache file."""
    h = hashlib.sha1(",".join(sorted(var_codes)).encode("utf-8"))
    return h.hexdigest()[:10]


# Module-level cache-hit counters; reset at start of main(), printed
# at end of main() as a one-line health check.
_cache_stats = {"tract_hit": 0, "tract_miss": 0, "cd_hit": 0, "cd_miss": 0}

# Vintages we pull. Each is published as its own /data/<year>/acs/acs5
# endpoint. Range starts at 2010 (the earliest ACS5 with CD-level data)
# and goes to 2022 (the latest released as of mid-2026). Extending to
# new vintages is one-line additions when they release each December.
ACS_VINTAGES = list(range(2010, 2023))

# The boundary at which ACS switched from 2010-decennial tract
# definitions to 2020-decennial tract definitions. Set empirically:
# ACS 2022 (covering 2018-2022) was the first vintage released using
# 2020-boundary tract IDs. Earlier vintages use 2010-boundary tracts.
TRACT2020_FIRST_VINTAGE = 2022

# Census's URL path changed mid-decade: 2010-2014 ACS5 originally
# lived at /data/{year}/acs5/ (no /acs/ subfolder) with 2015+ at
# /data/{year}/acs/acs5/. Census has since RETIRED the legacy path —
# verified 2026-06-12: /data/2010..2014/acs5 returns 404 while
# /data/{year}/acs/acs5 serves every vintage 2010-2022 with 200s for
# both tract and congressional-district geographies. Permanent caching
# of old vintages masked the breakage until a variable-list change
# forced fresh fetches. Single modern path for all years.
def acs_base(year: int) -> str:
    return f"https://api.census.gov/data/{year}/acs/acs5"


# ---------------------------------------------------------------------
# Indicator definitions
# ---------------------------------------------------------------------

# Aggregation strategy per indicator — `agg` describes how the value is
# obtained AT A PUBLISHED GEOGRAPHY. It is shared with the metro +
# national pipelines (census_acs_metro.py / census_acs_national.py),
# which fetch each indicator directly at their own geography:
#   "sum"                       single count cell
#   "cd_level"                  single cell (counts OR published medians)
#   "cd_level_sum"              sum of multiple cells
#   "median_from_distribution"  single published-median cell (B19013) —
#                               named for the CD pipeline's historical
#                               handling; metro/national fetch var_code
#   "median_from_cd_distribution"  median interpolated from bin cells
#                               fetched at the pipeline's own geography
#                               (used where Census publishes no median
#                               table, e.g. B08303 travel time)
#   "pct"                       numerator / denominator * 100 over two
#                               already-computed indicators (same geo
#                               basis required; numerator may be kept
#                               internal via emit=False)
#
# THE CD PIPELINE OVERRIDES `agg` with the cd_basis field below: any
# indicator with a cd_basis is rebuilt from TRACT-level data through
# the 118th-Congress crosswalk (stable geography), regardless of its
# `agg`. Indicators without a cd_basis fall back to contemporaneous
# CD-level fetches keyed off `agg` — as of the stable-geo rebuild
# that's only the tables Census doesn't publish at tract level
# (B19083 Gini, C24080 class of worker).
AGG_SUM = "sum"
AGG_CD_LEVEL = "cd_level"
AGG_CD_LEVEL_SUM = "cd_level_sum"
AGG_MEDIAN_DIST = "median_from_distribution"
AGG_MEDIAN_CD_DIST = "median_from_cd_distribution"
AGG_PCT = "pct"

# CD-pipeline basis overrides (census_acs_cd.py only):
#   "tract"        crosswalk-sum var_code (or sum_codes) at tract level
#   "tract_median" crosswalk-sum the cd_bin_schedule's bin cells at
#                  tract level, then interpolate the median
CD_BASIS_TRACT = "tract"
CD_BASIS_TRACT_MEDIAN = "tract_median"


@dataclass
class AcsVar:
    out_id: str
    var_code: str           # primary variable code (Census table cell)
    name_prefix: str
    unit: str
    decimals: int
    agg: str                # one of AGG_* (metro/national fetch basis)
    # Bin list for median-from-distribution aggregations: entries are
    # (cell, lower, upper) where `cell` is a var code OR a tuple of var
    # codes whose counts merge into one bin (e.g. the male + female
    # cells of an age bracket). The top bin's upper is typically
    # open-ended upstream; we use a synthetic cap (~2x lower bound,
    # Pareto-style convention) for interpolation.
    bins: list[tuple[object, float, float]] = field(default_factory=list)
    # For cd_level_sum agg, list of Census variable codes whose values
    # get summed at fetch time. var_code is left blank in that case;
    # the sum becomes the indicator's value.
    sum_codes: list[str] = field(default_factory=list)
    # For AGG_PCT: out_ids of the numerator and denominator indicators
    # (both must be computed earlier this vintage, same geo basis).
    numerator_id: str = ""
    denominator_id: str = ""
    # When False, the indicator is computed but NOT written as a user-
    # facing series — used to keep a raw count internal as a percentage's
    # numerator without surfacing it in the picker.
    emit: bool = True
    # ----- CD-pipeline stable-geography overrides (this file only) -----
    # cd_basis: CD_BASIS_TRACT / CD_BASIS_TRACT_MEDIAN / "" (= follow
    # `agg` at contemporaneous CD level). Metro/national ignore these.
    cd_basis: str = ""
    # For CD_BASIS_TRACT_MEDIAN: vintage-keyed bin tables, entries
    # (first_vintage, bins) ascending — Census re-cut the home-value /
    # rent / year-built bins over time. resolve_cd_bins() picks the
    # entry with the largest first_vintage <= year.
    cd_bin_schedule: list[tuple[int, list]] = field(default_factory=list)
    # First ACS5 vintage with TRACT-level data for this indicator's
    # table (0 = all vintages). Pre-gates the fetch so we don't probe
    # vintages where Census never published the table at tract level
    # (B27010 insurance: 2013+; B18101 disability: 2012+).
    first_tract_vintage: int = 0


# B19001 = Household Income in the Past 12 Months. Cells 002-017 are
# the 16 income bins; 001 is the total household count. Bounds in 2020
# dollars per ACS specification.
B19001_BINS = [
    ("B19001_002E",      0,  9_999),
    ("B19001_003E", 10_000, 14_999),
    ("B19001_004E", 15_000, 19_999),
    ("B19001_005E", 20_000, 24_999),
    ("B19001_006E", 25_000, 29_999),
    ("B19001_007E", 30_000, 34_999),
    ("B19001_008E", 35_000, 39_999),
    ("B19001_009E", 40_000, 44_999),
    ("B19001_010E", 45_000, 49_999),
    ("B19001_011E", 50_000, 59_999),
    ("B19001_012E", 60_000, 74_999),
    ("B19001_013E", 75_000, 99_999),
    ("B19001_014E", 100_000, 124_999),
    ("B19001_015E", 125_000, 149_999),
    ("B19001_016E", 150_000, 199_999),
    # Top bin is "200,000 or more". For weighted-median interpolation
    # we cap at 2x the lower bound (a Pareto-distribution-style
    # convention used by Census's own median estimates). True top-bin
    # median is unbounded; this is best-available approximation.
    ("B19001_017E", 200_000, 400_000),
]


# B08303 = "Travel Time to Work". Cells 002-013 are the 12 commute-time
# bins; 001 is the total. Used to compute median commute time from the
# distribution (linear interpolation across the bin containing the
# median). Bounds are minutes.
B08303_BINS = [
    ("B08303_002E",  0,  5),    # <5 minutes
    ("B08303_003E",  5,  9),
    ("B08303_004E", 10, 14),
    ("B08303_005E", 15, 19),
    ("B08303_006E", 20, 24),
    ("B08303_007E", 25, 29),
    ("B08303_008E", 30, 34),
    ("B08303_009E", 35, 39),
    ("B08303_010E", 40, 44),
    ("B08303_011E", 45, 59),
    ("B08303_012E", 60, 89),
    # Top bin "90+ minutes" — interpolation cap at 2x the lower bound
    # (Pareto convention, same as we use for the top income bin).
    ("B08303_013E", 90, 180),
]


def bin_cell_codes(cell) -> tuple[str, ...]:
    """Normalize a bin entry's cell field: a bare var code or a tuple of
    var codes (multi-cell bins, e.g. male + female age cells)."""
    return cell if isinstance(cell, tuple) else (cell,)


def resolve_cd_bins(v: "AcsVar", year: int) -> list:
    """The bin table in effect for `year` from the indicator's
    vintage-keyed schedule (largest first_vintage <= year), or []."""
    chosen: list = []
    for first_year, bins in v.cd_bin_schedule:
        if year >= first_year:
            chosen = bins
    return chosen


# B01001 = Sex by Age. 23 age brackets published per sex (male cells
# 003-025, female 027-049, parallel). Each bin merges the male + female
# cells for that bracket. Bracket layout verified identical across the
# 2010 and 2022 vintages. Top bin "85+" capped at 95 for interpolation.
B01001_AGE_BINS = [
    (("B01001_003E", "B01001_027E"), 0, 5),
    (("B01001_004E", "B01001_028E"), 5, 10),
    (("B01001_005E", "B01001_029E"), 10, 15),
    (("B01001_006E", "B01001_030E"), 15, 18),
    (("B01001_007E", "B01001_031E"), 18, 20),
    (("B01001_008E", "B01001_032E"), 20, 21),
    (("B01001_009E", "B01001_033E"), 21, 22),
    (("B01001_010E", "B01001_034E"), 22, 25),
    (("B01001_011E", "B01001_035E"), 25, 30),
    (("B01001_012E", "B01001_036E"), 30, 35),
    (("B01001_013E", "B01001_037E"), 35, 40),
    (("B01001_014E", "B01001_038E"), 40, 45),
    (("B01001_015E", "B01001_039E"), 45, 50),
    (("B01001_016E", "B01001_040E"), 50, 55),
    (("B01001_017E", "B01001_041E"), 55, 60),
    (("B01001_018E", "B01001_042E"), 60, 62),
    (("B01001_019E", "B01001_043E"), 62, 65),
    (("B01001_020E", "B01001_044E"), 65, 67),
    (("B01001_021E", "B01001_045E"), 67, 70),
    (("B01001_022E", "B01001_046E"), 70, 75),
    (("B01001_023E", "B01001_047E"), 75, 80),
    (("B01001_024E", "B01001_048E"), 80, 85),
    (("B01001_025E", "B01001_049E"), 85, 95),
]

# B25075 = Value (owner-occupied units). Cells 002-024 are identical
# across all vintages; the top changed in 2015: pre-2015 ends at
# 025 = "$1,000,000 or more", 2015+ splits it into 025/026/027 with
# 027 = "$2,000,000 or more". Layouts verified against the Census
# groups metadata for 2010/2014/2015/2022.
_B25075_COMMON = [
    ("B25075_002E",       0,   9_999),
    ("B25075_003E",  10_000,  14_999),
    ("B25075_004E",  15_000,  19_999),
    ("B25075_005E",  20_000,  24_999),
    ("B25075_006E",  25_000,  29_999),
    ("B25075_007E",  30_000,  34_999),
    ("B25075_008E",  35_000,  39_999),
    ("B25075_009E",  40_000,  49_999),
    ("B25075_010E",  50_000,  59_999),
    ("B25075_011E",  60_000,  69_999),
    ("B25075_012E",  70_000,  79_999),
    ("B25075_013E",  80_000,  89_999),
    ("B25075_014E",  90_000,  99_999),
    ("B25075_015E", 100_000, 124_999),
    ("B25075_016E", 125_000, 149_999),
    ("B25075_017E", 150_000, 174_999),
    ("B25075_018E", 175_000, 199_999),
    ("B25075_019E", 200_000, 249_999),
    ("B25075_020E", 250_000, 299_999),
    ("B25075_021E", 300_000, 399_999),
    ("B25075_022E", 400_000, 499_999),
    ("B25075_023E", 500_000, 749_999),
    ("B25075_024E", 750_000, 999_999),
]
B25075_VALUE_BINS_2010 = _B25075_COMMON + [
    ("B25075_025E", 1_000_000, 2_000_000),  # "$1M or more", capped 2x
]
B25075_VALUE_BINS_2015 = _B25075_COMMON + [
    ("B25075_025E", 1_000_000, 1_499_999),
    ("B25075_026E", 1_500_000, 1_999_999),
    ("B25075_027E", 2_000_000, 4_000_000),  # "$2M or more", capped 2x
]

# B25063 = Gross Rent. Median universe is CASH renters only: bin cells
# start at 003 ("With cash rent!!..."); 002 is the cash-rent subtotal
# and the final cell ("No cash rent") is excluded. Cells 003-022 are
# identical across vintages; 023 MEANS DIFFERENT THINGS by era —
# "$2,000 or more" pre-2015 vs "$2,000 to $2,499" from 2015, when
# 024-026 were added (026 = "$3,500 or more").
_B25063_COMMON = [
    ("B25063_003E",     0,    99),
    ("B25063_004E",   100,   149),
    ("B25063_005E",   150,   199),
    ("B25063_006E",   200,   249),
    ("B25063_007E",   250,   299),
    ("B25063_008E",   300,   349),
    ("B25063_009E",   350,   399),
    ("B25063_010E",   400,   449),
    ("B25063_011E",   450,   499),
    ("B25063_012E",   500,   549),
    ("B25063_013E",   550,   599),
    ("B25063_014E",   600,   649),
    ("B25063_015E",   650,   699),
    ("B25063_016E",   700,   749),
    ("B25063_017E",   750,   799),
    ("B25063_018E",   800,   899),
    ("B25063_019E",   900,   999),
    ("B25063_020E", 1_000, 1_249),
    ("B25063_021E", 1_250, 1_499),
    ("B25063_022E", 1_500, 1_999),
]
B25063_RENT_BINS_2010 = _B25063_COMMON + [
    ("B25063_023E", 2_000, 4_000),  # "$2,000 or more", capped 2x
]
B25063_RENT_BINS_2015 = _B25063_COMMON + [
    ("B25063_023E", 2_000, 2_499),
    ("B25063_024E", 2_500, 2_999),
    ("B25063_025E", 3_000, 3_499),
    ("B25063_026E", 3_500, 7_000),  # "$3,500 or more", capped 2x
]

# B25034 = Year Structure Built. Census re-cuts the NEWEST bin as the
# decade advances, reusing the same cell codes with different meanings
# (and adding a cell in 2015) — so the schedule below is per-era, with
# transition years pinned against the groups metadata for every vintage
# 2010-2022. Bins listed oldest-first (ascending) for the median walk;
# "1939 or earlier" floored at 1900; the newest open bin is capped at
# the last calendar year covered by that era's vintages + 1.
B25034_YEAR_BINS_2010 = [
    ("B25034_010E", 1900, 1940),
    ("B25034_009E", 1940, 1950),
    ("B25034_008E", 1950, 1960),
    ("B25034_007E", 1960, 1970),
    ("B25034_006E", 1970, 1980),
    ("B25034_005E", 1980, 1990),
    ("B25034_004E", 1990, 2000),
    ("B25034_003E", 2000, 2005),
    ("B25034_002E", 2005, 2012),  # "2005 or later" (eras 2010-2011)
]
B25034_YEAR_BINS_2012 = [
    ("B25034_010E", 1900, 1940),
    ("B25034_009E", 1940, 1950),
    ("B25034_008E", 1950, 1960),
    ("B25034_007E", 1960, 1970),
    ("B25034_006E", 1970, 1980),
    ("B25034_005E", 1980, 1990),
    ("B25034_004E", 1990, 2000),
    ("B25034_003E", 2000, 2010),
    ("B25034_002E", 2010, 2015),  # "2010 or later" (eras 2012-2014)
]
B25034_YEAR_BINS_2015 = [
    ("B25034_011E", 1900, 1940),
    ("B25034_010E", 1940, 1950),
    ("B25034_009E", 1950, 1960),
    ("B25034_008E", 1960, 1970),
    ("B25034_007E", 1970, 1980),
    ("B25034_006E", 1980, 1990),
    ("B25034_005E", 1990, 2000),
    ("B25034_004E", 2000, 2010),
    ("B25034_003E", 2010, 2014),
    ("B25034_002E", 2014, 2021),  # "2014 or later" (eras 2015-2020)
]
B25034_YEAR_BINS_2021 = [
    ("B25034_011E", 1900, 1940),
    ("B25034_010E", 1940, 1950),
    ("B25034_009E", 1950, 1960),
    ("B25034_008E", 1960, 1970),
    ("B25034_007E", 1970, 1980),
    ("B25034_006E", 1980, 1990),
    ("B25034_005E", 1990, 2000),
    ("B25034_004E", 2000, 2010),
    ("B25034_003E", 2010, 2020),
    ("B25034_002E", 2020, 2026),  # "2020 or later" (eras 2021+)
]

# B01001 age-by-sex cells, used to compute under-18 + 65+ population
# shares without storing 49 separate cells as their own sources.
#   Males:   003 (under 5), 004 (5-9), 005 (10-14), 006 (15-17),
#            007 (18-19), 008 (20), 009 (21), 010 (22-24),
#            011 (25-29), 012 (30-34), 013 (35-39), 014 (40-44),
#            015 (45-49), 016 (50-54), 017 (55-59), 018 (60-61),
#            019 (62-64), 020 (65-66), 021 (67-69), 022 (70-74),
#            023 (75-79), 024 (80-84), 025 (85+)
#   Females: 027-049 (parallel structure)
B01001_UNDER_18 = [
    f"B01001_{cell:03d}E"
    for cell in (3, 4, 5, 6, 27, 28, 29, 30)
]
B01001_65_PLUS = [
    f"B01001_{cell:03d}E"
    for cell in (20, 21, 22, 23, 24, 25, 44, 45, 46, 47, 48, 49)
]

# B27010 = Types of Health Insurance Coverage by Age. The "uninsured"
# count is the sum of cells reporting "No health insurance coverage"
# across the four published age brackets: under-19, 19-34, 35-64, 65+.
B27010_UNINSURED = [
    "B27010_017E",  # under-19 no coverage
    "B27010_033E",  # 19-34 no coverage
    "B27010_050E",  # 35-64 no coverage
    "B27010_066E",  # 65+ no coverage
]

# B18101 = Sex by Age by Disability Status. The "with a disability"
# count is the sum of 12 cells (6 male age groups + 6 female), one per
# (sex, age) bin in the table.
B18101_WITH_DISABILITY = [
    f"B18101_{cell:03d}E"
    for cell in (
        # Males: under 5, 5-17, 18-34, 35-64, 65-74, 75+
        4, 7, 10, 13, 16, 19,
        # Females: under 5, 5-17, 18-34, 35-64, 65-74, 75+
        23, 26, 29, 32, 35, 38,
    )
]

# C24080 = Class of Worker. Government cells are 015 (federal),
# 016 (state), 017 (local). C24080_001 is total employed.
C24080_GOVERNMENT = ["C24080_015E", "C24080_016E", "C24080_017E"]


INDICATORS = [
    # Count indicators — aggregated via crosswalk sum.
    AcsVar("population", "B01003_001E",
           "Total population", "people", 0, AGG_SUM),
    AcsVar("poverty_count", "B17001_002E",
           "People in poverty", "people", 0, AGG_SUM),
    AcsVar("foreign_born", "B05002_013E",
           "Foreign-born population", "people", 0, AGG_SUM),
    # Education: the raw degree counts stay emitted (derive_acs_state_from_cd,
    # the choropleth pipeline, and the composer's "share × population" total
    # reconstruction all need the underlying series), but they're marked
    # hidden:true in the generated YAML so they don't clutter the picker.
    # The user-facing indicators are "Adults 25+" + the two shares below.
    AcsVar("bachelors_plus", "B15003_022E",
           "Adults 25+ with a bachelor's degree", "people", 0, AGG_SUM),
    AcsVar("masters_plus", "B15003_023E",
           "Adults 25+ with a master's degree", "people", 0, AGG_SUM),
    AcsVar("adults_25plus", "B15003_001E",
           "Adults 25+", "people", 0, AGG_SUM),
    AcsVar("pct_bachelors", "",
           "Adults 25+ with a bachelor's degree", "%", 1, AGG_PCT,
           numerator_id="bachelors_plus", denominator_id="adults_25plus"),
    AcsVar("pct_masters", "",
           "Adults 25+ with a master's degree", "%", 1, AGG_PCT,
           numerator_id="masters_plus", denominator_id="adults_25plus"),
    AcsVar("owner_occupied", "B25003_002E",
           "Owner-occupied housing units", "households", 0, AGG_SUM),
    AcsVar("renter_occupied", "B25003_003E",
           "Renter-occupied housing units", "households", 0, AGG_SUM),
    AcsVar("veterans", "B21001_002E",
           "Civilian veteran population (18+)", "people", 0, AGG_SUM),
    AcsVar("broadband_households", "B28002_004E",
           "Households with broadband internet", "households", 0, AGG_SUM),
    # Medians, all recomputed from distribution bins at tract level on
    # stable geography (see module docstring). var_code stays set to the
    # published-median cell — the metro/national pipelines fetch THAT
    # directly at their own geographies; only the CD pipeline uses the
    # bin schedules.
    AcsVar("median_hh_income", "B19013_001E",
           "Median household income", "USD", 0, AGG_MEDIAN_DIST,
           bins=B19001_BINS,
           cd_basis=CD_BASIS_TRACT_MEDIAN,
           cd_bin_schedule=[(2010, B19001_BINS)]),
    AcsVar("median_age", "B01002_001E",
           "Median age", "years", 1, AGG_CD_LEVEL,
           cd_basis=CD_BASIS_TRACT_MEDIAN,
           cd_bin_schedule=[(2010, B01001_AGE_BINS)]),
    AcsVar("median_home_value", "B25077_001E",
           "Median home value (owner-occupied)", "USD", 0, AGG_CD_LEVEL,
           cd_basis=CD_BASIS_TRACT_MEDIAN,
           cd_bin_schedule=[(2010, B25075_VALUE_BINS_2010),
                            (2015, B25075_VALUE_BINS_2015)]),
    AcsVar("median_gross_rent", "B25064_001E",
           "Median gross rent", "USD", 0, AGG_CD_LEVEL,
           cd_basis=CD_BASIS_TRACT_MEDIAN,
           cd_bin_schedule=[(2010, B25063_RENT_BINS_2010),
                            (2015, B25063_RENT_BINS_2015)]),
    # ----- v4 expansion: ratio components + new medians -----
    # Strategy: store the underlying COUNTS so users can compose any
    # ratio they want via the composer's derived-source modal. Direct
    # values (Gini, median year built, median commute) are stored as
    # single numbers. As of the stable-geo rebuild, everything here is
    # crosswalk-rebuilt from tract data (cd_basis) EXCEPT the two
    # tables Census doesn't publish at tract level in any vintage:
    # B19083 (Gini) and C24080 (class of worker). Those keep riding
    # contemporaneous CD boundaries, with the documented caveat.
    AcsVar("gini_index", "B19083_001E",
           "Income inequality (Gini index)", "ratio", 3, AGG_CD_LEVEL),
    AcsVar("median_year_built", "B25035_001E",
           "Median year housing structure built", "year", 0, AGG_CD_LEVEL,
           cd_basis=CD_BASIS_TRACT_MEDIAN,
           cd_bin_schedule=[(2010, B25034_YEAR_BINS_2010),
                            (2012, B25034_YEAR_BINS_2012),
                            (2015, B25034_YEAR_BINS_2015),
                            (2021, B25034_YEAR_BINS_2021)]),
    AcsVar("households_above_200k", "B19001_017E",
           "Households with income $200k+", "households", 0, AGG_CD_LEVEL,
           cd_basis=CD_BASIS_TRACT),
    AcsVar("households_total_income", "B19001_001E",
           "Total households (income-table denominator)", "households",
           0, AGG_CD_LEVEL, cd_basis=CD_BASIS_TRACT),
    AcsVar("workers_wfh", "B08301_021E",
           "Workers who work from home", "workers", 0, AGG_CD_LEVEL,
           cd_basis=CD_BASIS_TRACT),
    AcsVar("workers_total_commute", "B08301_001E",
           "Total workers (commute-table denominator)", "workers",
           0, AGG_CD_LEVEL, cd_basis=CD_BASIS_TRACT),
    AcsVar("households_no_vehicle", "B08201_002E",
           "Households with no vehicle available", "households",
           0, AGG_CD_LEVEL, cd_basis=CD_BASIS_TRACT),
    AcsVar("households_total_vehicle", "B08201_001E",
           "Total households (vehicle-table denominator)", "households",
           0, AGG_CD_LEVEL, cd_basis=CD_BASIS_TRACT),
    AcsVar("insurance_universe", "B27010_001E",
           "Total population (insurance-table denominator)", "people",
           0, AGG_CD_LEVEL, cd_basis=CD_BASIS_TRACT,
           first_tract_vintage=2013),
    # Movers = everyone who moved in the past year: the sum of the four
    # "Moved ..." totals (within county / different county same state /
    # different state / from abroad). B07003_003E was WRONG — that's the
    # FEMALE subtotal (~50% of the universe everywhere), not movers. Fixed
    # 2026-05-29 after the share view exposed the constant-~50% giveaway.
    AcsVar("movers_last_year", "",
           "People who moved in the last year", "people", 0, AGG_CD_LEVEL_SUM,
           sum_codes=["B07003_007E", "B07003_010E", "B07003_013E", "B07003_016E"],
           cd_basis=CD_BASIS_TRACT),
    AcsVar("mobility_universe", "B07003_001E",
           "Total population (mobility-table denominator)", "people",
           0, AGG_CD_LEVEL, cd_basis=CD_BASIS_TRACT),
    AcsVar("born_same_state", "B05002_003E",
           "Population born in current state of residence", "people",
           0, AGG_CD_LEVEL, cd_basis=CD_BASIS_TRACT),
    AcsVar("workers_manufacturing", "C24070_004E",
           "Workers in manufacturing", "workers", 0, AGG_CD_LEVEL,
           cd_basis=CD_BASIS_TRACT),
    AcsVar("workers_total_industry", "C24070_001E",
           "Total workers (industry-table denominator)", "workers",
           0, AGG_CD_LEVEL, cd_basis=CD_BASIS_TRACT),
    # C24080 has no tract-level publication in any vintage (verified
    # 2010-2022) — class-of-worker stays contemporaneous-CD.
    AcsVar("workers_class_universe", "C24080_001E",
           "Total workers (class-of-worker-table denominator)", "workers",
           0, AGG_CD_LEVEL),
    AcsVar("households_below_25k", "",
           "Households with income under $25k", "households",
           0, AGG_CD_LEVEL_SUM,
           sum_codes=["B19001_002E", "B19001_003E", "B19001_004E", "B19001_005E"],
           cd_basis=CD_BASIS_TRACT),
    AcsVar("population_under_18", "",
           "Population under 18", "people", 0, AGG_CD_LEVEL_SUM,
           sum_codes=B01001_UNDER_18, cd_basis=CD_BASIS_TRACT),
    AcsVar("population_65_plus", "",
           "Population 65 and older", "people", 0, AGG_CD_LEVEL_SUM,
           sum_codes=B01001_65_PLUS, cd_basis=CD_BASIS_TRACT),
    AcsVar("people_uninsured", "",
           "People without health insurance coverage", "people",
           0, AGG_CD_LEVEL_SUM, sum_codes=B27010_UNINSURED,
           cd_basis=CD_BASIS_TRACT, first_tract_vintage=2013),
    AcsVar("people_with_disability", "",
           "People with a disability", "people", 0, AGG_CD_LEVEL_SUM,
           sum_codes=B18101_WITH_DISABILITY,
           cd_basis=CD_BASIS_TRACT, first_tract_vintage=2012),
    AcsVar("people_disability_universe", "B18101_001E",
           "Civilian noninstitutionalized population (disability-table denominator)",
           "people", 0, AGG_CD_LEVEL,
           cd_basis=CD_BASIS_TRACT, first_tract_vintage=2012),
    AcsVar("workers_government", "",
           "Workers in government employment (federal + state + local)",
           "workers", 0, AGG_CD_LEVEL_SUM, sum_codes=C24080_GOVERNMENT),
    AcsVar("median_commute_minutes", "",
           "Median travel time to work", "minutes", 1, AGG_MEDIAN_CD_DIST,
           bins=B08303_BINS,
           cd_basis=CD_BASIS_TRACT_MEDIAN,
           cd_bin_schedule=[(2010, B08303_BINS)]),
    # ----- Count → share conversions (#102, expanded #112) -----
    # numerator / denominator * 100, both already-computed indicators sharing
    # a geo basis (see AGG_PCT). The numerator count stays in the data (the
    # generator marks it hidden:true) so the composer's rebuild chip can
    # substitute the exact count via derivedFrom; the denominator stays
    # user-facing. foreign-born rides the stable-geo SUM basis; the rest ride
    # contemporaneous-CD. All verified plausible across diverse districts
    # (e.g. Arlington 28% earning $200k+ vs rural WV 2%; rural VA 14%
    # manufacturing vs Manhattan 3%).
    #
    # disability, movers, uninsured, manufacturing, $200k+, <$25k were
    # unblocked by the #112 cd-level fetch fix (movers used the wrong cell —
    # B07003_003E is Female, not movers — and the robust chunked fetch
    # stopped an invalid neighbor var zeroing its whole 45-var chunk).
    # pct_government stays out: C24080 (class of worker) has no CD-level data.
    AcsVar("pct_foreign_born", "", "Foreign-born share of population", "%", 1,
           AGG_PCT, numerator_id="foreign_born", denominator_id="population"),
    AcsVar("pct_workers_wfh", "", "Work-from-home share of workers", "%", 1,
           AGG_PCT, numerator_id="workers_wfh", denominator_id="workers_total_commute"),
    AcsVar("pct_no_vehicle", "", "Share of households with no vehicle", "%", 1,
           AGG_PCT, numerator_id="households_no_vehicle", denominator_id="households_total_vehicle"),
    AcsVar("pct_movers", "", "Share who moved in the past year", "%", 1,
           AGG_PCT, numerator_id="movers_last_year", denominator_id="mobility_universe"),
    AcsVar("pct_disability", "", "Share of people with a disability", "%", 1,
           AGG_PCT, numerator_id="people_with_disability", denominator_id="people_disability_universe"),
    AcsVar("pct_uninsured", "", "Uninsured share of population", "%", 1,
           AGG_PCT, numerator_id="people_uninsured", denominator_id="insurance_universe"),
    AcsVar("pct_manufacturing", "", "Manufacturing share of workers", "%", 1,
           AGG_PCT, numerator_id="workers_manufacturing", denominator_id="workers_total_industry"),
    AcsVar("pct_households_above_200k", "", "Share of households earning $200k+", "%", 1,
           AGG_PCT, numerator_id="households_above_200k", denominator_id="households_total_income"),
    AcsVar("pct_households_below_25k", "", "Share of households earning under $25k", "%", 1,
           AGG_PCT, numerator_id="households_below_25k", denominator_id="households_total_income"),
]


# State FIPS for the 50 states + DC.
STATE_FIPS = [
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
    "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "44", "45", "46", "47", "48", "49", "50", "51", "53",
    "54", "55", "56",
]
STATE_ABBR = {
    "01": "al", "02": "ak", "04": "az", "05": "ar", "06": "ca", "08": "co",
    "09": "ct", "10": "de", "11": "dc", "12": "fl", "13": "ga", "15": "hi",
    "16": "id", "17": "il", "18": "in", "19": "ia", "20": "ks", "21": "ky",
    "22": "la", "23": "me", "24": "md", "25": "ma", "26": "mi", "27": "mn",
    "28": "ms", "29": "mo", "30": "mt", "31": "ne", "32": "nv", "33": "nh",
    "34": "nj", "35": "nm", "36": "ny", "37": "nc", "38": "nd", "39": "oh",
    "40": "ok", "41": "or", "42": "pa", "44": "ri", "45": "sc", "46": "sd",
    "47": "tn", "48": "tx", "49": "ut", "50": "vt", "51": "va", "53": "wa",
    "54": "wv", "55": "wi", "56": "wy",
}


# ---------------------------------------------------------------------
# Crosswalks
# ---------------------------------------------------------------------

def load_crosswalk(path: Path) -> dict[str, list[tuple[str, str, float]]]:
    """
    Returns {tract_geoid: [(state_fips, cd, weight), ...]}.
    Tracts that straddle CD boundaries appear with multiple entries.
    """
    out: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    if not path.exists():
        print(f"  crosswalk not found: {path}", file=sys.stderr)
        return out
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            tract = row.get("tract_geoid", "")
            state = row.get("state_fips", "")
            cd = row.get("cd_district", "")
            try:
                weight = float(row.get("weight", "0"))
            except ValueError:
                continue
            if tract and state and cd:
                out[tract].append((state, cd, weight))
    return out


def cd_slug(state_fips: str, cd: str) -> str | None:
    """Convert (state_fips, cd_code) to our slug pattern: 'va_08' or 'mt_al'."""
    abbr = STATE_ABBR.get(state_fips)
    if not abbr:
        return None
    if cd == "00":
        return f"{abbr}_al"
    try:
        return f"{abbr}_{int(cd):02d}"
    except ValueError:
        return None


# ---------------------------------------------------------------------
# ACS API
# ---------------------------------------------------------------------

def acs_fetch(year: int, var_codes: list[str], geo: str, key: str) -> list[list[str]]:
    """
    Fire one Census API request. Returns list of rows (first row = headers).
    Empty list on failure. Logs non-empty error responses so silent
    failures (404 because of wrong URL path, "geography not supported"
    because of wrong filter shape, etc.) are visible in workflow output.
    """
    vars_csv = ",".join(var_codes)
    url = (
        f"{acs_base(year)}?get=NAME,{vars_csv}"
        f"&for={geo}&key={key}"
    )
    try:
        out = subprocess.run(
            ["curl", "-s", "-S", "--max-time", "120", "-w", "%{http_code}", url],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    curl failed for year={year} geo={geo!r}: {e}", file=sys.stderr)
        return []
    # `-w "%{http_code}"` appends the HTTP code at the very end of stdout.
    body = out.stdout
    code = body[-3:] if body[-3:].isdigit() else "???"
    payload = body[:-3] if body[-3:].isdigit() else body
    if code != "200":
        # First non-200 per year is loud; subsequent ones (same state
        # variants etc.) we trust the per-loop logging already covers.
        if len(payload) < 500:
            snippet = payload.strip()[:200]
        else:
            snippet = payload.strip()[:200] + "..."
        print(f"    HTTP {code} for year={year} geo={geo!r}: {snippet}", file=sys.stderr)
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error year={year} geo={geo!r}: {e}", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def parse_value(s: str) -> float | None:
    """Parse a Census value, treating sentinel-negatives as missing."""
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    if v < -1_000_000:
        return None
    return v


# ---------------------------------------------------------------------
# Median-from-bins
# ---------------------------------------------------------------------

def weighted_median_from_bins(
    bins: list[tuple[object, float, float]],
    counts: dict[str, float],
) -> float | None:
    """
    Given bins as (cell, lower, upper) — where `cell` is a var code or
    a tuple of var codes whose counts merge into the bin — and a counts
    dict mapping var_code -> count, return the linearly-interpolated
    median. Returns None if total count is zero.
    """
    def bin_count(cell) -> float:
        return sum(counts.get(code, 0) for code in bin_cell_codes(cell))

    total = sum(bin_count(cell) for cell, _, _ in bins)
    if total <= 0:
        return None
    target = total / 2.0
    cum = 0.0
    for cell, lower, upper in bins:
        c = bin_count(cell)
        if c <= 0:
            continue
        if cum + c >= target:
            # Median falls within this bin. Linear interpolation:
            # median = lower + (target - cum) / c * (upper - lower)
            fraction = (target - cum) / c
            return lower + fraction * (upper - lower)
        cum += c
    return None


# ---------------------------------------------------------------------
# Per-vintage fetch
# ---------------------------------------------------------------------

def fetch_vintage_tract(
    year: int,
    var_codes: list[str],
    state_fips: str,
    key: str,
) -> dict[str, dict[str, float]]:
    """
    Tract-level fetch for one state, one vintage. Returns
    {tract_geoid_11: {var_code: value}}.

    Geography hierarchy: `tract:* in=state:XX county:*`. The wildcard
    county is supported universally across ACS vintages back to 2010.
    Earlier code used `tract:* in=state:XX` (no county), which the
    modern API accepts but the pre-2015 API rejects — that's why our
    pre-2017 vintages came back empty before this fix.

    Cached on disk by (year, state_fips, vars_hash). For vintages
    >= 2 years old the cache is effectively permanent (data is
    immutable); for recent vintages a 30-day TTL applies.
    """
    cache_key = f"{year}_state{state_fips}_{_vars_hash(var_codes)}"
    max_age = _cache_max_age_days(year)
    cached = cache_get(_CACHE_BUCKET_TRACT, cache_key, max_age)
    if cached is not None:
        try:
            parsed = json.loads(cached.decode("utf-8"))
            if isinstance(parsed, dict):
                _cache_stats["tract_hit"] += 1
                return parsed
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
            pass  # Fall through; treat corrupt cache as a miss.

    _cache_stats["tract_miss"] += 1
    geo = f"tract:*&in=state:{state_fips}%20county:*"
    rows = acs_fetch(year, var_codes, geo, key)
    if not rows or len(rows) < 2:
        return {}
    headers = rows[0]
    try:
        state_col = headers.index("state")
        county_col = headers.index("county")
        tract_col = headers.index("tract")
    except ValueError:
        return {}
    out: dict[str, dict[str, float]] = {}
    for row in rows[1:]:
        if len(row) < len(headers):
            continue
        state = row[state_col]
        county = row[county_col]
        tract = row[tract_col]
        geoid = f"{state:>2}{county:>3}{tract:>6}"
        per_var: dict[str, float] = {}
        for code in var_codes:
            try:
                col = headers.index(code)
            except ValueError:
                continue
            v = parse_value(row[col])
            if v is not None:
                per_var[code] = v
        if per_var:
            out[geoid] = per_var
    # Only cache successful (non-empty) results — empty means upstream
    # failure (HTTP error, malformed payload, etc.) and we want the
    # next run to retry rather than memoize the failure.
    if out:
        try:
            cache_put(
                _CACHE_BUCKET_TRACT,
                cache_key,
                json.dumps(out).encode("utf-8"),
            )
        except OSError as e:
            print(f"    cache write failed for {cache_key}: {e}", file=sys.stderr)
    return out


def fetch_vintage_cd_level(
    year: int,
    var_codes: list[str],
    key: str,
) -> dict[tuple[str, str], dict[str, float]]:
    """
    CD-level fetch (no aggregation) for one vintage. Returns
    {(state_fips, cd): {var_code: value}}. Used for medians we don't
    recompute via distribution.

    Cached on disk by (year, vars_hash). JSON can't hold tuple keys,
    so we serialize as ``"state|cd"`` strings and re-tuple on read.
    """
    cache_key = f"{year}_cd_{_vars_hash(var_codes)}"
    max_age = _cache_max_age_days(year)
    cached = cache_get(_CACHE_BUCKET_DISTRICT, cache_key, max_age)
    if cached is not None:
        try:
            stored = json.loads(cached.decode("utf-8"))
            if isinstance(stored, dict):
                _cache_stats["cd_hit"] += 1
                # Re-tuple the "state|cd" composite keys.
                return {
                    tuple(k.split("|", 1)): v  # type: ignore[misc]
                    for k, v in stored.items()
                    if "|" in k and isinstance(v, dict)
                }
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
            pass  # Treat corrupt cache as a miss.

    _cache_stats["cd_miss"] += 1
    rows = acs_fetch(year, var_codes, "congressional%20district:*", key)
    if not rows or len(rows) < 2:
        return {}
    headers = rows[0]
    try:
        state_col = headers.index("state")
        dist_col = headers.index("congressional district")
    except ValueError:
        return {}
    out: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows[1:]:
        if len(row) < len(headers):
            continue
        state = row[state_col]
        cd = row[dist_col]
        per_var: dict[str, float] = {}
        for code in var_codes:
            try:
                col = headers.index(code)
            except ValueError:
                continue
            v = parse_value(row[col])
            if v is not None:
                per_var[code] = v
        if per_var:
            out[(state, cd)] = per_var
    if out:
        try:
            to_cache = {f"{s}|{cd}": v for (s, cd), v in out.items()}
            cache_put(
                _CACHE_BUCKET_DISTRICT,
                cache_key,
                json.dumps(to_cache).encode("utf-8"),
            )
        except OSError as e:
            print(f"    cache write failed for {cache_key}: {e}", file=sys.stderr)
    return out


def fetch_cd_level_robust(
    year: int,
    codes: list[str],
    key: str,
) -> dict[tuple[str, str], dict[str, float]]:
    """CD-level fetch that tolerates variables a vintage doesn't publish.

    The Census API rejects the ENTIRE request (HTTP 400) if any requested
    variable is unknown for the year — which used to silently zero every
    other variable sharing that 45-var chunk (the bug that under-summed
    people_with_disability and zeroed whole tables). We fetch in <=45-var
    chunks; when a chunk comes back empty we binary-split it to isolate the
    offending variable(s), dropping only the ones that fail on their own.
    Valid variables always make it through. Sub-chunk results are cached by
    fetch_vintage_cd_level's own (year, vars-hash) key."""
    merged: dict[tuple[str, str], dict[str, float]] = {}

    def absorb(part: dict[tuple[str, str], dict[str, float]]) -> None:
        for k, per_var in part.items():
            merged.setdefault(k, {}).update(per_var)

    def recurse(sub: list[str]) -> None:
        if not sub:
            return
        data = fetch_vintage_cd_level(year, sub, key)
        if data:
            absorb(data)
            return
        # Empty → an invalid var poisoned the request (or there's genuinely no
        # CD-level data). A lone var that fails is the bad one — drop it.
        # Otherwise split to isolate it from its valid neighbors.
        if len(sub) <= 1:
            return
        mid = len(sub) // 2
        recurse(sub[:mid])
        recurse(sub[mid:])

    for i in range(0, len(codes), 45):
        recurse(codes[i:i + 45])
    return merged


def fetch_tract_robust(
    year: int,
    codes: list[str],
    state_fips: str,
    key: str,
    _fetch=None,
) -> dict[str, dict[str, float]]:
    """Tract-level fetch that handles >45 variables and tolerates
    variables a vintage doesn't publish at tract level.

    Same strategy as fetch_cd_level_robust: chunk into <=45-var calls
    (the Census API caps ~50 per request and 400s the WHOLE request if
    any variable is unknown); binary-split any empty chunk to isolate
    offending variables, dropping only the ones that fail alone. The
    per-(year, state, vars-hash) disk cache inside fetch_vintage_tract
    applies to every sub-chunk. `_fetch` is injectable for tests.
    """
    fetch = _fetch if _fetch is not None else fetch_vintage_tract
    merged: dict[str, dict[str, float]] = {}

    def absorb(part: dict[str, dict[str, float]]) -> None:
        for geoid, per_var in part.items():
            merged.setdefault(geoid, {}).update(per_var)

    def recurse(sub: list[str]) -> None:
        if not sub:
            return
        data = fetch(year, sub, state_fips, key)
        if data:
            absorb(data)
            return
        if len(sub) <= 1:
            return
        mid = len(sub) // 2
        recurse(sub[:mid])
        recurse(sub[mid:])

    for i in range(0, len(codes), 45):
        recurse(codes[i:i + 45])
    return merged


# ---------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------

def main() -> int:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        print(
            "census_acs_cd.py: CENSUS_API_KEY not set. Skipping. "
            "Register a free key at https://api.census.gov/data/key_signup.html "
            "and set the env var.",
            file=sys.stderr,
        )
        return 0

    # Reset cache stats for this run (module-level so we don't have to
    # thread state through every fetch helper).
    for k in _cache_stats:
        _cache_stats[k] = 0

    cw_2020 = load_crosswalk(CROSSWALK_DIR / "tract2020_to_cd118.csv")
    cw_2010 = load_crosswalk(CROSSWALK_DIR / "tract2010_to_cd118.csv")
    print(f"Loaded crosswalks: tract2020={len(cw_2020):,} tracts, "
          f"tract2010={len(cw_2010):,} tracts", flush=True)

    # Indicator classification. TRACT basis (stable geography through
    # the crosswalk): every AGG_SUM indicator (always was tract-based)
    # plus everything carrying a cd_basis override. CD-level fallback
    # (contemporaneous boundaries): the remaining cd_basis-less
    # indicators — only the tables Census doesn't publish at tract
    # level (Gini, class of worker).
    tract_sum_indicators = [
        v for v in INDICATORS
        if v.agg == AGG_SUM or v.cd_basis == CD_BASIS_TRACT
    ]
    tract_median_indicators = [
        v for v in INDICATORS if v.cd_basis == CD_BASIS_TRACT_MEDIAN
    ]
    cd_single_indicators = [
        v for v in INDICATORS if v.agg == AGG_CD_LEVEL and not v.cd_basis
    ]
    cd_sum_indicators = [
        v for v in INDICATORS if v.agg == AGG_CD_LEVEL_SUM and not v.cd_basis
    ]
    cd_median_dist_indicators = [
        v for v in INDICATORS if v.agg == AGG_MEDIAN_CD_DIST and not v.cd_basis
    ]
    pct_indicators = [v for v in INDICATORS if v.agg == AGG_PCT]
    var_by_id = {v.out_id: v for v in INDICATORS}

    def tract_codes_for(v: AcsVar) -> list[str]:
        """Cells a tract-sum indicator needs: the single var_code or
        the multi-cell sum_codes list."""
        return [v.var_code] if v.var_code else list(v.sum_codes)

    # All CD-level variable codes we still need to fetch (the non-tract
    # leftovers). Dedupe so we don't send the same code twice.
    cd_level_codes_set: set[str] = set()
    for v in cd_single_indicators:
        if v.var_code:
            cd_level_codes_set.add(v.var_code)
    for v in cd_sum_indicators:
        cd_level_codes_set.update(v.sum_codes)
    for v in cd_median_dist_indicators:
        cd_level_codes_set.update(
            code for cell, _, _ in v.bins for code in bin_cell_codes(cell)
        )
    cd_level_codes = sorted(cd_level_codes_set)

    # Accumulator: {(out_id, cd_slug): [{t, v}, ...]}
    series_accum: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for year in ACS_VINTAGES:
        anchor = f"{year}-12-31"
        cw = cw_2020 if year >= TRACT2020_FIRST_VINTAGE else cw_2010
        print(f"\nFetching ACS5 vintage {year} (using "
              f"{'tract2020' if year >= TRACT2020_FIRST_VINTAGE else 'tract2010'} crosswalk)...",
              flush=True)

        # Per-CD accumulator for this vintage: {cd_slug: {out_id: value}}
        cd_values: dict[str, dict[str, float]] = defaultdict(dict)
        # Per-CD bin sums for the median-distribution indicators:
        # {cd_slug: {out_id: {bin_code: count_sum}}}
        cd_bins: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

        # Resolve what's active THIS vintage: sum indicators whose table
        # has tract data by now, and each median's era-correct bin
        # table. Also assemble the deduped tract variable list — well
        # over the API's ~50-var cap nowadays, so fetch_tract_robust
        # chunks it.
        active_sums = [
            (v, tract_codes_for(v))
            for v in tract_sum_indicators
            if year >= v.first_tract_vintage
        ]
        active_medians = []
        for v in tract_median_indicators:
            if year < v.first_tract_vintage:
                continue
            bins = resolve_cd_bins(v, year)
            if bins:
                active_medians.append((v, bins))
        tract_codes_set: set[str] = set()
        for _, codes in active_sums:
            tract_codes_set.update(codes)
        for _, bins in active_medians:
            for cell, _, _ in bins:
                tract_codes_set.update(bin_cell_codes(cell))
        tract_codes = sorted(tract_codes_set)

        for fips in STATE_FIPS:
            tract_data = fetch_tract_robust(year, tract_codes, fips, key)
            if not tract_data:
                continue

            for tract_geoid, per_var in tract_data.items():
                cd_assignments = cw.get(tract_geoid, [])
                if not cd_assignments:
                    continue
                for (cd_state, cd, weight) in cd_assignments:
                    slug = cd_slug(cd_state, cd)
                    if not slug:
                        continue
                    # Sum-aggregated indicators: add tract_value * weight.
                    # Multi-cell indicators sum whichever cells are
                    # present (same skip-if-none semantics as the CD-
                    # level path — never store a false zero).
                    for v, codes in active_sums:
                        parts = [per_var.get(c) for c in codes]
                        present = [p for p in parts if p is not None]
                        if not present:
                            continue
                        cd_values[slug][v.out_id] = (
                            cd_values[slug].get(v.out_id, 0)
                            + sum(present) * weight
                        )
                    # Distribution-bin counts: sum each bin cell.
                    for v, bins in active_medians:
                        acc = cd_bins[slug][v.out_id]
                        for cell, _, _ in bins:
                            for code in bin_cell_codes(cell):
                                val = per_var.get(code)
                                if val is None:
                                    continue
                                acc[code] += val * weight

        # Compute medians from accumulated distributions
        for slug, by_indicator in cd_bins.items():
            for v, bins in active_medians:
                bins_data = by_indicator.get(v.out_id, {})
                med = weighted_median_from_bins(bins, bins_data)
                if med is not None:
                    cd_values[slug][v.out_id] = med

        # CD-level fetch (no crosswalk; contemporaneous boundaries) for
        # the cd_basis-less leftovers — only gini_index plus the
        # class-of-worker pair (workers_government + universe), whose
        # tables Census doesn't publish at tract level. Chunked into
        # <=45-var requests to stay under the Census API's 50-variable-
        # per-call cap; results are merged back into one per-CD dict.
        if cd_level_codes:
            # Robust fetch: the Census API 400s the WHOLE request if ANY
            # requested variable is unknown for the vintage, which silently
            # zeroed every other variable in the same 45-var chunk. That
            # under-summed people_with_disability ~6x (B18101 cells sharing a
            # chunk with an invalid neighbor such as C24080_001E, unknown in
            # 2022) and zeroed entire tables. fetch_cd_level_robust isolates
            # the invalid vars by binary-splitting any failed chunk.
            cd_level_merged = fetch_cd_level_robust(year, cd_level_codes, key)
            for (state_fips, cd_raw), per_var in cd_level_merged.items():
                slug = cd_slug(state_fips, cd_raw)
                if not slug:
                    continue
                # AGG_CD_LEVEL: store the single fetched cell directly.
                for v in cd_single_indicators:
                    val = per_var.get(v.var_code)
                    if val is not None:
                        cd_values[slug][v.out_id] = val
                # AGG_CD_LEVEL_SUM: sum the listed cells. Skip the
                # indicator entirely if none of its cells came back (vs.
                # storing 0, which would falsely imply "no people in this
                # category" instead of "data unavailable").
                for v in cd_sum_indicators:
                    parts = [per_var.get(c) for c in v.sum_codes]
                    present = [p for p in parts if p is not None]
                    if present:
                        cd_values[slug][v.out_id] = sum(present)
                # AGG_MEDIAN_CD_DIST: build a {cell_code: count} dict from
                # the per-CD fetched values and compute the linearly-
                # interpolated median across the bin distribution.
                # (Empty since the stable-geo rebuild moved the last
                # user — median_commute_minutes — to the tract basis;
                # kept for any future no-tract-table median.)
                for v in cd_median_dist_indicators:
                    bins_data = {
                        code: per_var[code]
                        for cell, _, _ in v.bins
                        for code in bin_cell_codes(cell)
                        if code in per_var
                    }
                    med = weighted_median_from_bins(v.bins, bins_data)
                    if med is not None:
                        cd_values[slug][v.out_id] = med

        # Percentages: numerator / denominator * 100, both already computed
        # this vintage (same geo basis). Skip when either is missing or the
        # denominator is non-positive (avoids div-by-zero / nonsense shares).
        for slug, values in cd_values.items():
            for v in pct_indicators:
                num = values.get(v.numerator_id)
                den = values.get(v.denominator_id)
                if num is not None and den and den > 0:
                    values[v.out_id] = num / den * 100.0

        # Emit accumulated values into the main series accumulator — but
        # skip indicators flagged emit=False (raw counts kept only as
        # percentage numerators).
        for slug, values in cd_values.items():
            for out_id, value in values.items():
                var = var_by_id.get(out_id)
                if var is not None and not var.emit:
                    continue
                series_accum[(out_id, slug)].append({"t": anchor, "v": value})

    # Single-CD states (AK, DE, ND, SD, VT, WY) and DC have one
    # congressional "district" that's the same area as the state.
    # The CD-level YAMLs are retired (acs_state/<series>_<st> is the
    # public-facing series), but the DATA still has to land somewhere
    # — derive_acs_state_from_cd.py reads acs_cd JSONs to build the
    # state-level aggregates, and a missing CD JSON yields a single-
    # point or empty state-level series. So for these slugs we
    # redirect the write to acs_state/<series>_<st>.json directly,
    # giving the state-level series full multi-vintage coverage with
    # the CD-level YAML still retired.
    SINGLE_CD_REDUNDANT = {
        "ak_al": "ak", "de_al": "de", "nd_al": "nd", "sd_al": "sd",
        "vt_al": "vt", "wy_al": "wy", "dc_98": "dc",
    }

    # The district universe is whatever the crosswalks can produce.
    # CD-level indicators (gini, class-of-worker) fetch `congressional
    # district:*` per vintage, so the 2010-2011 vintages hand back
    # 2000s-era districts (ia_05, ny_29, la_07 …) abolished in the 2012
    # redistricting and present in NEITHER crosswalk. Those are pure
    # relics — drop any series whose slug the crosswalks never assign,
    # so CD-level indicators stay on the same district set as the
    # crosswalk-aggregated ones. (When the crosswalk is rebuilt for the
    # true 118th, its universe — and thus this filter — updates with it.)
    known_slugs = {
        cd_slug(st, cd)
        for cw in (cw_2010, cw_2020)
        for assignments in cw.values()
        for (st, cd, _w) in assignments
    }
    known_slugs.discard(None)

    # Write per-(indicator, CD) time series JSON files
    written = 0
    redirected = 0
    skipped_unknown = 0
    # Track every district slug we actually emit to acs_cd this run, so we
    # can prune superseded districts afterwards (see below).
    acs_cd_slugs_written: set[str] = set()
    for (out_id, slug), points in series_accum.items():
        if not points:
            continue
        if slug not in known_slugs:
            skipped_unknown += 1
            continue
        points.sort(key=lambda p: p["t"])
        # Round counts to integers (crosswalk-weighted sums are
        # fractional), keep medians + Gini at their declared decimal
        # precision.
        var = next((v for v in INDICATORS if v.out_id == out_id), None)
        if var and (var.agg in (AGG_SUM, AGG_CD_LEVEL_SUM)
                    or var.cd_basis == CD_BASIS_TRACT):
            for p in points:
                p["v"] = round(p["v"])
        elif var and var.decimals > 0:
            for p in points:
                p["v"] = round(p["v"], var.decimals)
        name_prefix = var.name_prefix if var else out_id
        unit = var.unit if var else "value"
        if slug in SINGLE_CD_REDUNDANT:
            # Don't redirect series that have no acs_state YAML generator —
            # the redirected file would be an orphan (data on disk, no YAML).
            # Two cases:
            #   - pct shares (AGG_PCT): single-CD states get no share YAMLs.
            #   - adults_25plus: the education-attainment denominator is the
            #     one count NOT in derive_acs_state_from_cd.py's ALL_INDICATORS
            #     (state education is surfaced via bachelors_plus/masters_plus
            #     + the choropleth pct snapshots, not this bare base), so it
            #     has no state-level YAML emitter either.
            # Both stay emitted at the CD level for multi-CD states; the other
            # counts/medians DO get acs_state YAMLs via
            # derive_acs_state_from_cd.py, so those still redirect.
            if out_id == "adults_25plus" or (var is not None and var.agg == AGG_PCT):
                continue
            # Route to the state-level path. derive_acs_state_from_cd.py
            # would otherwise produce an empty/single-point series for
            # these because no CD JSON exists to aggregate from.
            st = SINGLE_CD_REDUNDANT[slug]
            series_id = f"{out_id}_{st}"
            # merge=False: every run recomputes the FULL 2010-2022
            # history from cache/API, and the stable-geo rebuild
            # changed the methodology — merging would let stale
            # contemporaneous-boundary points survive inside
            # crosswalk-rebuilt series (mixed bases in one line).
            write_timeseries(
                pipeline="acs_state",
                series_id=series_id,
                name=f"{name_prefix} — {st.upper()}",
                points=points,
                unit=unit,
                merge=False,
            )
            redirected += 1
            continue
        series_id = f"{out_id}_{slug}"
        write_timeseries(
            pipeline="acs_cd",
            series_id=series_id,
            name=f"{name_prefix} — {slug.upper().replace('_', '-')}",
            points=points,
            unit=unit,
            merge=False,
        )
        written += 1
        acs_cd_slugs_written.add(slug)
    # Cache summary: how much upstream traffic did we save this run?
    th = _cache_stats["tract_hit"]
    tm = _cache_stats["tract_miss"]
    ch = _cache_stats["cd_hit"]
    cm = _cache_stats["cd_miss"]
    tract_total = th + tm
    cd_total = ch + cm
    tract_pct = f"{th * 100 // tract_total}%" if tract_total else "n/a"
    cd_pct = f"{ch * 100 // cd_total}%" if cd_total else "n/a"
    print(
        f"acs_cd: cache tract {th}/{tract_total} hit ({tract_pct}), "
        f"cd {ch}/{cd_total} hit ({cd_pct})",
        flush=True,
    )

    # Prune superseded districts. write_timeseries only overwrites; nothing
    # here used to remove a slug the crosswalk no longer produces. So a
    # redistricting renumber (ca_53 -> ca_52, MT at-large -> mt_01/mt_02)
    # left the stale files on disk, and derive_acs_state_from_cd.py — which
    # SUMS every acs_cd series for a state — then double-counted old + new
    # districts into a bogus state total (MT pop read ~2x). Delete any
    # acs_cd file whose slug we did NOT write this run. Guarded: a run that
    # wrote implausibly few slugs (interrupted / failed) skips pruning so it
    # can't wipe the catalog.
    pruned = 0
    # Prune only WITHIN states we actually wrote this run. A per-state tract
    # fetch can fail silently (fetch returns {} -> the state is skipped), so a
    # blanket "delete any slug we didn't write" would wipe a transiently-failed
    # state's committed districts. Protect any state that produced no output,
    # and bail entirely if implausibly few states wrote (a systemic failure).
    written_states = {s.split("_", 1)[0] for s in acs_cd_slugs_written}
    EXPECTED_MULTI_CD_STATES = 44  # 50 states - 6 single-CD (at-large); DC redirects to acs_state
    if len(written_states) < EXPECTED_MULTI_CD_STATES * 0.9:
        print(
            f"acs_cd: prune SKIPPED — only {len(written_states)} states wrote "
            f"(expected ~{EXPECTED_MULTI_CD_STATES}); refusing to prune to avoid data loss",
            file=sys.stderr,
        )
    else:
        slug_rx = re.compile(r"_([a-z]{2}_[a-z0-9]{2})$")
        acs_cd_dir = REPO_ROOT / "public" / "data" / "acs_cd"
        for p in acs_cd_dir.glob("*.json"):
            stem = (
                p.name[: -len(".summary.json")]
                if p.name.endswith(".summary.json")
                else p.stem
            )
            m = slug_rx.search(stem)
            if not m:
                continue
            slug = m.group(1)
            # Only prune a superseded district within a state we refreshed;
            # never touch a state that returned no data this run.
            if slug.split("_", 1)[0] in written_states and slug not in acs_cd_slugs_written:
                p.unlink()
                pruned += 1
        if pruned:
            print(f"acs_cd: pruned {pruned} orphan files "
                  f"(superseded districts in refreshed states)", flush=True)

    print(f"\nacs_cd: wrote {written} stable-geo series across "
          f"{len(ACS_VINTAGES)} vintages "
          f"(plus {redirected} single-CD-state series redirected to acs_state; "
          f"skipped {skipped_unknown} series for districts outside the crosswalk "
          f"universe — pre-2012 relics)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
