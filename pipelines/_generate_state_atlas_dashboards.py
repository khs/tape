"""
Generate four regional "State Atlas" dashboards that surface the 204
per-state tract maps from the state-tract-maps chart library.

Census regions:
  Northeast  9 states (CT ME MA NH NJ NY PA RI VT)
  Midwest    12 states (IL IN IA KS MI MN MO NE ND OH SD WI)
  South      17 jurisdictions (AL AR DE DC FL GA KY LA MD MS NC OK SC TN TX VA WV)
  West       13 states (AK AZ CA CO HI ID MT NV NM OR UT WA WY)

Per dashboard: one section per state, four charts each (poverty rate,
median household income, bachelor's-or-higher share, foreign-born
share). Page weight is ~36-68 tiles depending on region — heavy but
not so heavy that the tile-payload summary mode (commit cdf057db
era) can't keep it under a few hundred KB.

Idempotent: re-running overwrites the four MDX files in place.

Run: ``python pipelines/_generate_state_atlas_dashboards.py``
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "src" / "content" / "dashboards"

# Census Bureau region assignments. Source:
# https://www2.census.gov/geo/pdfs/maps-data/maps/reference/us_regdiv.pdf
REGIONS: dict[str, dict] = {
    "northeast": {
        "title": "State Atlas — Northeast",
        "order": 10,
        "states": [
            ("CT", "Connecticut"), ("ME", "Maine"), ("MA", "Massachusetts"),
            ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NY", "New York"),
            ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("VT", "Vermont"),
        ],
        "description": (
            "Tract-level ACS demographics for the nine Census Bureau "
            "Northeast region states. Each state has four indicator "
            "maps: poverty rate, median household income, bachelor's-"
            "or-higher share, and foreign-born share, all at vintage 2022."
        ),
    },
    "midwest": {
        "title": "State Atlas — Midwest",
        "order": 11,
        "states": [
            ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
            ("KS", "Kansas"), ("MI", "Michigan"), ("MN", "Minnesota"),
            ("MO", "Missouri"), ("NE", "Nebraska"), ("ND", "North Dakota"),
            ("OH", "Ohio"), ("SD", "South Dakota"), ("WI", "Wisconsin"),
        ],
        "description": (
            "Tract-level ACS demographics for the twelve Census Bureau "
            "Midwest region states. Each state has four indicator maps "
            "at vintage 2022."
        ),
    },
    "south": {
        "title": "State Atlas — South",
        "order": 12,
        "states": [
            ("AL", "Alabama"), ("AR", "Arkansas"), ("DE", "Delaware"),
            ("DC", "DC"), ("FL", "Florida"), ("GA", "Georgia"),
            ("KY", "Kentucky"), ("LA", "Louisiana"), ("MD", "Maryland"),
            ("MS", "Mississippi"), ("NC", "North Carolina"),
            ("OK", "Oklahoma"), ("SC", "South Carolina"),
            ("TN", "Tennessee"), ("TX", "Texas"), ("VA", "Virginia"),
            ("WV", "West Virginia"),
        ],
        "description": (
            "Tract-level ACS demographics for the sixteen Census Bureau "
            "South region states plus DC. Each jurisdiction has four "
            "indicator maps at vintage 2022."
        ),
    },
    "west": {
        "title": "State Atlas — West",
        "order": 13,
        "states": [
            ("AK", "Alaska"), ("AZ", "Arizona"), ("CA", "California"),
            ("CO", "Colorado"), ("HI", "Hawaii"), ("ID", "Idaho"),
            ("MT", "Montana"), ("NV", "Nevada"), ("NM", "New Mexico"),
            ("OR", "Oregon"), ("UT", "Utah"), ("WA", "Washington"),
            ("WY", "Wyoming"),
        ],
        "description": (
            "Tract-level ACS demographics for the thirteen Census "
            "Bureau West region states. Each state has four indicator "
            "maps at vintage 2022."
        ),
    },
}

# Indicator id -> short label used in the per-state section descriptions.
INDICATORS: list[tuple[str, str]] = [
    ("poverty_rate", "poverty rate"),
    ("median_hh_income", "median household income"),
    ("bachelors_plus_pct", "bachelor's-or-higher share"),
    ("foreign_born_pct", "foreign-born share"),
]

# Block-group indicators — Census only publishes 2 of the 4 at BG
# level (B17001 poverty universe and B05002 place of birth are
# suppressed at BG by disclosure-avoidance). The BG charts are
# referenced from the chart-library directory state-bg-maps/, which
# pipelines/_generate_state_bg_charts.py populates.
BG_INDICATORS: list[tuple[str, str]] = [
    ("median_hh_income", "median household income (BG)"),
    ("bachelors_plus_pct", "bachelor's-or-higher share (BG)"),
]


def section_for_state(code: str, name: str) -> str:
    """Render a single state's section: 4 tract charts + 2 BG charts.
    Block-group charts appear after the tract charts so the user
    reads coarser-then-finer geography down the column."""
    tract_ids = [
        f"      - state-tract-maps/{code.lower()}_{ind}_2022"
        for ind, _ in INDICATORS
    ]
    bg_ids = [
        f"      - state-bg-maps/{code.lower()}_{ind}_bg_2022"
        for ind, _ in BG_INDICATORS
    ]
    chart_lines = "\n".join(tract_ids + bg_ids)
    return (
        f"  - title: \"{name}\"\n"
        f"    charts:\n{chart_lines}\n"
    )


def render_dashboard(slug: str, spec: dict) -> str:
    sections = "\n".join(
        section_for_state(code, name) for code, name in spec["states"]
    )
    indicator_list = ", ".join(label for _, label in INDICATORS)
    return f"""---
title: "{spec['title']}"
order: {spec['order']}
defaultDelta: 1y
description: "{spec['description']}"
aboutBlurb: "Per-state tract maps for the four ACS 5-year indicators: {indicator_list}. Boundaries are Census TIGER 2024 tracts, simplified for client-side render. Data is ACS 5-year ending 2022."
sections:
{sections}---

## How to use this atlas

Each state's section has the same four maps:

| Map | Indicator | Source |
|---|---|---|
| Poverty rate | Share of population in poverty (B17001) | ACS 5-year 2018-2022 |
| Median household income | B19013 | ACS 5-year 2018-2022 |
| Bachelor's-or-higher | Share of 25+ adults with BA+ (B15003) | ACS 5-year 2018-2022 |
| Foreign-born share | Born outside US (B05002) | ACS 5-year 2018-2022 |

Click any tile to expand into a full-screen map with:

- **Hover** over a tract to see its name + value
- **Scroll** or **+/−** keys to zoom
- **Drag** to pan
- A **color-scheme picker** for alternative palettes
- A **vintage year slider** (when older vintages are on disk for the
  state — backfilling as the data refresh workflow runs)

## Why hatched tracts?

Some tracts render with grey diagonal stripes instead of a color:

- **Special land-use tracts** (6-digit code starting with 98) — the
  CIA Langley campus, military bases, national parks, water bodies,
  airports. Census reserves 9800-series tract numbers for places with
  no resident population, so ACS publishes no demographics for them.
- **Newly-split tracts** (e.g., Fairfax 4405.04) — the topology
  includes the post-2020 split but the ACS vintage's sample frame
  didn't, so values aren't published yet.

Hover any hatched tract for the specific explanation.

## Other regions

| Region | Dashboard |
|---|---|
| Northeast | [/state-atlas-northeast/](/state-atlas-northeast/) |
| Midwest | [/state-atlas-midwest/](/state-atlas-midwest/) |
| South | [/state-atlas-south/](/state-atlas-south/) |
| West | [/state-atlas-west/](/state-atlas-west/) |
"""


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for slug, spec in REGIONS.items():
        out_path = OUT_DIR / f"state-atlas-{slug}.mdx"
        out_path.write_text(render_dashboard(slug, spec), encoding="utf-8")
        n = len(spec["states"]) * len(INDICATORS)
        print(f"Wrote {out_path.relative_to(ROOT)} "
              f"({len(spec['states'])} states, {n} tiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
