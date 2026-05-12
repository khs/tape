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
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from common import write_timeseries


BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


@dataclass
class BlsSpec:
    series_id: str  # BLS series identifier
    out_id: str  # how we write the file (data/bls/<out_id>.json)
    label: str
    unit: str
    notes: str = ""


# Curated set. Categories:
#   1. CPI subcomponents — beyond what FRED carries broadly
#   2. JOLTS by industry — labor demand granularity
#   3. State-level unemployment — geographic dispersion
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
        notes="Quits as a share of employment — the 'great resignation' metric.",
    ),
    BlsSpec(
        series_id="JTS000000000000000HIR",
        out_id="jolts_hires_rate",
        label="JOLTS: hires rate (total nonfarm)",
        unit="% of employment",
    ),
    # ---- Regional / state unemployment, illustrative. CA + TX + NY are
    #      the three biggest state economies; we can extend the list later.
    BlsSpec(
        series_id="LASST060000000000003",
        out_id="state_unemployment_ca",
        label="California unemployment rate",
        unit="%",
    ),
    BlsSpec(
        series_id="LASST480000000000003",
        out_id="state_unemployment_tx",
        label="Texas unemployment rate",
        unit="%",
    ),
    BlsSpec(
        series_id="LASST360000000000003",
        out_id="state_unemployment_ny",
        label="New York unemployment rate",
        unit="%",
    ),
]


def fetch_bls(series_ids: list[str]) -> dict[str, list[dict]]:
    """
    POST to BLS API with up to 25 series at a time. Returns
    {series_id: [{year, period, value}, ...]} dict.
    """
    if not series_ids:
        return {}
    if len(series_ids) > 25:
        raise ValueError("BLS API caps at 25 series per request")

    # Years window: BLS's unregistered API returns at most 10 years per
    # request and, in practice, gives us the *first* 10 years of any
    # requested range rather than the last. So ask for the trailing
    # 10-year window only — extending the window earns no extra data
    # and just discards the recent years. When we register for an API
    # key (free, 20-year limit + higher quotas), bump this back to ~19.
    end_year = datetime.now(timezone.utc).year
    start_year = end_year - 9  # 10 years inclusive

    payload = {
        "seriesid": series_ids,
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    body = json.dumps(payload)
    result = subprocess.run(
        [
            "curl", "-sS", "--max-time", "60",
            "-H", "Content-Type: application/json",
            "-d", body,
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
        sid = s.get("seriesID", "")
        out[sid] = s.get("data", [])
    return out


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
    # Batch up to 25 per request.
    batches = [SERIES[i : i + 25] for i in range(0, len(SERIES), 25)]
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

    for spec in SERIES:
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
        out = write_timeseries(
            pipeline="bls",
            series_id=spec.out_id,
            name=spec.label,
            points=points,
            unit=spec.unit,
        )
        print(
            f"  {spec.series_id} -> {spec.out_id}: "
            f"{len(points)} pts, latest {points[-1]['t']} = {points[-1]['v']}"
        )
        print(f"    [{out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
