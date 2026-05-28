"""
One-shot scaffolder for the 204 state-level government-employment
source YAMLs (51 entities × 4 categories: total + federal + state-
govt + local-govt). Run once; YAMLs are committed, the script stays
around as documentation. Idempotent — skips existing files.

Sources are placed under src/content/sources/fred/ following the
existing state-slug convention `state_<series>_<lowercase-st>` so
they're picked up by parseStateSourceId + the SourcePicker's
state-chip popover.
"""
from __future__ import annotations
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "content" / "sources" / "fred"

STATES = [
    ("AL", "01", "Alabama"), ("AK", "02", "Alaska"),
    ("AZ", "04", "Arizona"), ("AR", "05", "Arkansas"),
    ("CA", "06", "California"), ("CO", "08", "Colorado"),
    ("CT", "09", "Connecticut"), ("DE", "10", "Delaware"),
    ("DC", "11", "District of Columbia"),
    ("FL", "12", "Florida"), ("GA", "13", "Georgia"),
    ("HI", "15", "Hawaii"), ("ID", "16", "Idaho"),
    ("IL", "17", "Illinois"), ("IN", "18", "Indiana"),
    ("IA", "19", "Iowa"), ("KS", "20", "Kansas"),
    ("KY", "21", "Kentucky"), ("LA", "22", "Louisiana"),
    ("ME", "23", "Maine"), ("MD", "24", "Maryland"),
    ("MA", "25", "Massachusetts"), ("MI", "26", "Michigan"),
    ("MN", "27", "Minnesota"), ("MS", "28", "Mississippi"),
    ("MO", "29", "Missouri"), ("MT", "30", "Montana"),
    ("NE", "31", "Nebraska"), ("NV", "32", "Nevada"),
    ("NH", "33", "New Hampshire"), ("NJ", "34", "New Jersey"),
    ("NM", "35", "New Mexico"), ("NY", "36", "New York"),
    ("NC", "37", "North Carolina"), ("ND", "38", "North Dakota"),
    ("OH", "39", "Ohio"), ("OK", "40", "Oklahoma"),
    ("OR", "41", "Oregon"), ("PA", "42", "Pennsylvania"),
    ("RI", "44", "Rhode Island"), ("SC", "45", "South Carolina"),
    ("SD", "46", "South Dakota"), ("TN", "47", "Tennessee"),
    ("TX", "48", "Texas"), ("UT", "49", "Utah"),
    ("VT", "50", "Vermont"), ("VA", "51", "Virginia"),
    ("WA", "53", "Washington"), ("WV", "54", "West Virginia"),
    ("WI", "55", "Wisconsin"), ("WY", "56", "Wyoming"),
]

# (slug-suffix, series-id-template, friendly-name-template, blurb, kind)
# `kind` is "employment" (thousands of persons, BLS) or "money"
# (thousands USD, Census). Drives the unit + formatting block.
CATEGORIES = [
    (
        "totgovemp",
        "{abbr}GOVT",
        "Total government employment in {name}",
        "All government employees (federal + state + local) "
        "in {name}. Headline public-sector workforce signal "
        "for the state.",
        "employment",
    ),
    (
        "fedgovemp",
        "SMS{fips}000009091000001",
        "Federal government employment in {name}",
        "Federal civilian employees working in {name}, monthly "
        "(BLS SAES). Includes the U.S. Postal Service, which is "
        "~25% of total federal employment nationally.",
        "employment",
    ),
    (
        "stgovemp",
        "SMS{fips}000009092000001",
        "State government employment in {name}",
        "Employees of {name}'s state government (BLS SAES). "
        "Higher education, corrections, transportation, and "
        "regulatory agencies typically dominate.",
        "employment",
    ),
    (
        "locgovemp",
        "SMS{fips}000009093000001",
        "Local government employment in {name}",
        "Employees of city, county, and special-district "
        "governments within {name} (BLS SAES). K-12 school "
        "district payrolls are the largest single component.",
        "employment",
    ),
    (
        "taxrev",
        "QTAXTOTALQTAXCAT3{abbr}NO",
        "State + local total tax collections, {name}",
        "Quarterly state + local tax revenue for {name} "
        "(Census Quarterly Summary of State + Local Tax "
        "Revenue, redistributed via FRED). Income tax + sales "
        "tax + property tax + other; total. Revenue-side "
        "complement to government employment.",
        "money",
    ),
]


def q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def yaml_for(abbr: str, fips: str, state_name: str, cat: tuple) -> str:
    suffix, sid_tmpl, name_tmpl, blurb_tmpl, kind = cat
    sid = sid_tmpl.format(abbr=abbr, fips=fips)
    name = name_tmpl.format(name=state_name)
    blurb = blurb_tmpl.format(name=state_name)
    if kind == "employment":
        provider_phrase = "Public-domain BLS data via FRED"
        provider_line = "  provider: U.S. Bureau of Labor Statistics (BLS) via FRED"
        unit = "thousands of persons"
        style = "number"
        decimals = "1"
        notation = "compact"
        scale_line = None
        tags = ["macro", "labor", "government", "us-state", "us"]
        unit_class = "count"
    else:  # "money" — Census tax revenue
        provider_phrase = "Public-domain Census data via FRED"
        provider_line = "  provider: U.S. Census Bureau via FRED"
        unit = "thousands USD"
        style = "currency"
        decimals = "0"
        notation = "compact"
        scale_line = "  scaleFactor: 1000"  # thousands → raw USD for compact display
        tags = ["macro", "government", "tax", "us-state", "us"]
        unit_class = "currency"
    # Description shouldn't reference internal UI names (SourcePicker,
    # state chip, etc.) — earlier versions of this scaffolder leaked
    # those into 253 YAMLs that had to be stripped post-hoc. The
    # state-tag synthesis in library.json.ts handles the visibility
    # gating; users don't need to know.
    desc = f"{blurb} {provider_phrase}."
    cat_short = {
        "totgovemp": "total govt",
        "fedgovemp": "federal govt",
        "stgovemp": "state govt",
        "locgovemp": "local govt",
        "taxrev": "tax rev",
    }.get(suffix, suffix)
    short = f"{abbr} {cat_short}"
    lines = [
        f"name: {q(name)}",
        f"shortName: {q(short)}",
        f"description: {q(desc)}",
        "kind: timeseries",
        "pipeline: fred_series",
        f"dataFile: data/fred/{sid}.json",
        'supportedDeltas: ["1m", "ytd", "1y", "5y", "10y", "30y"]',
        f'unit: "{unit}"',
        "emphasis: level",
        "formatting:",
        f"  style: {style}",
        f"  decimals: {decimals}",
        f"  notation: {notation}",
    ]
    if scale_line:
        lines.append(scale_line)
    lines.extend([
        "provenance:",
        provider_line,
        f"  series: {sid}",
        f"  url: https://fred.stlouisfed.org/series/{sid}",
        (
            '  license: "Public domain (US government data; see FRED tag '
            "'public domain: citation requested')\""
        ),
        "tags:",
    ])
    for t in tags:
        lines.append(f"  - {t}")
    lines.append(f"unitClass: {unit_class}")
    return "\n".join(lines) + "\n"


def main() -> int:
    SRC.mkdir(parents=True, exist_ok=True)
    created = skipped = 0
    for abbr, fips, state_name in STATES:
        for cat in CATEGORIES:
            suffix = cat[0]
            path = SRC / f"state_{suffix}_{abbr.lower()}.yaml"
            if path.exists():
                skipped += 1
                continue
            path.write_text(
                yaml_for(abbr, fips, state_name, cat),
                encoding="utf-8",
            )
            created += 1
    print(f"Created {created} YAMLs; skipped {skipped} existing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
