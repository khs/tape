"""One-off fetcher for the AI + datacenter expansion.

Fetches:
  * 3 new FRED series (PCU33443344, PCU518210518210, IPMINE)
  * 18 new Yahoo equities/ETFs (semis chain, datacenter REITs,
    AI-tailwind power producers, AI thematic ETFs)
And writes source YAMLs for each. Run from project root.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "pipelines")

import fred_series  # noqa: E402
import yahoo_quotes  # noqa: E402
import build_summaries  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent
FRED_SOURCES = REPO_ROOT / "src" / "content" / "sources" / "fred"
YAHOO_SOURCES = REPO_ROOT / "src" / "content" / "sources" / "yahoo"


# New FRED series specs — metadata for YAML generation, matching the
# specs already added to fred_series.py SPECS.
FRED_NEW = [
    {
        "fred_id": "PCU33443344",
        "slug": "ppi_semiconductor",
        "name": "PPI — Semiconductor & related device mfg",
        "shortName": "PPI semiconductor",
        "description": (
            "Producer Price Index for semiconductor and related device "
            "manufacturing (NAICS 3344). Tracks wholesale prices in the "
            "chip-making industry — crashes during memory + commodity-"
            "chip gluts, climbs during AI-driven capacity tightness. "
            "Monthly from BLS via FRED."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y"]',
        "unit": "index (Jun 2009=100)",
        "fmt": {"style": "index", "decimals": 1},
        "tags": ["tech", "macro", "us"],
        "unitClass": "index",
    },
    {
        "fred_id": "PCU518210518210",
        "slug": "ppi_data_processing_hosting",
        "name": "PPI — Data processing, hosting & related services",
        "shortName": "PPI data hosting",
        "description": (
            "Producer Price Index for data processing, hosting, and "
            "related services (NAICS 518210). The closest published-"
            "price index to wholesale cloud-and-hosting pricing. Lags "
            "spot but tracks the secular price trend (long-run down "
            "from cloud scale, but recently bottoming as AI-compute "
            "demand chases finite supply). Monthly from BLS via FRED."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y"]',
        "unit": "index (Dec 2009=100)",
        "fmt": {"style": "index", "decimals": 1},
        "tags": ["tech", "macro", "us"],
        "unitClass": "index",
    },
    {
        "fred_id": "IPMINE",
        "slug": "industrial_production_mining",
        "name": "Industrial production — Mining",
        "shortName": "IP mining",
        "description": (
            "Industrial production index for mining (NAICS 21), "
            "including oil & gas extraction. Pair with IPMAN "
            "(manufacturing) and IPUTIL (utilities) for the three-sector "
            "view of US industrial output — these often diverge sharply "
            "(e.g. utilities up on AI demand while mining swings on oil "
            "prices). Monthly from Fed via FRED."
        ),
        "supported_deltas": '["1y", "5y", "10y", "30y", "50y"]',
        "unit": "index (2017=100)",
        "fmt": {"style": "index", "decimals": 2},
        "tags": ["macro", "us", "commodities"],
        "unitClass": "index",
    },
]


# New Yahoo specs — metadata for YAML generation. The actual data fetch
# uses yahoo_quotes' SPECS list directly (since the YahooSpec was already
# added there); this dict just drives YAML metadata.
YAHOO_NEW = [
    # Semis (chip + supply chain)
    {"sym": "AMD", "name": "Advanced Micro Devices (AMD)",
     "desc": "GPU + CPU manufacturer; primary AI-GPU competitor to NVIDIA. Daily adjusted close.",
     "tags": ["large-stocks", "tech", "us"]},
    {"sym": "INTC", "name": "Intel (INTC)",
     "desc": "CPU + datacenter chip maker; recent foundry pivot. Daily adjusted close.",
     "tags": ["large-stocks", "tech", "us"]},
    {"sym": "AMAT", "name": "Applied Materials (AMAT)",
     "desc": "Wafer fab equipment leader — the upstream tools that make every chip. Daily adjusted close.",
     "tags": ["large-stocks", "tech", "us"]},
    {"sym": "KLAC", "name": "KLA Corp (KLAC)",
     "desc": "Process control + inspection equipment for semiconductor manufacturing. Daily adjusted close.",
     "tags": ["large-stocks", "tech", "us"]},
    {"sym": "LRCX", "name": "Lam Research (LRCX)",
     "desc": "Etch and deposition equipment for semiconductor fabs. Daily adjusted close.",
     "tags": ["large-stocks", "tech", "us"]},
    {"sym": "ARM", "name": "Arm Holdings (ARM)",
     "desc": "CPU architecture licensor — IP shipped in nearly every mobile chip + growing AI inference share. Daily adjusted close.",
     "tags": ["large-stocks", "tech"]},
    {"sym": "SMCI", "name": "Super Micro Computer (SMCI)",
     "desc": "AI server systems integrator — assembles GPU racks for hyperscalers and enterprises. Daily adjusted close.",
     "tags": ["large-stocks", "tech", "us"]},
    # Datacenter REITs
    {"sym": "EQIX", "name": "Equinix (EQIX)",
     "desc": "Largest US datacenter colocation REIT; runs interconnection-dense facilities in 30+ countries. Daily adjusted close.",
     "tags": ["large-stocks", "real-estate", "tech", "us"]},
    {"sym": "DLR", "name": "Digital Realty (DLR)",
     "desc": "Datacenter REIT focused on hyperscale + colocation; major beneficiary of AI capacity buildout. Daily adjusted close.",
     "tags": ["large-stocks", "real-estate", "tech", "us"]},
    {"sym": "IRM", "name": "Iron Mountain (IRM)",
     "desc": "Records-storage REIT pivoting into datacenter hosting; legacy paper business + growing digital. Daily adjusted close.",
     "tags": ["large-stocks", "real-estate", "us"]},
    # AI-tailwind power producers
    {"sym": "VST", "name": "Vistra (VST)",
     "desc": "Gas + nuclear power producer; signed long-term deal with Microsoft to power AI datacenters from Comanche Peak nuclear plant. Daily adjusted close.",
     "tags": ["large-stocks", "energy", "us"]},
    {"sym": "CEG", "name": "Constellation Energy (CEG)",
     "desc": "Largest US nuclear operator; signed 20-year PPA with Microsoft to restart Three Mile Island Unit 1 for AI datacenter power. Daily adjusted close.",
     "tags": ["large-stocks", "energy", "us"]},
    {"sym": "TLN", "name": "Talen Energy (TLN)",
     "desc": "Mid-cap independent power producer; nuclear-heavy fleet, signed AWS deal to colocate datacenters at Susquehanna nuclear plant. Daily adjusted close.",
     "tags": ["large-stocks", "energy", "us"]},
    {"sym": "NRG", "name": "NRG Energy (NRG)",
     "desc": "Broad merchant power producer + retail electricity; AI-demand exposure via Texas + Northeast service territories. Daily adjusted close.",
     "tags": ["large-stocks", "energy", "us"]},
    # AI thematic ETFs
    {"sym": "BOTZ", "name": "Global X Robotics + AI ETF (BOTZ)",
     "desc": "Holds companies positioned to benefit from increased adoption of robotics + AI — heavy in NVDA, Japanese industrial robotics, semis. Daily adjusted close.",
     "tags": ["equity-index", "tech"]},
    {"sym": "AIQ", "name": "Global X AI + Tech ETF (AIQ)",
     "desc": "Holds companies developing and using AI technology — broader than BOTZ; heavy in mega-cap tech (MSFT, GOOG, META) plus chipmakers. Daily adjusted close.",
     "tags": ["equity-index", "tech"]},
    {"sym": "ROBO", "name": "ROBO Global Robotics + Automation ETF (ROBO)",
     "desc": "Equal-weighted basket of robotics + automation companies — different tilt from BOTZ's market-cap weighting, more industrial automation exposure. Daily adjusted close.",
     "tags": ["equity-index", "tech"]},
    {"sym": "SMH", "name": "VanEck Semiconductor ETF (SMH)",
     "desc": "Broader semiconductor ETF than SOXX; market-cap weighted, heavy NVDA + TSM concentration. Daily adjusted close.",
     "tags": ["equity-index", "tech", "us"]},
]


def fetch_fred_new() -> int:
    """Fetch the 3 new FRED series + write data + YAMLs."""
    written = 0
    for spec in FRED_NEW:
        print(f"FRED {spec['fred_id']}... ", end="", flush=True)
        points = fred_series.fetch_series(spec["fred_id"])
        if not points:
            print("FAILED")
            continue
        print(f"{len(points)} pts, last {points[-1]['t']}={points[-1]['v']}")
        fred_series.write_timeseries(
            pipeline="fred",
            series_id=spec["fred_id"],
            name=spec["name"],
            points=points,
            unit=spec["unit"],
        )
        # Write source YAML.
        yaml_path = FRED_SOURCES / f"{spec['slug']}.yaml"
        if yaml_path.exists():
            continue
        lines = [
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
            f"  decimals: {spec['fmt']['decimals']}",
            "emphasis: change",
            "provenance:",
            "  provider: FRED (St. Louis Fed)",
            f"  series: {spec['fred_id']}",
            f"  url: https://fred.stlouisfed.org/series/{spec['fred_id']}",
            "  license: Public domain (US government data)",
            "tags:",
        ]
        for t in spec["tags"]:
            lines.append(f"  - {t}")
        lines.append(f"unitClass: {spec['unitClass']}")
        yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1
    return written


def fetch_yahoo_new() -> int:
    """Fetch only the new Yahoo specs + write data + YAMLs."""
    new_symbols = [s["sym"] for s in YAHOO_NEW]
    # Run yahoo_quotes.main with the new symbols only.
    yahoo_quotes.main(["yahoo_quotes.py"] + new_symbols)

    written = 0
    for spec in YAHOO_NEW:
        yaml_path = YAHOO_SOURCES / f"{spec['sym'].lower()}.yaml"
        if yaml_path.exists():
            continue
        lines = [
            f"name: {spec['name']}",
            f"shortName: {spec['sym']}",
            f"description: {spec['desc']}",
            "kind: timeseries",
            "pipeline: yahoo_quotes",
            f"dataFile: data/yahoo/{spec['sym']}.json",
            'supportedDeltas: ["1w", "1m", "ytd", "1y", "5y", "10y"]',
            "unit: USD",
            "formatting:",
            "  style: currency",
            "  currency: USD",
            "  decimals: 2",
            "emphasis: change",
            "provenance:",
            "  provider: Yahoo Finance",
            f"  series: {spec['sym']}",
            f"  url: https://finance.yahoo.com/quote/{spec['sym']}",
            "tags:",
        ]
        for t in spec["tags"]:
            lines.append(f"  - {t}")
        lines.append("unitClass: currency")
        yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1
    return written


if __name__ == "__main__":
    print("=== FRED new (3 series) ===")
    fred_count = fetch_fred_new()
    print(f"\n=== Yahoo new ({len(YAHOO_NEW)} tickers) ===")
    yahoo_count = fetch_yahoo_new()
    print(f"\nFRED YAMLs: {fred_count}, Yahoo YAMLs: {yahoo_count}")
    print("\n=== building summaries ===")
    build_summaries.main()
