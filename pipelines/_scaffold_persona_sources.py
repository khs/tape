"""
One-shot scaffold for the analyst-persona FRED source YAMLs added in
the 2026-05-27 expansion. Run once; the YAMLs are committed and the
script can be deleted, but keeping it documents which series got
which metadata. Re-running is safe (it skips files that already
exist).
"""
from __future__ import annotations
from pathlib import Path
from textwrap import dedent

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "content" / "sources" / "fred"

# Each row: (slug, fred_series_id, name, short_name, unit, fmt_style,
#            decimals, notation_or_None, persona_tags, emphasis,
#            blurb_paragraph).
ROWS = [
    # ---- Health ----
    (
        "health_care_employment",
        "CES6562000001",
        "Health care + social assistance employment",
        "Healthcare jobs",
        "thousands of persons",
        "number", 0, "compact",
        ["macro", "labor", "health", "us"],
        "level",
        "All employees in the health care + social assistance sector (BLS CES). "
        "Largest single industry by employment in the modern US economy and one "
        "of the most counter-cyclical, keeps growing through recessions when "
        "other sectors shed jobs.",
    ),
    (
        "health_spending_per_capita",
        "HLTHSCPCHCSA",
        "Personal health-care spending per capita",
        "Health $/cap",
        "USD",
        "currency", 0, "compact",
        ["macro", "health", "consumer", "us"],
        "level",
        "Personal health-care expenditures per capita, from the BEA's National "
        "Health Expenditure accounts. The headline number for healthcare-cost "
        "trajectory; rises faster than per-capita GDP in most years.",
    ),
    # ---- Defense ----
    (
        "defense_pct_gdp",
        "A824RE1Q156NBEA",
        "National defense, share of GDP",
        "Defense % GDP",
        "%",
        "percent", 2, None,
        ["macro", "defense", "government", "us"],
        "level",
        "National defense consumption + gross investment as a share of GDP "
        "(BEA NIPA Table 1.1.10). Trended down from ~6.5% in the early 1980s "
        "to ~3% by the 2010s; the cleanest single read of how much of the "
        "economy goes to defense.",
    ),
    # ---- Energy ----
    (
        "oil_gas_production",
        "IPG211S",
        "Industrial production: oil + gas extraction",
        "Oil & gas IP",
        "index (2017=100)",
        "number", 1, None,
        ["macro", "energy", "industrial-production", "us"],
        "level",
        "Federal Reserve industrial-production index for oil + gas extraction. "
        "Captures the shale-revolution surge of 2010-19 + the COVID dip + the "
        "post-2022 recovery without needing barrel-volume data.",
    ),
    (
        "electric_power_production",
        "IPG2211S",
        "Industrial production: electric power generation",
        "Power gen IP",
        "index (2017=100)",
        "number", 1, None,
        ["macro", "energy", "industrial-production", "us"],
        "level",
        "Federal Reserve industrial-production index for electric power "
        "generation, transmission, and distribution. Tracks economy-wide "
        "electricity demand independent of specific fuel mix.",
    ),
    # ---- Tech ----
    (
        "semiconductor_production",
        "IPG3344S",
        "Industrial production: semiconductors + electronic components",
        "Semis IP",
        "index (2017=100)",
        "number", 1, None,
        ["macro", "tech", "industrial-production", "us"],
        "level",
        "Federal Reserve industrial-production index for semiconductor and "
        "other electronic-component manufacturing. The post-CHIPS-Act US "
        "fab buildout shows up here directly.",
    ),
    (
        "semiconductor_capacity_util",
        "CAPUTLG3344S",
        "Capacity utilization: semiconductors",
        "Semis util",
        "%",
        "percent", 1, None,
        ["macro", "tech", "industrial-production", "us"],
        "level",
        "Capacity utilization for the semiconductor + electronic-component "
        "manufacturing sub-industry. Pair with the IP index to see whether "
        "production growth is coming from new fab capacity (util flat) or "
        "running the existing base harder (util rising).",
    ),
    (
        "information_employment",
        "USINFO",
        "Information-sector employment",
        "Info jobs",
        "thousands of persons",
        "number", 0, "compact",
        ["macro", "labor", "tech", "us"],
        "level",
        "All employees in the information sector, software publishing, "
        "telecoms, broadcasting, motion pictures, data processing, web "
        "search. The tech-employment headline in BLS terms.",
    ),
    (
        "computer_electronics_orders",
        "A34SNO",
        "New orders: computers + electronic products",
        "Computer orders",
        "millions USD",
        "currency", 0, "compact",
        ["macro", "tech", "us"],
        "level",
        "Manufacturers' new orders for computers and electronic products (Census "
        "M3 survey). A demand-side leading indicator for tech capex; turns "
        "before semiconductor production does.",
    ),
    # ---- Government spending + employment ----
    (
        "federal_expenditures",
        "FGEXPND",
        "Federal government current expenditures",
        "Fed expend.",
        "billions USD",
        "currency", 0, "compact",
        ["macro", "government", "us"],
        "level",
        "Total federal current expenditures (BEA NIPA). Includes consumption, "
        "transfers, interest, and subsidies, broader than the cash-basis "
        "outlays we get from Treasury via USAspending.",
    ),
    (
        "state_local_expenditures",
        "SLEXPND",
        "State + local government current expenditures",
        "S+L expend.",
        "billions USD",
        "currency", 0, "compact",
        ["macro", "government", "us"],
        "level",
        "State + local current expenditures (BEA NIPA). The other half of the "
        "general-government picture; ~$3T-vs-federal-$7T scale matters for "
        "anyone thinking about total public-sector economic footprint.",
    ),
    (
        "total_govt_employment",
        "USGOVT",
        "Government employment, total",
        "Govt jobs",
        "thousands of persons",
        "number", 0, "compact",
        ["macro", "labor", "government", "us"],
        "level",
        "All employees in government (BLS CES, federal + state + local "
        "combined). ~22 million people; the headline jobs metric for "
        "public-sector employment.",
    ),
    (
        "federal_employment",
        "CES9091000001",
        "Federal government employment",
        "Fed jobs",
        "thousands of persons",
        "number", 0, "compact",
        ["macro", "labor", "government", "us"],
        "level",
        "Federal employees (BLS CES). Includes USPS, which makes up ~25% of "
        "the total, non-postal federal employment moves at a different "
        "cadence + reflects the size of the civilian executive branch.",
    ),
    (
        "state_employment",
        "CES9092000001",
        "State government employment",
        "State jobs",
        "thousands of persons",
        "number", 0, "compact",
        ["macro", "labor", "government", "us"],
        "level",
        "State-government employees (BLS CES). Heavy on higher education, "
        "corrections, and public safety; tracks state-budget conditions "
        "more closely than federal employment does.",
    ),
    (
        "local_employment",
        "CES9093000001",
        "Local government employment",
        "Local jobs",
        "thousands of persons",
        "number", 0, "compact",
        ["macro", "labor", "government", "us"],
        "level",
        "Local-government employees (BLS CES). K-12 school district payrolls "
        "are the dominant component; the September peak each year reflects "
        "the academic-year hiring cycle.",
    ),
    # ---- Labor demographics ----
    (
        "unemployment_white",
        "LNS14000003",
        "Unemployment rate, White",
        "Unrate (W)",
        "%",
        "percent", 1, None,
        ["macro", "labor", "demographics", "us"],
        "level",
        "Civilian unemployment rate, White workers (BLS CPS). Lowest of the "
        "three race/ethnicity series we carry; useful as the baseline for "
        "reading the persistent gaps with Black and Hispanic unemployment.",
    ),
    (
        "unemployment_black",
        "LNS14000006",
        "Unemployment rate, Black or African American",
        "Unrate (B)",
        "%",
        "percent", 1, None,
        ["macro", "labor", "demographics", "us"],
        "level",
        "Civilian unemployment rate, Black or African American workers (BLS "
        "CPS). Historically runs roughly 2× the White unemployment rate; "
        "the gap narrows in late-cycle full-employment regimes (2018-19, "
        "2022-25) but doesn't close.",
    ),
    (
        "unemployment_hispanic",
        "LNS14000009",
        "Unemployment rate, Hispanic or Latino",
        "Unrate (H)",
        "%",
        "percent", 1, None,
        ["macro", "labor", "demographics", "us"],
        "level",
        "Civilian unemployment rate, Hispanic or Latino workers (BLS CPS). "
        "Runs between the White and Black series in most cycles; reflects "
        "industry-composition differences as much as anything else.",
    ),
    # ---- Consumer (per-capita complement) ----
    (
        "real_dpi_per_capita",
        "A229RX0",
        "Real disposable personal income per capita",
        "Real DPI/cap",
        "chained 2017 USD",
        "currency", 0, None,
        ["macro", "consumer", "us"],
        "level",
        "Per-capita real disposable personal income (BEA). The aggregate "
        "series we also carry (DSPIC96) responds to population growth + "
        "income growth; this per-capita version isolates the per-person "
        "purchasing-power read.",
    ),
]


def yaml_for(row: tuple) -> str:
    (
        slug, sid, name, short_name, unit, fmt_style, decimals,
        notation, tags, emphasis, blurb,
    ) = row
    unit_class = (
        "currency" if fmt_style == "currency"
        else "rate" if fmt_style == "percent"
        else "count" if "persons" in unit
        else "index"
    )
    # Single-quote name + shortName + description because they may
    # contain colons ("New orders: computers + ...") that YAML would
    # otherwise read as a nested key. The js-yaml parser blew up on
    # an unquoted name with a colon when this script first ran.
    def q(s: str) -> str:
        # YAML single-quote escaping: doubled single-quotes inside
        # the string. Apostrophes survive that way.
        return "'" + s.replace("'", "''") + "'"

    lines: list[str] = []
    lines.append(f"name: {q(name)}")
    lines.append(f"shortName: {q(short_name)}")
    desc = f"{blurb} Public-domain federal-agency data via FRED."
    lines.append(f"description: {q(desc)}")
    lines.append("kind: timeseries")
    lines.append("pipeline: fred_series")
    lines.append(f"dataFile: data/fred/{sid}.json")
    lines.append('supportedDeltas: ["1m", "ytd", "1y", "5y", "10y", "30y"]')
    lines.append(f'unit: "{unit}"')
    lines.append(f"emphasis: {emphasis}")
    lines.append("formatting:")
    lines.append(f"  style: {fmt_style}")
    lines.append(f"  decimals: {decimals}")
    if notation:
        lines.append(f"  notation: {notation}")
    if fmt_style == "currency" and notation == "compact":
        if "billions" in unit:
            lines.append("  scaleFactor: 1000000000")
        elif "millions" in unit:
            lines.append("  scaleFactor: 1000000")
    lines.append("provenance:")
    lines.append("  provider: U.S. federal-agency data via FRED")
    lines.append(f"  series: {sid}")
    lines.append(f"  url: https://fred.stlouisfed.org/series/{sid}")
    # Wrap the license string in YAML double-quotes — it contains
    # single quotes AND a colon, both of which trip the parser if
    # the value is bare. Double-quote escaping leaves the inner
    # single quotes untouched.
    lines.append(
        '  license: "Public domain (US government data; '
        "see FRED tag 'public domain: citation requested')\""
    )
    lines.append("tags:")
    for t in tags:
        lines.append(f"  - {t}")
    lines.append(f"unitClass: {unit_class}")
    return "\n".join(lines) + "\n"


def main() -> int:
    SRC.mkdir(parents=True, exist_ok=True)
    created = skipped = 0
    for row in ROWS:
        path = SRC / f"{row[0]}.yaml"
        if path.exists():
            skipped += 1
            continue
        path.write_text(yaml_for(row), encoding="utf-8")
        created += 1
    print(f"Created {created} YAMLs; skipped {skipped} existing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
