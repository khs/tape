"""
Fetch FRED time series via the public fredgraph.csv endpoint (no API key).
Run with: ``python pipelines/fred_series.py``.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from dataclasses import dataclass
from io import StringIO

from common import write_timeseries

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


@dataclass
class FredSpec:
    series_id: str
    name: str
    unit: str | None = None


SPECS: list[FredSpec] = [
    FredSpec("DGS10", "US 10-year Treasury yield", "%"),
    FredSpec("DGS2", "US 2-year Treasury yield", "%"),
    FredSpec("T10Y2Y", "10Y minus 2Y Treasury spread", "%"),
    FredSpec("UNRATE", "US unemployment rate", "%"),
    FredSpec("CPIAUCSL", "CPI, all urban consumers", "index (1982-84=100)"),
    FredSpec("UMCSENT", "UMich consumer sentiment", "index"),
    FredSpec("GDPC1", "US real GDP (chained 2017 dollars)", "billions USD"),
    FredSpec("INDPRO", "US industrial production", "index (2017=100)"),
    FredSpec("SP500", "S&P 500 Index", "index"),
    FredSpec("NASDAQCOM", "NASDAQ Composite", "index"),
    FredSpec("GASREGW", "US retail gasoline, regular grade", "USD/gal"),
    FredSpec("GASDESW", "US retail diesel", "USD/gal"),
    FredSpec("DHHNGSP", "Henry Hub natural gas spot", "USD/mmbtu"),
    # ------------------------------------------------------------------
    # Library expansion: rates curve, core inflation, labor, housing, credit, monetary
    # ------------------------------------------------------------------
    # Rates — Treasury curve
    FredSpec("DGS3MO", "US 3-month Treasury yield", "%"),
    FredSpec("DGS5", "US 5-year Treasury yield", "%"),
    FredSpec("DGS30", "US 30-year Treasury yield", "%"),
    FredSpec("FEDFUNDS", "Federal funds effective rate", "%"),
    FredSpec("MORTGAGE30US", "30-year fixed mortgage rate", "%"),
    # Inflation
    FredSpec("CPILFESL", "Core CPI (all items less food & energy)", "index (1982-84=100)"),
    FredSpec("PCEPI", "PCE price index (headline)", "index (2017=100)"),
    FredSpec("PCEPILFE", "Core PCE price index", "index (2017=100)"),
    # Labor
    FredSpec("PAYEMS", "Nonfarm payrolls", "thousands of persons"),
    FredSpec("CIVPART", "Labor force participation rate", "%"),
    FredSpec("AHETPI", "Average hourly earnings (production & nonsupervisory)", "USD/hour"),
    # Output / utilization
    FredSpec("TCU", "Capacity utilization (total industry)", "%"),
    # Housing
    FredSpec("HOUST", "Housing starts (new privately-owned units)", "thousands, SAAR"),
    FredSpec("CSUSHPISA", "Case-Shiller national home price index", "index"),
    FredSpec("MSPUS", "Median sales price of houses sold", "USD"),
    # Spending & income
    FredSpec("RSAFS", "Retail sales (advance, total ex auto)", "millions USD"),
    FredSpec("PI", "Personal income", "billions USD"),
    FredSpec("PSAVERT", "Personal saving rate", "%"),
    # Monetary / Fed
    FredSpec("M2SL", "M2 money supply", "billions USD"),
    FredSpec("WALCL", "Fed total assets (balance sheet)", "millions USD"),
    # Credit spreads
    FredSpec("BAMLH0A0HYM2", "ICE BofA HY corporate option-adjusted spread", "%"),
    FredSpec("BAMLC0A0CM", "ICE BofA IG corporate option-adjusted spread", "%"),
    # Risk
    FredSpec("VIXCLS", "VIX (CBOE volatility index)", "index"),
    # ------------------------------------------------------------------
    # Library expansion v2: labor sub-series, real estate, government finances
    # ------------------------------------------------------------------
    # Labor
    FredSpec("U6RATE", "U-6 unemployment rate (broader)", "%"),
    FredSpec("ICSA", "Initial jobless claims (weekly)", "thousands"),
    FredSpec("CCSA", "Continuing jobless claims", "thousands"),
    FredSpec("JTSJOL", "Job openings (JOLTS, total nonfarm)", "thousands"),
    # Real estate
    FredSpec("PERMIT", "Building permits (new private housing)", "thousands, SAAR"),
    FredSpec("HSN1F", "New single-family home sales", "thousands, SAAR"),
    # Government finances
    FredSpec("GFDEGDQ188S", "Federal debt held by the public, % of GDP", "%"),
    FredSpec("FYFSGDA188S", "Federal surplus/deficit, % of GDP", "%"),
    # ------------------------------------------------------------------
    # Library expansion v3: fiscal depth, labor depth, inflation expectations,
    # real estate depth, trade
    # ------------------------------------------------------------------
    # Fiscal policy / revenue + spending
    FredSpec("FYFRGDA188S", "Federal receipts, % of GDP", "%"),
    FredSpec("FYONGDA188S", "Federal outlays, % of GDP", "%"),
    FredSpec("FYOIGDA188S", "Federal net interest outlays, % of GDP", "%"),
    FredSpec("FDEFX", "Federal defense outlays", "billions USD"),
    # Inflation expectations (TIPS-derived breakevens)
    FredSpec("T5YIE", "5-year breakeven inflation", "%"),
    FredSpec("T10YIE", "10-year breakeven inflation", "%"),
    FredSpec("DFII10", "10-year TIPS yield (real)", "%"),
    # Labor depth
    FredSpec("LNS11300060", "Prime-age (25-54) labor force participation", "%"),
    FredSpec("JTSQUR", "Quits rate (JOLTS)", "%"),
    FredSpec("MANEMP", "Manufacturing employment", "thousands of persons"),
    FredSpec("CES0500000003", "Average hourly earnings, all employees", "USD/hour"),
    # Real estate depth
    FredSpec("MORTGAGE15US", "15-year fixed mortgage rate", "%"),
    FredSpec("MSACSR", "Months supply of new houses for sale", "months"),
    # Trade
    FredSpec("BOPGSTB", "US trade balance, goods and services", "millions USD"),
    # Recession indicator (NBER, monthly)
    FredSpec("USREC", "NBER recession indicator", "binary"),
    # Population — exposed as a quick-divisor in the composer's derived-
    # source modal so users can build per-capita series in one click.
    FredSpec("POPTHM", "US population, all persons (monthly)", "thousands"),
    # ---- Federal spending by function (quarterly, OMB/BEA) ----
    # NIPA Table 3.9.5 functional breakdown is what people actually argue
    # about: defense vs entitlements vs interest. These are nominal $B
    # annual rates. For ratio-to-GDP analyses, pair with us_real_gdp +
    # the divide quick-action in the composer.
    FredSpec("FDEFX", "Federal defense spending (NIPA)", "billions USD"),
    FredSpec("W068RCQ027SBEA", "Federal nondefense consumption + investment", "billions USD"),
    FredSpec("W823RC1Q027SBEA", "Federal Medicare benefits", "billions USD"),
    FredSpec("W824RC1Q027SBEA", "Federal Medicaid benefits", "billions USD"),
    FredSpec("W825RC1Q027SBEA", "Federal Social Security benefits", "billions USD"),
    FredSpec("A091RC1Q027SBEA", "Federal interest payments", "billions USD"),
    # ---- Real estate fundamentals ----
    # Rent CPI is on FRED as part of CPI; separately, this is the
    # standalone shelter and rent-of-primary-residence index, useful for
    # the "is rent inflation persisting?" question.
    FredSpec("CUUR0000SEHA", "CPI: Rent of primary residence", "index 1982-84=100"),
    FredSpec("CUUR0000SAH1", "CPI: Shelter", "index 1982-84=100"),
    # Vacancy rates — Census/HVS quarterly. RRVRUSQ156N = rental vacancy.
    FredSpec("RRVRUSQ156N", "US rental vacancy rate", "%"),
    FredSpec("RHVRUSQ156N", "US homeowner vacancy rate", "%"),
    # Total housing starts (we already have it as housing_starts in
    # contents/charts but worth keeping it here for completeness).
    # Median listing price by national — useful for current-conditions
    # snapshots.
    FredSpec("MEDLISPRIUS", "US median listing price (homes for sale)", "USD"),
    # ---- Productivity (BLS via FRED mirror) ----
    # Output per hour, nonfarm business sector — the headline productivity
    # number that wage-vs-productivity debates hinge on.
    FredSpec("OPHNFB", "Nonfarm business: output per hour", "index 2017=100"),
    FredSpec("ULCNFB", "Nonfarm business: unit labor costs", "index 2017=100"),
    # Manufacturing-sector productivity for the "is reshoring real?" debate
    FredSpec("OPHMFG", "Manufacturing: output per hour", "index 2017=100"),
]


def fetch_series(series_id: str) -> list[dict]:
    url = FRED_CSV_URL.format(series_id=series_id)
    # urllib.request hangs on these responses in some environments; curl is reliable.
    # FRED blocks custom User-Agent strings; use curl default.
    result = subprocess.run(
        ["curl", "-sS", "--max-time", "60", url],
        capture_output=True,
        check=True,
        text=True,
    )
    raw = result.stdout

    reader = csv.DictReader(StringIO(raw))
    points: list[dict] = []
    for row in reader:
        date = row.get("DATE") or row.get("observation_date") or row.get("Date")
        raw_v = row.get(series_id)
        if not date or raw_v in (None, "", "."):
            continue
        try:
            v = float(raw_v)
        except (TypeError, ValueError):
            continue
        points.append({"t": date, "v": v})
    return points


def main(argv: list[str] | None = None) -> int:
    selected = set((argv or [])[1:])
    run = [s for s in SPECS if not selected or s.series_id in selected]
    if not run:
        print(f"No specs matched {selected}")
        return 2
    for spec in run:
        print(f"Fetching FRED {spec.series_id}...", flush=True)
        points = fetch_series(spec.series_id)
        out = write_timeseries(
            pipeline="fred",
            series_id=spec.series_id,
            name=spec.name,
            points=points,
            unit=spec.unit,
        )
        print(f"  {len(points):>6} points -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
