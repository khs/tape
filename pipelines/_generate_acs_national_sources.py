"""
Generate source-metadata YAML files for ACS national-level data.

census_acs_national.py drops JSON files into public/data/acs_national/
named ``<indicator>_us.json``. Astro's content layer needs a matching
YAML in src/content/sources/acs_national/<indicator>_us.yaml for each
one to be discoverable by the composer + renderable in charts.

This script scans the data directory and fills in any missing YAMLs.
Idempotent: doesn't overwrite. Re-run after extending INDICATORS in
census_acs_cd.py (which census_acs_national.py imports from).

Run with: ``python pipelines/_generate_acs_national_sources.py``
"""
from __future__ import annotations

from pathlib import Path

from _generate_acs_sources import INDICATORS


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "public" / "data" / "acs_national"
SOURCES_DIR = ROOT / "src" / "content" / "sources" / "acs_national"


def description_for(ind: dict) -> str:
    """One-sentence-ish description for a national-level series."""
    table = ind["table"]
    return (
        f"{ind['name_prefix']} (US national level). From the American "
        f"Community Survey 5-year estimates (table {table}), released "
        f"annually."
    )


def render_yaml(ind: dict) -> str:
    name = f"{ind['name_prefix']} — US"
    short = f"US {ind['short_suffix']}"
    desc = description_for(ind)
    tags = ["government", "us"] + list(ind.get("extra_tags", []))

    lines: list[str] = [
        f"name: {name}",
        f"shortName: {short}",
        f"description: {desc}",
        "kind: timeseries",
        "pipeline: census_acs_national",
        f"dataFile: data/acs_national/{ind['out_id']}_us.json",
        'supportedDeltas: ["5y", "10y"]',
        f"unit: {ind['unit']}",
        "formatting:",
        f"  style: {ind['fmt_style']}",
    ]
    if ind.get("currency"):
        lines.append(f"  currency: {ind['currency']}")
    lines.append(f"  decimals: {ind['decimals']}")
    if ind.get("notation"):
        lines.append(f"  notation: {ind['notation']}")
    lines.append("emphasis: change")
    lines.append("provenance:")
    lines.append("  provider: US Census Bureau (ACS 5-year)")
    lines.append(f"  series: {ind['out_id']}_us")
    lines.append("  url: https://api.census.gov/data/2022/acs/acs5")
    lines.append("  license: Public domain (US government data)")
    lines.append("tags:")
    for tag in tags:
        lines.append(f"  - {tag}")
    if ind.get("unit_class"):
        lines.append(f"unitClass: {ind['unit_class']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    for ind in INDICATORS:
        data_file = DATA_DIR / f"{ind['out_id']}_us.json"
        if not data_file.exists():
            # No national data yet — skip until census_acs_national has run.
            continue
        yaml_path = SOURCES_DIR / f"{ind['out_id']}_us.yaml"
        if yaml_path.exists():
            skipped += 1
            continue
        yaml_path.write_text(render_yaml(ind), encoding="utf-8")
        written += 1
    print(f"Wrote {written} new national-level source YAMLs ({skipped} already existed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
