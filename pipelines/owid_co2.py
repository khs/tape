"""
Our World in Data — CO2 & energy pipeline.

Source: https://owid-public.owid.io/data/co2/owid-co2-data.csv  (no API key)
License: Creative Commons BY (Our World in Data). Licit to redistribute
with attribution; the source YAMLs carry "CC BY 4.0 (Our World in Data)"
and each chart/source page renders the credit.

New-data-source checklist notes (docs/new-data-source-checklist.md):
  - Authoritative label: OWID's own column codebook
    (owid-co2-codebook.csv). We anchor each indicator's human name to
    the codebook concept and PREFLIGHT that every indicator column +
    "country"/"year"/"iso_code" exist in the live CSV header before
    writing — so an OWID schema reshuffle FAILS the refresh rather than
    silently mislabelling (the usda_nass / cdc_health correct-by-
    construction pattern). No separate audit script: there is no
    per-series label endpoint to diff against, and the labels are
    constructed here, not transcribed.
  - Identifier convention: owid_co2/<indicator_slug>_<country_slug>;
    provenance.series = "<csv_column> / <iso3>".
  - Canonical units: emissions stored as published (million tonnes CO2);
    these are physical counts, not currency, so no billions rescale.

Run: python pipelines/owid_co2.py            (all)
     python pipelines/owid_co2.py co2 world   (filter by indicator/country slug substrings)
"""
from __future__ import annotations

import csv
import io
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from common import write_timeseries

CSV_URL = "https://owid-public.owid.io/data/co2/owid-co2-data.csv"
SElF_DIR = Path(__file__).resolve().parent
SOURCES_DIR = SElF_DIR.parent / "src" / "content" / "sources" / "owid_co2"


@dataclass
class Indicator:
    col: str          # CSV column name
    slug: str         # indicator slug fragment
    label: str        # human label (goes in "<label> — <country>")
    short: str        # short label fragment
    unit: str
    style: str        # currency | index | percent | number
    decimals: int
    unit_class: str | None  # currency|count|rate|index|ratio|price or None
    desc: str         # one-line concept description (codebook-anchored)


INDICATORS: list[Indicator] = [
    Indicator("co2", "co2", "Annual CO2 emissions", "CO2",
              "million tonnes CO2", "number", 0, "count",
              "Annual production-based emissions of carbon dioxide from fossil fuels and industry, measured in million tonnes."),
    Indicator("co2_per_capita", "co2_per_capita", "CO2 emissions per capita", "CO2 per capita",
              "tonnes CO2 per person", "number", 2, "ratio",
              "Annual production-based CO2 emissions divided by population, in tonnes per person."),
    Indicator("share_global_co2", "share_global_co2", "Share of global CO2 emissions", "Share of global CO2",
              "%", "percent", 1, "rate",
              "The country's annual CO2 emissions as a percentage of the global total."),
    Indicator("consumption_co2", "consumption_co2", "Consumption-based CO2 emissions", "Consumption CO2",
              "million tonnes CO2", "number", 0, "count",
              "Production emissions adjusted for trade — emissions embedded in imports are added and those in exports subtracted. Million tonnes."),
    Indicator("cumulative_co2", "cumulative_co2", "Cumulative CO2 emissions", "Cumulative CO2",
              "million tonnes CO2", "number", 0, "count",
              "Total CO2 emitted by the country since 1750 — a measure of historical contribution. Million tonnes."),
    Indicator("coal_co2", "coal_co2", "CO2 emissions from coal", "Coal CO2",
              "million tonnes CO2", "number", 0, "count",
              "Annual CO2 emissions from coal, in million tonnes."),
    Indicator("oil_co2", "oil_co2", "CO2 emissions from oil", "Oil CO2",
              "million tonnes CO2", "number", 0, "count",
              "Annual CO2 emissions from oil, in million tonnes."),
    Indicator("gas_co2", "gas_co2", "CO2 emissions from gas", "Gas CO2",
              "million tonnes CO2", "number", 0, "count",
              "Annual CO2 emissions from natural gas, in million tonnes."),
    Indicator("energy_per_capita", "energy_per_capita", "Primary energy consumption per capita", "Energy per capita",
              "kWh per person", "number", 0, "ratio",
              "Primary energy consumption per person, in kilowatt-hours."),
]

# (owid country name in the CSV, slug, iso3 for provenance). World uses
# OWID's WRL aggregate. Curated to the largest emitters + the EU + World
# so the first cut covers the bulk of global emissions without 200 entities.
ENTITIES: list[tuple[str, str, str]] = [
    ("World", "world", "WRL"),
    ("United States", "united_states", "USA"),
    ("China", "china", "CHN"),
    ("India", "india", "IND"),
    ("Russia", "russia", "RUS"),
    ("Japan", "japan", "JPN"),
    ("Germany", "germany", "DEU"),
    ("Iran", "iran", "IRN"),
    ("South Korea", "south_korea", "KOR"),
    ("Saudi Arabia", "saudi_arabia", "SAU"),
    ("Indonesia", "indonesia", "IDN"),
    ("Canada", "canada", "CAN"),
    ("Brazil", "brazil", "BRA"),
    ("United Kingdom", "united_kingdom", "GBR"),
    ("France", "france", "FRA"),
    ("Mexico", "mexico", "MEX"),
    ("Australia", "australia", "AUS"),
    ("Italy", "italy", "ITA"),
    ("South Africa", "south_africa", "ZAF"),
    ("Turkey", "turkey", "TUR"),
    ("European Union (27)", "european_union", "EU27"),
]

SUPPORTED_DELTAS = ["5y", "10y", "30y", "50y"]


def fetch_csv() -> list[dict]:
    res = subprocess.run(
        ["curl", "-sS", "--max-time", "120", CSV_URL],
        capture_output=True, check=True, text=True,
    )
    reader = csv.DictReader(io.StringIO(res.stdout))
    return list(reader)


def preflight(header: list[str]) -> None:
    """Fail loudly if OWID reshuffles columns — this IS the audit."""
    need = {"country", "year", "iso_code"} | {ind.col for ind in INDICATORS}
    missing = need - set(header)
    if missing:
        raise SystemExit(
            f"OWID CSV schema changed — missing columns: {sorted(missing)}. "
            "Re-check the codebook before trusting labels."
        )


def yaml_for(ind: Indicator, country: str, slug: str, iso3: str) -> str:
    data_id = f"{ind.slug}_{slug}"
    lines = [
        f'name: "{ind.label} — {country}"',
        f"shortName: {country} {ind.short}",
        f"description: {ind.desc} Values for {country}, annual, from Our World in Data's CO2 dataset.",
        "kind: timeseries",
        "pipeline: owid_co2",
        f"dataFile: data/owid_co2/{data_id}.json",
        f'supportedDeltas: {["5y", "10y", "30y", "50y"]}'.replace("'", '"'),
        f'unit: "{ind.unit}"',
        "formatting:",
        f"  style: {ind.style}",
        f"  decimals: {ind.decimals}",
        "emphasis: change",
        "provenance:",
        "  provider: Our World in Data (CO2 dataset)",
        f"  series: {ind.col} / {iso3}",
        "  url: https://github.com/owid/co2-data",
        "  license: CC BY 4.0 (Our World in Data)",
        # NB: no "world" tag. Per the worldbank_extended precedent +
        # the test_source_corpus world-tag invariant, "world" is reserved
        # for true world/regional AGGREGATES, not per-country series — the
        # country lives in the title, and these surface under the
        # climate/energy topical chips + the Generators tab.
        "tags:",
        "  - climate",
        "  - energy",
        "  - macro",
    ]
    if ind.unit_class:
        lines.append(f"unitClass: {ind.unit_class}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    filters = [a.lower() for a in (argv or [])[1:]]
    rows = fetch_csv()
    if not rows:
        raise SystemExit("OWID CSV came back empty.")
    preflight(list(rows[0].keys()))

    # index rows by country name for quick per-entity slicing
    by_country: dict[str, list[dict]] = {}
    for r in rows:
        by_country.setdefault(r["country"], []).append(r)

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for ind in INDICATORS:
        for country, slug, iso3 in ENTITIES:
            data_id = f"{ind.slug}_{slug}"
            if filters and not all(
                f in (ind.slug + " " + slug) for f in filters
            ):
                # filter: every token must appear in indicator-or-country slug
                if not any(f in ind.slug or f in slug for f in filters):
                    continue
            crows = by_country.get(country, [])
            points = []
            for r in crows:
                raw = r.get(ind.col, "")
                yr = r.get("year", "")
                if raw in ("", None) or not yr:
                    continue
                try:
                    v = float(raw)
                except ValueError:
                    continue
                points.append({"t": f"{yr}-01-01", "v": v})
            if not points:
                continue
            write_timeseries(
                pipeline="owid_co2",
                series_id=data_id,
                name=f"{ind.label} — {country}",
                points=points,
                unit=ind.unit,
            )
            (SOURCES_DIR / f"{data_id}.yaml").write_text(
                yaml_for(ind, country, slug, iso3), encoding="utf-8"
            )
            written += 1
    print(f"owid_co2: wrote {written} series (data + YAML).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
