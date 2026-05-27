# Yahoo Finance data — compliance audit

## TL;DR

| Data category | Underlying owner | Status | Action |
| --- | --- | --- | --- |
| Individual equity prices (yahoo_marketcap/*) | NYSE / NASDAQ for the print, exchange listings each company chose | Gray zone | KEEP for now, with clear attribution. Document the gray area. |
| Commodity futures curves (WTI, Brent, natgas, ag) | CME Group + ICE Futures (NYMEX, CBOT, etc.) | Gray zone | KEEP for now, with clear attribution. Historical EOD futures data is widely redistributed in practice. |
| VIX futures curve (yahoo_futures/vix_curve) | Cboe Futures Exchange / Cboe Global Markets | **Requires licensor agreement** | REMOVE — same class as the FRED VIX series we already removed. |
| **VIX index (proposed addition)** | Cboe Global Markets | **Requires licensor agreement** | DO NOT ADD — Cboe ToS requires written consent to redistribute. |
| **SPY (proposed addition)** | NYSE Arca for price + S&P Dow Jones Indices for the underlying index | **Requires multiple licensor agreements** | DO NOT ADD — needs NYSE Arca redistribution license AND S&P index license. |

Bottom line: VIX and SPY are not bringable in within compliance constraints. The Yahoo data we already carry is in a gray zone Yahoo doesn't generally enforce against non-commercial research; we keep it for now with attribution but should expect to revisit if the product moves materially commercial.

---

## What Yahoo's terms actually say

Yahoo's [Developer API Terms of Use](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html) and general site terms:

- Yahoo retired its public market-data API in 2017. The `yfinance` Python library that powers `pipelines/yahoo_marketcap.py` and `pipelines/yahoo_futures.py` calls Yahoo's internal endpoints — technically against ToS, widely tolerated in practice for non-commercial research.
- Yahoo's ToS prohibits "copying or republishing" content without permission. Strict reading: every chart we render from Yahoo data violates this.
- Enforcement has been near-zero for personal / research / open-source projects. The `yfinance` library has ~14k GitHub stars without Yahoo issuing takedowns.
- Commercial productization that redistributes scraped data carries higher exposure.

Tape's commercial posture: there's an "Ask about enterprise" CTA but no paid traffic yet. We're closer to "personal research / open-source" than "commercial product" in 2026.

## What the underlying exchanges say

The data Yahoo redistributes is owned by exchanges and index providers, each with their own terms.

### Equity prices (NYSE / NASDAQ / other exchanges)

- **Real-time prices** require an exchange data agreement (NYSE / NASDAQ market data fees, typically $$$/month per professional user).
- **End-of-day historical prices** are more freely available — most major financial sites republish them. Strict redistribution rights still belong to the exchanges, but enforcement against EOD historical display is essentially nonexistent.
- **Our use**: daily closing prices from yfinance, used to compute historical market cap by multiplying against SEC EDGAR share counts. The share counts are public-domain federal data; the prices are the gray-area component.

### Commodity futures (CME Group / ICE Futures)

- WTI, Brent, natgas, ag, livestock futures: settlement prices come from the CME and ICE exchanges.
- CME publishes EOD settlement prices freely on its website with citation; commercial redistribution requires a license.
- ICE has similar terms.
- Our curves are constructed from EOD settlement prints across the futures chain. Same class as exchange-EOD-historical — widely redistributed in practice, technically licensable.

### VIX (Cboe Global Markets) — the explicit no

[Cboe's terms](https://www.cboe.com/terms) state: *"copying, reproducing, or distributing Materials without prior written consent"* is prohibited. The free historical VIX CSV at `cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv` is "for convenience of site visitors" — not for redistribution.

This applies to:
- The VIX index level itself.
- VIX futures curve (CFE-traded, Cboe-owned).
- Any derived product that requires the VIX name or methodology.

To bring VIX in we would need a Cboe data license. That's a real business agreement, not a checkbox.

### S&P 500 / SPY (S&P Dow Jones Indices + NYSE Arca)

SPY is the SPDR S&P 500 ETF Trust. Displaying its price involves two separate licensors:

1. **S&P Dow Jones Indices LLC** owns the S&P 500 methodology + the brand. They license to ETF issuers. Displaying anything labelled "S&P 500" requires S&P permission.
2. **NYSE Arca** is the exchange where SPY trades. Even displaying SPY EOD prices implicates NYSE market-data terms.

Both are paid licenses. SPY specifically has been the subject of past litigation against unlicensed redistribution.

## VIX-equivalent + SPY-equivalent — public-domain substitutes

If the use case is "show a market-stress signal" rather than VIX specifically:

- **St. Louis Fed Financial Stress Index (STLFSI4)** — already in our library. Federal Reserve's own composite stress measure. Public domain via FRED.
- **Realized Treasury-yield volatility** — derivable from the FRED Treasury data we already carry. Compute rolling-window stddev of daily yield changes. Not the same instrument as VIX (no implied-vol forward-looking premium) but moves with it.
- **HY-spread proxy** — we don't carry ICE BofA spreads (removed for the same reason as VIX), but anyone needing a credit-stress read can use the STLFSI4 components.

If the use case is "show a broad equity index" rather than SPY:

- We currently have **no public-domain US equity index** in our library. NASDAQ, S&P 500, Russell, Wilshire are all licensable.
- **Closest substitute**: aggregate market cap of the largest US listed companies (which we have via the yahoo_marketcap pipeline, with SEC EDGAR share counts + Yahoo prices). Not exactly an index but moves with the equity market.
- **Cleaner non-Yahoo substitute would require a paid data feed.** Worth considering if you ever want a real equity-market signal.

## Recommended action for the existing Yahoo data

Three options, ranked by how strict you want to be:

1. **Status quo with disclaimer.** Keep yahoo_marketcap + yahoo_futures (excluding vix_curve), add a clear note on each yahoo-pipeline source page that the data is sourced from public-internet endpoints with redistribution permitted only for the non-commercial portion of the site. **My recommendation** given Keller's "compliance matters, don't manufacture red tape" stance.

2. **Remove the VIX-futures curve only.** vix_curve is in the same legal class as the FRED VIX we already removed. The rest of the futures data is on solid-enough ground. Simplest cleanup move.

3. **Migrate to licensed data.** Pay a real data vendor (Polygon, Tiingo, Quandl/NASDAQ Data Link, etc.) for tick / EOD redistribution rights. Real cost: ~$50–500/month depending on scope. Right move if the product goes seriously commercial.

I'd ship (1) + (2) — keep the equity / commodity data with clear attribution, drop vix_curve since it's the one item that's clearly Cboe-licensed.

## Why I'm not just removing all Yahoo data

It would be consistent with the FRED-third-party stance, but the symmetry breaks because:

- FRED's third-party series (S&P, CBOE, etc.) are **explicitly tagged** by the data provider as requiring pre-approval. The compliance violation is unambiguous.
- Yahoo's individual equity prices and EOD futures are a **gray zone** with ~25 years of universally-tolerated industry practice. Removing them is the legal-maximalist position, not the practical-compliance one.
- Keller's stated stance: *"compliance is a priority, but I don't want to be endlessly bogged down in red tape over laws that nobody complies with."* The sailboat-at-dock framing applies here in a way it didn't to the FRED case.

If the product hits commercial scale and Yahoo (or NYSE) starts noticing, that's the trigger to migrate to licensed feeds. Until then, keeping the current Yahoo pipeline with clear attribution is defensible.

---

## Sources

- [Yahoo Developer API Terms of Use](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html)
- [Cboe Terms of Use](https://www.cboe.com/terms)
- [Cboe Market Data Policies (PDF)](https://cdn.cboe.com/resources/membership/Market_Data_Policies.pdf)
- [yfinance library (GitHub)](https://github.com/ranaroussi/yfinance)
- [Promptcloud: Enterprise Yahoo Finance scraping considerations (2026)](https://www.promptcloud.com/blog/scrape-yahoo-finance/)
