# Yahoo Finance data — compliance audit

## TL;DR

The right line: **scraping from Yahoo's gray zone is OK by our stance; pulling directly from a licensor's own publication is not.** Yahoo's terms bind anyone scraping yfinance — and Yahoo's terms treat all their data uniformly (gray-zone, near-universally-tolerated non-commercial research). The underlying licensor (Cboe, S&P, NYSE, CME, ICE) matters for enforcement-risk calibration but doesn't change the legal-class because the chain of custody runs Licensor → Yahoo → us, not Licensor → us.

| Data category | Underlying owner | Yahoo gray zone? | Action |
| --- | --- | --- | --- |
| Individual equity prices (yahoo_marketcap/*) | NYSE / NASDAQ | Yes — low enforcement risk historically | KEEP with attribution. |
| Commodity futures curves (WTI, Brent, natgas, ag) | CME Group + ICE Futures | Yes — EOD historical is widely tolerated | KEEP with attribution. |
| VIX-futures curve (yahoo_futures/vix_curve) | Cboe Futures Exchange | Yes — but elevated enforcement risk (Cboe actively licenses VIX). Same chain-of-custody as the rest of Yahoo. | KEEP with attribution + the "elevated risk" note. |
| **VIX index direct from cdn.cboe.com** | Cboe Global Markets | Not via Yahoo — direct from licensor. **Cboe explicitly forbids redistribution.** | DO NOT ADD. |
| **SPY price direct from NYSE Arca or licensed vendor** | NYSE Arca + S&P Dow Jones Indices | Not via Yahoo — direct from licensor. Multiple paid licenses required. | DO NOT ADD. |
| **SPY price via Yahoo (if it were added)** | Same underlying, but chain runs Licensor → Yahoo → us | Yes — same gray zone as XOM-via-Yahoo | Could in principle be added with the same gray-zone framing, but Bloomberg-style equity-index redistribution carries higher enforcement risk than individual-equity EOD; the value-add over our existing yahoo_marketcap basket is small. Skipping for now. |

Bottom line: the Yahoo gray-zone position applies consistently across everything we get via yfinance. The FRED VIX was a different case because the chain of custody was Cboe → FRED → us, and FRED's authoritative tag system flagged it `copyrighted: pre-approval required` — explicit licensor instruction. Yahoo doesn't tag individual series that way; Yahoo's ToS is a flat blanket.

## Previously-incorrect framing (corrected 2026-05-28)

An earlier version of this doc said the VIX-futures curve had to be removed as "same class as the FRED VIX" — that conflated two different chains of custody. The FRED VIX failed because FRED itself told us (via the `cc: copyrighted: pre-approval required` tag) that the licensor required pre-approval. The Yahoo VIX-futures don't carry such a flag because Yahoo doesn't have that taxonomy; everything Yahoo serves is uniformly in the gray zone Yahoo doesn't enforce against. Removing the VIX curve while keeping AAPL was inconsistent. Restored.

The honest precise statement: **VIX-futures-via-Yahoo carries higher enforcement risk than AAPL-via-Yahoo because Cboe is a more aggressive licensor than NYSE. But the legal class — Yahoo gray-zone scraping for non-commercial research — is the same.** If Cboe ever specifically nots the Yahoo VIX surface, we revisit. Until then, consistency.

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

**Status quo with attribution.** Keep yahoo_marketcap + yahoo_futures (including vix_curve), with a clear note on each yahoo-pipeline source page that the data is sourced from public-internet endpoints under the gray-zone non-commercial-research norm. Consistent with Keller's "compliance matters, don't manufacture red tape" stance.

### Why not "migrate to a licensed data vendor"

Naive advice. The paid feeds (Polygon, Tiingo, Quandl/NASDAQ Data Link, IEX Cloud, etc.) almost universally restrict redistribution at the consumer/developer tier:

- **Polygon** consumer plans are "for internal use" — public display + redistribution is the enterprise tier ($$$).
- **Tiingo** lets you use the data for personal analysis but explicitly prohibits redistribution at the free + starter tiers.
- **IEX Cloud** ($$$ enterprise tier required for any public-facing redistribution).
- **NASDAQ Data Link** terms vary by feed; many of the interesting ones are pre-approval-required.

So paying $50–500/month doesn't actually solve "can I show this data on a public website" — it just changes the licensor. The tier that DOES permit redistribution is institutional pricing ($$$$/year) and typically also restricts to "your end users" not "the open internet". Real-world: Tape's options for public redistribution of US equity / volatility data are either (a) stay in the Yahoo gray zone, or (b) negotiate directly with the exchange / index licensor (Cboe, S&P, NYSE), which is a real business agreement, not a SaaS subscription.

This is roughly the same trap that caught FRED's third-party series: the "you can pay to license this" path exists but costs serious money + isn't unlocked by hobbyist-tier subscriptions.

## Takedown-response posture

The gray-zone position is defensible because it's paired with a fast, no-questions takedown response. Keller's stated operating principle:

> A reasonably likely outcome is that I'm asked to stop, and if asked to stop I will, and I think people have to be active assholes to do more than that if I'm appropriately polite and responsive after doing something that was in a grey zone.

Operationally, this means:

- The `/terms/` page has a "Data takedown / removal requests" section pointing at `keller.scholl@gmail.com` with a one-business-week target.
- A data provider who asks us to remove their series gets the data removed within that window. No demand for justification, no attempt to negotiate, no requirement that they invoke counsel — a polite email is enough.
- The same applies to attribution / citation corrections.

This posture is what distinguishes the Yahoo gray-zone position from "ask forgiveness not permission as a tactic." It's good-faith use that respects the data provider's right to say no, with friction-free compliance when they exercise it. If Cboe ever specifically tells us to stop showing VIX-from-Yahoo, we stop. Until that happens, the position is consistent across all our Yahoo data.

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
