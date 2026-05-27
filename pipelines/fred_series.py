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
    # FRED supports server-side transformations on its CSV endpoint via
    # `&transformation=X`. Common values:
    #   pc1  = percent change from year ago (12-month YoY)
    #   pca  = percent change annualized (1-period, annualized)
    #   chg  = change in level (1-period)
    # When set, the output file is named {series_id}_{transformation.upper()}.json
    # so it doesn't collide with the un-transformed series.
    transformation: str | None = None


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
    # UMCSENT (UMich consumer sentiment) intentionally NOT ingested:
    # third-party copyrighted (University of Michigan), pre-approval
    # required under FRED ToS § III. Removed 2026-05-27. See
    # docs/fred-copyright-audit.md.
    FredSpec("GDPC1", "US real GDP (chained 2017 dollars)", "billions USD"),
    FredSpec("INDPRO", "US industrial production", "index (2017=100)"),
    # SP500 (S&P 500) intentionally NOT ingested: third-party
    # copyrighted by S&P Dow Jones Indices LLC, pre-approval
    # required. Removed 2026-05-27.
    # NASDAQCOM (NASDAQ Composite) intentionally NOT ingested:
    # third-party copyrighted by Nasdaq, Inc. The heuristic in
    # the original audit missed this; FRED's authoritative tag
    # surfaced it after the API key landed. Removed 2026-05-27.
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
    # CSUSHPISA (Case-Shiller national) intentionally NOT ingested:
    # third-party copyrighted by S&P / CoreLogic / Case-Shiller,
    # pre-approval required. Removed 2026-05-27.
    # FHFA House Price Index is the clean substitute: federal-agency
    # data, public domain via FRED, broader geographic coverage than
    # Case-Shiller's 20-city composite. Quarterly. Two versions
    # ingested: all-transactions (USSTHPI, longer history, includes
    # refinances) and purchase-only (HPIPONM226S, SA, shorter
    # history but cleaner because no refi-driven noise).
    FredSpec("USSTHPI", "FHFA all-transactions HPI, national", "index"),
    FredSpec("HPIPONM226S", "FHFA purchase-only HPI, national (SA)", "index"),
    FredSpec("MSPUS", "Median sales price of houses sold", "USD"),
    # Spending & income
    FredSpec("RSAFS", "Retail sales (advance, total ex auto)", "millions USD"),
    FredSpec("PI", "Personal income", "billions USD"),
    FredSpec("PSAVERT", "Personal saving rate", "%"),
    # Consumer-confidence proxies. UMich's headline sentiment series
    # is third-party copyrighted (removed 2026-05-27), so we surface
    # a range of public-domain series that move with consumer mood
    # from different angles:
    #   DSPIC96 — real disposable personal income (BEA): the income
    #     foundation underneath any sentiment.
    #   JTSQUR  — JOLTS quits rate (BLS): people quit when they're
    #     confident they can find another job.
    #   TOTALSL — total consumer credit (FRB): borrowing willingness
    #     as a confidence signal. (PSAVERT above is the inverse
    #     read — saving up when worried.)
    FredSpec("DSPIC96", "Real disposable personal income", "billions chained 2017 USD"),
    FredSpec("JTSQUR", "JOLTS quits rate", "%"),
    FredSpec("TOTALSL", "Total consumer credit (owned and securitized)", "billions USD"),
    # Monetary / Fed
    FredSpec("M2SL", "M2 money supply", "billions USD"),
    FredSpec("WALCL", "Fed total assets (balance sheet)", "millions USD"),
    # ------------------------------------------------------------------
    # Analyst-persona expansion 2026-05: targeted public-domain series
    # added so analysts working in health, defense, energy, tech,
    # government, and labor demographics have first-class data.
    # All are PUBLIC-DOMAIN per FRED's tag system + audited via
    # pipelines/audit_fred_copyright.py before ingest. The
    # `consumer-confidence proxies` group earlier in this file is a
    # sibling expansion (DSPIC96 / JTSQUR / TOTALSL).
    # ------------------------------------------------------------------
    # Health analyst
    FredSpec("CES6562000001", "Health care + social assistance employment", "thousands of persons"),
    FredSpec("HLTHSCPCHCSA", "Health expenditures per capita", "USD"),
    # Defense analyst (federal-defense outlays already covered by
    # FDEFX; this adds the % of GDP read).
    FredSpec("A824RE1Q156NBEA", "National defense, share of GDP", "%"),
    # Energy analyst
    FredSpec("IPG211S", "Industrial production: oil + gas extraction", "index (2017=100)"),
    FredSpec("IPG2211S", "Industrial production: electric power generation", "index (2017=100)"),
    # Tech / semiconductors / electronics
    FredSpec("IPG3344S", "Industrial production: semiconductors + electronic components", "index (2017=100)"),
    FredSpec("CAPUTLG3344S", "Capacity utilization: semiconductors", "%"),
    FredSpec("USINFO", "Information-sector employment", "thousands of persons"),
    FredSpec("A34SNO", "New orders: computers + electronic products", "millions USD"),
    # Government spending + employment (the analyst persona Tape's
    # audience leans hardest into — DC econ/policy).
    FredSpec("FGEXPND", "Federal government current expenditures", "billions USD"),
    FredSpec("SLEXPND", "State + local government current expenditures", "billions USD"),
    FredSpec("USGOVT", "Government employment, total", "thousands of persons"),
    FredSpec("CES9091000001", "Federal government employment", "thousands of persons"),
    FredSpec("CES9092000001", "State government employment", "thousands of persons"),
    FredSpec("CES9093000001", "Local government employment", "thousands of persons"),
    # Labor demographics — unemployment rate split by race/ethnicity.
    # The headline UNRATE we already carry hides large + persistent
    # cross-group gaps; these surface them.
    FredSpec("LNS14000003", "Unemployment rate: White", "%"),
    FredSpec("LNS14000006", "Unemployment rate: Black or African American", "%"),
    FredSpec("LNS14000009", "Unemployment rate: Hispanic or Latino", "%"),
    # Per-capita complement to the real disposable income series
    # added above.
    FredSpec("A229RX0", "Real disposable personal income per capita", "chained 2017 USD"),
    # Credit spreads + risk indexes intentionally NOT ingested:
    # BAMLH0A0HYM2 + BAMLC0A0CM are third-party copyrighted by
    # ICE BofA / ICE Data Indices; VIXCLS by Cboe Global Markets.
    # All three are pre-approval-required under FRED ToS § III.
    # Removed 2026-05-27. See docs/fred-copyright-audit.md.
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
    # Federal-spending-by-function series. Series IDs corrected in May
    # 2026 after a chart-tooltip bug surfaced the prior mismapping —
    # SS, Medicare, Medicaid, and nondefense were all pointing at the
    # wrong NIPA series:
    #   W823 = Social security (was labeled Medicare)
    #   W824 = Medicare        (was labeled Medicaid)
    #   W729 = Medicaid        (wasn't fetched at all)
    #   W825 = Unemployment    (was labeled Social Security)
    #   FNDEFX = Federal nondefense (was W068 = TOTAL government,
    #            including state + local, ~$11T/yr)
    # The W825 + W068 specs are kept (with corrected labels) below in
    # case other charts want to surface them — they're real series,
    # just not what we thought.
    FredSpec("FDEFX", "Federal defense spending (NIPA)", "billions USD"),
    FredSpec("FNDEFX", "Federal nondefense consumption + investment (NIPA)", "billions USD"),
    FredSpec("W823RC1Q027SBEA", "Federal Social Security benefits (NIPA)", "billions USD"),
    FredSpec("W824RC1Q027SBEA", "Federal Medicare benefits (NIPA)", "billions USD"),
    FredSpec("W729RC1Q027SBEA", "Federal Medicaid benefits (NIPA)", "billions USD"),
    FredSpec("W825RC1Q027SBEA", "Federal unemployment insurance benefits (NIPA)", "billions USD"),
    FredSpec("W068RCQ027SBEA", "Government total expenditures (federal + state + local)", "billions USD"),
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
    # Sahm rule (Claudia Sahm, 2019). Triggers a recession indicator
    # when the 3-month MA of the unemployment rate rises 0.5pp above
    # its trailing-12-month minimum. SAHMREALTIME uses the data
    # available at the time (no revisions baked in), which is the
    # honest "would this have signaled in real time?" series. The
    # alternative SAHMCURRENT uses the latest revised data and is
    # easier to dismiss as backfit.
    FredSpec("SAHMREALTIME", "Sahm rule recession indicator (real-time)", "%"),
    # CPI YoY (12-month percent change of CPIAUCSL). Fetched via
    # FRED's transformation=pc1 so we don't have to compute it on
    # the client. Pairs with FEDFUNDS as the diff component for a
    # real-fed-funds chart (op: diff).
    FredSpec("CPIAUCSL", "CPI YoY (all urban consumers, year-over-year %)", "%",
             transformation="pc1"),
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
    # businesses + individuals, BEA NIPA Table 3.2 line "Subsidies."
    # Quarterly. (Previously this spec used W994 — which is "Net lending
    # or net borrowing, NIPAs: Private," a completely different series.
    # B096 is the actual federal-subsidies series. May 2026 audit catch.)
    FredSpec("B096RC1Q027SBEA", "Federal subsidies (NIPA)", "billions USD"),
    # ---- AI + datacenter sector PPI ----
    # Producer Price Index for semiconductor + related device manufacturing
    # (NAICS 3344). Tracks wholesale prices in the chip-making industry —
    # crashes during gluts, climbs during AI-driven supply tightness.
    FredSpec("PCU33443344", "PPI — Semiconductor & related device mfg", "index (Jun 2009=100)"),
    # PPI for data processing, hosting, and related services (NAICS 518210).
    # The closest published-price index to "cloud + hosting wholesale
    # prices." Lags spot pricing but trends.
    FredSpec("PCU518210518210", "PPI — Data processing, hosting & related services", "index (Dec 2009=100)"),
    # Industrial production: Mining (rounds out the IPMAN + IPUTIL pair —
    # mining is the third major sub-sector and trends very differently).
    FredSpec("IPMINE", "Industrial production — Mining", "index (2017=100)"),
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
    # WDXRSA (DC-metro Case-Shiller) intentionally NOT ingested:
    # third-party copyrighted by S&P / CoreLogic / Case-Shiller.
    # Removed 2026-05-27. FHFA DC-MSA HPI is the clean substitute:
    # public domain, quarterly, covers the same metro area.
    FredSpec("ATNHPIUS47894Q", "FHFA all-transactions HPI, DC-MSA", "index"),
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


# FRED series whose metadata label says "thousands" but whose CSV
# endpoint returns values in raw counts already. Rescaling these would
# inflate the data 1000x. See main()'s is_thousand_count guard.
ALREADY_RAW_DESPITE_THOUSANDS = {
    "CCSA",  # Continuing jobless claims (insured unemployment) — weekly
    "ICSA",  # Initial jobless claims — weekly
}


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


def fetch_fred_official_title(series_id: str) -> str | None:
    """Probe the FRED series page and extract the official title.
    Used to record ground truth alongside each data file so a later
    audit doesn't need network access to verify labels."""
    url = f"https://fred.stlouisfed.org/series/{series_id}"
    try:
        r = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", "20", url],
            capture_output=True, check=True,
        )
    except subprocess.CalledProcessError:
        return None
    try:
        body = r.stdout.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    import re as _re
    m = _re.search(r"<title>([^<]+)</title>", body, _re.IGNORECASE)
    if not m:
        return None
    title = m.group(1).strip()
    title = title.replace(" | FRED | St. Louis Fed", "").strip()
    # Strip the parenthesized ID at the end.
    m2 = _re.match(r"^(.+?)\s*\([A-Z0-9_]+\)\s*$", title)
    if m2:
        title = m2.group(1).strip()
    return title


def fetch_series(series_id: str, transformation: str | None = None) -> list[dict]:
    url = FRED_CSV_URL.format(series_id=series_id)
    if transformation:
        url = f"{url}&transformation={transformation}"
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
    # FRED's transformation endpoint returns the data column under the
    # series_id key (NOT series_id + suffix) — verified against
    # CPIAUCSL with transformation=pc1. We still fall back to "the first
    # non-date column" so future transformations that change the header
    # don't silently produce zero points.
    date_keys = {"DATE", "observation_date", "Date"}
    for row in reader:
        date = next((row[k] for k in date_keys if k in row and row[k]), None)
        if not date:
            continue
        raw_v = row.get(series_id)
        if raw_v in (None, "", "."):
            # Fallback: pick the first non-date column with a value.
            for k, val in row.items():
                if k in date_keys or val in (None, "", "."):
                    continue
                raw_v = val
                break
        if raw_v in (None, "", "."):
            continue
        try:
            v = float(raw_v)
        except (TypeError, ValueError):
            continue
        points.append({"t": date, "v": v})
    return points


def _name_overlap(spec_name: str, fred_title: str) -> set[str]:
    """Token-set intersection used as a cheap "do these refer to the
    same thing" check. Filters out common stop words so the overlap
    is meaningful identifiers (security, medicare, defense, …)
    rather than connectives. Matches the heuristic in
    scripts/audit_fred_series.py — keep them in sync."""
    import re as _re
    stop = {"of", "the", "and", "to", "for", "in", "us", "u", "s",
            "by", "from", "all", "rate", "index", "level", "per",
            "total", "current", "expenditures", "consumption",
            "payments", "receipts"}
    def toks(t: str) -> set[str]:
        return {w for w in _re.findall(r"[a-z0-9]+", t.lower()) if w not in stop}
    return toks(spec_name) & toks(fred_title)


def main(argv: list[str] | None = None) -> int:
    selected = set((argv or [])[1:])
    run = [s for s in SPECS if not selected or s.series_id in selected]
    if not run:
        print(f"No specs matched {selected}")
        return 2
    label_drift: list[tuple[str, str, str]] = []
    for spec in run:
        # Output ID gets a {_TRANSFORMATION} suffix when the spec asks
        # for one — that way CPIAUCSL (level) and CPIAUCSL_PC1 (YoY)
        # coexist as separate data files.
        out_id = (
            f"{spec.series_id}_{spec.transformation.upper()}"
            if spec.transformation
            else spec.series_id
        )
        print(f"Fetching FRED {out_id}...", flush=True)
        points = fetch_series(spec.series_id, spec.transformation)
        # Canonical-unit normalization: FRED reports many count series in
        # "thousands" (population, payrolls, etc.). We rescale to raw
        # counts at write time so derived sources (e.g. currency /
        # population per-capita) get numerically sane combine results
        # without per-source magnitude gymnastics in the renderer. Same
        # treatment was applied retroactively via
        # pipelines/rescale_counts_to_raw.py.
        #
        # Wrinkle: a handful of FRED series carry "thousands" metadata
        # in their FRED.org listing but the CSV endpoint actually returns
        # values in raw counts (no division applied). CCSA + ICSA jobless
        # claims are the known cases. Rescaling those by 1000 inflates
        # the data by 1000x — caught by pipelines/audit_source_scales.py
        # when CCSA showed 1.78B "claims" against the real ~1.78M. The
        # ALREADY_RAW_DESPITE_THOUSANDS list pins those exceptions.
        is_thousand_count = (
            "thousand" in spec.unit.lower()
            and spec.series_id not in ALREADY_RAW_DESPITE_THOUSANDS
        )
        if is_thousand_count:
            points = [{"t": p["t"], "v": p["v"] * 1000.0} for p in points]
            # Replace the FRED-native unit string with the natural noun;
            # mirrors rescale_counts_to_raw.py's infer_unit logic.
            spec_unit = _infer_raw_count_unit(spec.series_id, spec.unit)
        else:
            spec_unit = (
                _infer_raw_count_unit(spec.series_id, spec.unit)
                if spec.series_id in ALREADY_RAW_DESPITE_THOUSANDS
                else spec.unit
            )
        out = write_timeseries(
            pipeline="fred",
            series_id=out_id,
            name=spec.name,
            points=points,
            unit=spec_unit,
        )
        # Defense-in-depth: probe FRED's official series page for the
        # human title, compare it to spec.name. If the overlap is
        # near-zero (e.g. spec says "Social Security" but FRED says
        # "Unemployment Insurance" — the May 2026 bug), flag for
        # post-run reporting. We don't fail the pipeline mid-loop
        # because partial-fetches are useful (especially on quota
        # limits); the scripts/audit_fred_series.py --strict step in
        # CI is the hard gate.
        official = fetch_fred_official_title(spec.series_id)
        if official is not None:
            overlap = _name_overlap(spec.name, official)
            if not overlap:
                label_drift.append((spec.series_id, spec.name, official))
        print(f"  {len(points):>6} points -> {out}")
    if label_drift:
        print("\nWARNING: FRED label drift detected — spec.name doesn't "
              "share any identifying tokens with FRED's official title:")
        for sid, name, official in label_drift:
            print(f"  {sid}: spec='{name}'  FRED='{official}'")
        print("\nRun `python scripts/audit_fred_series.py` for a fuller check.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
