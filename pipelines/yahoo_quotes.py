"""
Fetch daily adjusted-close prices from Yahoo Finance via yfinance.

Run with: ``python pipelines/yahoo_quotes.py`` (all specs), or
          ``python pipelines/yahoo_quotes.py AAPL CL_F`` (specific series).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import yfinance as yf

from common import write_timeseries


@dataclass
class YahooSpec:
    symbol: str  # Yahoo ticker (e.g. "AAPL", "CL=F")
    series_id: str  # ID for output file (filename-safe)
    name: str
    unit: str | None = None


SPECS: list[YahooSpec] = [
    # Tech
    YahooSpec("QQQ", "QQQ", "Invesco QQQ (Nasdaq-100 ETF)", "USD"),
    YahooSpec("XLK", "XLK", "Technology Select Sector SPDR ETF", "USD"),
    YahooSpec("SOXX", "SOXX", "iShares Semiconductor ETF", "USD"),
    YahooSpec("AAPL", "AAPL", "Apple", "USD"),
    YahooSpec("MSFT", "MSFT", "Microsoft", "USD"),
    YahooSpec("GOOG", "GOOG", "Alphabet (Class C)", "USD"),
    YahooSpec("AMZN", "AMZN", "Amazon", "USD"),
    YahooSpec("META", "META", "Meta Platforms", "USD"),
    YahooSpec("NVDA", "NVDA", "NVIDIA", "USD"),
    # Tech-adjacent credit
    YahooSpec("XHYT", "XHYT", "BondBloxx HY Telecom/Media/Tech bond ETF", "USD"),
    # Oil & energy
    YahooSpec("CL=F", "CL_F", "WTI crude oil front-month (NYMEX)", "USD/bbl"),
    YahooSpec("BZ=F", "BZ_F", "Brent crude front-month (ICE)", "USD/bbl"),
    YahooSpec("NG=F", "NG_F", "Henry Hub natural gas front-month", "USD/mmbtu"),
    YahooSpec("RB=F", "RB_F", "RBOB gasoline wholesale (NYMEX)", "USD/gal"),
    YahooSpec("HO=F", "HO_F", "NY Harbor ULSD / heating oil (NYMEX)", "USD/gal"),
    YahooSpec("XLE", "XLE", "Energy Select Sector SPDR ETF", "USD"),
    YahooSpec("XOP", "XOP", "SPDR Oil & Gas Exploration ETF", "USD"),
    YahooSpec("URA", "URA", "Global X Uranium ETF", "USD"),
    YahooSpec("ICLN", "ICLN", "iShares Global Clean Energy ETF", "USD"),
    YahooSpec("TAN", "TAN", "Invesco Solar ETF", "USD"),
    YahooSpec("USO", "USO", "United States Oil Fund", "USD"),
    # ------------------------------------------------------------------
    # AI + datacenter expansion: chip-supply chain, colocation REITs,
    # power producers riding the AI demand wave, and AI thematic ETFs.
    # ------------------------------------------------------------------
    # Semis (chip manufacturers + the upstream equipment supply chain).
    # NVDA already covered via yahoo_marketcap; this rounds out the rest.
    YahooSpec("AMD", "AMD", "Advanced Micro Devices", "USD"),
    YahooSpec("INTC", "INTC", "Intel", "USD"),
    YahooSpec("AMAT", "AMAT", "Applied Materials (semicap)", "USD"),
    YahooSpec("KLAC", "KLAC", "KLA Corp (semicap inspection)", "USD"),
    YahooSpec("LRCX", "LRCX", "Lam Research (semicap etch & deposition)", "USD"),
    YahooSpec("ARM", "ARM", "Arm Holdings (CPU IP licensor)", "USD"),
    YahooSpec("SMCI", "SMCI", "Super Micro Computer (AI server systems)", "USD"),
    # Datacenter REITs (the physical AI buildout).
    YahooSpec("EQIX", "EQIX", "Equinix (datacenter colocation REIT)", "USD"),
    YahooSpec("DLR", "DLR", "Digital Realty (datacenter REIT)", "USD"),
    YahooSpec("IRM", "IRM", "Iron Mountain (records + datacenter)", "USD"),
    # AI-tailwind power producers. The 2024-25 datacenter electricity-
    # demand story drove utility valuations sharply: nuclear-heavy
    # operators got bid up first (Microsoft/Three Mile Island, AWS/Talen,
    # MSFT/Vistra Comanche Peak), gas+coal peakers second.
    YahooSpec("VST", "VST", "Vistra (gas + nuclear, MSFT Comanche Peak deal)", "USD"),
    YahooSpec("CEG", "CEG", "Constellation Energy (nuclear, MSFT TMI deal)", "USD"),
    YahooSpec("TLN", "TLN", "Talen Energy (nuclear, AWS deal)", "USD"),
    YahooSpec("NRG", "NRG", "NRG Energy", "USD"),
    # AI thematic ETFs (retail/institutional belief signal).
    YahooSpec("BOTZ", "BOTZ", "Global X Robotics + AI ETF", "USD"),
    YahooSpec("AIQ", "AIQ", "Global X Artificial Intelligence + Tech ETF", "USD"),
    YahooSpec("ROBO", "ROBO", "ROBO Global Robotics + Automation ETF", "USD"),
    YahooSpec("SMH", "SMH", "VanEck Semiconductor ETF (broader than SOXX)", "USD"),
    # Countries + global benchmark
    YahooSpec("VT", "VT", "Vanguard Total World Stock ETF", "USD"),
    YahooSpec("EWJ", "EWJ", "iShares MSCI Japan ETF", "USD"),
    YahooSpec("EWG", "EWG", "iShares MSCI Germany ETF", "USD"),
    YahooSpec("EWU", "EWU", "iShares MSCI UK ETF", "USD"),
    YahooSpec("EWZ", "EWZ", "iShares MSCI Brazil ETF", "USD"),
    YahooSpec("FXI", "FXI", "iShares China Large-Cap ETF", "USD"),
    YahooSpec("INDA", "INDA", "iShares MSCI India ETF", "USD"),
    YahooSpec("EWC", "EWC", "iShares MSCI Canada ETF", "USD"),
    YahooSpec("EWA", "EWA", "iShares MSCI Australia ETF", "USD"),
    YahooSpec("EWW", "EWW", "iShares MSCI Mexico ETF", "USD"),
    YahooSpec("EWY", "EWY", "iShares MSCI South Korea ETF", "USD"),
    # ------------------------------------------------------------------
    # Library expansion: commodities, indices, sector SPDRs, famous stocks
    # ------------------------------------------------------------------
    # Precious & base metals
    YahooSpec("GC=F", "GC_F", "Gold front-month (COMEX)", "USD/oz"),
    YahooSpec("SI=F", "SI_F", "Silver front-month (COMEX)", "USD/oz"),
    YahooSpec("PL=F", "PL_F", "Platinum front-month (NYMEX)", "USD/oz"),
    YahooSpec("PA=F", "PA_F", "Palladium front-month (NYMEX)", "USD/oz"),
    YahooSpec("HG=F", "HG_F", "Copper front-month (COMEX)", "USD/lb"),
    YahooSpec("GLD", "GLD", "SPDR Gold Shares ETF", "USD"),
    YahooSpec("SLV", "SLV", "iShares Silver Trust ETF", "USD"),
    # Agricultural & softs
    YahooSpec("ZC=F", "ZC_F", "Corn front-month (CBOT)", "USc/bu"),
    YahooSpec("ZW=F", "ZW_F", "Wheat front-month (CBOT)", "USc/bu"),
    YahooSpec("ZS=F", "ZS_F", "Soybean front-month (CBOT)", "USc/bu"),
    YahooSpec("KC=F", "KC_F", "Coffee front-month (ICE)", "USc/lb"),
    YahooSpec("SB=F", "SB_F", "Sugar No. 11 front-month (ICE)", "USc/lb"),
    YahooSpec("CT=F", "CT_F", "Cotton No. 2 front-month (ICE)", "USc/lb"),
    YahooSpec("CC=F", "CC_F", "Cocoa front-month (ICE)", "USD/ton"),
    YahooSpec("LE=F", "LE_F", "Live cattle front-month (CME)", "USc/lb"),
    YahooSpec("OJ=F", "OJ_F", "Orange juice front-month (ICE)", "USc/lb"),
    YahooSpec("LBR=F", "LBR_F", "Lumber front-month (CME)", "USD/1000 bd-ft"),
    # Broad-commodity ETFs
    YahooSpec("DBC", "DBC", "Invesco DB Commodity Index Tracking ETF", "USD"),
    YahooSpec("GSG", "GSG", "iShares S&P GSCI Commodity ETF", "USD"),
    YahooSpec("DBA", "DBA", "Invesco DB Agriculture ETF", "USD"),
    # Sector SPDRs (XLK and XLE already present)
    YahooSpec("XLF", "XLF", "Financial Select Sector SPDR ETF", "USD"),
    YahooSpec("XLV", "XLV", "Health Care Select Sector SPDR ETF", "USD"),
    YahooSpec("XLI", "XLI", "Industrial Select Sector SPDR ETF", "USD"),
    YahooSpec("XLP", "XLP", "Consumer Staples Select Sector SPDR ETF", "USD"),
    YahooSpec("XLY", "XLY", "Consumer Discretionary Select Sector SPDR ETF", "USD"),
    YahooSpec("XLB", "XLB", "Materials Select Sector SPDR ETF", "USD"),
    YahooSpec("XLC", "XLC", "Communication Services Select Sector SPDR ETF", "USD"),
    YahooSpec("XLRE", "XLRE", "Real Estate Select Sector SPDR ETF", "USD"),
    YahooSpec("XLU", "XLU", "Utilities Select Sector SPDR ETF", "USD"),
    # Broad US indices (ETFs)
    YahooSpec("DIA", "DIA", "SPDR Dow Jones Industrial Average ETF", "USD"),
    YahooSpec("IWM", "IWM", "iShares Russell 2000 ETF", "USD"),
    YahooSpec("IWB", "IWB", "iShares Russell 1000 ETF", "USD"),
    YahooSpec("VTI", "VTI", "Vanguard Total Stock Market ETF", "USD"),
    # International (beyond VT + country ETFs)
    YahooSpec("EFA", "EFA", "iShares MSCI EAFE ETF", "USD"),
    YahooSpec("VEA", "VEA", "Vanguard FTSE Developed Markets ETF", "USD"),
    YahooSpec("EEM", "EEM", "iShares MSCI Emerging Markets ETF", "USD"),
    YahooSpec("VWO", "VWO", "Vanguard FTSE Emerging Markets ETF", "USD"),
    # Famous stocks — financials
    YahooSpec("BRK-B", "BRK_B", "Berkshire Hathaway (Class B)", "USD"),
    YahooSpec("JPM", "JPM", "JPMorgan Chase", "USD"),
    YahooSpec("BAC", "BAC", "Bank of America", "USD"),
    YahooSpec("GS", "GS", "Goldman Sachs", "USD"),
    YahooSpec("V", "V", "Visa", "USD"),
    YahooSpec("MA", "MA", "Mastercard", "USD"),
    # Famous stocks — healthcare
    YahooSpec("JNJ", "JNJ", "Johnson & Johnson", "USD"),
    YahooSpec("UNH", "UNH", "UnitedHealth Group", "USD"),
    YahooSpec("LLY", "LLY", "Eli Lilly", "USD"),
    YahooSpec("PFE", "PFE", "Pfizer", "USD"),
    # Famous stocks — energy
    YahooSpec("XOM", "XOM", "ExxonMobil", "USD"),
    YahooSpec("CVX", "CVX", "Chevron", "USD"),
    # Famous stocks — consumer
    YahooSpec("KO", "KO", "Coca-Cola", "USD"),
    YahooSpec("PEP", "PEP", "PepsiCo", "USD"),
    YahooSpec("WMT", "WMT", "Walmart", "USD"),
    YahooSpec("COST", "COST", "Costco", "USD"),
    YahooSpec("HD", "HD", "Home Depot", "USD"),
    YahooSpec("MCD", "MCD", "McDonald's", "USD"),
    YahooSpec("DIS", "DIS", "Walt Disney", "USD"),
    # Famous stocks — industrial / auto
    YahooSpec("BA", "BA", "Boeing", "USD"),
    YahooSpec("CAT", "CAT", "Caterpillar", "USD"),
    YahooSpec("GE", "GE", "GE Aerospace", "USD"),
    YahooSpec("TSLA", "TSLA", "Tesla", "USD"),
    # Famous stocks — more tech & media
    YahooSpec("NFLX", "NFLX", "Netflix", "USD"),
    YahooSpec("ASML", "ASML", "ASML Holding", "USD"),
    YahooSpec("TSM", "TSM", "Taiwan Semiconductor (ADR)", "USD"),
    YahooSpec("AVGO", "AVGO", "Broadcom", "USD"),
    YahooSpec("ORCL", "ORCL", "Oracle", "USD"),
    YahooSpec("CRM", "CRM", "Salesforce", "USD"),
    YahooSpec("CSCO", "CSCO", "Cisco Systems", "USD"),
    # ------------------------------------------------------------------
    # Library expansion v2: crypto, FX, real estate
    # ------------------------------------------------------------------
    # Crypto
    YahooSpec("BTC-USD", "BTC_USD", "Bitcoin (USD)", "USD"),
    YahooSpec("ETH-USD", "ETH_USD", "Ethereum (USD)", "USD"),
    YahooSpec("COIN", "COIN", "Coinbase Global", "USD"),
    # FX (= USD per unit of the foreign currency, except DXY which is the
    # broad trade-weighted dollar index against six majors).
    YahooSpec("DX-Y.NYB", "DXY", "US Dollar Index (DXY)", "index"),
    YahooSpec("EURUSD=X", "EURUSD", "EUR / USD", "USD"),
    YahooSpec("JPY=X", "USDJPY", "USD / JPY", "JPY"),
    YahooSpec("CNY=X", "USDCNY", "USD / CNY", "CNY"),
    # Real estate ETFs
    YahooSpec("VNQ", "VNQ", "Vanguard Real Estate ETF (VNQ)", "USD"),
    YahooSpec("XHB", "XHB", "SPDR S&P Homebuilders ETF (XHB)", "USD"),
    # ------------------------------------------------------------------
    # Library expansion v3: more crypto, more FX, more real estate stocks
    # ------------------------------------------------------------------
    # More crypto
    YahooSpec("SOL-USD", "SOL_USD", "Solana (USD)", "USD"),
    YahooSpec("XRP-USD", "XRP_USD", "XRP (USD)", "USD"),
    YahooSpec("MSTR", "MSTR", "Strategy (formerly MicroStrategy)", "USD"),
    # More FX
    YahooSpec("GBPUSD=X", "GBPUSD", "GBP / USD", "USD"),
    YahooSpec("CAD=X", "USDCAD", "USD / CAD", "CAD"),
    YahooSpec("MXN=X", "USDMXN", "USD / MXN", "MXN"),
    YahooSpec("INR=X", "USDINR", "USD / INR", "INR"),
    # Real estate REITs
    YahooSpec("PLD", "PLD", "Prologis (PLD)", "USD"),
    YahooSpec("AMT", "AMT", "American Tower (AMT)", "USD"),
    # ------------------------------------------------------------------
    # Library expansion v4: broader crypto coverage
    # ------------------------------------------------------------------
    # The top dozen-or-so coins by market cap, plus a couple ETF/proxy
    # vehicles for users who care about TradFi-accessible exposure rather
    # than spot tokens. Use the canonical Yahoo "<TICKER>-USD" form for
    # spot prices.
    YahooSpec("ADA-USD", "ADA_USD", "Cardano (USD)", "USD"),
    YahooSpec("DOGE-USD", "DOGE_USD", "Dogecoin (USD)", "USD"),
    YahooSpec("LTC-USD", "LTC_USD", "Litecoin (USD)", "USD"),
    YahooSpec("BNB-USD", "BNB_USD", "BNB (Binance) (USD)", "USD"),
    YahooSpec("DOT-USD", "DOT_USD", "Polkadot (USD)", "USD"),
    YahooSpec("LINK-USD", "LINK_USD", "Chainlink (USD)", "USD"),
    YahooSpec("AVAX-USD", "AVAX_USD", "Avalanche (USD)", "USD"),
    # Polygon (MATIC-USD) removed 2026-06-11: the token rebranded to POL
    # in 2024 and the MATIC ticker went dead on Yahoo 2025-03-24, so the
    # series silently stopped updating. Add POL-USD here if/when Polygon
    # coverage is wanted again.
    YahooSpec("TRX-USD", "TRX_USD", "TRON (USD)", "USD"),
    YahooSpec("SHIB-USD", "SHIB_USD", "Shiba Inu (USD)", "USD"),
    # Crypto-adjacent equities + ETFs — TradFi vehicles for crypto exposure
    YahooSpec("IBIT", "IBIT", "iShares Bitcoin Trust ETF (IBIT)", "USD"),
    YahooSpec("FBTC", "FBTC", "Fidelity Wise Origin Bitcoin Fund (FBTC)", "USD"),
    YahooSpec("ETHA", "ETHA", "iShares Ethereum Trust ETF (ETHA)", "USD"),
    YahooSpec("MARA", "MARA", "Marathon Digital Holdings (MARA)", "USD"),
    YahooSpec("RIOT", "RIOT", "Riot Platforms (RIOT)", "USD"),
]


def fetch_series(spec: YahooSpec) -> list[dict]:
    hist = yf.Ticker(spec.symbol).history(period="max", auto_adjust=True)
    if hist.empty:
        return []
    closes = hist["Close"].dropna()
    return [
        {"t": ts.strftime("%Y-%m-%d"), "v": float(v)}
        for ts, v in closes.items()
    ]


def main(argv: list[str] | None = None) -> int:
    wanted = set((argv or [])[1:])
    run = [
        s for s in SPECS
        if not wanted or s.series_id in wanted or s.symbol in wanted
    ]
    if not run:
        print(f"No specs matched {wanted}")
        return 2
    errors = 0
    for spec in run:
        print(f"Fetching Yahoo {spec.symbol}...", flush=True)
        try:
            points = fetch_series(spec)
        except Exception as e:
            print(f"  ERROR: {e}")
            errors += 1
            continue
        if not points:
            print("  (no data returned)")
            errors += 1
            continue
        out = write_timeseries(
            pipeline="yahoo",
            series_id=spec.series_id,
            name=spec.name,
            points=points,
            unit=spec.unit,
        )
        print(f"  {len(points):>6} points -> {out}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
