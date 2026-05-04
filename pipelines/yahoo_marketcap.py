"""
Compute historical market capitalization (valuation) for a set of tickers.

Approach:
  market_cap(t) = unadjusted_close(t) * shares_outstanding(t)

yfinance's ``get_shares_full()`` returns point-in-time share counts at roughly
quarterly cadence; we forward-fill to align with daily closing prices. We use
UNADJUSTED prices here — adjusted prices are backward-corrected for splits,
which would double-count against the actual (pre-split) share count in history.

Run AFTER yahoo_quotes.py (they can also run independently).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from common import write_timeseries


@dataclass
class MarketCapSpec:
    symbol: str
    series_id: str
    name: str


SPECS: list[MarketCapSpec] = [
    # Tech mega-caps (original set)
    MarketCapSpec("AAPL", "AAPL_mc", "Apple market cap"),
    MarketCapSpec("MSFT", "MSFT_mc", "Microsoft market cap"),
    MarketCapSpec("GOOG", "GOOG_mc", "Alphabet (Class C) market cap"),
    MarketCapSpec("AMZN", "AMZN_mc", "Amazon market cap"),
    MarketCapSpec("META", "META_mc", "Meta Platforms market cap"),
    MarketCapSpec("NVDA", "NVDA_mc", "NVIDIA market cap"),
    # Financials
    MarketCapSpec("BRK-B", "BRK_B_mc", "Berkshire Hathaway (B) market cap"),
    MarketCapSpec("JPM", "JPM_mc", "JPMorgan Chase market cap"),
    MarketCapSpec("BAC", "BAC_mc", "Bank of America market cap"),
    MarketCapSpec("GS", "GS_mc", "Goldman Sachs market cap"),
    MarketCapSpec("V", "V_mc", "Visa market cap"),
    MarketCapSpec("MA", "MA_mc", "Mastercard market cap"),
    # Healthcare
    MarketCapSpec("JNJ", "JNJ_mc", "Johnson & Johnson market cap"),
    MarketCapSpec("UNH", "UNH_mc", "UnitedHealth market cap"),
    MarketCapSpec("LLY", "LLY_mc", "Eli Lilly market cap"),
    MarketCapSpec("PFE", "PFE_mc", "Pfizer market cap"),
    # Energy
    MarketCapSpec("XOM", "XOM_mc", "ExxonMobil market cap"),
    MarketCapSpec("CVX", "CVX_mc", "Chevron market cap"),
    # Consumer
    MarketCapSpec("KO", "KO_mc", "Coca-Cola market cap"),
    MarketCapSpec("PEP", "PEP_mc", "PepsiCo market cap"),
    MarketCapSpec("WMT", "WMT_mc", "Walmart market cap"),
    MarketCapSpec("COST", "COST_mc", "Costco market cap"),
    MarketCapSpec("HD", "HD_mc", "Home Depot market cap"),
    MarketCapSpec("MCD", "MCD_mc", "McDonald's market cap"),
    MarketCapSpec("DIS", "DIS_mc", "Walt Disney market cap"),
    # Industrial / auto
    MarketCapSpec("BA", "BA_mc", "Boeing market cap"),
    MarketCapSpec("CAT", "CAT_mc", "Caterpillar market cap"),
    MarketCapSpec("GE", "GE_mc", "GE Aerospace market cap"),
    MarketCapSpec("TSLA", "TSLA_mc", "Tesla market cap"),
    # More tech / media
    MarketCapSpec("NFLX", "NFLX_mc", "Netflix market cap"),
    MarketCapSpec("ASML", "ASML_mc", "ASML market cap"),
    MarketCapSpec("TSM", "TSM_mc", "Taiwan Semiconductor (ADR) market cap"),
    MarketCapSpec("AVGO", "AVGO_mc", "Broadcom market cap"),
    MarketCapSpec("ORCL", "ORCL_mc", "Oracle market cap"),
    MarketCapSpec("CRM", "CRM_mc", "Salesforce market cap"),
    MarketCapSpec("CSCO", "CSCO_mc", "Cisco market cap"),
]


def fetch_marketcap(symbol: str) -> list[dict]:
    ticker = yf.Ticker(symbol)
    # Note: even with auto_adjust=False, modern yfinance returns "Close" that
    # is silently split-adjusted (pre-split rows in post-split dollars). We
    # recover the truly unadjusted price by multiplying by the product of all
    # split ratios that occurred AFTER each date.
    hist = ticker.history(period="max", auto_adjust=False)
    if hist.empty:
        return []
    closes = hist["Close"].dropna()
    closes.index = closes.index.tz_localize(None).normalize()

    splits = hist["Stock Splits"].fillna(0).copy() if "Stock Splits" in hist.columns else None
    if splits is not None and len(splits) > 0:
        splits.index = splits.index.tz_localize(None).normalize()
        splits = splits[~splits.index.duplicated(keep="last")]
        # Treat zero-rows as ratio-1; multiply going backward to get cumulative
        # future-split factor at each date. On a split day the close is already
        # at post-split basis, so we exclude that day's split from its own
        # factor (factor = rev_cumprod / self_ratio).
        splits_clean = splits.where(splits > 0, 1.0)
        rev_cumprod = splits_clean.iloc[::-1].cumprod().iloc[::-1]
        future_factor = rev_cumprod / splits_clean
        future_factor = future_factor.reindex(closes.index, method="ffill").fillna(1.0)
        closes = closes * future_factor

    raw_shares = ticker.get_shares_full(start="1980-01-01")
    points: list[dict] = []
    if raw_shares is not None and len(raw_shares) > 0:
        raw_shares = raw_shares.sort_index()
        raw_shares.index = raw_shares.index.tz_localize(None).normalize()
        # Bucket all values per day so we can pick the right one when there's
        # ambiguity. yfinance frequently returns 2-3 values on a split day:
        # the pre-split count, the post-split count, and (occasionally) a
        # bogus value (e.g., post-split × split-ratio again). We prefer the
        # one closest to expected = prev × split_ratio rather than blindly
        # taking max/last/first.
        per_day: dict[pd.Timestamp, list[float]] = {}
        for ts, v in raw_shares.items():
            per_day.setdefault(ts, []).append(float(v))

        # Build a clean per-trading-day share count aligned to closes.index.
        # On split days we synthesize prev × ratio if no plausible value exists.
        # On non-split days we take the latest yfinance value (or carry forward).
        # NB: yfinance can return stale pre-split-equivalent counts for some
        # weeks AFTER a split (Apple's late-2020 case). The split-day override
        # corrects the split-day point itself; subsequent ffill carries the
        # corrected value until yfinance returns a consistent newer value.
        clean = {}
        last_known: float | None = None
        for ts in closes.index:
            ratio = float(splits.get(ts, 0)) if splits is not None else 0.0
            available = per_day.get(ts, [])
            if ratio > 0:
                expected = last_known * ratio if last_known is not None else None
                chosen: float | None = None
                if available and expected is not None:
                    chosen = min(available, key=lambda v: abs(v - expected))
                    # Reject if it's wildly off (e.g., yfinance's bogus 4.65B
                    # for Tesla, which is 5x the expected post-split count).
                    if abs(chosen - expected) / expected > 0.5:
                        chosen = expected
                elif expected is not None:
                    chosen = expected
                elif available:
                    # No prior known shares; just take the largest as a guess.
                    chosen = max(available)
                if chosen is not None:
                    clean[ts] = chosen
                    last_known = chosen
            else:
                if available:
                    # Plain non-split day. Take last reported value. Reject
                    # if it implies an implausibly huge jump (>10x) from the
                    # last known — that signals a stale pre-split entry
                    # surfacing late. (Smaller jumps from real issuance or
                    # buybacks pass through fine.)
                    cand = available[-1]
                    if last_known is not None and (
                        cand > last_known * 10 or cand < last_known / 10
                    ):
                        clean[ts] = last_known
                    else:
                        clean[ts] = cand
                        last_known = cand
                elif last_known is not None:
                    clean[ts] = last_known

        for ts, close_v in closes.items():
            shares_v = clean.get(ts)
            if shares_v is None or pd.isna(shares_v):
                continue
            mc = float(close_v) * float(shares_v)
            if mc <= 0:
                continue
            points.append({"t": ts.strftime("%Y-%m-%d"), "v": mc})
    else:
        # Fallback: use current shares count × historical prices (approximation)
        current_shares = ticker.info.get("sharesOutstanding")
        if not current_shares:
            return []
        for ts, close_v in closes.items():
            mc = float(close_v) * float(current_shares)
            points.append({"t": ts.strftime("%Y-%m-%d"), "v": mc})
    return points


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
        print(f"Computing market cap for {spec.symbol}...", flush=True)
        try:
            points = fetch_marketcap(spec.symbol)
        except Exception as e:
            print(f"  ERROR: {e}")
            errors += 1
            continue
        if not points:
            print("  (no data)")
            errors += 1
            continue
        out = write_timeseries(
            pipeline="yahoo_marketcap",
            series_id=spec.series_id,
            name=spec.name,
            points=points,
            unit="USD",
        )
        first_v = points[0]["v"]
        last_v = points[-1]["v"]
        print(
            f"  {len(points):>6} points, ${first_v / 1e9:.1f}B -> ${last_v / 1e9:.1f}B  [{out}]"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
