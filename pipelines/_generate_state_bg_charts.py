"""
Auto-generate per-state block-group choropleth chart YAMLs.

Parallel to _generate_state_tract_charts.py but for the block-group
geography. Census suppresses 2 of the 4 ACS indicators we publish at
the BG level (B17001 poverty universe + B05002 place of birth) — only
median_hh_income and bachelors_plus_pct have nationwide BG data. So
this generator emits 2 × 51 = 102 chart YAMLs instead of 4 × 51.

Each chart references the per-state BG TopoJSON
(<st>-block-groups-topo.json) committed in the BG-topology-generator
run, plus the per-state BG ACS data file (data/acs_block_group/<st>/
<indicator>_2022.json).

Run: ``python pipelines/_generate_state_bg_charts.py``
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "src" / "content" / "charts" / "state-bg-maps"

# 50 states + DC, matching pipelines/_generate_state_tract_charts.py.
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

# Only 2 indicators have BG-level coverage (Census suppresses the other
# 2 ACS indicators we publish at BG geo via disclosure-avoidance).
INDICATORS = [
    (
        "median_hh_income",
        "median household income",
        "greens",
        "median pre-tax money income at block-group resolution — "
        "finer than tract-level. Darker green = higher income.",
    ),
    (
        "bachelors_plus_pct",
        "bachelor's-or-higher share",
        "blues",
        "share of adults 25+ with at least a bachelor's degree at "
        "block-group resolution. Darker blue = higher educational "
        "attainment.",
    ),
]


def write_chart(state_code: str, state_name: str, indicator: str,
                label: str, scheme: str, blurb_snippet: str) -> Path:
    out_path = OUT_DIR / f"{state_code.lower()}_{indicator}_bg_2022.yaml"
    title = f"{label.capitalize()} by census block group — {state_name} (2022)"
    content = f"""title: {title}
render: choropleth
geo: block-group
states: [{state_code}]
indicator: {indicator}
vintage: "2022"
boundaryFile: /maps/{state_code.lower()}-block-groups-topo.json
colorScheme: {scheme}
colorScale: linear
tags: [demographics, state-bg-map, {indicator.replace("_", "-")}, {state_code.lower()}]
blurb: |
  Block-group-level {blurb_snippet} ACS 5-year ending 2022.
  Block-groups divide a census tract into 1-4 sub-units of ~600-3,000
  residents each — the finest geography ACS publishes for income
  and education. Click to expand; the dialog supports zoom, pan,
  and a color-scheme picker.
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
    print(f"Wrote {written} per-state BG chart YAMLs under "
          f"{OUT_DIR.relative_to(ROOT)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
