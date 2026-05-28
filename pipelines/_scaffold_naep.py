"""
One-shot scaffolder for the NAEP test-score source YAMLs under
src/content/sources/naep/.

Data comes from pipelines/naep_scores.py. Iterates the data files that
exist and emits one YAML each (YAML<->data parity).

Per-state IDs (`naep/state_<metric>_<st>`) are recognized by
parseStateSourceId → gated behind the composer's state chip; national
`naep/us_<metric>` series stay default-visible and carry the education
tag. Idempotent.

Source: NCES NAEP ("the Nation's Report Card") — public domain US
government data.
"""
from __future__ import annotations

import re
from pathlib import Path

from naep_scores import METRICS, PIPELINE, STATES

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "content" / "sources" / PIPELINE
DATA = REPO / "public" / "data" / PIPELINE

METRIC_LABEL = {suffix: label for _subj, _sub, _g, suffix, label in METRICS}
# subject + grade per suffix, for the provenance series string + audit.
METRIC_META = {suffix: (subj, g) for subj, _sub, g, suffix, _label in METRICS}
STATE_NAME = {abbr.lower(): name for abbr, name in STATES}
SHORT_METRIC = {
    "mathg4": "g4 math", "mathg8": "g8 math",
    "readg4": "g4 reading", "readg8": "g8 reading",
}
NAEP_URL = "https://www.nationsreportcard.gov/"


def q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def yaml_for(sid: str) -> str | None:
    m_state = re.match(r"^state_(.+)_([a-z]{2})$", sid)
    m_us = re.match(r"^us_(.+)$", sid)
    if m_us and m_us.group(1) in METRIC_LABEL:
        metric, scope, where = m_us.group(1), "us", "the US"
        name = f"NAEP {METRIC_LABEL[metric]} score (US)"
        short = f"NAEP {SHORT_METRIC[metric]} (US)"
        tags = ["education", "us"]
    elif m_state and m_state.group(1) in METRIC_LABEL and m_state.group(2) in STATE_NAME:
        metric, st = m_state.group(1), m_state.group(2)
        scope, where = "state", STATE_NAME[st]
        name = f"{where} NAEP {METRIC_LABEL[metric]} score"
        short = f"{st.upper()} NAEP {SHORT_METRIC[metric]}"
        tags = ["education", "us-state", "us"]
    else:
        return None

    subj, grade = METRIC_META[metric]
    desc = (
        f"Average NAEP scale score, {METRIC_LABEL[metric]}, for {where}. "
        f"NAEP (\"the Nation's Report Card\", NCES) is administered "
        f"identically in every state, so scores are directly comparable "
        f"across states — unlike each state's own proficiency tests. "
        f"Public-domain US government data."
    )
    lines = [
        f"name: {q(name)}",
        f"shortName: {q(short)}",
        f"description: {q(desc)}",
        "kind: timeseries",
        f"pipeline: {PIPELINE}",
        f"dataFile: data/{PIPELINE}/{sid}.json",
        'supportedDeltas: ["5y", "10y"]',
        'unit: "scale score"',
        "emphasis: level",
        "formatting:",
        "  style: number",
        "  decimals: 0",
        "provenance:",
        "  provider: U.S. Dept. of Education, NCES — NAEP (Nation's Report Card)",
        f"  series: NAEP {subj} grade {grade} mean scale score",
        f"  url: {NAEP_URL}",
        "  license: Public domain (US government data)",
        "tags:",
    ]
    for t in tags:
        lines.append(f"  - {t}")
    lines.append("unitClass: index")
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
    print(f"Created {created} YAMLs; skipped {skipped}; {unknown} unparseable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
