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
    # T10Y2Y removed: the 10Y−2Y spread is now rendered as a chart-level
    # diff op over the underlying DGS10/DGS2 series rather than as a
    # standalone FRED series. Keeping it as a separate fetch would just
    # duplicate data we already compute on the fly. See
    # src/content/charts/us-macro/curve_spread.yaml.
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
    # Inflation expectations (TIPS — real yields). Breakeven inflation is
    # the spread between the nominal Treasury yield and the TIPS yield of
    # the same maturity; rendered as chart-level diff ops in
    # src/content/charts/us-macro/breakeven_{5y,10y}.yaml rather than as
    # standalone FRED series. We just need to fetch the constituents.
    FredSpec("DFII5", "5-year TIPS yield (real)", "%"),
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
    # ---- Library expansion v4: monetary plumbing, inflation detail, ----
    # ---- recession signals, FX, fiscal level                            ----
    # Senior Loan Officer Opinion Survey (SLOOS). Quarterly; banks
    # tightening (positive) vs. easing (negative) credit standards.
    # The Fed reads these obsessively as a forward financial-conditions
    # signal.
    FredSpec("DRTSCILM", "SLOOS — banks tightening C&I loan standards (large/medium firms)", "%"),
    FredSpec("DRTSCLCC", "SLOOS — banks tightening credit-card standards", "%"),
    # CPI subindexes — granularity behind the headline.
    FredSpec("CPIUFDSL", "CPI: Food", "index (1982-84=100)"),
    FredSpec("CPIENGSL", "CPI: Energy", "index (1982-84=100)"),
    FredSpec("CPIMEDSL", "CPI: Medical care", "index (1982-84=100)"),
    # GDP deflator — broadest inflation measure, distinct from CPI/PCE.
    FredSpec("GDPDEF", "GDP price deflator", "index (2017=100)"),
    # Recession signals. Philly Fed's Anxious Index isn't on FRED — its SPF
    # release publishes via the Philly Fed's own site (CSV download); a
    # follow-up pipeline could pull it directly. Skipping for now.
    FredSpec("RECPROUSM156N", "Recession probability — NY Fed yield-curve model", "%"),
    FredSpec("STLFSI4", "St. Louis Fed Financial Stress Index", "index (z-score)"),
    # Labor — manufacturing weekly hours; classic leading indicator.
    FredSpec("AWHMAN", "Average weekly hours, manufacturing", "hours"),
    # FX — Chinese yuan / USD, the most-watched political-economy currency.
    FredSpec("DEXCHUS", "Chinese yuan per US dollar (CNY/USD)", "CNY per USD"),
    # Fiscal level — the absolute debt number people argue about, in
    # millions USD. Pair with the existing GFDEGDQ188S (debt-to-GDP) for
    # context.
    FredSpec("GFDEBTN", "Federal debt outstanding (total public debt)", "millions USD"),
    # Federal subsidies — direct subsidy outlays from the government to
    # businesses + individuals, BEA NIPA Table 3.2. Quarterly.
    FredSpec("W994RC1Q027SBEA", "Federal subsidies", "billions USD"),
    # ---- Productivity (BLS via FRED mirror) ----
    # Output per hour, nonfarm business sector — the headline productivity
    # number that wage-vs-productivity debates hinge on.
    FredSpec("OPHNFB", "Nonfarm business: output per hour", "index 2017=100"),
    FredSpec("ULCNFB", "Nonfarm business: unit labor costs", "index 2017=100"),
    # Manufacturing-sector productivity for the "is reshoring real?" debate
    FredSpec("OPHMFG", "Manufacturing: output per hour", "index 2017=100"),
    # ---- DC-metro variants (for the VA-08 + DC-area workbooks) ----
    # The Washington-Arlington-Alexandria MSA cuts across DC, parts of VA,
    # parts of MD, and parts of WV — so these series capture economic
    # conditions in the federal-economy core regardless of jurisdiction.
    FredSpec("WDXRSA", "DC-metro Case-Shiller home price index", "index 2000=100"),
    FredSpec("WASH911URN", "DC-metro unemployment rate", "%"),
    FredSpec("WASH911NA", "DC-metro nonfarm payroll employment", "thousands"),
    FredSpec("MEDLISPRI47900", "DC-metro median listing price (homes for sale)", "USD"),
    FredSpec("CUUSA311SA0", "DC-metro CPI, all items", "index 1982-84=100"),
    # ---- State population, annual, for all 50 states + DC ----
    # FRED series naming: <STATE_ABBR>POP. Annual data from Census Bureau
    # Population Estimates Program. Used as a denominator for state-level
    # per-capita derivations in the composer (paired with the existing
    # ÷ quick-divisor chips).
    *[FredSpec(f"{a}POP", f"{n} population", "thousands") for a, n in [
        ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"),
        ("AR", "Arkansas"), ("CA", "California"), ("CO", "Colorado"),
        ("CT", "Connecticut"), ("DE", "Delaware"), ("DC", "District of Columbia"),
        ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"),
        ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"),
        ("IA", "Iowa"), ("KS", "Kansas"), ("KY", "Kentucky"),
        ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
        ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"),
        ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"),
        ("NE", "Nebraska"), ("NV", "Nevada"), ("NH", "New Hampshire"),
        ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
        ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
        ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"),
        ("RI", "Rhode Island"), ("SC", "South Carolina"), ("SD", "South Dakota"),
        ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"),
        ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"),
        ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
    ]],
]


def _infer_raw_count_unit(series_id: str, fred_unit: str) -> str:
    """
    Pick a natural-language unit string for a raw-count series after
    rescaling from "thousands". Mirrors the heuristic in
    pipelines/rescale_counts_to_raw.py so both code paths produce the
    same source-YAML output.
    """
    lower = (series_id + " " + fred_unit).lower()
    for keyword, noun in (
        ("population", "people"),
        ("popthm", "people"),
        ("payrolls", "jobs"),
        ("payems", "jobs"),
        ("employment", "jobs"),
        ("claim", "claims"),
        ("ics", "claims"),
        ("ccs", "claims"),
        ("opening", "openings"),
        ("jolts", "openings"),
        ("permit", "permits"),
        ("starts", "starts"),
        ("houst", "starts"),
        ("sales", "homes sold"),
        ("hsn", "homes sold"),
    ):
        if keyword in lower:
            return noun
    return "count"


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
        # Canonical-unit normalization: FRED reports many count series in
        # "thousands" (population, payrolls, claims, etc.). We rescale to
        # raw counts at write time so derived sources (e.g. currency /
        # population per-capita) get numerically sane combine results
        # without per-source magnitude gymnastics in the renderer. Same
        # treatment was applied retroactively via
        # pipelines/rescale_counts_to_raw.py.
        is_thousand_count = "thousand" in spec.unit.lower()
        if is_thousand_count:
            points = [{"t": p["t"], "v": p["v"] * 1000.0} for p in points]
            # Replace the FRED-native unit string with the natural noun;
            # mirrors rescale_counts_to_raw.py's infer_unit logic.
            spec_unit = _infer_raw_count_unit(spec.series_id, spec.unit)
        else:
            spec_unit = spec.unit
        out = write_timeseries(
            pipeline="fred",
            series_id=spec.series_id,
            name=spec.name,
            points=points,
            unit=spec_unit,
        )
        print(f"  {len(points):>6} points -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
