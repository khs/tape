"""
World Bank macroeconomic + demographic series for China + continent/
region aggregates.

The existing worldbank_gdp.py pipeline pulls a single indicator (real
GDP) for a fixed country list. This pipeline complements it by pulling
many indicators × a few entities, with two scopes:

  1. China-specific deep dive (~15 indicators): the China economic story
     people argue about — GDP composition, currency, foreign reserves,
     industry vs. services split, urbanization, FDI flows.

  2. Continent / region aggregates published by the World Bank itself
     (precomputed sums over their constituent economies):
       SSF — Sub-Saharan Africa (proxy for "Africa")
       EUU — European Union (proxy for "Europe")
       ECS — Europe & Central Asia (broader regional aggregate)
       LCN — Latin America & Caribbean
       MEA — Middle East & North Africa
       NAC — North America
       SAS — South Asia
       EAS — East Asia & Pacific

     For each region we pull a shared 5-indicator set: GDP, GDP per
     capita, CPI inflation, population, life expectancy.

Source-ID convention: ``worldbank_extended/<indicator>_<region>``
e.g. ``worldbank_extended/gdp_current_usd_chn``.

Run with: ``python pipelines/worldbank_extended.py``.
No API key required (World Bank API is public).
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from common import write_timeseries


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "worldbank_extended"

WB_URL_TEMPLATE = (
    "https://api.worldbank.org/v2/country/{code}/indicator/{indicator}"
    "?format=json&per_page=200"
)


@dataclass
class WbIndicator:
    """One World Bank indicator definition."""

    out_id: str               # filename slug (kept short + lowercase)
    code: str                 # WB indicator code (e.g. "NY.GDP.MKTP.CD")
    name: str                 # human-readable label
    unit: str                 # natural-language unit
    fmt_style: str            # "currency" | "percent" | "number"
    decimals: int
    unit_class: str           # "currency" | "rate" | "count" | "index" | "ratio"
    extra_tags: list[str] = field(default_factory=list)
    # If True, divide raw value by 1e9 before writing (raw WB GDP values
    # come in like 17_000_000_000_000 = $17T; storing billions keeps
    # numbers compact + matches the convention used by worldbank_gdp_raw).
    rescale_to_billions: bool = False
    # If True, scale to compact (round to nearest 1e9-multiplier for
    # decimals=0 currency display).
    notation_compact: bool = True


# --------------------------------------------------------------------
# Indicator set: shared across all regions + countries
# --------------------------------------------------------------------

# Five-indicator set every region gets.
SHARED_INDICATORS: list[WbIndicator] = [
    WbIndicator(
        out_id="gdp_current_usd",
        code="NY.GDP.MKTP.CD",
        name="GDP (current USD)",
        unit="billions USD",
        fmt_style="currency",
        decimals=1,
        unit_class="currency",
        extra_tags=["macro"],
        rescale_to_billions=True,
    ),
    WbIndicator(
        out_id="gdp_per_capita_usd",
        code="NY.GDP.PCAP.CD",
        name="GDP per capita (current USD)",
        unit="USD",
        fmt_style="currency",
        decimals=0,
        unit_class="currency",
        extra_tags=["macro"],
        notation_compact=False,
    ),
    WbIndicator(
        out_id="cpi_inflation",
        code="FP.CPI.TOTL.ZG",
        name="CPI inflation, annual %",
        unit="%",
        fmt_style="percent",
        decimals=2,
        unit_class="rate",
        extra_tags=["macro"],
        notation_compact=False,
    ),
    WbIndicator(
        out_id="population",
        code="SP.POP.TOTL",
        name="Total population",
        unit="people",
        fmt_style="number",
        decimals=0,
        unit_class="count",
        extra_tags=[],
        notation_compact=True,
    ),
    WbIndicator(
        out_id="life_expectancy",
        code="SP.DYN.LE00.IN",
        name="Life expectancy at birth",
        unit="years",
        fmt_style="number",
        decimals=1,
        unit_class="ratio",
        extra_tags=[],
        notation_compact=False,
    ),
]

# China-only deep dive (10 additional indicators on top of the shared 5).
CHINA_EXTRA_INDICATORS: list[WbIndicator] = [
    WbIndicator(
        out_id="exports_current_usd",
        code="NE.EXP.GNFS.CD",
        name="Exports of goods and services (current USD)",
        unit="billions USD",
        fmt_style="currency", decimals=1, unit_class="currency",
        extra_tags=["macro", "world"],
        rescale_to_billions=True,
    ),
    WbIndicator(
        out_id="imports_current_usd",
        code="NE.IMP.GNFS.CD",
        name="Imports of goods and services (current USD)",
        unit="billions USD",
        fmt_style="currency", decimals=1, unit_class="currency",
        extra_tags=["macro", "world"],
        rescale_to_billions=True,
    ),
    WbIndicator(
        out_id="reserves_total_usd",
        code="FI.RES.TOTL.CD",
        name="Total foreign reserves (current USD)",
        unit="billions USD",
        fmt_style="currency", decimals=1, unit_class="currency",
        extra_tags=["macro"],
        rescale_to_billions=True,
    ),
    WbIndicator(
        out_id="exchange_rate_official",
        code="PA.NUS.FCRF",
        name="Official exchange rate (LCU per USD)",
        unit="local currency per USD",
        fmt_style="number", decimals=3, unit_class="ratio",
        extra_tags=["fx"],
        notation_compact=False,
    ),
    WbIndicator(
        out_id="industry_pct_gdp",
        code="NV.IND.TOTL.ZS",
        name="Industry (incl. construction) value-added (% of GDP)",
        unit="%",
        fmt_style="percent", decimals=1, unit_class="rate",
        extra_tags=["macro"],
        notation_compact=False,
    ),
    WbIndicator(
        out_id="manufacturing_pct_gdp",
        code="NV.IND.MANF.ZS",
        name="Manufacturing value-added (% of GDP)",
        unit="%",
        fmt_style="percent", decimals=1, unit_class="rate",
        extra_tags=["macro"],
        notation_compact=False,
    ),
    WbIndicator(
        out_id="services_pct_gdp",
        code="NV.SRV.TOTL.ZS",
        name="Services value-added (% of GDP)",
        unit="%",
        fmt_style="percent", decimals=1, unit_class="rate",
        extra_tags=["macro"],
        notation_compact=False,
    ),
    WbIndicator(
        out_id="urban_population_pct",
        code="SP.URB.TOTL.IN.ZS",
        name="Urban population (% of total)",
        unit="%",
        fmt_style="percent", decimals=1, unit_class="rate",
        extra_tags=[],
        notation_compact=False,
    ),
    WbIndicator(
        out_id="fdi_inflows_pct_gdp",
        code="BX.KLT.DINV.WD.GD.ZS",
        name="FDI inflows (% of GDP)",
        unit="%",
        fmt_style="percent", decimals=2, unit_class="rate",
        extra_tags=["macro", "world"],
        notation_compact=False,
    ),
    WbIndicator(
        out_id="broad_money_pct_gdp",
        code="FM.LBL.BMNY.GD.ZS",
        name="Broad money (% of GDP)",
        unit="%",
        fmt_style="percent", decimals=1, unit_class="rate",
        extra_tags=["macro"],
        notation_compact=False,
    ),
]

# --------------------------------------------------------------------
# Entities: regions + China
# --------------------------------------------------------------------

@dataclass
class Entity:
    code: str        # World Bank country / aggregate code
    slug: str        # filename suffix
    name: str        # display name
    tag_region: str  # tag added to all of this entity's sources


# China gets the full 15-indicator deep dive.
# Regional aggregates get the 5-indicator shared set.
REGIONS: list[Entity] = [
    Entity("SSF", "africa_ssf", "Sub-Saharan Africa", "africa"),
    Entity("EUU", "europe_eu", "European Union", "europe"),
    Entity("ECS", "europe_central_asia", "Europe and Central Asia", "europe"),
    Entity("LCN", "latam", "Latin America and Caribbean", "world"),
    Entity("MEA", "mena", "Middle East and North Africa", "world"),
    Entity("NAC", "north_america", "North America", "world"),
    Entity("SAS", "south_asia", "South Asia", "world"),
    Entity("EAS", "east_asia_pacific", "East Asia and Pacific", "world"),
]
CHINA = Entity("CHN", "china", "China", "world")


# --------------------------------------------------------------------
# Fetch + parse
# --------------------------------------------------------------------

def fetch_wb_series(code: str, indicator: str) -> dict[str, float]:
    """Return {year_str: value}."""
    url = WB_URL_TEMPLATE.format(code=code, indicator=indicator)
    try:
        result = subprocess.run(
            ["curl", "-sS", "--max-time", "60", url],
            capture_output=True, check=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    curl failed for {code} / {indicator}: {e}", file=sys.stderr)
        return {}
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"    bad JSON for {code} / {indicator}", file=sys.stderr)
        return {}
    if not isinstance(raw, list) or len(raw) < 2 or raw[1] is None:
        return {}
    out: dict[str, float] = {}
    for row in raw[1]:
        year = row.get("date")
        v = row.get("value")
        if year and v is not None:
            try:
                out[str(year)] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def annual_to_points(series: dict[str, float], rescale_to_billions: bool) -> list[dict]:
    if not series:
        return []
    years = sorted(series.keys())
    points = []
    for y in years:
        v = series[y]
        if rescale_to_billions:
            v = v / 1e9
        points.append({"t": f"{y}-12-31", "v": v})
    today = datetime.now(timezone.utc).date().isoformat()
    if points and points[-1]["t"] < today:
        points.append({"t": today, "v": points[-1]["v"]})
    return points


# --------------------------------------------------------------------
# YAML emission
# --------------------------------------------------------------------

def yaml_escape(s: str) -> str:
    if not s:
        return '""'
    if any(ch in s for ch in [":", "#", "&", "*", "!", "|", ">", "%", "@"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def write_source_yaml(indicator: WbIndicator, entity: Entity) -> bool:
    """Write per-(indicator, entity) source YAML. Idempotent."""
    slug = f"{indicator.out_id}_{entity.slug}"
    out = SOURCES_DIR / f"{slug}.yaml"
    if out.exists():
        return False
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    name_full = f"{indicator.name} — {entity.name}"
    short = f"{entity.name} {indicator.out_id.replace('_', ' ')}"
    description = (
        f"{indicator.name} for {entity.name}, annual. From World Bank "
        f"World Development Indicators (series {indicator.code}). "
        f"Most regions and country aggregates available back to 1960; "
        f"individual series start dates vary."
    )
    tags = ["macro", "world"] + indicator.extra_tags + [entity.tag_region]
    # Dedupe + sort.
    tags = sorted(set(tags))
    lines = [
        f"name: {yaml_escape(name_full)}",
        f"shortName: {yaml_escape(short)}",
        f"description: {yaml_escape(description)}",
        "kind: timeseries",
        "pipeline: worldbank_extended",
        f"dataFile: data/worldbank_extended/{slug}.json",
        'supportedDeltas: ["5y", "10y", "30y", "50y"]',
        f'unit: "{indicator.unit}"',
        "formatting:",
        f"  style: {indicator.fmt_style}",
    ]
    if indicator.fmt_style == "currency":
        lines.append("  currency: USD")
    lines.append(f"  decimals: {indicator.decimals}")
    if indicator.notation_compact and indicator.fmt_style in ("currency", "number"):
        lines.append("  notation: compact")
    lines.extend([
        "emphasis: change",
        "provenance:",
        "  provider: World Bank (World Development Indicators)",
        f"  series: {indicator.code} / {entity.code}",
        f"  url: https://api.worldbank.org/v2/country/{entity.code}/indicator/{indicator.code}",
        "  license: CC BY 4.0",
        "tags:",
    ])
    for t in tags:
        lines.append(f"  - {t}")
    lines.append(f"unitClass: {indicator.unit_class}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------

def main() -> int:
    # (indicator, entity) tuples to fetch.
    plan: list[tuple[WbIndicator, Entity]] = []
    # China gets shared + extras.
    for ind in SHARED_INDICATORS + CHINA_EXTRA_INDICATORS:
        plan.append((ind, CHINA))
    # All regions get the shared 5.
    for ind in SHARED_INDICATORS:
        for region in REGIONS:
            plan.append((ind, region))

    print(f"Fetching {len(plan)} (indicator × entity) combinations from World Bank...")
    written_json = 0
    written_yaml = 0
    for indicator, entity in plan:
        print(f"  {entity.code} / {indicator.code} ({indicator.out_id})... ",
              end="", flush=True)
        series = fetch_wb_series(entity.code, indicator.code)
        points = annual_to_points(series, indicator.rescale_to_billions)
        if not points:
            print("(no data)")
            continue
        slug = f"{indicator.out_id}_{entity.slug}"
        write_timeseries(
            pipeline="worldbank_extended",
            series_id=slug,
            name=f"{indicator.name} — {entity.name}",
            points=points,
            unit=indicator.unit,
        )
        written_json += 1
        if write_source_yaml(indicator, entity):
            written_yaml += 1
        last = points[-1]
        print(f"{len(points)} pts (last {last['t'][:4]}={last['v']:.2f})")

    print(f"\nWrote {written_json} data files + {written_yaml} new source YAMLs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
