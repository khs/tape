"""
Generate source YAMLs for the BLS LAUS state labor-force series added in
bls.state_labor_force_specs() (employment / labor-force levels + the
employment-population ratio + labor-force participation rate, per state).

The other ~766 bls source YAMLs are hand-committed with no generator; this
family is large + uniform (5 measures x 51 states) so it gets a generator
for reproducibility. Run AFTER `python pipelines/bls.py <subset tokens>`
has written the data JSONs — a YAML is emitted only for a series whose data
file actually exists, so a state/measure the API didn't return is skipped
rather than pointing at a missing file.

Shape mirrors the existing LAUS series (state_unemployment_*.yaml): same
provider string so the source page groups them, same tag set, same
percent/count formatting conventions. Idempotent — overwrites in place.

Run with: ``python pipelines/_generate_bls_state_labor_sources.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bls  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "public" / "data" / "bls"
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "bls"

# Per-measure presentation metadata, keyed by the out_id stem used in
# bls.LAUS_MEASURES. {name}/{abbr} are filled per state.
PRESENTATION: dict[str, dict] = {
    "unemployed": {
        "name": "{name} unemployment level",
        "short": "{abbr} unemployed",
        "desc": (
            "Local Area Unemployment Statistics, {name} unemployment level "
            "(number of people unemployed), monthly, seasonally adjusted."
        ),
        "unit": "people",
        "style": "number",
        "decimals": 0,
        "compact": True,
        "unitClass": "count",
    },
    "employed": {
        "name": "{name} employment level",
        "short": "{abbr} employed",
        "desc": (
            "Local Area Unemployment Statistics, {name} employment level "
            "from the household survey, monthly, seasonally adjusted."
        ),
        "unit": "people",
        "style": "number",
        "decimals": 0,
        "compact": True,
        "unitClass": "count",
    },
    "labor_force": {
        "name": "{name} labor force",
        "short": "{abbr} labor force",
        "desc": (
            "Local Area Unemployment Statistics, {name} labor force level, "
            "monthly, seasonally adjusted."
        ),
        "unit": "people",
        "style": "number",
        "decimals": 0,
        "compact": True,
        "unitClass": "count",
    },
    "emp_pop_ratio": {
        "name": "{name} employment-population ratio",
        "short": "{abbr} emp-pop ratio",
        "desc": (
            "Local Area Unemployment Statistics, {name} "
            "employment-population ratio, monthly, seasonally adjusted."
        ),
        "unit": "%",
        "style": "percent",
        "decimals": 1,
        "compact": False,
        "unitClass": "rate",
    },
    "lfpr": {
        "name": "{name} labor force participation rate",
        "short": "{abbr} participation",
        "desc": (
            "Local Area Unemployment Statistics, {name} labor force "
            "participation rate, monthly, seasonally adjusted."
        ),
        "unit": "%",
        "style": "percent",
        "decimals": 1,
        "compact": False,
        "unitClass": "rate",
    },
}


def yaml_for(out_id: str, series_id: str, stem: str, abbr: str, name: str) -> str:
    p = PRESENTATION[stem]
    disp_name = p["name"].format(name=name, abbr=abbr)
    short = p["short"].format(name=name, abbr=abbr)
    desc = p["desc"].format(name=name, abbr=abbr)
    unit_line = 'unit: "%"' if p["unit"] == "%" else f"unit: {p['unit']}"
    fmt = f"  style: {p['style']}\n  decimals: {p['decimals']}"
    if p["compact"]:
        fmt += "\n  notation: compact"
    return (
        f"name: {disp_name}\n"
        f"shortName: {short}\n"
        f'description: "{desc}"\n'
        f"kind: timeseries\n"
        f"pipeline: bls\n"
        f"dataFile: data/bls/{out_id}.json\n"
        f'supportedDeltas: ["1m", "ytd", "1y", "5y", "10y"]\n'
        f"{unit_line}\n"
        f"formatting:\n{fmt}\n"
        f"emphasis: change\n"
        f"provenance:\n"
        f"  provider: U.S. Bureau of Labor Statistics\n"
        f"  series: {series_id}\n"
        f"  url: https://data.bls.gov/timeseries/{series_id}\n"
        f"  license: Public domain (US government data)\n"
        f"tags:\n"
        f"  - labor\n"
        f"  - macro\n"
        f"  - us\n"
        f"unitClass: {p['unitClass']}\n"
    )


def main() -> int:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for fips, (abbr, name) in bls.US_STATES.items():
        for code, stem, _suffix, _unit in bls.LAUS_MEASURES:
            out_id = f"state_{stem}_{abbr.lower()}"
            series_id = f"LASST{fips}0000000000{code}"
            if not (DATA_DIR / f"{out_id}.json").exists():
                print(f"  skip {out_id}: no data file", file=sys.stderr)
                skipped += 1
                continue
            (SOURCES_DIR / f"{out_id}.yaml").write_text(
                yaml_for(out_id, series_id, stem, abbr, name), encoding="utf-8"
            )
            written += 1
    print(f"Wrote {written} YAMLs, skipped {skipped} (no data file).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
