"""
One-shot scaffolder for the K-12 per-pupil-spending source YAMLs under
src/content/sources/edu_spending/.

Data comes from pipelines/edu_spending.py. Iterates the data files and
emits one YAML each (YAML<->data parity).

Per-state IDs (`edu_spending/state_perpupil_<st>`) are gated behind the
state chip; `edu_spending/us_perpupil` stays default-visible.

Attribution (per the provider ToS sweep): the underlying data is NCES
Common Core of Data (F-33), public domain, delivered via the Urban
Institute Education Data Portal under ODC-BY 1.0 — which requires citing
both Urban and the dataset. We credit both. Idempotent.
"""
from __future__ import annotations

import re
from pathlib import Path

from edu_spending import PIPELINE, STATES

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "content" / "sources" / PIPELINE
DATA = REPO / "public" / "data" / PIPELINE

STATE_NAME = {abbr.lower(): name for abbr, name in STATES.values()}
URBAN_URL = "https://educationdata.urban.org/"
# ODC-BY requires citing Urban + the dataset; this is the license string
# users see on each source page.
LICENSE = ("ODC-BY 1.0 — NCES Common Core of Data (public domain) via "
           "Urban Institute Education Data Portal; cite both")


def q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def yaml_for(sid: str) -> str | None:
    m_state = re.match(r"^state_perpupil_([a-z]{2})$", sid)
    if sid == "us_perpupil":
        name = "K-12 spending per pupil (US)"
        short = "US per-pupil K-12"
        where = "the US"
        tags = ["education", "fiscal", "us"]
    elif m_state and m_state.group(1) in STATE_NAME:
        st = m_state.group(1)
        where = STATE_NAME[st]
        name = f"{where} K-12 spending per pupil"
        short = f"{st.upper()} per-pupil K-12"
        tags = ["education", "fiscal", "us-state", "us"]
    else:
        return None

    desc = (
        f"Current spending per pupil on K-12 public education in {where} — "
        f"total current expenditure divided by fall enrollment. NCES Common "
        f"Core of Data (F-33 school-system finance), via the Urban Institute "
        f"Education Data Portal."
    )
    lines = [
        f"name: {q(name)}",
        f"shortName: {q(short)}",
        f"description: {q(desc)}",
        "kind: timeseries",
        f"pipeline: {PIPELINE}",
        f"dataFile: data/{PIPELINE}/{sid}.json",
        'supportedDeltas: ["1y", "5y", "10y"]',
        'unit: "USD"',
        "emphasis: level",
        "formatting:",
        "  style: currency",
        "  currency: USD",
        "  decimals: 0",
        "provenance:",
        "  provider: NCES Common Core of Data, via Urban Institute Education Data Portal",
        "  series: CCD F-33 current spending per pupil (exp_current_elsec_total / enrollment)",
        f"  url: {URBAN_URL}",
        f"  license: {q(LICENSE)}",
        "tags:",
    ]
    for t in tags:
        lines.append(f"  - {t}")
    lines.append("unitClass: currency")
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
