"""
One-shot scaffolder for the Census state-government-finance source
YAMLs: 5 national (``us_<suffix>``) + 50 states × 5 aggregates
(``state_<suffix>_<st>``) = 255 sources under
src/content/sources/census_govfin/.

Data is produced by pipelines/census_govfin.py; this only writes the
metadata YAMLs. Run once; the YAMLs are committed and the script
stays as documentation. Idempotent — skips existing files.

The per-state IDs (``census_govfin/state_<series>_<st>``) are
recognized by parseStateSourceId, so library.json.ts gives them the
synthetic ``us-state`` tag — they're hidden from the default browse
view and surface only under the composer's state chip. The national
``us_<suffix>`` sources stay default-visible and double as the
default-visible carriers for the ``fiscal`` / ``government`` topical
pills (which the build-time zero-count guard requires).
"""
from __future__ import annotations

from pathlib import Path

from census_govfin import AGGREGATES, STATES, PIPELINE

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "content" / "sources" / PIPELINE

# Short noun for the chip/card shortName (the long `noun` from
# AGGREGATES is for the full name + prose).
SHORT_NOUN = {
    "totrev": "revenue",
    "totexp": "total exp",
    "genexp": "general exp",
    "welfexp": "welfare",
    "hwyexp": "highways",
}

PROGRAM_URL = "https://www.census.gov/programs-surveys/state.html"
# Shared closing sentence — states the scope honestly (this is the
# state-government layer, not state+local). Data semantics, not an
# internal-implementation leak, so it belongs in the description.
SCOPE = (
    "Census Annual Survey of State Government Finances; the "
    "state-government layer only, excluding local and federal "
    "spending. Public-domain US government data."
)


def q(s: str) -> str:
    """Single-quote a YAML scalar, escaping embedded single quotes."""
    return "'" + s.replace("'", "''") + "'"


def yaml_for(scope_kind: str, abbr: str, name: str, agg: tuple) -> str:
    suffix, code, noun, blurb = agg
    if scope_kind == "us":
        sid = f"us_{suffix}"
        full_name = f"State governments' {noun} (US total)"
        short = f"State govt {SHORT_NOUN[suffix]} (US)"
        desc = f"{blurb}, summed across all 50 state governments. {SCOPE}"
        tags = ["fiscal", "government", "us"]
    else:  # "state"
        sid = f"state_{suffix}_{abbr.lower()}"
        full_name = f"{name} state government {noun}"
        short = f"{abbr} state {SHORT_NOUN[suffix]}"
        desc = f"{blurb}, for {name}'s state government. {SCOPE}"
        tags = ["fiscal", "government", "us-state", "us"]

    lines = [
        f"name: {q(full_name)}",
        f"shortName: {q(short)}",
        f"description: {q(desc)}",
        "kind: timeseries",
        f"pipeline: {PIPELINE}",
        f"dataFile: data/{PIPELINE}/{sid}.json",
        'supportedDeltas: ["1y", "5y", "10y"]',
        'unit: "billions USD"',
        "emphasis: change",
        "formatting:",
        "  style: currency",
        "  currency: USD",
        "  decimals: 1",
        "  suffix: ' B'",
        "provenance:",
        "  provider: U.S. Census Bureau, Annual Survey of State Government Finances",
        f"  series: govsstatefin {code}",
        f"  url: {PROGRAM_URL}",
        "  license: Public domain (US government data)",
        "tags:",
    ]
    for t in tags:
        lines.append(f"  - {t}")
    lines.append("unitClass: currency")
    return "\n".join(lines) + "\n"


def main() -> int:
    SRC.mkdir(parents=True, exist_ok=True)
    created = skipped = 0

    # National.
    for agg in AGGREGATES:
        path = SRC / f"us_{agg[0]}.yaml"
        if path.exists():
            skipped += 1
            continue
        path.write_text(yaml_for("us", "", "", agg), encoding="utf-8")
        created += 1

    # Per state.
    for abbr, _fips, name in STATES:
        for agg in AGGREGATES:
            path = SRC / f"state_{agg[0]}_{abbr.lower()}.yaml"
            if path.exists():
                skipped += 1
                continue
            path.write_text(yaml_for("state", abbr, name, agg), encoding="utf-8")
            created += 1

    print(f"Created {created} YAMLs; skipped {skipped} existing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
