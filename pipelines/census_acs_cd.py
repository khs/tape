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
        - Counts (population, poverty, foreign-born, etc.) sum cleanly:
          CD_total = sum(tract_value × tract_weight) across tracts.
        - Median household income is recomputed from the B19001
          household-income-distribution table (16 income bins per
          tract): sum bin counts across CD-assigned tracts, then
          compute the weighted-median income from the aggregated
          distribution. This gives a true CD-level median on stable
          geography.
        - Other medians (age, home value, rent) are taken at the
          contemporaneous CD level (i.e. vintage-boundary data with
          the historical caveat) — implementing those via
          distribution would be straightforward but isn't necessary
          for the headline use case yet.

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

# Census's URL path changed mid-decade:
#   2010-2014 ACS5: /data/{year}/acs5/     (no /acs/ subfolder)
#   2015+   ACS5: /data/{year}/acs/acs5/  (current)
# Both paths still exist on Census's side, but each only serves its own
# era. Hitting the wrong path returns 404, which our `acs_fetch` treats
# as empty data — historically that meant pre-2015 vintages silently
# disappeared. Pick per year.
def acs_base(year: int) -> str:
    if year >= 2015:
        return f"https://api.census.gov/data/{year}/acs/acs5"
    return f"https://api.census.gov/data/{year}/acs5"


# ---------------------------------------------------------------------
# Indicator definitions
# ---------------------------------------------------------------------

# Aggregation strategy per indicator. "sum" works at the tract level
# (counts add cleanly across crosswalk-weighted tracts). "cd_level"
# fetches contemporaneous CD-level data, no aggregation — the boundary
# changes across redistricting cycles. "median_from_distribution" fetches
# the income-bin distribution and reassembles the median on aggregated
# geography (only used for B19013 currently).
# "cd_level_sum" is like cd_level but sums multiple cells per indicator
# (e.g., "population under 18" = sum of B01001 cells for each under-18
# age group, separately for male + female). Used for the v4 expansion
# indicators that ride contemporaneous CD boundaries.
AGG_SUM = "sum"
AGG_CD_LEVEL = "cd_level"
AGG_CD_LEVEL_SUM = "cd_level_sum"
AGG_MEDIAN_DIST = "median_from_distribution"
# Median computed from a distribution at CD level (no tract crosswalk).
# Fetches the bin cells via the CD-level API call and interpolates a
# median from the per-CD distribution directly. Used for indicators
# where the underlying bin counts are themselves CD-level published
# values (e.g., B08303 travel time to work). Less stable-geo-accurate
# than AGG_MEDIAN_DIST but doesn't need tract-level fetches.
AGG_MEDIAN_CD_DIST = "median_from_cd_distribution"
# Percentage = numerator / denominator * 100, both already-computed
# indicators (referenced by out_id via numerator_id / denominator_id).
# Computed after the base indicators each vintage; the numerator and
# denominator MUST share a geo basis (both AGG_SUM, or both CD-level) so
# the ratio is meaningful. The raw numerator can be kept internal
# (emit=False) so only the percentage + denominator surface to users.
AGG_PCT = "pct"


@dataclass
class AcsVar:
    out_id: str
    var_code: str           # primary variable code (Census table cell)
    name_prefix: str
    unit: str
    decimals: int
    agg: str                # one of AGG_*
    # For median_from_distribution agg, list of (var_code, lower, upper)
    # describing each income bin. Lower/upper are dollar bounds; the
    # top bin's upper is typically open-ended (we use a synthetic 2x
    # lower bound as an interpolation cap).
    bins: list[tuple[str, float, float]] = field(default_factory=list)
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
    # Median from distribution — uses B19001 income bins, recomputed
    # at CD level on stable geography.
    AcsVar("median_hh_income", "B19013_001E",
           "Median household income", "USD", 0, AGG_MEDIAN_DIST,
           bins=B19001_BINS),
    # Medians on contemporaneous-CD geography. Documented caveat.
    AcsVar("median_age", "B01002_001E",
           "Median age", "years", 1, AGG_CD_LEVEL),
    AcsVar("median_home_value", "B25077_001E",
           "Median home value (owner-occupied)", "USD", 0, AGG_CD_LEVEL),
    AcsVar("median_gross_rent", "B25064_001E",
           "Median gross rent", "USD", 0, AGG_CD_LEVEL),
    # ----- v4 expansion: ratio components + new medians -----
    # Strategy: store the underlying COUNTS so users can compose any
    # ratio they want via the composer's derived-source modal. Direct
    # values (Gini, median year built, median commute) are stored as
    # single numbers. All v4 indicators fetched at contemporaneous CD
    # boundaries (AGG_CD_LEVEL or AGG_CD_LEVEL_SUM) to keep the tract-
    # level call's variable count under the Census API's 50-var cap.
    AcsVar("gini_index", "B19083_001E",
           "Income inequality (Gini index)", "ratio", 3, AGG_CD_LEVEL),
    AcsVar("median_year_built", "B25035_001E",
           "Median year housing structure built", "year", 0, AGG_CD_LEVEL),
    AcsVar("households_above_200k", "B19001_017E",
           "Households with income $200k+", "households", 0, AGG_CD_LEVEL),
    AcsVar("households_total_income", "B19001_001E",
           "Total households (income-table denominator)", "households",
           0, AGG_CD_LEVEL),
    AcsVar("workers_wfh", "B08301_021E",
           "Workers who work from home", "workers", 0, AGG_CD_LEVEL),
    AcsVar("workers_total_commute", "B08301_001E",
           "Total workers (commute-table denominator)", "workers",
           0, AGG_CD_LEVEL),
    AcsVar("households_no_vehicle", "B08201_002E",
           "Households with no vehicle available", "households",
           0, AGG_CD_LEVEL),
    AcsVar("households_total_vehicle", "B08201_001E",
           "Total households (vehicle-table denominator)", "households",
           0, AGG_CD_LEVEL),
    AcsVar("insurance_universe", "B27010_001E",
           "Total population (insurance-table denominator)", "people",
           0, AGG_CD_LEVEL),
    # Movers = everyone who moved in the past year: the sum of the four
    # "Moved ..." totals (within county / different county same state /
    # different state / from abroad). B07003_003E was WRONG — that's the
    # FEMALE subtotal (~50% of the universe everywhere), not movers. Fixed
    # 2026-05-29 after the share view exposed the constant-~50% giveaway.
    AcsVar("movers_last_year", "",
           "People who moved in the last year", "people", 0, AGG_CD_LEVEL_SUM,
           sum_codes=["B07003_007E", "B07003_010E", "B07003_013E", "B07003_016E"]),
    AcsVar("mobility_universe", "B07003_001E",
           "Total population (mobility-table denominator)", "people",
           0, AGG_CD_LEVEL),
    AcsVar("born_same_state", "B05002_003E",
           "Population born in current state of residence", "people",
           0, AGG_CD_LEVEL),
    AcsVar("workers_manufacturing", "C24070_004E",
           "Workers in manufacturing", "workers", 0, AGG_CD_LEVEL),
    AcsVar("workers_total_industry", "C24070_001E",
           "Total workers (industry-table denominator)", "workers",
           0, AGG_CD_LEVEL),
    AcsVar("workers_class_universe", "C24080_001E",
           "Total workers (class-of-worker-table denominator)", "workers",
           0, AGG_CD_LEVEL),
    AcsVar("households_below_25k", "",
           "Households with income under $25k", "households",
           0, AGG_CD_LEVEL_SUM,
           sum_codes=["B19001_002E", "B19001_003E", "B19001_004E", "B19001_005E"]),
    AcsVar("population_under_18", "",
           "Population under 18", "people", 0, AGG_CD_LEVEL_SUM,
           sum_codes=B01001_UNDER_18),
    AcsVar("population_65_plus", "",
           "Population 65 and older", "people", 0, AGG_CD_LEVEL_SUM,
           sum_codes=B01001_65_PLUS),
    AcsVar("people_uninsured", "",
           "People without health insurance coverage", "people",
           0, AGG_CD_LEVEL_SUM, sum_codes=B27010_UNINSURED),
    AcsVar("people_with_disability", "",
           "People with a disability", "people", 0, AGG_CD_LEVEL_SUM,
           sum_codes=B18101_WITH_DISABILITY),
    AcsVar("people_disability_universe", "B18101_001E",
           "Civilian noninstitutionalized population (disability-table denominator)",
           "people", 0, AGG_CD_LEVEL),
    AcsVar("workers_government", "",
           "Workers in government employment (federal + state + local)",
           "workers", 0, AGG_CD_LEVEL_SUM, sum_codes=C24080_GOVERNMENT),
    AcsVar("median_commute_minutes", "",
           "Median travel time to work", "minutes", 1, AGG_MEDIAN_CD_DIST,
           bins=B08303_BINS),
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
    bins: list[tuple[str, float, float]],
    counts: dict[str, float],
) -> float | None:
    """
    Given bins as (var_code, lower, upper) and a counts dict mapping
    var_code -> count, return the linearly-interpolated median.
    Returns None if total count is zero.
    """
    total = sum(counts.get(code, 0) for code, _, _ in bins)
    if total <= 0:
        return None
    target = total / 2.0
    cum = 0.0
    for code, lower, upper in bins:
        c = counts.get(code, 0)
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

    # Variable lists for the API calls
    sum_indicators = [v for v in INDICATORS if v.agg == AGG_SUM]
    sum_codes = [v.var_code for v in sum_indicators]
    median_dist_indicators = [v for v in INDICATORS if v.agg == AGG_MEDIAN_DIST]
    cd_single_indicators = [v for v in INDICATORS if v.agg == AGG_CD_LEVEL]
    cd_sum_indicators = [v for v in INDICATORS if v.agg == AGG_CD_LEVEL_SUM]
    cd_median_dist_indicators = [v for v in INDICATORS if v.agg == AGG_MEDIAN_CD_DIST]
    pct_indicators = [v for v in INDICATORS if v.agg == AGG_PCT]
    var_by_id = {v.out_id: v for v in INDICATORS}
    # All CD-level variable codes we need to fetch: the AGG_CD_LEVEL
    # single-var indicators, plus every cell referenced by AGG_CD_LEVEL_SUM
    # indicators, plus every bin cell from AGG_MEDIAN_CD_DIST indicators.
    # Dedupe so we don't send the same code twice in one call.
    cd_level_codes_set: set[str] = set()
    for v in cd_single_indicators:
        if v.var_code:
            cd_level_codes_set.add(v.var_code)
    for v in cd_sum_indicators:
        cd_level_codes_set.update(v.sum_codes)
    for v in cd_median_dist_indicators:
        cd_level_codes_set.update(code for code, _, _ in v.bins)
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

        for fips in STATE_FIPS:
            # Build the variable list for the tract-level call.
            tract_codes = list(sum_codes)
            for v in median_dist_indicators:
                tract_codes += [code for code, _, _ in v.bins]
            # Census limits ~50 vars per call. With 9 sum + 16 income
            # bins = 25 vars, we fit in one call. Add a guard so future
            # expansion still works.
            if len(tract_codes) > 48:
                # Split. (Future: chunk into multiple calls.)
                tract_codes = tract_codes[:48]
            tract_data = fetch_vintage_tract(year, tract_codes, fips, key)
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
                    # Sum-aggregated indicators: add tract_value * weight
                    for v in sum_indicators:
                        val = per_var.get(v.var_code)
                        if val is None:
                            continue
                        cd_values[slug][v.out_id] = cd_values[slug].get(v.out_id, 0) + val * weight
                    # Distribution-bin counts: sum each bin
                    for v in median_dist_indicators:
                        for code, _, _ in v.bins:
                            val = per_var.get(code)
                            if val is None:
                                continue
                            cd_bins[slug][v.out_id][code] += val * weight

        # Compute medians from accumulated distributions
        for slug, by_indicator in cd_bins.items():
            for v in median_dist_indicators:
                bins_data = by_indicator.get(v.out_id, {})
                med = weighted_median_from_bins(v.bins, bins_data)
                if med is not None:
                    cd_values[slug][v.out_id] = med

        # CD-level fetch (no crosswalk; contemporaneous boundaries). Covers
        # the AGG_CD_LEVEL single-var indicators (median_age, etc.), the
        # AGG_CD_LEVEL_SUM cell-sum indicators (population_under_18, etc.),
        # and the AGG_MEDIAN_CD_DIST distribution-median indicators
        # (median_commute_minutes). Chunked into <=45-var requests to stay
        # under the Census API's 50-variable-per-call cap; results are
        # merged back into one per-CD dict.
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
                for v in cd_median_dist_indicators:
                    bins_data = {
                        code: per_var[code]
                        for code, _, _ in v.bins
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

    # Write per-(indicator, CD) time series JSON files
    written = 0
    redirected = 0
    for (out_id, slug), points in series_accum.items():
        if not points:
            continue
        points.sort(key=lambda p: p["t"])
        # Round counts to integers, keep medians + Gini at their declared
        # decimal precision.
        var = next((v for v in INDICATORS if v.out_id == out_id), None)
        if var and var.agg in (AGG_SUM, AGG_CD_LEVEL_SUM):
            for p in points:
                p["v"] = round(p["v"])
        elif var and var.decimals > 0:
            for p in points:
                p["v"] = round(p["v"], var.decimals)
        name_prefix = var.name_prefix if var else out_id
        unit = var.unit if var else "value"
        if slug in SINGLE_CD_REDUNDANT:
            # Don't redirect pct shares to acs_state: single-CD states have
            # no acs_state YAML generator for share indicators, so a
            # redirected share is an orphan data file (data, no YAML). The
            # share is still emitted at the CD level for multi-CD states;
            # counts/medians DO get acs_state YAMLs via
            # derive_acs_state_from_cd.py, so those still redirect.
            if var is not None and var.agg == AGG_PCT:
                continue
            # Route to the state-level path. derive_acs_state_from_cd.py
            # would otherwise produce an empty/single-point series for
            # these because no CD JSON exists to aggregate from.
            st = SINGLE_CD_REDUNDANT[slug]
            series_id = f"{out_id}_{st}"
            write_timeseries(
                pipeline="acs_state",
                series_id=series_id,
                name=f"{name_prefix} — {st.upper()}",
                points=points,
                unit=unit,
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
        )
        written += 1
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

    print(f"\nacs_cd: wrote {written} stable-geo series across "
          f"{len(ACS_VINTAGES)} vintages "
          f"(plus {redirected} single-CD-state series redirected to acs_state)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
