"""
One-shot scaffolder for the ACS race-unemployment source YAMLs under
src/content/sources/acs_labor/.

Data comes from pipelines/census_acs_labor.py. Because small race groups
are suppressed in small states (the API returns -999999999, which the
pipeline drops), the set of series that actually exist is < 51 states ×
9 groups. So this scaffolder iterates the DATA FILES that the pipeline
wrote and emits exactly one YAML per data file — guaranteeing YAML↔data
parity rather than scaffolding combinations that have no data.

Per-state IDs (`acs_labor/state_<race>_<st>`) are recognized by
parseStateSourceId, so they're gated behind the composer's state chip;
the national `acs_labor/us_<race>` series stay default-visible and carry
the labor/macro tags.

Idempotent — skips existing files. Run once; YAMLs are committed.
"""
from __future__ import annotations

import re
from pathlib import Path

from census_acs_labor import PIPELINE, RACES, STATES

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "content" / "sources" / PIPELINE
DATA = REPO / "public" / "data" / PIPELINE

RACE_LABEL = {suffix: label for suffix, _code, label in RACES}
RACE_CODE = {suffix: code for suffix, code, _label in RACES}
STATE_NAME = {abbr.lower(): name for abbr, name in STATES.values()}

# Short race tag for the chip/card shortName.
SHORT_RACE = {
    "total": "all", "white": "White", "black": "Black", "aian": "AIAN",
    "asian": "Asian", "nhpi": "NHPI", "otherrace": "other race",
    "multi": "2+ races", "hispanic": "Hispanic",
}
TABLE_URL = "https://data.census.gov/table/ACSST1Y2023.S2301"


def q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def yaml_for(sid: str) -> str | None:
    m_state = re.match(r"^state_(.+)_([a-z]{2})$", sid)
    m_us = re.match(r"^us_(.+)$", sid)
    if m_us and m_us.group(1) in RACE_LABEL:
        race = m_us.group(1)
        label = RACE_LABEL[race]
        if race == "total":
            name = "Unemployment rate — all workers (US)"
            desc_scope = "all workers (ages 16+) nationally"
        else:
            name = f"Unemployment rate — {label} (US)"
            desc_scope = f"{label} workers (ages 16+) nationally"
        short = f"{SHORT_RACE[race]} unemployment (US)"
        tags = ["labor", "macro", "us"]
    elif m_state and m_state.group(1) in RACE_LABEL and m_state.group(2) in STATE_NAME:
        race, st = m_state.group(1), m_state.group(2)
        label = RACE_LABEL[race]
        sname = STATE_NAME[st]
        if race == "total":
            name = f"{sname} unemployment rate — all workers"
            desc_scope = f"all workers (ages 16+) in {sname}"
        else:
            name = f"{sname} unemployment rate — {label}"
            desc_scope = f"{label} workers (ages 16+) in {sname}"
        short = f"{st.upper()} {SHORT_RACE[race]} unemp"
        tags = ["labor", "macro", "us-state", "us"]
    else:
        return None

    desc = (
        f"Unemployment rate among {desc_scope}, Census American Community "
        f"Survey 1-year estimates (Subject Table S2301). ACS is a rolling "
        f"annual survey, so this differs from the monthly BLS state "
        f"unemployment rate."
    )
    code = RACE_CODE[race]
    lines = [
        f"name: {q(name)}",
        f"shortName: {q(short)}",
        f"description: {q(desc)}",
        "kind: timeseries",
        f"pipeline: {PIPELINE}",
        f"dataFile: data/{PIPELINE}/{sid}.json",
        'supportedDeltas: ["1y", "5y"]',
        'unit: "%"',
        "emphasis: level",
        "formatting:",
        "  style: percent",
        "  decimals: 1",
        "provenance:",
        "  provider: U.S. Census Bureau, American Community Survey (ACS 1-year)",
        f"  series: {code} (ACS 1-year Subject Table S2301)",
        f"  url: {TABLE_URL}",
        "  license: Public domain (US government data)",
        "tags:",
    ]
    for t in tags:
        lines.append(f"  - {t}")
    lines.append("unitClass: rate")
    return "\n".join(lines) + "\n"


def main() -> int:
    SRC.mkdir(parents=True, exist_ok=True)
    created = skipped = unknown = 0
    for data_path in sorted(DATA.glob("*.json")):
        sid = data_path.stem
        path = SRC / f"{sid}.yaml"
        if path.exists():
            skipped += 1
            continue
        body = yaml_for(sid)
        if body is None:
            unknown += 1
            print(f"  ?? could not parse id: {sid}")
            continue
        path.write_text(body, encoding="utf-8")
        created += 1
    print(f"Created {created} YAMLs; skipped {skipped} existing; "
          f"{unknown} unparseable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
