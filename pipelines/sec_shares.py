"""
Historical shares-outstanding per ticker, sourced from SEC EDGAR's free
XBRL CompanyFacts API.

Background — why this exists:
    Our market-cap series (yahoo_marketcap.py) needs shares-outstanding
    history to compute mc(t) = close(t) × shares(t). yfinance's
    `get_shares_full()` only returns data back to roughly 2017 (it's
    scraped from Yahoo's front-end timeline). For tickers whose listing
    history runs longer than that, the marketcap series gets truncated
    at the share-count start — there's no way to extend the marketcap
    history with the data Yahoo provides.

    SEC EDGAR publishes XBRL-tagged financial data for every public
    filer going back to ~2009 (when XBRL became mandatory for large
    filers; smaller filers phased in through 2014). The
    `EntityCommonStockSharesOutstanding` fact (in the "dei" taxonomy)
    is reported on the cover page of every 10-K / 10-Q (US filers) or
    20-F (foreign filers like ASML / TSM). It's the canonical "as of
    the filing date" share count.

    This pipeline pulls that fact for our universe of marketcap
    tickers and writes one JSON file per ticker. yahoo_marketcap.py
    reads those files as the authoritative source for shares-
    outstanding history, falling back to yfinance only when SEC
    coverage is sparse (foreign filers with fewer XBRL tags, special
    share classes like BRK-B where the parent's dei tag tracks
    Class A only, etc.).

Coverage notes:
    * Large US filers: data back to ~2009, quarterly cadence.
    * Foreign filers (20-F): annual cadence, generally 2009+ (TSM,
      ASML both confirmed).
    * BRK-B specifically: SEC tags Class A only via the dei concept
      and stopped tagging it after ~2011. yahoo_marketcap.py keeps
      yfinance as the primary for BRK-B.

Endpoint + rate limits:
    https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
    Free, no auth. SEC requests a descriptive User-Agent identifying
    the requester. Rate limit is documented as 10 req/sec — our 36
    tickers are well within budget.

Cache:
    Through common.cached_get with a 14-day TTL. Filings drop
    quarterly so a 2-week cache trades local-iteration speed for at
    most a 2-week stale lag on the most recent quarter's number.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from common import cached_get, write_timeseries


# Hand-curated map from yfinance-style ticker to SEC CIK. Verified
# against SEC's company_tickers.json at build time of this pipeline.
#
# Maintenance: when adding a new ticker to yahoo_marketcap.SPECS, look
# the CIK up at https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<ticker>
# (or in https://www.sec.gov/files/company_tickers.json) and add it here.
# Missing tickers fall through to a yfinance-only path in
# yahoo_marketcap.py — not fatal, just less history.
TICKER_TO_CIK: dict[str, int] = {
    # Tech mega-caps
    "AAPL": 320193,
    "MSFT": 789019,
    "GOOG": 1652044,
    "AMZN": 1018724,
    "META": 1326801,
    "NVDA": 1045810,
    # Financials
    "BRK-B": 1067983,  # CIK exists but dei tags only Class A and stopped in 2011 — see header
    "JPM": 19617,
    "BAC": 70858,
    "GS": 886982,
    "V": 1403161,
    "MA": 1141391,
    # Healthcare
    "JNJ": 200406,
    "UNH": 731766,
    "LLY": 59478,
    "PFE": 78003,
    # Energy
    "XOM": 34088,
    "CVX": 93410,
    # Consumer
    "KO": 21344,
    "PEP": 77476,
    "WMT": 104169,
    "COST": 909832,
    "HD": 354950,
    "MCD": 63908,
    "DIS": 1744489,
    # Industrial / auto
    "BA": 12927,
    "CAT": 18230,
    "GE": 40545,
    "TSLA": 1318605,
    # Tech / media (tier 2)
    "NFLX": 1065280,
    "ASML": 937966,  # 20-F filer, annual cadence
    "TSM": 1046179,  # 20-F filer, annual cadence; first XBRL filing 2017
    "AVGO": 1730168,
    "ORCL": 1341439,
    "CRM": 1108524,
    "CSCO": 858877,
}


# SEC asks API consumers to include a contact-bearing User-Agent so
# they can reach out if a script misbehaves. Static identifier here;
# never includes per-request secrets.
USER_AGENT = "Tape (financial dashboards) keller.scholl@gmail.com"


def _select_best_per_end(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """SEC sometimes carries multiple rows for the same `end` date when an
    amended filing (10-Q/A, 10-K/A, 20-F/A) restates the value. Pick the
    most-recently-FILED row per end date so we use the authoritative
    restated number."""
    by_end: dict[str, dict[str, Any]] = {}
    for r in rows:
        end = r.get("end")
        filed = r.get("filed", "")
        if not isinstance(end, str):
            continue
        prior = by_end.get(end)
        if prior is None or filed > prior.get("filed", ""):
            by_end[end] = r
    return [by_end[k] for k in sorted(by_end)]


def fetch_sec_shares(cik: int) -> list[dict[str, Any]]:
    """Return a chronologically-sorted list of {t, v} points for the
    given CIK's shares-outstanding history. Empty list if the company
    doesn't tag the dei concept (small, very old, or non-XBRL filer)."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    body = cached_get(
        url,
        ttl_seconds=14 * 24 * 3600,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    data = json.loads(body)
    dei = data.get("facts", {}).get("dei", {})
    fact = dei.get("EntityCommonStockSharesOutstanding")
    if not fact:
        return []
    units = fact.get("units", {})
    # SEC may report under multiple unit codes for the same concept
    # (e.g. "shares" + "USD/shares"). We want the share-count unit.
    rows = units.get("shares") or []
    if not rows:
        return []
    best = _select_best_per_end(rows)
    return [{"t": r["end"], "v": int(r["val"])} for r in best if "val" in r]


def main(argv: list[str] | None = None) -> int:
    wanted = set((argv or [])[1:])
    items = [
        (t, c) for t, c in TICKER_TO_CIK.items()
        if not wanted or t in wanted
    ]
    if not items:
        print(f"No tickers matched {wanted}")
        return 2

    errors = 0
    for ticker, cik in items:
        print(f"SEC: {ticker} (CIK {cik:>10})...", flush=True)
        try:
            points = fetch_sec_shares(cik)
        except Exception as e:
            print(f"  ERROR: {e}")
            errors += 1
            continue
        if not points:
            print("  (no XBRL coverage)")
            # Not an error — some tickers genuinely have no SEC coverage
            # (foreign filers with sparse tagging, etc.). yahoo_marketcap
            # falls back to yfinance for these cases.
            continue
        # Save under sec_shares/<TICKER>_shares.json. shares-as-of-date,
        # raw count (not in billions — counts stay raw per the canonical-
        # base invariant in CLAUDE.md).
        out = write_timeseries(
            pipeline="sec_shares",
            series_id=f"{ticker.replace('-', '_')}_shares",
            name=f"{ticker} shares outstanding (SEC)",
            points=points,
            unit="shares",
        )
        first = points[0]
        last = points[-1]
        print(
            f"  {len(points):>4} obs, {first['t']}={first['v']:,} -> "
            f"{last['t']}={last['v']:,}  [{out.relative_to(out.parents[2])}]"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
