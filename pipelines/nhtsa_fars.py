"""NHTSA FARS — motor-vehicle traffic fatalities by state and year.

FARS (the Fatality Analysis Reporting System) is a complete CENSUS of every
fatal traffic crash on a US public road (a death within 30 days of the crash),
run by NHTSA since 1975. Because it is a census, the per-state annual counts are
exact: no sampling error, no small-cell suppression, no <20-event reliability
flag to worry about even for the smallest jurisdictions.

Data access
-----------
The documented public API (crashviewer.nhtsa.dot.gov/CrashAPI) is Akamai-edge-
blocked for non-browser clients (HTTP 403 for any header combination), so it is
useless for an automated pipeline. Instead we read the static annual "National"
CSV zips, which serve cleanly from S3:

    https://static.nhtsa.gov/nhtsa/downloads/FARS/<YEAR>/National/FARS<YEAR>NationalCSV.zip

Each zip holds the crash-level ``accident.csv`` (one row per fatal crash). We
sum the ``FATALS`` column (deaths in that crash) grouped by ``STATE`` (FIPS) to
get per-state and national annual totals. Column order/casing drift across the
49 years, so we select columns by HEADER NAME, never index, and decode latin-1
(some early rows carry non-UTF-8 bytes). The National file covers the 50 states
+ DC (FIPS 1-56); Puerto Rico (72) and other territories live in separate files
and are excluded to match this project's geo keys.

Rates
-----
The CSVs are counts only. We derive the fatality RATE per 100,000 population
(NHTSA's headline cross-state metric, used in its State Traffic Safety
Information tables) by dividing by Census resident population, sourced from
FRED's keyless ``<USPS>POP`` series (annual, thousands; same Census estimates
NHTSA uses). The per-100-million-VMT rate (the other STSI metric) needs FHWA
Highway Statistics VM-2 data and is deferred to a later pass.

Caching: zips are ~5-35 MB each and we only need ``accident.csv``, so we cache
the tiny per-year ``{fips: fatals}`` aggregate (not the zip) under the shared
gitignored pipeline cache. A manual re-run then costs nothing; to pull a newly
posted final year, bump YEARS (FARS finalizes a data year ~1.5 yrs late).

Source YAMLs are emitted INLINE into src/content/sources/nhtsa_fars/
(overwrite-always; the dir is pipeline-owned). Like cms_nhe / bls_qcew this is a
manual bump-and-rerun (annual, final), not a weekly refresh.

Compliance / license: FARS is a US DOT federal-government work — public domain,
no copyright, no API key, no auth. Attribution: "NHTSA Fatality Analysis
Reporting System (FARS)."

Run: ``python pipelines/nhtsa_fars.py``  (optional argv: state codes / "us" to
limit which series are (re)written, e.g. ``python pipelines/nhtsa_fars.py tx``).
"""
from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import _env  # noqa: F401

from common import cached_get, write_timeseries

PIPELINE = "nhtsa_fars"
REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_DIR = REPO_ROOT / "src" / "content" / "sources" / PIPELINE
CACHE_DIR = REPO_ROOT / "pipelines" / "_cache" / "fars"

ZIP_URL = (
    "https://static.nhtsa.gov/nhtsa/downloads/FARS/"
    "{year}/National/FARS{year}NationalCSV.zip"
)
FARS_URL = "https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars"

START_YEAR = 1975  # FARS begins in 1975
# Bump as NHTSA posts each new FINAL National file (~Q1, ~1.5 yrs after the
# data year — 2023 final was posted Feb 2026).
END_YEAR = 2023

# State FIPS -> (USPS lowercase, full name). 50 states + DC; territories excluded.
FIPS_STATE = {
    1: ("al", "Alabama"), 2: ("ak", "Alaska"), 4: ("az", "Arizona"),
    5: ("ar", "Arkansas"), 6: ("ca", "California"), 8: ("co", "Colorado"),
    9: ("ct", "Connecticut"), 10: ("de", "Delaware"),
    11: ("dc", "District of Columbia"), 12: ("fl", "Florida"),
    13: ("ga", "Georgia"), 15: ("hi", "Hawaii"), 16: ("id", "Idaho"),
    17: ("il", "Illinois"), 18: ("in", "Indiana"), 19: ("ia", "Iowa"),
    20: ("ks", "Kansas"), 21: ("ky", "Kentucky"), 22: ("la", "Louisiana"),
    23: ("me", "Maine"), 24: ("md", "Maryland"), 25: ("ma", "Massachusetts"),
    26: ("mi", "Michigan"), 27: ("mn", "Minnesota"), 28: ("ms", "Mississippi"),
    29: ("mo", "Missouri"), 30: ("mt", "Montana"), 31: ("ne", "Nebraska"),
    32: ("nv", "Nevada"), 33: ("nh", "New Hampshire"), 34: ("nj", "New Jersey"),
    35: ("nm", "New Mexico"), 36: ("ny", "New York"),
    37: ("nc", "North Carolina"), 38: ("nd", "North Dakota"), 39: ("oh", "Ohio"),
    40: ("ok", "Oklahoma"), 41: ("or", "Oregon"), 42: ("pa", "Pennsylvania"),
    44: ("ri", "Rhode Island"), 45: ("sc", "South Carolina"),
    46: ("sd", "South Dakota"), 47: ("tn", "Tennessee"), 48: ("tx", "Texas"),
    49: ("ut", "Utah"), 50: ("vt", "Vermont"), 51: ("va", "Virginia"),
    53: ("wa", "Washington"), 54: ("wv", "West Virginia"),
    55: ("wi", "Wisconsin"), 56: ("wy", "Wyoming"),
}


# --- FARS download + aggregate ---------------------------------------------

def fetch_year_aggregate(year: int) -> dict[int, int]:
    """Return ``{state_fips: total_fatals}`` for one FARS year, summing FATALS
    over every crash row in accident.csv. Cached as a tiny JSON so a re-run
    never re-downloads the ~5-35 MB zip."""
    cache = CACHE_DIR / f"agg_{year}.json"
    if cache.exists():
        return {int(k): int(v) for k, v in json.loads(cache.read_text()).items()}

    url = ZIP_URL.format(year=year)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        blob = resp.read()
    zf = zipfile.ZipFile(io.BytesIO(blob))
    member = next(
        (m for m in zf.namelist() if m.lower().endswith("accident.csv")), None
    )
    if member is None:
        raise RuntimeError(f"no accident.csv in {url}: {zf.namelist()[:5]}")
    raw = zf.read(member)
    # Recent years (2021+) ship a UTF-8 BOM; older years are plain latin-1 with
    # the occasional stray high byte. utf-8-sig strips the BOM and decodes the
    # modern files; fall back to latin-1 for the legacy ones.
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    # Normalize header names: drop any stray BOM/zero-width junk + surrounding
    # space so the STATE/FATALS lookup is robust to encoding quirks.
    fields = {
        f.replace("﻿", "").strip().upper(): f
        for f in (reader.fieldnames or [])
    }
    state_f, fatals_f = fields.get("STATE"), fields.get("FATALS")
    if not state_f or not fatals_f:
        raise RuntimeError(
            f"missing STATE/FATALS in {url}: {reader.fieldnames}"
        )
    agg: dict[int, int] = {}
    for row in reader:
        try:
            fips = int(str(row[state_f]).strip())
            fat = int(float(str(row[fatals_f]).strip()))
        except (TypeError, ValueError):
            continue
        agg[fips] = agg.get(fips, 0) + fat
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(agg))
    return agg


def state_population(usps: str) -> dict[int, float]:
    """``{year: population_in_thousands}`` from FRED's keyless ``<USPS>POP``
    series (Census annual resident-population estimates, July 1, in thousands)."""
    sid = f"{usps.upper()}POP"
    body = cached_get(
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",
        ttl_seconds=30 * 24 * 3600,
    )
    out: dict[int, float] = {}
    for line in body.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        date, val = parts[0], parts[1].strip()
        if val in ("", "."):
            continue
        try:
            out[int(date[:4])] = float(val)
        except ValueError:
            continue
    return out


# --- Source-YAML emission (inline) -----------------------------------------

def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def write_yaml(sid: str, kind: str, geo_key: str, geo_name: str) -> None:
    """kind is 'count' or 'rate'."""
    if geo_key == "us":
        tags = ["health", "us"]
        loc = "US"
    else:
        tags = ["health", "us-state", "us"]
        loc = geo_key.upper()
    if kind == "count":
        name = f"Traffic fatalities — {geo_name}"
        short = f"{loc} traffic deaths"
        desc = (
            f"Motor-vehicle traffic fatalities in {geo_name}, by year. A complete "
            f"census of deaths from crashes on public roads, from the NHTSA "
            f"Fatality Analysis Reporting System. Annual, 1975 onward."
        )
        unit, decimals, suffix, uclass = "deaths", 0, "", "count"
        series = f"NHTSA FARS accident.csv FATALS summed; geo={geo_key}"
    else:
        name = f"Traffic fatality rate — {geo_name}"
        short = f"{loc} traffic death rate"
        desc = (
            f"Motor-vehicle traffic fatalities per 100,000 population in "
            f"{geo_name}, by year. Deaths from the NHTSA Fatality Analysis "
            f"Reporting System over Census resident population. Annual, 1975 "
            f"onward; the rate comparable across states and over time."
        )
        unit, decimals, suffix, uclass = (
            "per 100,000 population", 1, " per 100k", "rate",
        )
        series = f"NHTSA FARS FATALS / Census population * 100000; geo={geo_key}"

    lines = [
        f"name: {_q(name)}",
        f"shortName: {_q(short)}",
        f"description: {_q(desc)}",
        "kind: timeseries",
        f"pipeline: {PIPELINE}",
        f"dataFile: data/{PIPELINE}/{sid}.json",
        'supportedDeltas: ["1y", "5y", "10y", "30y", "50y"]',
        f'unit: "{unit}"',
        "emphasis: change",
        "formatting:",
        "  style: number",
        f"  decimals: {decimals}",
        f'  suffix: "{suffix}"',
        "provenance:",
        "  provider: NHTSA Fatality Analysis Reporting System (FARS)",
        f"  series: {series}",
        f"  url: {FARS_URL}",
        "  license: Public domain (US government data)",
        "tags:",
        *[f"  - {t}" for t in tags],
        f"unitClass: {uclass}",
        "",
    ]
    YAML_DIR.mkdir(parents=True, exist_ok=True)
    (YAML_DIR / f"{sid}.yaml").write_text("\n".join(lines), encoding="utf-8")


# --- Main ------------------------------------------------------------------

def run(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    want = {a.lower() for a in argv}  # empty = all geos

    years = list(range(START_YEAR, END_YEAR + 1))
    # {fips: {year: fatals}} + national {year: fatals}
    by_state: dict[int, dict[int, int]] = {}
    national: dict[int, int] = {}
    fetched = 0
    for yr in years:
        try:
            agg = fetch_year_aggregate(yr)
        except Exception as e:  # noqa: BLE001 — one bad year shouldn't kill the run
            print(f"  [{yr}] skipped: {e}", file=sys.stderr)
            continue
        fetched += 1
        nat = 0
        for fips, fat in agg.items():
            if fips not in FIPS_STATE:
                continue  # territories / unknown
            by_state.setdefault(fips, {})[yr] = fat
            nat += fat
        national[yr] = nat
    if fetched == 0:
        print("nhtsa_fars: no FARS years fetched (network?)", file=sys.stderr)
        return 1

    written = 0

    def emit(geo_key: str, geo_name: str, counts: dict[int, int],
             pop: dict[int, float]) -> None:
        nonlocal written
        if want and geo_key not in want:
            return
        cpts = [{"t": f"{y}-12-31", "v": counts[y]} for y in sorted(counts)]
        if len(cpts) >= 2:
            write_timeseries(PIPELINE, f"traffic_fatalities_{geo_key}",
                             f"Traffic fatalities — {geo_name}", cpts,
                             unit="deaths", merge=False)
            write_yaml(f"traffic_fatalities_{geo_key}", "count", geo_key, geo_name)
            written += 1
        rpts = []
        for y in sorted(counts):
            p = pop.get(y)
            if not p:
                continue
            rpts.append({"t": f"{y}-12-31", "v": round(counts[y] / p * 100, 1)})
        if len(rpts) >= 2:
            write_timeseries(PIPELINE, f"traffic_fatality_rate_{geo_key}",
                             f"Traffic fatality rate — {geo_name}", rpts,
                             unit="per 100,000 population", merge=False)
            write_yaml(f"traffic_fatality_rate_{geo_key}", "rate", geo_key, geo_name)
            written += 1

    # National population = sum of the 50 states + DC (consistent with the
    # state series; excludes territories, matching FARS National scope).
    nat_pop: dict[int, float] = {}
    state_pops: dict[int, dict[int, float]] = {}
    for fips, (usps, name) in FIPS_STATE.items():
        pop = state_population(usps)
        state_pops[fips] = pop
        for y, v in pop.items():
            nat_pop[y] = nat_pop.get(y, 0.0) + v

    emit("us", "United States", national, nat_pop)
    for fips, (usps, name) in FIPS_STATE.items():
        emit(usps, name, by_state.get(fips, {}), state_pops.get(fips, {}))

    print(f"nhtsa_fars: fetched {fetched} years, wrote {written} series (+ YAMLs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
