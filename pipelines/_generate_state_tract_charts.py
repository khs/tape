"""
Auto-generate per-state tract choropleth chart YAMLs.

After committing per-state tract topology files (commit edfb4a26bf)
and per-state tract data (commit 4cf8f2be03), every state has the
ingredients for tract-resolution maps. This script materializes the
chart YAMLs that put those ingredients together.

For each state × each of the 4 ACS indicators we publish at tract
level, write a chart YAML at:

  src/content/charts/state-tract-maps/<state>_<indicator>_2022.yaml

Idempotent: re-running overwrites in place. Files are kept under a
single directory so they're easy to bulk-delete if the user decides
they're too noisy in the library.

Run with: ``python pipelines/_generate_state_tract_charts.py``.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "src" / "content" / "charts" / "state-tract-maps"

# 50 states + DC, with full names for chart titles.
STATES: list[tuple[str, str]] = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"),
    ("AR", "Arkansas"), ("CA", "California"), ("CO", "Colorado"),
    ("CT", "Connecticut"), ("DE", "Delaware"), ("DC", "DC"),
    ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"),
    ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"),
    ("IA", "Iowa"), ("KS", "Kansas"), ("KY", "Kentucky"),
    ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"),
    ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"),
    ("NE", "Nebraska"), ("NV", "Nevada"), ("NH", "New Hampshire"),
    ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
    ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
    ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"), ("SC", "South Carolina"),
    ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"),
    ("UT", "Utah"), ("VT", "Vermont"), ("VA", "Virginia"),
    ("WA", "Washington"), ("WV", "West Virginia"),
    ("WI", "Wisconsin"), ("WY", "Wyoming"),
]

# (out_id, human label, color scheme, blurb snippet)
INDICATORS = [
    (
        "poverty_rate",
        "poverty rate",
        "reds",
        "ratio of people in poverty to the universe for whom poverty "
        "status is determined. Darker red = higher poverty rate.",
    ),
    (
        "median_hh_income",
        "median household income",
        "greens",
        "median pre-tax money income of the householder and other "
        "household members. Darker green = higher income.",
    ),
    (
        "bachelors_plus_pct",
        "bachelor's-or-higher share",
        "blues",
        "share of adults 25+ with at least a bachelor's degree. "
        "Darker blue = higher educational attainment.",
    ),
    (
        "foreign_born_pct",
        "foreign-born share",
        "purples",
        "share of residents born outside the US. Darker purple = "
        "larger foreign-born population share.",
    ),
]


def write_chart(state_code: str, state_name: str, indicator: str,
                label: str, scheme: str, blurb_snippet: str) -> Path:
    out_path = OUT_DIR / f"{state_code.lower()}_{indicator}_2022.yaml"
    title = f"{label.capitalize()} by census tract — {state_name} (2022)"
    content = f"""title: {title}
render: choropleth
geo: tract
states: [{state_code}]
indicator: {indicator}
vintage: "2022"
boundaryFile: /maps/{state_code.lower()}-tracts-topo.json
colorScheme: {scheme}
colorScale: linear
tags: [demographics, state-tract-map, {indicator.replace("_", "-")}, {state_code.lower()}]
blurb: |
  Tract-level {blurb_snippet} ACS 5-year ending 2022. The tract
  boundary file is derived from Census TIGER {2024} tract shapes;
  joined to ACS data on 11-digit GEOID. Click a tile to expand; the
  expanded view supports zoom, pan, and a color-scheme picker for
  alternative palettes.
"""
    out_path.write_text(content, encoding="utf-8")
    return out_path


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for code, name in STATES:
        for out_id, label, scheme, blurb in INDICATORS:
            write_chart(code, name, out_id, label, scheme, blurb)
            written += 1
    print(f"Wrote {written} per-state tract chart YAMLs under "
          f"{OUT_DIR.relative_to(ROOT)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
