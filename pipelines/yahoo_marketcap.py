"""
Compute historical market capitalization (valuation) for a set of tickers.

Approach:
  market_cap(t) = unadjusted_close(t) * shares_outstanding(t)

Shares-outstanding comes from two sources, merged by date (latest reading
at-or-before each daily close wins):
  * **SEC EDGAR XBRL** (sec_shares.py) — the authoritative source for
    US-listed companies and large foreign filers. Covers 2009-onward at
    quarterly cadence (10-Q / 10-K filers) or annual cadence (20-F
    filers like ASML, TSM). Pulled by the sibling sec_shares pipeline;
    this pipeline reads its on-disk JSONs.
  * **yfinance get_shares_full()** — fallback for the bleeding-edge
    (dates after the most recent SEC filing reaches the API) and for
    tickers where SEC tagging is sparse or absent (BRK-B's dei tag
    tracks Class A only and stopped in 2011; pre-merger DIS lives
    under a different CIK; etc.). Returns point-in-time share counts
    going back to roughly 2017.

We use UNADJUSTED prices throughout — adjusted prices are backward-
corrected for splits, which would double-count against the actual
(pre-split) share count in history. The future-split-factor adjustment
below recovers true unadjusted prices from yfinance's silently-split-
adjusted "Close" column.

Run AFTER yahoo_quotes.py (they can also run independently). When SEC
data is desired, run pipelines/sec_shares.py first; this pipeline still
works without it (it just falls back to yfinance-only history).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yfinance as yf

from common import DATA_ROOT, write_timeseries


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


# Tickers where the SEC share-count is NOT the right multiplier for the
# yfinance close price, even when ample data exists. Common reasons:
#
#   * **ADRs with non-1:1 ratios.** TSM trades as a 5:1 ADR — each NYSE
#     "TSM" share is 5 Taiwanese ordinary shares. SEC reports ~26B
#     ordinary shares; the ADR market cap is (ordinary / 5) × ADR price.
#     We don't try to track the ADR ratio (it can change rarely but
#     does), so we skip SEC and use yfinance which natively reports
#     the ADR-equivalent share count.
#   * **Dual-class structures where dei tracks one class only.** When
#     this matters, it's usually caught by the MIN_SEC_OBS / staleness
#     gating below — but the canonical pin for the case lives here so
#     future maintainers can reason about it without re-deriving it.
#
# ASML is NOT here: its NASDAQ listing is 1:1 with the Amsterdam
# ordinary shares (not an ADR), so the SEC ordinary-share count is
# directly compatible with the NASDAQ price.
SEC_EXCLUDED_TICKERS: set[str] = {"TSM"}


def _load_sec_shares(symbol: str) -> pd.Series | None:
    """Load the SEC-derived shares-outstanding timeseries for ``symbol``
    written by pipelines/sec_shares.py. Returns a pd.Series indexed by
    pd.Timestamp (one observation per filing), or None when no JSON
    exists. The series is dense at filing dates only — caller is
    responsible for reindexing onto daily price dates via forward-fill."""
    sec_path = DATA_ROOT / "sec_shares" / f"{symbol.replace('-', '_')}_shares.json"
    if not sec_path.exists():
        return None
    try:
        payload = json.loads(sec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    points = payload.get("points")
    if not isinstance(points, list) or not points:
        return None
    series = pd.Series(
        {pd.Timestamp(p["t"]): float(p["v"]) for p in points if "t" in p and "v" in p},
    )
    series = series.sort_index()
    series.index = series.index.tz_localize(None).normalize()
    return series


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

    # SEC-derived shares: authoritative, generally extends history back
    # to 2009 (start of XBRL mandate). May be None for tickers without
    # SEC coverage (re-pull pipelines/sec_shares.py to populate). Indexed
    # by filing-end date, sparse cadence (quarterly for 10-Q filers,
    # annual for 20-F filers).
    sec_series = (
        _load_sec_shares(symbol) if symbol not in SEC_EXCLUDED_TICKERS else None
    )
    sec_daily: pd.Series | None = None
    sec_first_ts: pd.Timestamp | None = None
    if symbol in SEC_EXCLUDED_TICKERS:
        print(f"  (skipping SEC for {symbol}: in SEC_EXCLUDED_TICKERS)", flush=True)
    # Gating thresholds — we'd rather use yfinance than a misleading SEC
    # series. Cases this catches:
    #   * BRK-B: dei tag tracks Class A only (different scale) and
    #     stopped in 2011 — only 7 rows, last 15 years ago. Skip.
    #   * V, MA: handful of rows in 2009-2010 then SEC abandons the
    #     dei tag. Forward-filling those across modern dates gives a
    #     constant 2009 share count for 16 years — wrong.
    #   * Foreign-filer ADRs that fall off the tag for some period.
    # Annual filers (20-F like ASML / TSM) pass the min-obs bar with
    # plenty of headroom (17 / 9 rows).
    MIN_SEC_OBS = 8
    MAX_SEC_STALENESS_YEARS = 3
    if sec_series is not None and len(sec_series) >= MIN_SEC_OBS:
        last_ts = sec_series.index.max()
        now_ts = pd.Timestamp.utcnow().tz_localize(None)
        staleness_years = (now_ts - last_ts).days / 365.25
        if staleness_years <= MAX_SEC_STALENESS_YEARS:
            # Forward-fill SEC observations onto every trading day so we
            # can look up the as-of-filing share count for any close-date.
            # ffill is correct semantically — a filed count remains the
            # company's official outstanding figure until the next filing.
            sec_daily = sec_series.reindex(closes.index, method="ffill")
            sec_first_ts = sec_series.index.min()
        else:
            print(
                f"  (skipping SEC for {symbol}: last filing "
                f"{last_ts.date()} is {staleness_years:.1f}y stale)",
                flush=True,
            )
    elif sec_series is not None:
        print(
            f"  (skipping SEC for {symbol}: only {len(sec_series)} "
            f"observations, below MIN_SEC_OBS={MIN_SEC_OBS})",
            flush=True,
        )

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
            # Prefer SEC's filed share count when it's published for this
            # date (sec_first_ts onwards). Falls through to the yfinance
            # clean dict for the pre-SEC-coverage tail (some tickers'
            # listings predate the XBRL mandate; SEC has no opinion).
            shares_v: float | None = None
            if (
                sec_daily is not None
                and sec_first_ts is not None
                and ts >= sec_first_ts
            ):
                sec_v = sec_daily.get(ts)
                if sec_v is not None and not pd.isna(sec_v):
                    shares_v = float(sec_v)
            if shares_v is None:
                yf_v = clean.get(ts)
                if yf_v is not None and not pd.isna(yf_v):
                    shares_v = float(yf_v)
            if shares_v is None:
                continue
            mc = float(close_v) * shares_v
            if mc <= 0:
                continue
            # Store in billions of USD so values combine sanely with the
            # FRED macro series (already billions-denominated). Raw
            # market-cap magnitudes (~10^11-10^13) blew up combineTwo
            # divides by 10^9; rescaling here is the cheapest fix.
            points.append({"t": ts.strftime("%Y-%m-%d"), "v": mc / 1e9})
    elif sec_daily is not None and sec_first_ts is not None:
        # No yfinance shares at all (uncommon) — SEC alone carries the
        # series from its first filing forward.
        for ts, close_v in closes.items():
            if ts < sec_first_ts:
                continue
            sec_v = sec_daily.get(ts)
            if sec_v is None or pd.isna(sec_v):
                continue
            mc = float(close_v) * float(sec_v)
            if mc <= 0:
                continue
            points.append({"t": ts.strftime("%Y-%m-%d"), "v": mc / 1e9})
    else:
        # Fallback: use current shares count × historical prices (approximation)
        current_shares = ticker.info.get("sharesOutstanding")
        if not current_shares:
            return []
        for ts, close_v in closes.items():
            mc = float(close_v) * float(current_shares)
            points.append({"t": ts.strftime("%Y-%m-%d"), "v": mc / 1e9})
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
        # v is already stored in billions of USD (see comment in
        # fetch_marketcap where mc / 1e9 is applied) — print directly.
        print(
            f"  {len(points):>6} points, {points[0]['t']}=${first_v:.1f}B -> "
            f"{points[-1]['t']}=${last_v:.1f}B  [{out}]"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
