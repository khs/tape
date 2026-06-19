"""
Pull series from the BLS Public Data API (https://api.bls.gov).

FRED redistributes most macro BLS series (CPI, unemployment, payrolls),
which we already have. The point of this pipeline is the *granular* BLS
data that FRED doesn't carry — state-level employment, CPI subcomponents
(beyond all-items and core), JOLTS by industry, regional inflation, etc.
These are the charts a DC policy reader actually wants when they're
arguing about, e.g., "rent inflation in major metros" or "healthcare
employment by state."

API notes:
* Unregistered usage allows 25 series per query, 10 years of data, and
  25 queries/day per IP — enough for a weekly refresh of a curated set.
* Registered (free) gets a key and bumps the daily quota; we don't need
  it yet but it's the next step when the series list grows.
* All BLS series have a static series-id format; the trick is knowing
  which ones to pull. The list below is curated for the DC audience.

Run with: ``python pipelines/bls.py``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

import _env  # noqa: F401 — load .env so BLS_API_KEY is available
from common import write_timeseries


BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
# Registered (free) BLS API key: 20-year window, 50 series/request, 500
# req/day. Without it we fall back to the keyless 10-year trailing window.
BLS_API_KEY = os.environ.get("BLS_API_KEY", "").strip()
# Earliest year we try to pull (keyed). Covers LAUS (1976+), CPI (1947+),
# CES state payrolls (1990+); series that begin later just return empty for
# the early windows. The keyed API caps each request at 20 years, so full
# history is fetched as a sequence of 20-year windows merged per series.
HISTORY_START = 1947


@dataclass
class BlsSpec:
    series_id: str  # BLS series identifier
    out_id: str  # how we write the file (data/bls/<out_id>.json)
    label: str
    unit: str
    notes: str = ""


# US states + DC, keyed by FIPS code. DC included because policy people
# care about it as a labor market and many congressional staffers live
# there; including it matches the rest of our audience-oriented choices.
US_STATES: dict[str, tuple[str, str]] = {
    "01": ("AL", "Alabama"),
    "02": ("AK", "Alaska"),
    "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"),
    "06": ("CA", "California"),
    "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"),
    "10": ("DE", "Delaware"),
    "11": ("DC", "District of Columbia"),
    "12": ("FL", "Florida"),
    "13": ("GA", "Georgia"),
    "15": ("HI", "Hawaii"),
    "16": ("ID", "Idaho"),
    "17": ("IL", "Illinois"),
    "18": ("IN", "Indiana"),
    "19": ("IA", "Iowa"),
    "20": ("KS", "Kansas"),
    "21": ("KY", "Kentucky"),
    "22": ("LA", "Louisiana"),
    "23": ("ME", "Maine"),
    "24": ("MD", "Maryland"),
    "25": ("MA", "Massachusetts"),
    "26": ("MI", "Michigan"),
    "27": ("MN", "Minnesota"),
    "28": ("MS", "Mississippi"),
    "29": ("MO", "Missouri"),
    "30": ("MT", "Montana"),
    "31": ("NE", "Nebraska"),
    "32": ("NV", "Nevada"),
    "33": ("NH", "New Hampshire"),
    "34": ("NJ", "New Jersey"),
    "35": ("NM", "New Mexico"),
    "36": ("NY", "New York"),
    "37": ("NC", "North Carolina"),
    "38": ("ND", "North Dakota"),
    "39": ("OH", "Ohio"),
    "40": ("OK", "Oklahoma"),
    "41": ("OR", "Oregon"),
    "42": ("PA", "Pennsylvania"),
    "44": ("RI", "Rhode Island"),
    "45": ("SC", "South Carolina"),
    "46": ("SD", "South Dakota"),
    "47": ("TN", "Tennessee"),
    "48": ("TX", "Texas"),
    "49": ("UT", "Utah"),
    "50": ("VT", "Vermont"),
    "51": ("VA", "Virginia"),
    "53": ("WA", "Washington"),
    "54": ("WV", "West Virginia"),
    "55": ("WI", "Wisconsin"),
    "56": ("WY", "Wyoming"),
}


def state_unemployment_specs() -> list[BlsSpec]:
    """
    LAUS state-level unemployment rate series IDs are formed by:
      LASST + <FIPS> + 0000000000 + 003
    where 003 is the unemployment-rate measure code. SA series.
    """
    out: list[BlsSpec] = []
    for fips, (abbr, name) in US_STATES.items():
        out.append(
            BlsSpec(
                series_id=f"LASST{fips}0000000000003",
                out_id=f"state_unemployment_{abbr.lower()}",
                label=f"{name} unemployment rate",
                unit="%",
            )
        )
    return out


# DC-metro counties for the VA-08 / DC-metro dashboard storyline. State
# FIPS + county FIPS combined into the 5-digit code BLS uses.
# Format below: (fips5, slug, display name).
DC_METRO_COUNTIES: list[tuple[str, str, str]] = [
    ("51013", "arlington_va",      "Arlington County, VA"),
    ("51510", "alexandria_va",     "Alexandria City, VA"),
    ("51610", "falls_church_va",   "Falls Church City, VA"),
    ("51059", "fairfax_va",        "Fairfax County, VA"),
    ("51107", "loudoun_va",        "Loudoun County, VA"),
    ("51153", "prince_william_va", "Prince William County, VA"),
    ("24031", "montgomery_md",     "Montgomery County, MD"),
    ("24033", "prince_georges_md", "Prince George's County, MD"),
]


def dc_metro_county_unemployment_specs() -> list[BlsSpec]:
    """
    LAUS county unemployment-rate series. Format:
        LAUCN + <5-digit state+county FIPS> + 0000000003
    where 003 is the unemployment-rate measure code. Monthly, NSA — BLS
    only publishes seasonally-adjusted county series for a handful of
    large metros; we use the not-seasonally-adjusted variant for
    consistency across all DC-metro jurisdictions.
    """
    out: list[BlsSpec] = []
    for fips5, slug, name in DC_METRO_COUNTIES:
        out.append(
            BlsSpec(
                series_id=f"LAUCN{fips5}0000000003",
                out_id=f"county_unemployment_{slug}",
                label=f"{name} — unemployment rate",
                unit="%",
            )
        )
    return out


def state_payrolls_specs() -> list[BlsSpec]:
    """
    CES (Current Employment Statistics) state-level total nonfarm payroll
    employment series IDs are formed by:
      SMS + <FIPS> + 00000 + 00 + 000000 + 01
    where the final 01 = "All Employees, In Thousands". SA series.
    """
    out: list[BlsSpec] = []
    for fips, (abbr, name) in US_STATES.items():
        out.append(
            BlsSpec(
                # 20-char SM series ID: SMS (3) + FIPS (2) + area (5)
                # + supersector (2) + industry (6) + data type (2)
                # = 3 + 2 + "000000000000001" (15 chars) = 20.
                series_id=f"SMS{fips}000000000000001",
                out_id=f"state_payrolls_{abbr.lower()}",
                label=f"{name} nonfarm payroll employment",
                unit="thousands of persons",
            )
        )
    return out


# LAUS measure codes beyond the headline unemployment rate (003, covered by
# state_unemployment_specs). Each tuple is (measure, out_id stem, label
# suffix, unit). Verified live against the California series 2026-06:
# employment 18.67M, labor force 19.72M, employed + unemployed == labor
# force exactly, and 1 - employed/labor-force reproduces the published
# unemployment rate (5.3%). Levels are RAW PERSON COUNTS (not thousands —
# that caveat is CES-only), stored raw per the canonical-units invariant.
LAUS_MEASURES: list[tuple[str, str, str, str]] = [
    ("004", "unemployed",     "unemployment level",                 "people"),
    ("005", "employed",       "employment level (household survey)", "people"),
    ("006", "labor_force",    "labor force",                        "people"),
    ("007", "emp_pop_ratio",  "employment-population ratio",        "%"),
    ("008", "lfpr",           "labor force participation rate",     "%"),
]


def state_labor_force_specs() -> list[BlsSpec]:
    """
    LAUS state-level labor-force measures beyond the headline unemployment
    rate. Series IDs: LASST + <FIPS> + 0000000000 + <measure>. SA, monthly.
    See LAUS_MEASURES for the per-measure codes, units, and the live
    California cross-check that pins down units + measure semantics.
    """
    out: list[BlsSpec] = []
    for fips, (abbr, name) in US_STATES.items():
        for code, stem, suffix, unit in LAUS_MEASURES:
            out.append(
                BlsSpec(
                    series_id=f"LASST{fips}0000000000{code}",
                    out_id=f"state_{stem}_{abbr.lower()}",
                    label=f"{name} {suffix}",
                    unit=unit,
                )
            )
    return out


# Curated set. Categories:
#   1. CPI subcomponents — beyond what FRED carries broadly
#   2. JOLTS by industry — labor demand granularity
#   3. State-level unemployment + payrolls — geographic dispersion across
#      all 50 states + DC
#
# Add more series here as needed; each one ships its own chart manifest.
SERIES: list[BlsSpec] = [
    # ---- CPI subcomponents (CUUR0000SA*, seasonally adjusted = SUUR/CUSR) ----
    BlsSpec(
        series_id="CUUR0000SAH1",
        out_id="cpi_shelter",
        label="CPI: shelter (housing)",
        unit="index 1982-84=100",
        notes="Headline shelter CPI; the single biggest weight in core CPI.",
    ),
    BlsSpec(
        series_id="CUUR0000SAM",
        out_id="cpi_medical",
        label="CPI: medical care",
        unit="index 1982-84=100",
    ),
    BlsSpec(
        series_id="CUUR0000SETA01",
        out_id="cpi_new_vehicles",
        label="CPI: new vehicles",
        unit="index 1982-84=100",
    ),
    BlsSpec(
        series_id="CUUR0000SETA02",
        out_id="cpi_used_vehicles",
        label="CPI: used cars & trucks",
        unit="index 1982-84=100",
    ),
    # ---- JOLTS (Job Openings & Labor Turnover Survey), national totals
    #      by industry slice. JTU* = total nonfarm; subsectors append a
    #      sector code. We carry the headline + a few high-information
    #      sectors. Levels are in thousands of jobs/quits/hires.
    BlsSpec(
        series_id="JTS000000000000000QUR",
        out_id="jolts_quits_rate",
        label="JOLTS: quits rate (total nonfarm)",
        unit="% of employment",
        notes="Quits as a share of employment, the 'great resignation' metric.",
    ),
    BlsSpec(
        series_id="JTS000000000000000HIR",
        out_id="jolts_hires_rate",
        label="JOLTS: hires rate (total nonfarm)",
        unit="% of employment",
    ),
    # ---- Employment Cost Index (ECI) ----
    # Quarterly index of labor costs (compensation per hour worked), holding
    # the job mix fixed so it isn't skewed by shifts between high/low-wage
    # work — the Fed's preferred wage-pressure gauge. Seasonally adjusted
    # "current dollar index", base Dec 2005 = 100 (CIS prefix = compensation,
    # seasonally adjusted; trailing I = index). Series IDs verified against the
    # BLS catalog (series_title) on 2026-06-19. Civilian = private + state/local
    # gov; we carry the civilian comp/wages/benefits split + the private and
    # government sector cuts.
    BlsSpec(
        series_id="CIS1010000000000I",
        out_id="eci_total_comp_civilian",
        label="ECI: total compensation (all civilian workers)",
        unit="index Dec 2005=100",
        notes="Headline Employment Cost Index; the Fed's preferred "
        "wage-pressure gauge.",
    ),
    BlsSpec(
        series_id="CIS1020000000000I",
        out_id="eci_wages_civilian",
        label="ECI: wages and salaries (all civilian workers)",
        unit="index Dec 2005=100",
    ),
    BlsSpec(
        series_id="CIS1030000000000I",
        out_id="eci_benefits_civilian",
        label="ECI: benefits (all civilian workers)",
        unit="index Dec 2005=100",
    ),
    BlsSpec(
        series_id="CIS2010000000000I",
        out_id="eci_total_comp_private",
        label="ECI: total compensation (private industry)",
        unit="index Dec 2005=100",
    ),
    BlsSpec(
        series_id="CIS3010000000000I",
        out_id="eci_total_comp_govt",
        label="ECI: total compensation (state & local government)",
        unit="index Dec 2005=100",
    ),
    # ---- Metro CPI ----
    # Replacement for the discontinued FRED Washington-Baltimore CMSA
    # series (CUUSA311SA0, dead since 2017). BLS redefined the area as
    # the Washington-Arlington-Alexandria CBSA (area code S35A) and
    # publishes it on the Public Data API but NOT via FRED's CSV
    # endpoint — hence the move to this pipeline. Semi-annual.
    BlsSpec(
        series_id="CUURS35ASA0",
        out_id="cpi_washington_metro",
        label="CPI: Washington-Arlington-Alexandria metro (all items)",
        unit="index 1982-84=100",
        notes="DC-metro consumer price index; successor to the "
        "discontinued FRED Washington-Baltimore CMSA series.",
    ),
    # ---- State-level series follow, generated programmatically. ----
] + (
    state_unemployment_specs()
    + state_payrolls_specs()
    + state_labor_force_specs()
    + dc_metro_county_unemployment_specs()
)


def _fetch_window(series_ids: list[str], start_year: int, end_year: int) -> dict[str, list[dict]]:
    """One BLS POST for a single window (<=20yr keyed, <=10yr keyless)."""
    payload: dict = {
        "seriesid": series_ids,
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    if BLS_API_KEY:
        payload["registrationkey"] = BLS_API_KEY
    result = subprocess.run(
        [
            "curl", "-sS", "--max-time", "60",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(payload),
            BLS_URL,
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    parsed = json.loads(result.stdout)
    if parsed.get("status") != "REQUEST_SUCCEEDED":
        msg = parsed.get("message", ["unknown error"])
        raise RuntimeError(f"BLS API: {msg}")
    out: dict[str, list[dict]] = {}
    for s in parsed.get("Results", {}).get("series", []):
        out[s.get("seriesID", "")] = s.get("data", [])
    return out


def fetch_bls(series_ids: list[str]) -> dict[str, list[dict]]:
    """
    Returns {series_id: [{year, period, value}, ...]}.

    WITH a registered BLS_API_KEY, pulls the FULL available history by
    sweeping 20-year windows from HISTORY_START to now and merging them
    (windows are non-overlapping; downstream dedupes by date anyway). The
    keyed API allows 50 series/request, 20-year windows, 500 req/day.

    WITHOUT a key, falls back to a single trailing 10-year window — the
    keyless API caps at 25 series and 10 years and returns only the first
    10 years of any wider range, so the trailing decade is all we can get.
    """
    if not series_ids:
        return {}
    cap = 50 if BLS_API_KEY else 25
    if len(series_ids) > cap:
        raise ValueError(f"BLS API caps at {cap} series per request")
    end_year = datetime.now(timezone.utc).year
    if not BLS_API_KEY:
        return _fetch_window(series_ids, end_year - 9, end_year)
    merged: dict[str, list[dict]] = defaultdict(list)
    hi = end_year
    while hi >= HISTORY_START:
        lo = max(HISTORY_START, hi - 19)  # 20 years inclusive
        for sid, rows in _fetch_window(series_ids, lo, hi).items():
            merged[sid].extend(rows)
        hi = lo - 1
    return dict(merged)


def bls_period_to_iso(year: str, period: str) -> str | None:
    """
    BLS uses period codes like:
      M01..M12: months  (M13 = annual average, skip)
      Q01..Q04: quarters
      A01:      annual
    Convert to ISO date (last day of period for max useful granularity).
    """
    try:
        y = int(year)
    except (ValueError, TypeError):
        return None
    if period.startswith("M"):
        m = int(period[1:])
        if not 1 <= m <= 12:
            return None
        # Use the 15th of the month — BLS doesn't publish a specific day,
        # mid-month avoids the "last-day-might-be-in-next-month" ambiguity.
        return f"{y:04d}-{m:02d}-15"
    if period.startswith("Q"):
        q = int(period[1:])
        if not 1 <= q <= 4:
            return None
        # End-of-quarter month, mid-month.
        m = q * 3
        return f"{y:04d}-{m:02d}-15"
    if period.startswith("A"):
        return f"{y:04d}-12-31"
    return None


def main() -> int:
    # Optional CLI subset: any positional args filter SERIES to specs whose
    # out_id or series_id contains one of the tokens. Lets us refetch just a
    # new family (e.g. `python pipelines/bls.py state_lfpr state_employed`)
    # without burning the keyless API's 25-queries/day budget on the ~117
    # series we already have, and without polluting the commit diff with
    # routine refreshes of unrelated series.
    tokens = [a for a in sys.argv[1:] if not a.startswith("-")]
    series = SERIES
    if tokens:
        series = [
            s for s in SERIES
            if any(t in s.out_id or t in s.series_id for t in tokens)
        ]
        print(
            f"Subset: {len(series)}/{len(SERIES)} series match {tokens}",
            flush=True,
        )
    # Batch up to 25 per request.
    batches = [series[i : i + 25] for i in range(0, len(series), 25)]
    all_data: dict[str, list[dict]] = {}
    for batch in batches:
        ids = [s.series_id for s in batch]
        print(f"Fetching BLS batch: {len(ids)} series", flush=True)
        try:
            data = fetch_bls(ids)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue
        all_data.update(data)

    for spec in series:
        rows = all_data.get(spec.series_id, [])
        if not rows:
            print(f"  {spec.series_id}: no data", file=sys.stderr)
            continue
        # BLS returns newest-first; build oldest-first points.
        points: list[dict] = []
        for row in reversed(rows):
            iso = bls_period_to_iso(row.get("year", ""), row.get("period", ""))
            if iso is None:
                continue
            try:
                v = float(row.get("value", ""))
            except (TypeError, ValueError):
                continue
            points.append({"t": iso, "v": v})
        if not points:
            print(f"  {spec.series_id}: parsed 0 points", file=sys.stderr)
            continue
        # Canonical-unit normalization: BLS state payrolls report
        # "thousands of persons" — rescale to raw jobs so combineTwo's
        # per-capita derivation produces sensible numbers. Mirrors
        # FRED's rescaling in pipelines/fred_series.py and the
        # retroactive script pipelines/rescale_counts_to_raw.py.
        spec_unit = spec.unit
        if "thousand" in spec.unit.lower():
            points = [{"t": p["t"], "v": p["v"] * 1000.0} for p in points]
            spec_unit = "jobs" if "payroll" in spec.label.lower() else "count"
        out = write_timeseries(
            pipeline="bls",
            series_id=spec.out_id,
            name=spec.label,
            points=points,
            unit=spec_unit,
        )
        print(
            f"  {spec.series_id} -> {spec.out_id}: "
            f"{len(points)} pts, latest {points[-1]['t']} = {points[-1]['v']}"
        )
        print(f"    [{out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
