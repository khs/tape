"""Our World in Data — energy pipeline (renewable electricity share).

Source: OWID grapher CSV (no API key):
    https://ourworldindata.org/grapher/share-electricity-renewables.csv
Underlying data: Ember + Energy Institute Statistical Review of World Energy.
License: CC BY (Our World in Data / Ember). Redistribution with attribution.

This is additive vs the in-repo EIA data, which is US-state-only — OWID gives
the cross-country renewable-electricity-share comparison the EIA set lacks.
Modeled on owid_co2.py, but the grapher CSV has a flat shape
(Entity, Code, Year, <indicator>) rather than the bundled co2-data.csv, so it
gets its own thin fetch/parse here.

New-data-source-checklist notes (docs/new-data-source-checklist.md):
  - Authoritative label: OWID's grapher title ("Share of electricity
    generated from renewables"). PREFLIGHT asserts the CSV header is exactly
    Entity/Code/Year/<value col> before writing, so an OWID reshuffle FAILS
    the refresh instead of silently mislabelling (the owid_co2 pattern). No
    separate audit script — the label is constructed here, not transcribed.
  - Identifier convention: owid_energy/<indicator_slug>_<country_slug>;
    provenance.series = "<csv column> / <iso3>".
  - Canonical units: a percentage (rate), stored as published.

Run: python pipelines/owid_energy.py            (all)
     python pipelines/owid_energy.py world       (filter by country-slug substring)
"""
from __future__ import annotations

import csv
import io
import subprocess
import sys
from pathlib import Path

from common import write_timeseries

# csvType=full returns the long series (all years); the value column is
# "Renewables" (% of electricity from renewable sources).
CSV_URL = (
    "https://ourworldindata.org/grapher/share-electricity-renewables.csv"
    "?csvType=full"
)
VALUE_COL = "Renewables"
SELF_DIR = Path(__file__).resolve().parent
SOURCES_DIR = SELF_DIR.parent / "src" / "content" / "sources" / "owid_energy"

# Reuse owid_co2's curated entity list (largest emitters + EU + World) so the
# climate/energy chips line up across the two OWID providers. (owid country
# name in the CSV "Entity", slug, iso3 for provenance / Code-column match.)
ENTITIES: list[tuple[str, str, str]] = [
    ("World", "world", "OWID_WRL"),
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
    ("European Union (27)", "european_union", "OWID_EU27"),
]

SUPPORTED_DELTAS = ["5y", "10y", "30y"]


def fetch_rows() -> list[dict]:
    res = subprocess.run(
        ["curl", "-sS", "--max-time", "120", CSV_URL],
        capture_output=True, check=True, text=True,
    )
    return list(csv.DictReader(io.StringIO(res.stdout)))


def preflight(header: list[str]) -> None:
    """Fail loudly if OWID reshuffles the grapher CSV — this IS the audit."""
    need = {"Entity", "Code", "Year", VALUE_COL}
    missing = need - set(header)
    if missing:
        raise SystemExit(
            f"OWID grapher CSV schema changed — missing columns: "
            f"{sorted(missing)} (have {header}). Re-check the grapher before "
            "trusting labels."
        )


def yaml_for(country: str, slug: str, iso3: str) -> str:
    data_id = f"renewable_electricity_share_{slug}"
    lines = [
        f'name: "Renewable electricity share — {country}"',
        f"shortName: {country} renewables %",
        f"description: Share of {country}'s electricity generated from renewable "
        "sources (hydro, wind, solar, bioenergy, geothermal), annual. From Our "
        "World in Data, based on Ember and the Energy Institute Statistical Review.",
        "kind: timeseries",
        "pipeline: owid_energy",
        f"dataFile: data/owid_energy/{data_id}.json",
        f'supportedDeltas: {SUPPORTED_DELTAS}'.replace("'", '"'),
        'unit: "%"',
        "formatting:",
        "  style: percent",
        "  decimals: 1",
        "emphasis: change",
        "provenance:",
        "  provider: Our World in Data (Ember; Energy Institute)",
        f"  series: {VALUE_COL} / {iso3}",
        "  url: https://ourworldindata.org/grapher/share-electricity-renewables",
        "  license: CC BY 4.0 (Our World in Data)",
        # No "world" tag — per the owid_co2 / worldbank_extended precedent +
        # the test_source_corpus world-tag invariant, "world" is reserved for
        # true aggregates; per-country series surface via the climate/energy
        # chips + the Generators tab, with the country in the title.
        "tags:",
        "  - energy",
        "  - climate",
        "  - macro",
        "unitClass: rate",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    filters = [a.lower() for a in (argv or [])[1:]]
    rows = fetch_rows()
    if not rows:
        raise SystemExit("OWID renewables CSV came back empty.")
    preflight(list(rows[0].keys()))

    # Index by Code (iso3 / OWID code) and by Entity name; match each curated
    # entity by Code first, then Entity name (covers World + EU aggregates).
    by_code: dict[str, list[dict]] = {}
    by_entity: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("Code"):
            by_code.setdefault(r["Code"], []).append(r)
        by_entity.setdefault(r.get("Entity", ""), []).append(r)

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    missing: list[str] = []
    for country, slug, iso3 in ENTITIES:
        if filters and not any(f in slug for f in filters):
            continue
        crows = by_code.get(iso3) or by_entity.get(country) or []
        if not crows:
            missing.append(f"{country} ({iso3})")
            continue
        points = []
        for r in crows:
            raw = (r.get(VALUE_COL) or "").strip()
            yr = (r.get("Year") or "").strip()
            if not raw or not yr:
                continue
            try:
                v = float(raw)
            except ValueError:
                continue
            points.append({"t": f"{yr}-01-01", "v": round(v, 2)})
        if len(points) < 2:
            missing.append(f"{country} (only {len(points)} pts)")
            continue
        data_id = f"renewable_electricity_share_{slug}"
        write_timeseries(
            pipeline="owid_energy",
            series_id=data_id,
            name=f"Renewable electricity share — {country}",
            points=points,
            unit="%",
        )
        (SOURCES_DIR / f"{data_id}.yaml").write_text(
            yaml_for(country, slug, iso3), encoding="utf-8"
        )
        written += 1
    print(f"owid_energy: wrote {written} renewable-share series (data + YAML).")
    if missing:
        # Surface entities not found rather than silently shipping fewer —
        # an OWID entity-name/code change shows up here.
        print("  not found / too sparse: " + "; ".join(missing), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
