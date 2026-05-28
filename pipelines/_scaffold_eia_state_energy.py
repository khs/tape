"""
One-shot scaffolder for the EIA state electricity-generation YAMLs under
src/content/sources/eia_state_energy/.

Data comes from pipelines/eia_state_energy.py. Because some (state, fuel)
combinations have no generation (no nuclear in many states, no wind in
others) the pipeline only writes series with >= 2 points, so this
scaffolder iterates the DATA FILES that exist and emits one YAML each —
guaranteeing YAML<->data parity.

Per-state IDs (`eia_state_energy/state_<fuel>_<st>`) are recognized by
parseStateSourceId and gated behind the composer's state chip; the
national `eia_state_energy/us_<fuel>` series stay default-visible and
carry the energy tag.

Idempotent — skips existing files.
"""
from __future__ import annotations

import re
from pathlib import Path

from eia_state_energy import FUELS, PIPELINE, STATE_NAME

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "content" / "sources" / PIPELINE
DATA = REPO / "public" / "data" / PIPELINE

FUEL_CODE = {suffix: code for suffix, code, _label in FUELS}
# IDs use lowercase postal codes; STATE_NAME is keyed uppercase.
STATE_NAME_LC = {abbr.lower(): name for abbr, name in STATE_NAME.items()}
# Name fragment (mid-sentence) per fuel.
FUEL_FRAG = {
    "all": "", "gas": "natural-gas", "coal": "coal", "nuclear": "nuclear",
    "wind": "wind", "solar": "solar", "hydro": "hydroelectric",
}
SHORT_FUEL = {
    "all": "generation", "gas": "gas gen", "coal": "coal gen",
    "nuclear": "nuclear gen", "wind": "wind gen", "solar": "solar gen",
    "hydro": "hydro gen",
}
BROWSER_URL = "https://www.eia.gov/electricity/data/browser/"


def q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def yaml_for(sid: str) -> str | None:
    m_state = re.match(r"^state_(.+)_([a-z]{2})$", sid)
    m_us = re.match(r"^us_(.+)$", sid)
    if m_us and m_us.group(1) in FUEL_CODE:
        fuel, scope, sname = m_us.group(1), "us", "the US"
        tags = ["energy", "us"]
    elif m_state and m_state.group(1) in FUEL_CODE and m_state.group(2) in STATE_NAME_LC:
        fuel, st = m_state.group(1), m_state.group(2)
        scope, sname = "state", STATE_NAME_LC[st]
        tags = ["energy", "us-state", "us"]
    else:
        return None

    frag = FUEL_FRAG[fuel]
    if fuel == "all":
        name = (f"US electricity net generation" if scope == "us"
                else f"{sname} electricity net generation")
        desc_src = "all fuels"
    else:
        name = (f"US {frag.replace('-', ' ')} electricity generation" if scope == "us"
                else f"{sname} {frag.replace('-', ' ')} electricity generation")
        desc_src = f"{frag.replace('-', ' ')}"
    short = (f"US {SHORT_FUEL[fuel]}" if scope == "us"
             else f"{m_state.group(2).upper()} {SHORT_FUEL[fuel]}")
    where = "the US" if scope == "us" else sname
    if fuel == "all":
        desc = (f"Total net electricity generation in {where}, all fuels and "
                f"sectors, U.S. Energy Information Administration. Annual.")
    else:
        desc = (f"Net electricity generation from {desc_src} in {where}, all "
                f"sectors, U.S. Energy Information Administration. Annual.")

    loc = "US" if scope == "us" else m_state.group(2).upper()
    code = FUEL_CODE[fuel]
    lines = [
        f"name: {q(name)}",
        f"shortName: {q(short)}",
        f"description: {q(desc)}",
        "kind: timeseries",
        f"pipeline: {PIPELINE}",
        f"dataFile: data/{PIPELINE}/{sid}.json",
        'supportedDeltas: ["1y", "5y", "10y"]',
        'unit: "TWh"',
        "emphasis: level",
        "formatting:",
        "  style: number",
        "  decimals: 1",
        "  suffix: ' TWh'",
        "provenance:",
        "  provider: U.S. Energy Information Administration (EIA)",
        f"  series: EIA electricity generation; fueltypeid={code}; location={loc}",
        f"  url: {BROWSER_URL}",
        "  license: Public domain (US government data)",
        "tags:",
    ]
    for t in tags:
        lines.append(f"  - {t}")
    lines.append("unitClass: count")
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
