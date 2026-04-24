"""
One-off generator for source + chart YAMLs for the library expansion.
Idempotent: never overwrites existing files; prints what it creates.

Run once:  python pipelines/_generate_content.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "content"

# -------- cadence -> supportedDeltas --------
CADENCE_DELTAS = {
    "daily": '["1w", "1m", "1y", "5y", "10y"]',
    "weekly": '["1w", "1m", "1y", "5y", "10y"]',
    "monthly": '["1m", "1y", "5y", "10y"]',
    "quarterly": '["1y", "5y", "10y"]',
}


def yaml_escape(s: str) -> str:
    """Quote a string if it contains chars that would need quoting in YAML."""
    if not s:
        return '""'
    if any(ch in s for ch in [":", "#", "&", "*", "!", "|", ">", "%", "@"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def write_if_absent(path: Path, body: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    print(f"  + {path.relative_to(ROOT)}")
    return True


def source_yaml(
    *,
    name: str,
    description: str,
    pipeline: str,
    data_file: str,
    cadence: str,
    kind: str = "timeseries",
    short_name: str | None = None,
    unit: str | None = None,
    fmt_style: str = "number",
    decimals: int = 2,
    currency: str | None = None,
    prefix: str | None = None,
    suffix: str | None = None,
    notation: str | None = None,
    emphasis: str = "level",
    provider: str = "Yahoo Finance",
    series: str | None = None,
    url: str | None = None,
    license_: str | None = None,
    notes: str | None = None,
) -> str:
    deltas = CADENCE_DELTAS[cadence]
    lines = [f"name: {yaml_escape(name)}"]
    if short_name:
        lines.append(f"shortName: {yaml_escape(short_name)}")
    if description:
        lines.append(f"description: {yaml_escape(description)}")
    lines.append(f"kind: {kind}")
    lines.append(f"pipeline: {pipeline}")
    lines.append(f"dataFile: {data_file}")
    lines.append(f"supportedDeltas: {deltas}")
    if unit:
        lines.append(f'unit: "{unit}"')
    lines.append("formatting:")
    lines.append(f"  style: {fmt_style}")
    if currency:
        lines.append(f"  currency: {currency}")
    lines.append(f"  decimals: {decimals}")
    if prefix is not None:
        lines.append(f'  prefix: "{prefix}"')
    if suffix is not None:
        lines.append(f'  suffix: "{suffix}"')
    if notation:
        lines.append(f"  notation: {notation}")
    if emphasis != "level":
        lines.append(f"emphasis: {emphasis}")
    lines.append("provenance:")
    lines.append(f"  provider: {yaml_escape(provider)}")
    if series:
        lines.append(f"  series: {yaml_escape(series)}")
    if url:
        lines.append(f"  url: {url}")
    if license_:
        lines.append(f"  license: {yaml_escape(license_)}")
    if notes:
        lines.append(f"  notes: {yaml_escape(notes)}")
    return "\n".join(lines) + "\n"


def chart_yaml(
    *,
    title: str,
    sources: list[str],
    default_delta: str = "1m",
    emphasis: str | None = None,
    blurb: str = "KELLER WRITE THIS",
) -> str:
    lines = [f"title: {yaml_escape(title)}"]
    if len(sources) == 1:
        lines.append(f'sources: ["{sources[0]}"]')
    else:
        lines.append("sources:")
        for s in sources:
            lines.append(f"  - {s}")
    lines.append("render: line")
    lines.append(f"defaultDelta: {default_delta}")
    if emphasis:
        lines.append(f"emphasis: {emphasis}")
    lines.append(f'blurb: "{blurb}"')
    return "\n".join(lines) + "\n"


# ==============================================================
#  YAHOO SOURCES + CHARTS
# ==============================================================

# --- Commodities: precious & base metals ---
METALS: list[tuple] = [
    # (slug, ticker, name, unit, fmt_prefix, fmt_suffix, decimals, cadence)
    ("gold_futures",     "GC_F", "Gold front-month",       "USD/oz", "$",  " /oz",      2, "daily"),
    ("silver_futures",   "SI_F", "Silver front-month",     "USD/oz", "$",  " /oz",      3, "daily"),
    ("platinum_futures", "PL_F", "Platinum front-month",   "USD/oz", "$",  " /oz",      2, "daily"),
    ("palladium_futures","PA_F", "Palladium front-month",  "USD/oz", "$",  " /oz",      2, "daily"),
    ("copper_futures",   "HG_F", "Copper front-month",     "USD/lb", "$",  " /lb",      3, "daily"),
]
for slug, tkr, name, unit, pfx, sfx, dec, cad in METALS:
    write_if_absent(
        SRC / "sources" / "yahoo" / f"{slug}.yaml",
        source_yaml(
            name=name,
            short_name=tkr.replace("_F", ""),
            description=f"NYMEX/COMEX {name.lower()} futures, daily.",
            pipeline="yahoo_quotes",
            data_file=f"data/yahoo/{tkr}.json",
            cadence=cad,
            unit=unit,
            fmt_style="number",
            decimals=dec,
            prefix=pfx,
            suffix=sfx,
            provider="Yahoo Finance",
            series=f"{tkr.replace('_F', '=F')}",
            url=f"https://finance.yahoo.com/quote/{tkr.replace('_F', '=F')}",
        ),
    )
    write_if_absent(
        SRC / "charts" / "commodities" / f"{slug}.yaml",
        chart_yaml(
            title=name.replace("front-month", "").strip(),
            sources=[f"yahoo/{slug}"],
            default_delta="1m",
        ),
    )

# Precious/industrial metals ETFs
METAL_ETFS = [
    ("gld", "GLD", "SPDR Gold Shares", "USD"),
    ("slv", "SLV", "iShares Silver Trust", "USD"),
]
for slug, tkr, name, unit in METAL_ETFS:
    write_if_absent(
        SRC / "sources" / "yahoo" / f"{slug}.yaml",
        source_yaml(
            name=name,
            short_name=tkr,
            description="Daily adjusted close.",
            pipeline="yahoo_quotes",
            data_file=f"data/yahoo/{tkr}.json",
            cadence="daily",
            unit=unit,
            fmt_style="currency",
            currency="USD",
            decimals=2,
            emphasis="change",
            provider="Yahoo Finance",
            series=tkr,
            url=f"https://finance.yahoo.com/quote/{tkr}",
        ),
    )
    write_if_absent(
        SRC / "charts" / "commodities" / f"{slug}.yaml",
        chart_yaml(title=f"{name} ({tkr})", sources=[f"yahoo/{slug}"], default_delta="1m"),
    )

# --- Commodities: agricultural & softs ---
# (slug, ticker, name, unit, prefix, suffix, decimals)
AG: list[tuple] = [
    ("corn_futures",       "ZC_F",  "Corn front-month",        "USc/bu",       "",  " \u00a2/bu",  2),
    ("wheat_futures",      "ZW_F",  "Wheat front-month",       "USc/bu",       "",  " \u00a2/bu",  2),
    ("soybean_futures",    "ZS_F",  "Soybean front-month",     "USc/bu",       "",  " \u00a2/bu",  2),
    ("coffee_futures",     "KC_F",  "Coffee front-month",      "USc/lb",       "",  " \u00a2/lb",  2),
    ("sugar_futures",      "SB_F",  "Sugar No. 11 front-month","USc/lb",       "",  " \u00a2/lb",  2),
    ("cotton_futures",     "CT_F",  "Cotton No. 2 front-month","USc/lb",       "",  " \u00a2/lb",  2),
    ("cocoa_futures",      "CC_F",  "Cocoa front-month",       "USD/ton",      "$", " /ton",      0),
    ("cattle_futures",     "LE_F",  "Live cattle front-month", "USc/lb",       "",  " \u00a2/lb",  2),
    ("orange_juice_futures","OJ_F", "Orange juice front-month","USc/lb",       "",  " \u00a2/lb",  2),
    ("lumber_futures",     "LBR_F", "Lumber front-month",      "USD/1000 bd-ft","$"," /1000bf",   2),
]
for slug, tkr, name, unit, pfx, sfx, dec in AG:
    base = name.replace("front-month", "").strip()
    write_if_absent(
        SRC / "sources" / "yahoo" / f"{slug}.yaml",
        source_yaml(
            name=name,
            short_name=tkr.replace("_F", ""),
            description=f"CBOT/ICE/CME {base.lower()} futures, daily.",
            pipeline="yahoo_quotes",
            data_file=f"data/yahoo/{tkr}.json",
            cadence="daily",
            unit=unit,
            fmt_style="number",
            decimals=dec,
            prefix=pfx or None,
            suffix=sfx,
            provider="Yahoo Finance",
            series=f"{tkr.replace('_F', '=F')}",
            url=f"https://finance.yahoo.com/quote/{tkr.replace('_F', '=F')}",
        ),
    )
    write_if_absent(
        SRC / "charts" / "commodities" / f"{slug}.yaml",
        chart_yaml(title=base, sources=[f"yahoo/{slug}"], default_delta="1m"),
    )

# --- Commodity ETFs (broad) ---
COMMODITY_ETFS = [
    ("dbc", "DBC", "Invesco DB Commodity Index Tracking ETF"),
    ("gsg", "GSG", "iShares S&P GSCI Commodity ETF"),
    ("dba", "DBA", "Invesco DB Agriculture ETF"),
]
for slug, tkr, name in COMMODITY_ETFS:
    write_if_absent(
        SRC / "sources" / "yahoo" / f"{slug}.yaml",
        source_yaml(
            name=name,
            short_name=tkr,
            description="Broad commodity-basket ETF. Daily adjusted close.",
            pipeline="yahoo_quotes",
            data_file=f"data/yahoo/{tkr}.json",
            cadence="daily",
            unit="USD",
            fmt_style="currency",
            currency="USD",
            decimals=2,
            emphasis="change",
            provider="Yahoo Finance",
            series=tkr,
            url=f"https://finance.yahoo.com/quote/{tkr}",
        ),
    )
    write_if_absent(
        SRC / "charts" / "commodities" / f"{slug}.yaml",
        chart_yaml(title=f"{tkr} ({name.split(' ')[-1]})", sources=[f"yahoo/{slug}"], default_delta="1m"),
    )


# ==============================================================
#  SECTOR SPDRs
# ==============================================================
SECTORS = [
    ("xlf",  "XLF",  "Financials",            "Financial Select Sector SPDR"),
    ("xlv",  "XLV",  "Healthcare",            "Health Care Select Sector SPDR"),
    ("xli",  "XLI",  "Industrials",           "Industrial Select Sector SPDR"),
    ("xlp",  "XLP",  "Consumer staples",      "Consumer Staples Select Sector SPDR"),
    ("xly",  "XLY",  "Consumer discretionary","Consumer Discretionary Select Sector SPDR"),
    ("xlb",  "XLB",  "Materials",             "Materials Select Sector SPDR"),
    ("xlc",  "XLC",  "Communications",        "Communication Services Select Sector SPDR"),
    ("xlre", "XLRE", "Real estate",           "Real Estate Select Sector SPDR"),
    ("xlu",  "XLU",  "Utilities",             "Utilities Select Sector SPDR"),
]
for slug, tkr, short_label, full_name in SECTORS:
    write_if_absent(
        SRC / "sources" / "yahoo" / f"{slug}.yaml",
        source_yaml(
            name=full_name,
            short_name=tkr,
            description=f"S&P 500 {short_label.lower()} sector ETF. Daily adjusted close.",
            pipeline="yahoo_quotes",
            data_file=f"data/yahoo/{tkr}.json",
            cadence="daily",
            unit="USD",
            fmt_style="currency",
            currency="USD",
            decimals=2,
            emphasis="change",
            provider="Yahoo Finance",
            series=tkr,
            url=f"https://finance.yahoo.com/quote/{tkr}",
        ),
    )
    write_if_absent(
        SRC / "charts" / "markets" / f"{slug}.yaml",
        chart_yaml(title=f"{short_label} ({tkr})", sources=[f"yahoo/{slug}"], default_delta="1m"),
    )


# ==============================================================
#  BROAD INDICES & INTERNATIONAL
# ==============================================================
BROAD_INDICES = [
    ("dia",  "DIA",  "Dow Jones (DIA)",                "SPDR Dow Jones Industrial Average ETF"),
    ("iwm",  "IWM",  "Russell 2000 (IWM)",             "iShares Russell 2000 ETF"),
    ("iwb",  "IWB",  "Russell 1000 (IWB)",             "iShares Russell 1000 ETF"),
    ("vti",  "VTI",  "Total US market (VTI)",          "Vanguard Total Stock Market ETF"),
    ("efa",  "EFA",  "MSCI EAFE (EFA)",                "iShares MSCI EAFE ETF"),
    ("vea",  "VEA",  "Developed ex-US (VEA)",          "Vanguard FTSE Developed Markets ETF"),
    ("eem",  "EEM",  "Emerging markets (EEM)",         "iShares MSCI Emerging Markets ETF"),
    ("vwo",  "VWO",  "Emerging markets (VWO)",         "Vanguard FTSE Emerging Markets ETF"),
]
for slug, tkr, short_label, full_name in BROAD_INDICES:
    write_if_absent(
        SRC / "sources" / "yahoo" / f"{slug}.yaml",
        source_yaml(
            name=full_name,
            short_name=tkr,
            description="Broad-index equity ETF. Daily adjusted close.",
            pipeline="yahoo_quotes",
            data_file=f"data/yahoo/{tkr}.json",
            cadence="daily",
            unit="USD",
            fmt_style="currency",
            currency="USD",
            decimals=2,
            emphasis="change",
            provider="Yahoo Finance",
            series=tkr,
            url=f"https://finance.yahoo.com/quote/{tkr}",
        ),
    )
    write_if_absent(
        SRC / "charts" / "markets" / f"{slug}.yaml",
        chart_yaml(title=short_label, sources=[f"yahoo/{slug}"], default_delta="1m"),
    )


# ==============================================================
#  FAMOUS STOCKS  (prices as Source; Charts use market-cap Source instead)
# ==============================================================
STOCKS = [
    # (slug, ticker, name, short)
    ("brk_b", "BRK-B", "Berkshire Hathaway (Class B)", "BRK.B"),
    ("jpm",   "JPM",   "JPMorgan Chase",                "JPM"),
    ("bac",   "BAC",   "Bank of America",               "BAC"),
    ("gs",    "GS",    "Goldman Sachs",                 "GS"),
    ("v",     "V",     "Visa",                          "V"),
    ("ma",    "MA",    "Mastercard",                    "MA"),
    ("jnj",   "JNJ",   "Johnson & Johnson",             "JNJ"),
    ("unh",   "UNH",   "UnitedHealth Group",            "UNH"),
    ("lly",   "LLY",   "Eli Lilly",                     "LLY"),
    ("pfe",   "PFE",   "Pfizer",                        "PFE"),
    ("xom",   "XOM",   "ExxonMobil",                    "XOM"),
    ("cvx",   "CVX",   "Chevron",                       "CVX"),
    ("ko",    "KO",    "Coca-Cola",                     "KO"),
    ("pep",   "PEP",   "PepsiCo",                       "PEP"),
    ("wmt",   "WMT",   "Walmart",                       "WMT"),
    ("cost",  "COST",  "Costco",                        "COST"),
    ("hd",    "HD",    "Home Depot",                    "HD"),
    ("mcd",   "MCD",   "McDonald's",                    "MCD"),
    ("dis",   "DIS",   "Walt Disney",                   "DIS"),
    ("ba",    "BA",    "Boeing",                        "BA"),
    ("cat",   "CAT",   "Caterpillar",                   "CAT"),
    ("ge",    "GE",    "GE Aerospace",                  "GE"),
    ("tsla",  "TSLA",  "Tesla",                         "TSLA"),
    ("nflx",  "NFLX",  "Netflix",                       "NFLX"),
    ("asml",  "ASML",  "ASML Holding",                  "ASML"),
    ("tsm",   "TSM",   "Taiwan Semiconductor (ADR)",    "TSM"),
    ("avgo",  "AVGO",  "Broadcom",                      "AVGO"),
    ("orcl",  "ORCL",  "Oracle",                        "ORCL"),
    ("crm",   "CRM",   "Salesforce",                    "CRM"),
    ("csco",  "CSCO",  "Cisco Systems",                 "CSCO"),
]
for slug, tkr, name, short in STOCKS:
    data_tkr = tkr.replace("-", "_")  # filesystem-safe for BRK-B
    # Source: stock price (for charts that want price)
    write_if_absent(
        SRC / "sources" / "yahoo" / f"{slug}.yaml",
        source_yaml(
            name=f"{name} ({tkr})",
            short_name=short,
            description="Daily adjusted close.",
            pipeline="yahoo_quotes",
            data_file=f"data/yahoo/{data_tkr}.json",
            cadence="daily",
            unit="USD",
            fmt_style="currency",
            currency="USD",
            decimals=2,
            emphasis="level",
            provider="Yahoo Finance",
            series=tkr,
            url=f"https://finance.yahoo.com/quote/{tkr}",
        ),
    )
    # Source: market cap
    mc_slug = f"{slug}_mc"
    mc_data_tkr = f"{data_tkr}_mc"
    write_if_absent(
        SRC / "sources" / "yahoo_marketcap" / f"{mc_slug}.yaml",
        source_yaml(
            name=f"{name} market cap",
            short_name=short,
            description="Unadjusted close \u00d7 historical shares outstanding (yfinance).",
            pipeline="yahoo_marketcap",
            data_file=f"data/yahoo_marketcap/{mc_data_tkr}.json",
            cadence="daily",
            unit="USD",
            fmt_style="currency",
            currency="USD",
            decimals=2,
            notation="compact",
            emphasis="level",
            provider="Yahoo Finance (derived)",
            series=f"{tkr} \u00d7 shares outstanding",
            url=f"https://finance.yahoo.com/quote/{tkr}",
            notes="Historical shares via yfinance get_shares_full(); shares forward-filled between quarterly observations.",
        ),
    )
    # Chart: points to market cap (per user's valuation preference)
    write_if_absent(
        SRC / "charts" / "stocks" / f"{slug}.yaml",
        chart_yaml(title=name, sources=[f"yahoo_marketcap/{mc_slug}"], default_delta="1m"),
    )


# ==============================================================
#  FRED — rates, inflation, labor, housing, spending, monetary, credit, risk
# ==============================================================
FRED_EXTENSION = [
    # (slug, series_id, name, short, unit, fmt_style, decimals, prefix, suffix, notation, emphasis, cadence, desc)
    # Rates curve
    ("us_3mo",          "DGS3MO",       "US 3-month Treasury yield",          "3M",    "%",                 "percent",  2, "",  "",  None,     "level",  "daily",   "Constant-maturity 3-month US Treasury yield. Daily."),
    ("us_5y",           "DGS5",         "US 5-year Treasury yield",           "5Y",    "%",                 "percent",  2, "",  "",  None,     "level",  "daily",   "Constant-maturity 5-year US Treasury yield. Daily."),
    ("us_30y",          "DGS30",        "US 30-year Treasury yield",          "30Y",   "%",                 "percent",  2, "",  "",  None,     "level",  "daily",   "Constant-maturity 30-year US Treasury yield. Daily."),
    ("fed_funds",       "FEDFUNDS",     "Federal funds effective rate",       "FedFunds","%",               "percent",  2, "",  "",  None,     "level",  "monthly", "Monthly average of daily fed funds effective rate."),
    ("mortgage_30y",    "MORTGAGE30US", "30-year fixed mortgage rate",        "30yMort","%",                "percent",  2, "",  "",  None,     "level",  "weekly",  "Freddie Mac primary mortgage market survey, weekly."),
    # Inflation
    ("core_cpi",        "CPILFESL",     "Core CPI (all items less food & energy)","Core CPI","index",      "number",   2, "",  "",  None,     "level",  "monthly", "Core CPI (1982-84=100), monthly."),
    ("headline_pce",    "PCEPI",        "PCE price index (headline)",         "PCE",    "index",            "number",   2, "",  "",  None,     "level",  "monthly", "PCE price index, 2017=100, monthly."),
    ("core_pce",        "PCEPILFE",     "Core PCE price index",               "Core PCE","index",           "number",   2, "",  "",  None,     "level",  "monthly", "Core PCE price index (ex food & energy), 2017=100, monthly."),
    # Labor
    ("payrolls",        "PAYEMS",       "Nonfarm payrolls",                   "Payrolls","thousands",       "number",   0, "",  "k",  None,     "level",  "monthly", "All employees, total nonfarm (thousands, SA). Monthly."),
    ("labor_participation","CIVPART",   "Labor force participation rate",     "LFPR",   "%",                "percent",  1, "",  "",  None,     "level",  "monthly", "Civilian labor force participation rate, monthly."),
    ("avg_hourly_earnings","AHETPI",    "Avg hourly earnings (production & nonsup.)","AHE","USD",           "currency", 2, "",  "",  None,     "level",  "monthly", "Average hourly earnings of production & nonsupervisory employees (USD), monthly."),
    # Output / utilization
    ("capacity_util",   "TCU",          "Capacity utilization (total industry)","CapUtil","%",              "percent",  1, "",  "",  None,     "level",  "monthly", "Total industry capacity utilization, monthly."),
    # Housing
    ("housing_starts",  "HOUST",        "Housing starts (privately-owned)",   "Starts", "thousands, SAAR",  "number",   0, "",  "k",  None,     "level",  "monthly", "New privately-owned housing units started, thousands SAAR, monthly."),
    ("case_shiller",    "CSUSHPISA",    "Case-Shiller national home price",   "CS HPI", "index",            "number",   1, "",  "",  None,     "level",  "monthly", "Case-Shiller national home price index (SA), monthly."),
    ("median_home_price","MSPUS",       "Median sales price of houses sold",  "Median \u0024",      "USD",          "currency", 0, "",  "",  "compact","level",  "quarterly","Median sales price of houses sold (USD), quarterly."),
    # Spending
    ("retail_sales",    "RSAFS",        "Retail sales (advance, total ex auto)","Retail","millions USD",    "currency", 0, "",  "",  "compact","level",  "monthly", "Advance retail sales, total ex auto (USD, SA), monthly."),
    ("personal_income", "PI",           "Personal income",                    "PI",     "billions USD",     "currency", 1, "",  "B",  None,     "level",  "monthly", "Personal income (SAAR, USD billions), monthly."),
    ("saving_rate",     "PSAVERT",      "Personal saving rate",               "Saving", "%",                "percent",  1, "",  "",  None,     "level",  "monthly", "Personal saving rate (SA), monthly."),
    # Monetary
    ("m2",              "M2SL",         "M2 money supply",                    "M2",     "billions USD",     "currency", 0, "",  "B",  None,     "level",  "monthly", "M2 money stock (SA), monthly."),
    ("fed_balance_sheet","WALCL",       "Fed total assets (balance sheet)",   "Fed BS", "millions USD",     "currency", 0, "",  "",  "compact","level",  "weekly",  "Federal Reserve total assets, weekly (Wednesday close)."),
    # Credit spreads
    ("hy_spread",       "BAMLH0A0HYM2", "HY corporate OAS (ICE BofA)",         "HY OAS", "%",                "percent",  2, "",  "",  None,     "level",  "daily",   "ICE BofA US high-yield corporate option-adjusted spread, daily."),
    ("ig_spread",       "BAMLC0A0CM",   "IG corporate OAS (ICE BofA)",         "IG OAS", "%",                "percent",  2, "",  "",  None,     "level",  "daily",   "ICE BofA US corporate (IG) option-adjusted spread, daily."),
    # Risk
    ("vix",             "VIXCLS",       "VIX (CBOE volatility index)",         "VIX",    "index",            "number",   2, "",  "",  None,     "change", "daily",   "CBOE S&P 500 implied-volatility index, daily close."),
]
for (slug, sid, name, short, unit, fmt, dec, pfx, sfx, notation, emph, cad, desc) in FRED_EXTENSION:
    write_if_absent(
        SRC / "sources" / "fred" / f"{slug}.yaml",
        source_yaml(
            name=name,
            short_name=short,
            description=desc,
            pipeline="fred_series",
            data_file=f"data/fred/{sid}.json",
            cadence=cad,
            unit=unit,
            fmt_style=fmt,
            decimals=dec,
            prefix=pfx or None,
            suffix=sfx or None,
            notation=notation,
            emphasis=emph,
            provider="FRED (St. Louis Fed)",
            series=sid,
            url=f"https://fred.stlouisfed.org/series/{sid}",
            license_="Public domain (US government data)",
        ),
    )

# Charts for FRED extensions — placed under us-macro/
FRED_CHART_DEFAULTS = {
    "us_3mo":            ("3-month Treasury yield",   "1m"),
    "us_5y":             ("5-year Treasury yield",    "1m"),
    "us_30y":            ("30-year Treasury yield",   "1m"),
    "fed_funds":         ("Federal funds rate",       "1y"),
    "mortgage_30y":      ("30-year fixed mortgage",   "1m"),
    "core_cpi":          ("Core CPI",                 "1y"),
    "headline_pce":      ("PCE (headline)",           "1y"),
    "core_pce":          ("Core PCE",                 "1y"),
    "payrolls":          ("Nonfarm payrolls",         "1m"),
    "labor_participation":("Labor force participation","1y"),
    "avg_hourly_earnings":("Avg hourly earnings",     "1y"),
    "capacity_util":     ("Capacity utilization",     "1y"),
    "housing_starts":    ("Housing starts",           "1y"),
    "case_shiller":      ("Case-Shiller home prices", "1y"),
    "median_home_price": ("Median home sale price",   "1y"),
    "retail_sales":      ("Retail sales",             "1y"),
    "personal_income":   ("Personal income",          "1y"),
    "saving_rate":       ("Personal saving rate",     "1y"),
    "m2":                ("M2 money supply",          "1y"),
    "fed_balance_sheet": ("Fed balance sheet",        "1y"),
    "hy_spread":         ("HY corporate spread",      "1m"),
    "ig_spread":         ("IG corporate spread",      "1m"),
    "vix":               ("VIX",                      "1m"),
}
for slug, (title, dd) in FRED_CHART_DEFAULTS.items():
    write_if_absent(
        SRC / "charts" / "us-macro" / f"{slug}.yaml",
        chart_yaml(title=title, sources=[f"fred/{slug}"], default_delta=dd),
    )


if __name__ == "__main__":
    print("Done.")
