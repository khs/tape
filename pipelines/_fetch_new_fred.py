"""One-off fetcher for the 12 FRED series added in the v4 expansion.

Mirrors the manual flow we used for DFII5, applied to a batch. Fetches
each series via the public fredgraph.csv endpoint, writes the data + a
matching source YAML.

Run with: ``python pipelines/_fetch_new_fred.py``
Idempotent (overwrites data files; skips YAMLs that already exist).
"""
from pathlib import Path

import fred_series
import build_summaries


NEW_SPECS = [
    {
        "fred_id": "DRTSCILM",
        "slug": "sloos_ci_loans_tightening",
        "name": "SLOOS - banks tightening C and I loan standards (large/medium firms)",
        "shortName": "SLOOS C and I tightening",
        "description": (
            "Senior Loan Officer Opinion Survey, share of banks reporting "
            "tightened lending standards on commercial and industrial loans "
            "to large and medium firms (net of those easing). Quarterly. "
            "Positive readings mean banks pulling back on credit; negative "
            "means easier money flowing to businesses. The Fed watches "
            "this as a forward financial-conditions input distinct from "
            "market-based stress indices."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y"]',
        "unit": "%",
        "fmt": {"style": "percent", "decimals": 1},
        "tags": ["macro", "rates", "us"],
        "unitClass": "rate",
    },
    {
        "fred_id": "DRTSCLCC",
        "slug": "sloos_cc_tightening",
        "name": "SLOOS - banks tightening credit-card standards",
        "shortName": "SLOOS card tightening",
        "description": (
            "Senior Loan Officer Opinion Survey, share of banks reporting "
            "tightened standards on consumer credit-card loans (net of "
            "those easing). Quarterly. Read alongside the business-loan "
            "SLOOS to see whether tightening is hitting households, firms, "
            "or both."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y"]',
        "unit": "%",
        "fmt": {"style": "percent", "decimals": 1},
        "tags": ["macro", "rates", "us"],
        "unitClass": "rate",
    },
    {
        "fred_id": "CPIUFDSL",
        "slug": "cpi_food",
        "name": "CPI - Food",
        "shortName": "CPI food",
        "description": (
            "Consumer Price Index for food, all urban consumers, "
            "seasonally adjusted. Monthly. Distinct from headline CPI in "
            "that food prices swing on commodity cycles and agricultural "
            "shocks rather than persistent labor-market dynamics."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y", "50y"]',
        "unit": "index (1982-84=100)",
        "fmt": {"style": "index", "decimals": 1},
        "tags": ["macro", "us"],
        "unitClass": "index",
    },
    {
        "fred_id": "CPIENGSL",
        "slug": "cpi_energy",
        "name": "CPI - Energy",
        "shortName": "CPI energy",
        "description": (
            "Consumer Price Index for energy goods and services (motor "
            "fuel, fuel oil, gas and electric), all urban consumers, "
            "seasonally adjusted. Monthly. The most volatile component "
            "of headline CPI - moves on crude prices, refinery dynamics, "
            "weather."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y", "50y"]',
        "unit": "index (1982-84=100)",
        "fmt": {"style": "index", "decimals": 1},
        "tags": ["macro", "us", "commodities"],
        "unitClass": "index",
    },
    {
        "fred_id": "CPIMEDSL",
        "slug": "cpi_medical",
        "name": "CPI - Medical care",
        "shortName": "CPI medical",
        "description": (
            "Consumer Price Index for medical care (services and "
            "commodities), all urban consumers, seasonally adjusted. "
            "Monthly. Different secular trend from any other CPI "
            "component - rises faster than headline almost every year "
            "and is central to healthcare-cost debates."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y", "50y"]',
        "unit": "index (1982-84=100)",
        "fmt": {"style": "index", "decimals": 1},
        "tags": ["macro", "us"],
        "unitClass": "index",
    },
    {
        "fred_id": "GDPDEF",
        "slug": "gdp_deflator",
        "name": "GDP price deflator",
        "shortName": "GDP deflator",
        "description": (
            "GDP price deflator from the BEA's national accounts. "
            "Quarterly. The broadest measure of US economy-wide "
            "inflation, distinct from CPI (consumer basket) or PCE "
            "(consumer spending weights). Reads slightly differently "
            "because it covers everything produced, including "
            "investment goods and government services."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y", "50y"]',
        "unit": "index (2017=100)",
        "fmt": {"style": "index", "decimals": 2},
        "tags": ["macro", "us"],
        "unitClass": "index",
    },
    # NOTE: ANXIOUS (Philly Fed SPF recession probability) isn't on FRED.
    # The Philly Fed publishes it on their own site as a CSV. A follow-up
    # pipeline could pull from there directly; not included in this batch.
    {
        "fred_id": "RECPROUSM156N",
        "slug": "recession_probability_ny_fed",
        "name": "Recession probability - NY Fed yield-curve model",
        "shortName": "NY Fed recession prob",
        "description": (
            "Smoothed recession probability for the US derived from the "
            "10Y minus 3M Treasury spread by the New York Fed. Monthly. "
            "Distinct from the NBER binary indicator and the Anxious "
            "Index - this one is purely model-driven from a market "
            "signal, with no judgment input."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y"]',
        "unit": "%",
        "fmt": {"style": "percent", "decimals": 1},
        "tags": ["macro", "rates", "us"],
        "unitClass": "rate",
    },
    {
        "fred_id": "STLFSI4",
        "slug": "stlfsi",
        "name": "St. Louis Fed Financial Stress Index",
        "shortName": "STLFSI",
        "description": (
            "St. Louis Fed Financial Stress Index, version 4. Weekly. "
            "A z-score that combines 18 financial-market series into one "
            "number; zero is normal, positive is stressed. Alternative "
            "to Chicago Fed's NFCI; reads differently because of "
            "variable weighting and the underlying index basket."
        ),
        "supported_deltas": '["1m", "ytd", "1y", "5y", "10y", "30y"]',
        "unit": "index (z-score)",
        "fmt": {"style": "number", "decimals": 2},
        "tags": ["macro", "rates", "us"],
        "unitClass": "index",
    },
    {
        "fred_id": "AWHMAN",
        "slug": "manufacturing_weekly_hours",
        "name": "Average weekly hours, manufacturing",
        "shortName": "Mfg weekly hours",
        "description": (
            "Average weekly hours worked by production and nonsupervisory "
            "employees in manufacturing, seasonally adjusted. Monthly. "
            "A classic leading indicator - when demand softens, hours "
            "per worker contract before headcount does, so this turns "
            "down 3-6 months ahead of the broader labor market."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y", "50y"]',
        "unit": "hours",
        "fmt": {"style": "number", "decimals": 1},
        "tags": ["labor", "macro", "us"],
        "unitClass": "ratio",
    },
    {
        "fred_id": "DEXCHUS",
        "slug": "cny_usd",
        "name": "Chinese yuan per US dollar (CNY/USD)",
        "shortName": "CNY/USD",
        "description": (
            "Spot exchange rate, Chinese yuan per US dollar, daily noon "
            "buying rates from the Federal Reserve H.10 release. A "
            "widely watched political-economy currency - the PBoC "
            "manages CNY tightly, so big moves are usually deliberate "
            "signals."
        ),
        "supported_deltas": '["1w", "1m", "ytd", "1y", "5y", "10y", "30y"]',
        "unit": "CNY per USD",
        "fmt": {"style": "number", "decimals": 4},
        "tags": ["fx", "world"],
        "unitClass": "ratio",
    },
    {
        "fred_id": "GFDEBTN",
        "slug": "federal_debt_total",
        "name": "Federal debt outstanding (total public debt)",
        "shortName": "Federal debt",
        "description": (
            "Total public debt outstanding for the federal government, "
            "in millions USD, from Treasury. Quarterly. The "
            "absolute-dollar number behind the headline 35-trillion-and-"
            "counting framing - pair with us_real_gdp via the composer's "
            "divide op to get debt to GDP at any point in time."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y", "50y"]',
        "unit": "millions USD",
        "fmt": {
            "style": "currency", "currency": "USD",
            "decimals": 1, "notation": "compact",
        },
        "tags": ["government", "macro", "us"],
        "unitClass": "currency",
    },
]


def fetch_and_write_data() -> int:
    """Fetch each series from FRED, write the data JSON."""
    fetched = 0
    for spec in NEW_SPECS:
        print(f"Fetching {spec['fred_id']}... ", end="", flush=True)
        points = fred_series.fetch_series(spec["fred_id"])
        if not points:
            print("FAILED (no points)")
            continue
        print(f"{len(points)} points, last {points[-1]['t']} = {points[-1]['v']}")
        fred_series.write_timeseries(
            pipeline="fred",
            series_id=spec["fred_id"],
            name=spec["name"],
            points=points,
            unit=spec["unit"],
        )
        fetched += 1
    return fetched


def render_yaml(spec: dict) -> str:
    lines: list[str] = [
        f"name: {spec['name']}",
        f"shortName: {spec['shortName']}",
        f"description: {spec['description']}",
        "kind: timeseries",
        "pipeline: fred_series",
        f"dataFile: data/fred/{spec['fred_id']}.json",
        f"supportedDeltas: {spec['supported_deltas']}",
        f'unit: "{spec["unit"]}"',
        "formatting:",
        f"  style: {spec['fmt']['style']}",
    ]
    if spec["fmt"].get("currency"):
        lines.append(f"  currency: {spec['fmt']['currency']}")
    lines.append(f"  decimals: {spec['fmt']['decimals']}")
    if spec["fmt"].get("notation"):
        lines.append(f"  notation: {spec['fmt']['notation']}")
    if spec["fmt"].get("suffix"):
        lines.append(f"  suffix: '{spec['fmt']['suffix']}'")
    lines.append("emphasis: change")
    lines.append("provenance:")
    lines.append("  provider: FRED (St. Louis Fed)")
    lines.append(f"  series: {spec['fred_id']}")
    lines.append(f"  url: https://fred.stlouisfed.org/series/{spec['fred_id']}")
    lines.append("  license: Public domain (US government data)")
    lines.append("tags:")
    for t in spec["tags"]:
        lines.append(f"  - {t}")
    lines.append(f"unitClass: {spec['unitClass']}")
    return "\n".join(lines) + "\n"


def write_yamls() -> int:
    # Always resolve relative to the repo root, not the script's cwd, so
    # this works whether run from `pipelines/` or from the project root.
    repo_root = Path(__file__).resolve().parent.parent
    src_dir = repo_root / "src" / "content" / "sources" / "fred"
    written = 0
    for spec in NEW_SPECS:
        path = src_dir / f"{spec['slug']}.yaml"
        if path.exists():
            print(f"  skip (exists): {spec['slug']}.yaml")
            continue
        path.write_text(render_yaml(spec), encoding="utf-8")
        written += 1
        print(f"  wrote: {spec['slug']}.yaml")
    return written


if __name__ == "__main__":
    fetched = fetch_and_write_data()
    print()
    print(f"=== fetched {fetched} series, generating source YAMLs ===")
    written = write_yamls()
    print()
    print(f"Wrote {written} new FRED source YAMLs.")
    print()
    print("=== building summaries ===")
    build_summaries.main()
