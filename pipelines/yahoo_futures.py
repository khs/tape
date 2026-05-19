"""
Forward-curve pipeline for the three major energy commodity futures on
Yahoo — WTI crude (NYMEX), Brent crude (Yahoo treats as NYMEX-listed
even though it trades on ICE), and Henry Hub natural gas (NYMEX).

What this captures that ``yahoo_quotes.py`` doesn't
---------------------------------------------------
``yahoo_quotes.py`` records the FRONT-MONTH daily close — one number
per day, the price of the nearest contract about to expire. That's
already enough to see today's spot oil and how it's moved historically.

What it misses is the SHAPE of the futures curve: at any given moment
the market also quotes prices for contracts expiring in each month for
the next ~12-18 months. Those quotes are the market's collective
forecast of where prices are headed. A flat curve says "the market
expects today's price to hold." An upward-sloping (contango) curve
implies expected appreciation; a downward-sloping (backwardation) one
implies expected depreciation. Either way the curve is the cleanest
public price-forecast available for these commodities.

We pull it as Forecast-UI projections on top of the historical spot:
  ``points``      = monthly-averaged spot history (last ~10 years)
  ``projections`` = a map keyed by SNAPSHOT date; each value is the full
                    contract curve at that snapshot, with each contract's
                    mid-month delivery date as ``t`` and its closing
                    price as ``v``.

The renderer picks the latest snapshot's curve and draws it as a dashed
extension to the right of the historical line — see Phase 2 of the
Forecast UI in ``docs/data-source-roadmap.md``.

Snapshots are accumulated across runs: each refresh stamps a new
date-keyed vintage and preserves prior ones (capped to a rolling
~90-day window so the file doesn't grow forever). Future Phase-3
work will surface an "as of" picker that lets a reader rewind the
curve to what it looked like a week or a month ago.

Output structure
----------------
One source per commodity, written to
``public/data/yahoo_futures/<id>.json``:

  - ``wti_curve``     — WTI crude (USD per barrel)
  - ``brent_curve``   — Brent crude (USD per barrel)
  - ``natgas_curve``  — Henry Hub natural gas (USD per MMBtu)

Run with
--------
  python pipelines/yahoo_futures.py             # all three
  python pipelines/yahoo_futures.py wti_curve   # just WTI
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from common import write_timeseries

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "public" / "data"

# CME / NYMEX / ICE monthly contracts encode the delivery month as a
# single letter. Listed alphabetically these aren't in calendar order —
# the canonical mapping below is what Yahoo / ticker symbols use.
MONTH_CODES = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]
# month_idx_1based -> code: MONTH_CODES[month - 1]


@dataclass
class FuturesSpec:
    series_id: str
    name: str
    description: str
    # Front-month spot symbol on Yahoo (e.g. "CL=F"). Used for the
    # ``points`` historical-spot series.
    spot_symbol: str
    # Contract-symbol pattern. Yahoo strings these together as
    # ``<prefix><month-code><yy>.<exchange-suffix>`` — e.g. CLN26.NYM
    # for July 2026 WTI. The suffix is .NYM for all three commodities
    # we cover; we keep it as a field so a future commodity on a
    # different Yahoo exchange (e.g. KC=F coffee on ICE = .NYB) can
    # be added without touching the curve-fetch code.
    contract_prefix: str
    contract_suffix: str
    unit: str
    # How many monthly contracts to attempt to fetch. WTI + Brent
    # publish liquid quotes ~24 months out; gas peters out around 12.
    horizon_months: int


SPECS: list[FuturesSpec] = [
    FuturesSpec(
        series_id="wti_curve",
        name="WTI crude oil — spot history + futures curve",
        description=(
            "WTI (West Texas Intermediate) crude. Solid line is the "
            "monthly-averaged spot front-month; dashed extension is "
            "the current NYMEX forward curve (each contract's last "
            "close plotted at its delivery month)."
        ),
        spot_symbol="CL=F",
        contract_prefix="CL",
        contract_suffix=".NYM",
        unit="USD/bbl",
        horizon_months=18,
    ),
    FuturesSpec(
        series_id="brent_curve",
        name="Brent crude oil — spot history + futures curve",
        description=(
            "Brent crude (North Sea). Global oil benchmark — about "
            "two-thirds of the world's traded crude prices off Brent. "
            "Solid line is monthly-averaged spot; dashed extension is "
            "the current forward curve."
        ),
        spot_symbol="BZ=F",
        contract_prefix="BZ",
        contract_suffix=".NYM",
        unit="USD/bbl",
        horizon_months=18,
    ),
    FuturesSpec(
        series_id="natgas_curve",
        name="Henry Hub natural gas — spot history + futures curve",
        description=(
            "Henry Hub natural gas (Louisiana hub). The reference price "
            "for US natural gas wholesale markets. Solid line is "
            "monthly-averaged spot; dashed extension is the current "
            "NYMEX forward curve."
        ),
        spot_symbol="NG=F",
        contract_prefix="NG",
        contract_suffix=".NYM",
        unit="USD/MMBtu",
        horizon_months=15,
    ),
]


# Cap on how many vintage snapshots we keep per commodity. ~90 daily
# snapshots ≈ 3 months of curve history — enough to let a future
# "as of" picker show "where did the market expect summer prices to
# be back in March?" without ballooning the JSON.
MAX_VINTAGES = 90


def fetch_spot_monthly(symbol: str, lookback_years: int = 10) -> list[dict]:
    """
    Pull historical daily front-month closes and resample to monthly
    averages. Monthly resolution keeps the JSON small (~120 points
    over 10 years) and matches the resolution of the forward curve
    (which is also monthly), so the solid+dashed segments read at the
    same visual rhythm.
    """
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=f"{lookback_years}y", auto_adjust=False)
    if hist.empty or "Close" not in hist.columns:
        return []
    closes = hist["Close"].dropna()
    # Strip tz so resample keys are naive dates.
    closes.index = closes.index.tz_localize(None)
    monthly = closes.resample("ME").mean()
    out: list[dict] = []
    for ts, v in monthly.items():
        if pd.isna(v):
            continue
        out.append({"t": ts.strftime("%Y-%m-%d"), "v": round(float(v), 3)})
    return out


def fetch_forward_curve(
    prefix: str,
    suffix: str,
    horizon: int,
) -> list[dict]:
    """
    Pull the latest close for each of the next ``horizon`` monthly
    contracts. Each contract symbol is constructed from prefix +
    month-code + 2-digit year + suffix (e.g. ``CLN26.NYM``).

    Contracts that return no data — illiquid back-months, expired
    fronts mid-month, or symbols Yahoo simply doesn't carry — are
    skipped. We attempt all ``horizon`` months regardless; some
    commodities (gas) lose liquidity past month 12 and the resulting
    curve naturally truncates.
    """
    today = datetime.now(timezone.utc)
    out: list[dict] = []
    # Start at next calendar month — the current month's contract may
    # already be in delivery (front-month rolls before month-end), so
    # its quote often disappears or behaves oddly. The user wants a
    # forward-looking view; skipping the current month is the cleaner
    # default.
    for k in range(1, horizon + 1):
        target_month = today.month + k
        target_year = today.year + (target_month - 1) // 12
        target_month = (target_month - 1) % 12 + 1
        code = MONTH_CODES[target_month - 1]
        yy = target_year % 100
        sym = f"{prefix}{code}{yy:02d}{suffix}"
        try:
            t = yf.Ticker(sym)
            df = t.history(period="5d", auto_adjust=False)
            if df.empty or "Close" not in df.columns:
                continue
            tail = df["Close"].dropna()
            if tail.empty:
                continue
            last_close = float(tail.iloc[-1])
        except Exception as e:
            # yfinance throws a variety of HTTP / parse errors on
            # missing symbols. Treat all as "no curve point here" so
            # one illiquid back-month doesn't break the whole pull.
            print(f"  skip {sym}: {e}", file=sys.stderr)
            continue
        # Anchor each contract's delivery to mid-month — settlement
        # actually happens around the 25th of the prior month for most
        # of these, but mid-month makes the curve render at the same
        # cadence as the monthly-averaged spot history.
        expiry_anchor = datetime(target_year, target_month, 15).strftime("%Y-%m-%d")
        out.append({"t": expiry_anchor, "v": round(last_close, 3)})
    return out


def load_existing_projections(pipeline: str, series_id: str) -> dict[str, list[dict]]:
    """
    Read the existing JSON's ``projections`` field if the file exists.
    Used so each run accumulates vintages rather than overwriting them.
    """
    p = DATA_ROOT / pipeline / f"{series_id}.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  could not read prior projections for {series_id}: {e}", file=sys.stderr)
        return {}
    existing = data.get("projections")
    if not isinstance(existing, dict):
        return {}
    # Defensive: drop entries that aren't lists. A malformed prior
    # write shouldn't poison this run.
    return {
        k: v for k, v in existing.items()
        if isinstance(v, list) and all(isinstance(p, dict) for p in v)
    }


def prune_old_vintages(projections: dict[str, list[dict]], cap: int) -> dict[str, list[dict]]:
    """Keep the most recent ``cap`` vintage snapshots, drop the rest."""
    if len(projections) <= cap:
        return projections
    sorted_keys = sorted(projections.keys(), reverse=True)
    return {k: projections[k] for k in sorted_keys[:cap]}


def main(argv: list[str] | None = None) -> int:
    wanted = set((argv or [])[1:])
    runs = [s for s in SPECS if not wanted or s.series_id in wanted]
    if not runs:
        print(
            f"No matches for {wanted}; available: "
            f"{[s.series_id for s in SPECS]}",
            file=sys.stderr,
        )
        return 2

    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    errors = 0
    for spec in runs:
        print(f"Fetching {spec.series_id} ({spec.spot_symbol})...", flush=True)
        try:
            spot = fetch_spot_monthly(spec.spot_symbol)
        except Exception as e:
            print(f"  spot fetch failed: {e}", file=sys.stderr)
            errors += 1
            continue
        if not spot:
            print("  spot fetch returned empty; skipping curve")
            errors += 1
            continue
        try:
            curve = fetch_forward_curve(
                spec.contract_prefix,
                spec.contract_suffix,
                spec.horizon_months,
            )
        except Exception as e:
            print(f"  curve fetch failed: {e}", file=sys.stderr)
            curve = []

        projections = load_existing_projections("yahoo_futures", spec.series_id)
        if curve:
            projections[today_iso] = curve
            projections = prune_old_vintages(projections, MAX_VINTAGES)

        out = write_timeseries(
            pipeline="yahoo_futures",
            series_id=spec.series_id,
            name=spec.name,
            points=spot,
            unit=spec.unit,
            projections=projections if projections else None,
        )
        spot_range = f"${spot[0]['v']:.2f} -> ${spot[-1]['v']:.2f}"
        curve_summary = (
            f"{len(curve)} forward points ({curve[0]['t']} -> {curve[-1]['t']})"
            if curve else "no forward curve fetched"
        )
        print(
            f"  {len(spot)} monthly spot ({spot_range}); "
            f"{curve_summary}; "
            f"{len(projections)} vintage(s) on disk -> {out}",
            flush=True,
        )

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
