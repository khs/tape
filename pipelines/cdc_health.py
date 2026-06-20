"""CDC / NCHS health — life expectancy + leading causes of death.

Two public CDC Socrata datasets (data.cdc.gov, no API key; an optional
``$$app_token`` raises rate limits but isn't required):

  w9j2-ggv5  "Death rates and life expectancy at birth"
      National, 1900–present, by race × sex. Columns:
        year, race, sex, average_life_expectancy (years), mortality
        (age-adjusted all-cause death rate per 100,000).
      We keep race = "All Races": Both Sexes / Male / Female life
      expectancy, plus the Both-Sexes all-cause death rate.

  bi63-dtpu  "NCHS - Leading Causes of Death: United States"
      Per (year, cause, state), 1999–2017. Columns:
        year, _113_cause_name, cause_name (simplified), state, deaths,
        aadr (age-adjusted death rate per 100,000).
      We emit the age-adjusted rate per leading cause for the US + each
      state (the rate, not raw deaths, is what's comparable across
      states and over time).

Units: life expectancy in years; death rates per 100,000 (unitClass
"rate"). Emits data JSONs (public/data/cdc_health/) + source YAMLs
(src/content/sources/cdc_health/).

Compliance / ToS
----------------
These are PUBLIC-USE aggregate datasets (US-government work → public
domain; "freely distributed and copied," acknowledgment requested — we
attribute via provenance). The NCHS Data User Agreement binds us to two
things, both satisfied here: use the data for statistical reporting /
analysis only (a dashboard of aggregate rates is exactly that), and never
link or attempt to re-identify individuals. We serve only state/national
aggregates — no micro-data, no PII — so combining these in the composer
can't enable re-identification. HARD LINE: never ingest NCHS
RESTRICTED-USE micro-data (individual death records via the Research Data
Center); that carries a binding DUA and is off-limits to this pipeline.
Reliability: CDC flags rates built on <20 deaths as statistically
unreliable. This state-level leading-causes dataset is already floored
there (min observed = 21 deaths; median ~1,700), so every rate we serve
clears the threshold — and build_causes() drops any <20-death cell anyway,
so a future vintage with small cells can't slip a noisy rate through.
License: public domain (US government data).

Run: ``python pipelines/cdc_health.py`` (hits data.cdc.gov).
"""
from __future__ import annotations

import calendar
import csv
import io
import re
import sys
from pathlib import Path

import _env  # noqa: F401

from common import cached_get, strip_footnote_marker, write_timeseries

PIPELINE = "cdc_health"
REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_DIR = REPO_ROOT / "src" / "content" / "sources" / PIPELINE

LE_DATASET = "w9j2-ggv5"
CAUSES_DATASET = "bi63-dtpu"
# Drug-overdose mortality. The FINAL age-adjusted death-rate series (national +
# every state, 1999-2018) lives in "Drug Poisoning Mortality by State"
# (44rk-q6r2). The only post-2018 coverage on data.cdc.gov is the PROVISIONAL
# VSRR 12-month-ending counts (xkb8-kh2a), which bridges the recency gap.
OVERDOSE_FINAL_DATASET = "44rk-q6r2"
OVERDOSE_PROV_DATASET = "xkb8-kh2a"
# Maternal mortality (national only; states are suppressed). VSRR provisional
# maternal death counts + rates, 2019-present, post-2018-checkbox methodology.
MATERNAL_DATASET = "e2d5-ggg7"
# Infant mortality (national). Long final annual series 1915-2013; recent final
# years are hand-appended from NCHS reports (see build_infant).
INFANT_DATASET = "epev-k6ss"
SOCRATA = "https://data.cdc.gov/resource/{}.csv"

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
    "December": 12,
}


def _month_end(year: int, month: int) -> str:
    """ISO date for the last day of (year, month) — the natural timestamp for a
    12-month-ending observation reported for that month."""
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"

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
NAME_TO_ABBR = {name: ab for ab, name in STATE_NAME.items()}
NAME_TO_ABBR["United States"] = "US"  # national row in the causes dataset


def fetch_csv(
    dataset: str,
    where: str | None = None,
    select: str | None = None,
    limit: int = 200000,
) -> list[dict[str, str]]:
    """Fetch a Socrata dataset as parsed CSV rows. ``where``/``select`` pass
    SoQL ``$where``/``$select`` filters; cached_get keys the on-disk cache on
    the full param set, so a filtered fetch never collides with an unfiltered
    one. ``requests`` URL-encodes the literal ``$`` param names and the quoted
    string values, so callers write plain SoQL (e.g. ``state='United States'``).
    Note SoQL reserved words like ``group`` must be backtick-quoted by the
    caller."""
    params: dict[str, object] = {"$limit": limit}
    if select:
        params["$select"] = select
    if where:
        params["$where"] = where
    url = SOCRATA.format(dataset)
    body = cached_get(url, ttl_seconds=7 * 24 * 3600, params=params)
    return list(csv.DictReader(io.StringIO(body)))


def _f(v: str | None):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def slug(s: str) -> str:
    s = s.lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return re.sub(r"_+", "_", s)


def _yaml_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def write_yaml(
    sid: str, name: str, short_name: str, description: str, geo_key: str,
    supported: list[str], unit: str, decimals: int, suffix: str,
    series_note: str, url: str, unit_class: str | None,
    extra_tags: list[str] | None = None,
) -> None:
    YAML_DIR.mkdir(parents=True, exist_ok=True)
    # ["health", <extra topic tags>, "us-state" (states only), "us"]
    tags = ["health", *(extra_tags or [])]
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
        f'unit: "{unit}"',
        "emphasis: change",
        "formatting:",
        "  style: number",
        f"  decimals: {decimals}",
        f'  suffix: "{suffix}"',
        "provenance:",
        "  provider: CDC / National Center for Health Statistics",
        f"  series: {_yaml_str(series_note)}",
        f"  url: {url}",
        "  license: Public domain (US government data)",
        "tags:",
        *[f"  - {t}" for t in tags],
    ]
    if unit_class:
        lines.append(f"unitClass: {unit_class}")
    lines.append("")
    (YAML_DIR / f"{sid}.yaml").write_text("\n".join(lines), encoding="utf-8")


LE_URL = "https://data.cdc.gov/NCHS/NCHS-Death-rates-and-life-expectancy-at-birth/w9j2-ggv5"
CAUSES_URL = "https://data.cdc.gov/NCHS/NCHS-Leading-Causes-of-Death-United-States/bi63-dtpu"


def build_life_expectancy() -> int:
    rows = [r for r in fetch_csv(LE_DATASET) if (r.get("race") or "").strip() == "All Races"]
    by_sex: dict[str, list[dict]] = {}
    mortality: list[dict] = []
    for r in rows:
        yr = (r.get("year") or "").strip()
        sex = (r.get("sex") or "").strip()
        le = _f(r.get("average_life_expectancy"))
        if not yr or le is None:
            continue
        by_sex.setdefault(sex, []).append({"t": f"{yr}-12-31", "v": round(le, 1)})
        if sex == "Both Sexes":
            m = _f(r.get("mortality"))
            if m is not None:
                mortality.append({"t": f"{yr}-12-31", "v": round(m, 1)})

    # Splice 2019-2020 from the per-year "U.S. State Life Expectancy by Sex"
    # datasets: the headline w9j2-ggv5 table stops at 2018, so without this
    # the life-expectancy charts froze there (missing the COVID drop). Each
    # per-year dataset carries a "United States" national row by sex. The
    # LE column drifted (leb in 2019, le in 2020) and "Total" is our
    # "Both Sexes". The 2018 value is byte-identical across w9j2 and these,
    # so the methodology is consistent. 2021+ national-by-sex values exist
    # ONLY in NVSS report tables (not Socrata) and are appended below.
    PER_YEAR_LE = [("2019", "ncvk-7amm"), ("2020", "ss2j-8ajj")]
    SEX_MAP = {"Total": "Both Sexes", "Male": "Male", "Female": "Female"}
    for yr, ds in PER_YEAR_LE:
        for r in fetch_csv(ds):
            geo = strip_footnote_marker(r.get("state") or r.get("area") or "")
            if geo != "United States":
                continue
            sex = SEX_MAP.get((r.get("sex") or "").strip())
            if not sex:
                continue
            le = _f(r.get("leb") or r.get("le") or r.get("life_expectancy"))
            if le is None:
                continue
            by_sex.setdefault(sex, []).append({"t": f"{yr}-12-31", "v": round(le, 1)})

    # 2021+ US national life-expectancy-by-sex exists ONLY in NVSS/NCHS
    # report tables ("Mortality in the United States" Data Briefs), NOT in
    # any Socrata API dataset (the 2021 state dataset even dropped the
    # national row). Hand-entered FINAL figures, each cross-checked against
    # the cited primary source. When adding a year, verify Male/Female/Total
    # against that year's Data Brief before committing.
    NVSS_LE: dict[str, tuple[float, float, float]] = {
        # year: (Both Sexes, Male, Female)
        "2021": (76.4, 73.5, 79.3),  # NCHS Data Brief 456 (final 2021)
        "2022": (77.5, 74.8, 80.2),  # NCHS Data Brief 492; confirmed in 521
        "2023": (78.4, 75.8, 81.1),  # NCHS Data Brief 521 (final 2023)
        "2024": (79.0, 76.5, 81.4),  # NCHS Data Brief 548 (final 2024)
    }
    for yr, (tot, male, female) in NVSS_LE.items():
        by_sex.setdefault("Both Sexes", []).append({"t": f"{yr}-12-31", "v": tot})
        by_sex.setdefault("Male", []).append({"t": f"{yr}-12-31", "v": male})
        by_sex.setdefault("Female", []).append({"t": f"{yr}-12-31", "v": female})

    n = 0
    SEX = [("Both Sexes", "life_expectancy_us", "Life expectancy at birth — United States", "US life expectancy"),
           ("Male", "life_expectancy_male_us", "Life expectancy at birth, male — United States", "US life expectancy (male)"),
           ("Female", "life_expectancy_female_us", "Life expectancy at birth, female — United States", "US life expectancy (female)")]
    for sex, sid, name, short in SEX:
        pts = sorted(by_sex.get(sex, []), key=lambda p: p["t"])
        if len(pts) < 2:
            continue
        write_timeseries(PIPELINE, sid, name, pts, unit="years", merge=False)
        sexnote = "" if sex == "Both Sexes" else f", {sex.lower()}"
        write_yaml(
            sid, name, short,
            f"Life expectancy at birth{sexnote} for the United States, by year. "
            f"CDC / National Center for Health Statistics. Values through 2020 "
            f"come from NCHS Socrata datasets; 2021 onward are final figures "
            f"from the NCHS 'Mortality in the United States' Data Briefs, which "
            f"are the only authoritative source for recent national-by-sex "
            f"values (not available via the Socrata API).",
            "us", ["1y", "10y", "30y", "50y"], "years", 1, " yrs",
            f"CDC NCHS life expectancy at birth; All Races; {sex}", LE_URL, None,
        )
        n += 1
    # The w9j2-ggv5 mortality column also stops at 2018. Append the final
    # age-adjusted all-cause death rate (per 100k) for 2019+ from the NCHS
    # "Mortality in the United States" Data Briefs. Cross-checked against the
    # VSRR Socrata dataset 489q-934x (All causes / Age-adjusted / 12-months-
    # ending-Q4 = calendar year) for 2023+ (750.5, 722.1 — exact match).
    # That VSRR dataset only carries a ~2-year rolling window, so it can't
    # be the sole source; hand-entered final figures, verify on update.
    NVSS_DEATH_RATE = {
        "2019": 715.2,  # Data Brief 395 (final 2019)
        "2020": 835.4,  # Data Brief 427 (final 2020)
        "2021": 879.7,  # Data Brief 456 (final 2021)
        "2022": 798.8,  # Data Brief 492 (final 2022)
        "2023": 750.5,  # Data Brief 521 (final 2023); matches VSRR 489q-934x
        "2024": 722.1,  # Data Brief 548 (final 2024); matches VSRR 489q-934x
    }
    for yr, rate in NVSS_DEATH_RATE.items():
        mortality.append({"t": f"{yr}-12-31", "v": rate})

    if len(mortality) >= 2:
        mortality.sort(key=lambda p: p["t"])
        write_timeseries(PIPELINE, "death_rate_us", "Age-adjusted death rate — United States",
                         mortality, unit="per 100k", merge=False)
        write_yaml(
            "death_rate_us", "Age-adjusted death rate — United States", "US death rate",
            "Age-adjusted all-cause death rate per 100,000 population for the "
            "United States, by year. CDC / National Center for Health Statistics. "
            "Values through 2018 are from NCHS Socrata; 2019 onward are final "
            "figures from the NCHS 'Mortality in the United States' Data Briefs.",
            "us", ["1y", "10y", "30y", "50y"], "per 100k", 1, " per 100k",
            "CDC NCHS age-adjusted death rate; all causes; All Races; Both Sexes",
            LE_URL, "rate",
        )
        n += 1
    return n


def build_causes() -> int:
    # {(geo_key, cause_name): [{t, v(aadr)}]}
    series: dict[tuple[str, str], list[dict]] = {}
    for r in fetch_csv(CAUSES_DATASET):
        state = strip_footnote_marker(r.get("state") or "")
        cause = (r.get("cause_name") or "").strip()
        yr = (r.get("year") or "").strip()
        aadr = _f(r.get("aadr"))
        deaths = _f(r.get("deaths"))
        abbr = NAME_TO_ABBR.get(state)
        if not abbr or not cause or not yr or aadr is None:
            continue
        # NCHS reliability standard: a rate built on <20 deaths is
        # statistically unreliable. CDC already floors this dataset at 20
        # (min observed = 21), but enforce it here so a future vintage with
        # small cells can't slip a noisy rate onto the site.
        if deaths is not None and deaths < 20:
            continue
        geo_key = abbr.lower()  # "us" for United States
        series.setdefault((geo_key, cause), []).append({"t": f"{yr}-12-31", "v": round(aadr, 1)})

    n = 0
    for (geo_key, cause), pts in series.items():
        if len(pts) < 2:
            continue
        pts.sort(key=lambda p: p["t"])
        cslug = slug(cause)
        sid = f"{cslug}_aadr_{geo_key}"
        if geo_key == "us":
            geo_name = "United States"
            abbr = "US"
        else:
            geo_name = STATE_NAME[geo_key.upper()]
            abbr = geo_key.upper()
        name = f"{cause} death rate — {geo_name}"
        write_timeseries(PIPELINE, sid, name, pts, unit="per 100k", merge=False)
        write_yaml(
            sid, name, f"{abbr} {cause.lower()} deaths",
            f"Age-adjusted death rate per 100,000 population from {cause.lower()} "
            f"for {geo_name}, by year. CDC / National Center for Health "
            f"Statistics (Leading Causes of Death).",
            geo_key, ["1y", "5y", "10y"], "per 100k", 1, " per 100k",
            f"CDC NCHS leading causes of death; cause={cause}; geo={geo_key}",
            CAUSES_URL, "rate",
        )
        n += 1
    return n


OVERDOSE_FINAL_URL = "https://data.cdc.gov/d/44rk-q6r2"
OVERDOSE_PROV_URL = (
    "https://data.cdc.gov/NCHS/VSRR-Provisional-Drug-Overdose-Death-Counts/"
    "xkb8-kh2a"
)


def build_overdose() -> int:
    """Drug-overdose mortality: final age-adjusted death rate (national + every
    state, 1999-2018) + a provisional national 12-month-ending count that
    bridges the recency gap past 2018."""
    n = 0

    # ---- FINAL age-adjusted death rate, national + per state (1999-2018) ----
    # CRITICAL: 44rk-q6r2 carries one row per (state, year, sex, age, race);
    # filter to the all-population total or an unfiltered read silently grabs a
    # sub-stratum. ageadjrate is age-adjusted to the 2000 US standard pop.
    rows = fetch_csv(
        OVERDOSE_FINAL_DATASET,
        where=("sex='Both Sexes' AND age='All Ages' AND "
               "race='All Races-All Origins'"),
        select="state,year,deaths,ageadjrate",
    )
    series: dict[str, list[dict]] = {}
    for r in rows:
        state = strip_footnote_marker(r.get("state") or "")
        abbr = NAME_TO_ABBR.get(state)
        yr = (r.get("year") or "").strip()
        aadr = _f(r.get("ageadjrate"))
        deaths = _f(r.get("deaths"))
        if not abbr or not yr or aadr is None:
            continue
        # NCHS flags rates built on <20 deaths as unreliable; drop them.
        if deaths is not None and deaths < 20:
            continue
        series.setdefault(abbr.lower(), []).append(
            {"t": f"{yr}-12-31", "v": round(aadr, 1)}
        )

    for geo_key, pts in series.items():
        if len(pts) < 2:
            continue
        pts.sort(key=lambda p: p["t"])
        sid = f"drug_overdose_aadr_{geo_key}"
        if geo_key == "us":
            geo_name, abbr = "United States", "US"
        else:
            geo_name, abbr = STATE_NAME[geo_key.upper()], geo_key.upper()
        name = f"Drug overdose death rate — {geo_name}"
        write_timeseries(PIPELINE, sid, name, pts, unit="per 100k", merge=False)
        write_yaml(
            sid, name, f"{abbr} overdose deaths",
            f"Age-adjusted death rate per 100,000 population from drug overdose "
            f"(drug poisoning) for {geo_name}, by year. CDC / National Center "
            f"for Health Statistics. Final data, 1999 through 2018; ICD-10 "
            f"underlying-cause codes X40-X44, X60-X64, X85, Y10-Y14.",
            geo_key, ["1y", "5y", "10y", "30y"], "per 100k", 1, " per 100k",
            f"CDC NCHS drug poisoning mortality; age-adjusted; geo={geo_key}",
            OVERDOSE_FINAL_URL, "rate",
        )
        n += 1

    # ---- PROVISIONAL national 12-month-ending count (recency bridge) ----
    # Rolling-year totals reported monthly. predicted_value is CDC's
    # completeness-adjusted figure (the headline VSRR number); it corrects the
    # downward bias in the most recent months, where data_value undercounts
    # because toxicology / death records are still landing. Fall back to the raw
    # data_value if a predicted value is missing.
    prov = fetch_csv(
        OVERDOSE_PROV_DATASET,
        where=("state='US' AND indicator='Number of Drug Overdose Deaths' "
               "AND period='12 month-ending'"),
        select="year,month,data_value,predicted_value",
    )
    ppts: list[dict] = []
    for r in prov:
        yr = (r.get("year") or "").strip()
        mon = MONTHS.get((r.get("month") or "").strip())
        val = _f(r.get("predicted_value"))
        if val is None:
            val = _f(r.get("data_value"))
        if not yr or not mon or val is None:
            continue
        ppts.append({"t": _month_end(int(yr), mon), "v": int(round(val))})

    if len(ppts) >= 2:
        ppts.sort(key=lambda p: p["t"])
        sid = "drug_overdose_deaths_12mo_us"
        name = "Drug overdose deaths, 12-month rolling — United States"
        write_timeseries(PIPELINE, sid, name, ppts, unit="deaths", merge=False)
        write_yaml(
            sid, name, "US overdose deaths",
            "Provisional count of US drug-overdose deaths over the trailing 12 "
            "months, reported monthly. CDC / National Center for Health "
            "Statistics, Vital Statistics Rapid Release. Each point is a "
            "rolling-year total (not a calendar-year count); values are the "
            "completeness-adjusted predicted figure CDC publishes as the "
            "headline. This bridges the final age-adjusted rate series, which "
            "ends in 2018.",
            "us", ["1y", "5y", "10y"], "deaths", 0, "",
            "CDC NCHS VSRR provisional drug overdose deaths; 12 month-ending; US",
            OVERDOSE_PROV_URL, "count",
        )
        n += 1

    return n


MATERNAL_URL = (
    "https://data.cdc.gov/NCHS/"
    "VSRR-Provisional-Maternal-Death-Counts-and-Rates/e2d5-ggg7"
)
# (exact subgroup string, id slug, human label). Total/White/Black/Hispanic are
# reliable across all years; AIAN and NHOPI cells are frequently <20 deaths and
# suppressed, so they are deliberately left out.
MATERNAL_RACE = [
    ("Black, Non-Hispanic", "black", "Black (non-Hispanic)"),
    ("White, Non-Hispanic", "white", "White (non-Hispanic)"),
    ("Hispanic", "hispanic", "Hispanic"),
]
_MATERNAL_CAVEAT = (
    "National only; most state cells are suppressed. Figures use the post-2018 "
    "pregnancy-checkbox coding and are not comparable to maternal mortality "
    "published before 2018 (historically near 12 to 15 per 100,000). Each year "
    "is the December 12-month-ending window (the calendar-year value); recent "
    "years are provisional and revised as records complete."
)


def build_maternal() -> int:
    """National maternal mortality rate (deaths per 100,000 live births),
    overall + the three reliably-reported race/ethnicity groups, plus the raw
    death count. NCHS VSRR; national only (states suppressed). Uses the
    December 12-month-ending row as the calendar-year value."""
    rows = [
        r for r in fetch_csv(MATERNAL_DATASET)
        if (r.get("jurisdiction") or "").strip() == "United States"
        and (r.get("month_of_death") or "").strip() == "12"
    ]
    n = 0

    def rate_points(group: str, subgroup: str) -> list[dict]:
        pts = []
        for r in rows:
            if (r.get("group") or "").strip() != group:
                continue
            if (r.get("subgroup") or "").strip() != subgroup:
                continue
            yr = (r.get("year_of_death") or "").strip()
            rate = _f(r.get("maternal_mortality_rate"))
            if not yr or rate is None:
                continue
            pts.append({"t": f"{yr}-12-31", "v": round(rate, 1)})
        pts.sort(key=lambda p: p["t"])
        return pts

    # ---- Overall rate ----
    total = rate_points("Total", "Total")
    if len(total) >= 2:
        write_timeseries(
            PIPELINE, "maternal_mortality_rate_us",
            "Maternal mortality rate — United States", total,
            unit="per 100,000 live births", merge=False,
        )
        write_yaml(
            "maternal_mortality_rate_us",
            "Maternal mortality rate — United States", "US maternal mortality",
            f"Maternal deaths per 100,000 live births for the United States, by "
            f"year. CDC / National Center for Health Statistics, Vital "
            f"Statistics Rapid Release. WHO maternal-death definition (death "
            f"while pregnant or within 42 days). {_MATERNAL_CAVEAT}",
            "us", ["1y", "5y", "10y"], "per 100,000 live births", 1, " per 100k",
            "CDC NCHS VSRR maternal mortality; Total; 12 month-ending Dec; US",
            MATERNAL_URL, "rate", extra_tags=["gender"],
        )
        n += 1

    # ---- Overall death count ----
    cpts = []
    for r in rows:
        if ((r.get("group") or "").strip() == "Total"
                and (r.get("subgroup") or "").strip() == "Total"):
            yr = (r.get("year_of_death") or "").strip()
            d = _f(r.get("maternal_deaths"))
            if yr and d is not None:
                cpts.append({"t": f"{yr}-12-31", "v": int(round(d))})
    cpts.sort(key=lambda p: p["t"])
    if len(cpts) >= 2:
        write_timeseries(
            PIPELINE, "maternal_deaths_us",
            "Maternal deaths — United States", cpts, unit="deaths", merge=False,
        )
        write_yaml(
            "maternal_deaths_us", "Maternal deaths — United States",
            "US maternal deaths",
            f"Number of maternal deaths in the United States, by year (the "
            f"numerator behind the maternal mortality rate). CDC / National "
            f"Center for Health Statistics, Vital Statistics Rapid Release. "
            f"{_MATERNAL_CAVEAT}",
            "us", ["1y", "5y", "10y"], "deaths", 0, "",
            "CDC NCHS VSRR maternal deaths; Total; 12 month-ending Dec; US",
            MATERNAL_URL, "count", extra_tags=["gender"],
        )
        n += 1

    # ---- Race / ethnicity rates (disparity) ----
    for subgroup, slug_, label in MATERNAL_RACE:
        pts = rate_points("Race and Hispanic origin", subgroup)
        if len(pts) < 2:
            continue
        sid = f"maternal_mortality_rate_{slug_}_us"
        name = f"Maternal mortality rate, {label} — United States"
        write_timeseries(
            PIPELINE, sid, name, pts,
            unit="per 100,000 live births", merge=False,
        )
        write_yaml(
            sid, name, f"US maternal mortality ({slug_})",
            f"Maternal deaths per 100,000 live births for {label} women in the "
            f"United States, by year. CDC / National Center for Health "
            f"Statistics, Vital Statistics Rapid Release. {_MATERNAL_CAVEAT}",
            "us", ["1y", "5y", "10y"], "per 100,000 live births", 1, " per 100k",
            f"CDC NCHS VSRR maternal mortality; {subgroup}; 12 month-ending Dec; US",
            MATERNAL_URL, "rate", extra_tags=["gender"],
        )
        n += 1

    return n


INFANT_URL = "https://data.cdc.gov/d/epev-k6ss"
# FINAL national infant mortality rate (deaths under 1 year per 1,000 live
# births) for the years past the 1915-2013 Socrata series. From NCHS "Infant
# Mortality in the United States" reports: 2014-2022 = NVSR Vol 73 No 5 (Jul
# 2024, Table 1); 2023 = NVSR Vol 74 No 7 (Jun 2025). 2022 was the first
# statistically significant annual rise in roughly two decades. Verify each
# value against the cited report when extending this dict.
INFANT_FINAL = {
    "2014": 5.82, "2015": 5.90, "2016": 5.87, "2017": 5.79, "2018": 5.67,
    "2019": 5.58, "2020": 5.42, "2021": 5.44, "2022": 5.61, "2023": 5.61,
}
# Provisional latest year (NCHS VSRR No. 42, Jan 2026); revised as records land.
INFANT_PROVISIONAL = {"2024": 5.52}


def build_infant() -> int:
    """National infant mortality rate (deaths under 1 year per 1,000 live
    births). Long final annual series 1915-2013 from NCHS Socrata (epev-k6ss,
    type=Infant), extended with hand-entered NCHS-report finals (2014-2023) and
    the latest provisional year. National only — no state IMR is published on
    data.cdc.gov (it lives only in query-only CDC WONDER)."""
    rows = fetch_csv(
        INFANT_DATASET, where="type='Infant'", select="year,mortality_rate",
    )
    pts = []
    for r in rows:
        yr = (r.get("year") or "").strip()
        v = _f(r.get("mortality_rate"))
        if yr and v is not None:
            pts.append({"t": f"{yr}-12-31", "v": round(v, 2)})
    for yr, v in {**INFANT_FINAL, **INFANT_PROVISIONAL}.items():
        pts.append({"t": f"{yr}-12-31", "v": v})
    # De-dup by year (Socrata ends 2013, appends start 2014 — no overlap, but be
    # defensive); a later entry wins.
    by_t = {p["t"]: p for p in pts}
    pts = [by_t[t] for t in sorted(by_t)]
    if len(pts) < 2:
        return 0
    write_timeseries(
        PIPELINE, "infant_mortality_rate_us",
        "Infant mortality rate — United States", pts,
        unit="per 1,000 live births", merge=False,
    )
    write_yaml(
        "infant_mortality_rate_us",
        "Infant mortality rate — United States", "US infant mortality",
        "Deaths of infants under 1 year per 1,000 live births in the United "
        "States, by year. CDC / National Center for Health Statistics. The long "
        "annual series (1915-2013) is from NCHS Socrata; 2014-2023 are final "
        "figures from the NCHS 'Infant Mortality in the United States' reports "
        "and 2024 is provisional. National only; state infant mortality is not "
        "published on data.cdc.gov. The rate fell from about 100 per 1,000 in "
        "1915 to a low of 5.42 in 2020, then rose significantly in 2022.",
        "us", ["1y", "10y", "30y", "50y"], "per 1,000 live births", 2,
        " per 1k",
        "CDC NCHS infant mortality; type=Infant; US (Socrata 1915-2013 + NCHS "
        "report finals 2014-2023 + 2024 provisional)",
        INFANT_URL, "rate",
    )
    return 1


ABORTION_URL = "https://www.cdc.gov/mmwr/volumes/73/ss/ss7307a1.htm"
_ABORTION_CAVEAT = (
    "National only. CDC abortion surveillance is voluntary and incomplete: "
    "several areas do not report, including California, Maryland, New Hampshire, "
    "and New Jersey, so the count undercounts total US abortions. These figures "
    "use the 47 areas that reported every year from 2013 to 2022, so the series "
    "is consistent over time; the fuller national count published by the "
    "Guttmacher Institute is substantially higher. Recent years are provisional."
)
# year -> (number, rate per 1,000 women 15-44, ratio per 1,000 live births).
# CDC Abortion Surveillance (MMWR SS73/07, Table 1); the 47 reporting areas that
# reported continuously 2013-2022 (year-comparable; the all-48-areas 2022 total
# was 613,383, intentionally not mixed in). Hand-entered from the MMWR report,
# the same pattern as the NVSS life-expectancy / infant-mortality dicts above;
# there is NO Socrata dataset for national abortion surveillance.
ABORTION = {
    "2013": (640154, 12.4, 198), "2014": (625668, 12.0, 190),
    "2015": (613911, 11.8, 187), "2016": (599001, 11.5, 184),
    "2017": (587611, 11.2, 184), "2018": (591884, 11.2, 188),
    "2019": (603168, 11.4, 194), "2020": (592939, 11.1, 197),
    "2021": (622108, 11.6, 204), "2022": (609360, 11.2, 199),
}


def build_abortion() -> int:
    """National reported-abortion count, rate, and ratio (CDC Abortion
    Surveillance). National only; hand-entered from the MMWR report (no Socrata
    endpoint exists). Tagged gender, alongside maternal mortality."""
    yrs = sorted(ABORTION)
    specs = [
        ("abortions_reported_us", "Reported abortions — United States",
         "US abortions", 0, "abortions", 0, "", "count",
         "CDC Abortion Surveillance MMWR; 47 continuous reporting areas; number",
         "Number of legal induced abortions reported to CDC"),
        ("abortion_rate_us", "Abortion rate — United States",
         "US abortion rate", 1, "per 1,000 women 15-44", 1, " per 1k", "rate",
         "CDC Abortion Surveillance MMWR; 47 continuous reporting areas; rate",
         "Legal induced abortions per 1,000 women aged 15 to 44"),
        ("abortion_ratio_us", "Abortion ratio — United States",
         "US abortion ratio", 2, "per 1,000 live births", 0, " per 1k births",
         "ratio",
         "CDC Abortion Surveillance MMWR; 47 continuous reporting areas; ratio",
         "Legal induced abortions per 1,000 live births"),
    ]
    n = 0
    for sid, name, short, idx, unit, dec, suf, ucls, note, lead in specs:
        pts = [{"t": f"{y}-12-31", "v": ABORTION[y][idx]} for y in yrs]
        write_timeseries(PIPELINE, sid, name, pts, unit=unit, merge=False)
        write_yaml(
            sid, name, short,
            f"{lead} in the United States, by year. CDC / National Center for "
            f"Health Statistics, Abortion Surveillance. {_ABORTION_CAVEAT}",
            "us", ["1y", "5y", "10y"], unit, dec, suf, note, ABORTION_URL,
            ucls, extra_tags=["gender"],
        )
        n += 1
    return n


BUILDERS = {
    "life_expectancy": build_life_expectancy,
    "causes": build_causes,
    "overdose": build_overdose,
    "maternal": build_maternal,
    "infant": build_infant,
    "abortion": build_abortion,
}


def main(argv: list[str] | None = None) -> int:
    # Optional subset filter: `python pipelines/cdc_health.py overdose causes`
    # runs only those builders. With no args, run them all. Selective runs keep
    # an incremental add from rewriting every other series' file (merge-on-write
    # bumps lastUpdated on each write, which would otherwise churn the diff).
    argv = sys.argv[1:] if argv is None else argv
    selected = [a for a in argv if a in BUILDERS]
    unknown = [a for a in argv if a not in BUILDERS]
    if unknown:
        print(f"  unknown builder(s) ignored: {', '.join(unknown)} "
              f"(known: {', '.join(BUILDERS)})", file=sys.stderr)
    names = selected or list(BUILDERS)
    counts = {name: BUILDERS[name]() for name in names}
    summary = " + ".join(f"{counts[n]} {n}" for n in names)
    print(f"[cdc_health] wrote {summary} series (+ YAMLs).")
    if sum(counts.values()) == 0:
        print("  nothing written — check network access to data.cdc.gov",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
