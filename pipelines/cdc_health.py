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

import csv
import io
import re
import sys
from pathlib import Path

import _env  # noqa: F401

from common import cached_get, write_timeseries

PIPELINE = "cdc_health"
REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_DIR = REPO_ROOT / "src" / "content" / "sources" / PIPELINE

LE_DATASET = "w9j2-ggv5"
CAUSES_DATASET = "bi63-dtpu"
SOCRATA = "https://data.cdc.gov/resource/{}.csv"

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


def fetch_csv(dataset: str) -> list[dict[str, str]]:
    url = SOCRATA.format(dataset)
    body = cached_get(url, ttl_seconds=7 * 24 * 3600, params={"$limit": 200000})
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
) -> None:
    YAML_DIR.mkdir(parents=True, exist_ok=True)
    tags = ["health"]
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
            geo = (r.get("state") or r.get("area") or "").strip()
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
    if len(mortality) >= 2:
        mortality.sort(key=lambda p: p["t"])
        write_timeseries(PIPELINE, "death_rate_us", "Age-adjusted death rate — United States",
                         mortality, unit="per 100k", merge=False)
        write_yaml(
            "death_rate_us", "Age-adjusted death rate — United States", "US death rate",
            "Age-adjusted all-cause death rate per 100,000 population for the "
            "United States, by year. CDC / National Center for Health Statistics.",
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
        state = (r.get("state") or "").strip()
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


def main() -> int:
    le = build_life_expectancy()
    causes = build_causes()
    print(f"[cdc_health] wrote {le} life-expectancy/mortality + {causes} "
          f"cause-of-death series (+ YAMLs).")
    if le == 0 and causes == 0:
        print("  nothing written — check network access to data.cdc.gov",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
