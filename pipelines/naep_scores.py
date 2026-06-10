"""
NAEP (National Assessment of Educational Progress, "the Nation's Report
Card") state test scores — per state + national, by subject and grade.

The canonical measure of K-12 *outcomes* that's comparable across
states: NAEP administers the same assessment everywhere, so unlike state
proficiency tests the scores mean the same thing in every state. We pull
the four headline metrics — grade 4 and grade 8, mathematics and reading
— as mean scale scores (NAEP 0-500 scale).

Source: NCES NAEP Data Service (nationsreportcard.gov). Public domain
(US government data). The GetAdhocData endpoint is open / unkeyed.

Query shape (one call returns every assessment year for a metric +
jurisdiction):
  GetAdhocData.aspx?type=data&subject=mathematics&grade=8
    &subscale=MRPCM&variable=TOTAL&stattype=MN:MN
    &jurisdiction=CA&Year=2003,2005,...,2024
  -> result: [{year, value (mean scale score), errorFlag, ...}, ...]

Notes:
  - Math subscale = MRPCM, reading = RRPCM; variable=TOTAL is "all
    students"; stattype MN:MN is the mean score.
  - State-level NAEP runs in odd years 2003-2019, then 2022 and 2024
    (the schedule shifted post-COVID). We request a superset of years
    and keep whatever comes back with errorFlag==0.
  - Jurisdiction codes: 2-letter postal for states (+ DC); national
    public = "NP".
  - Scores stored verbatim (e.g. 269.8); unit "scale score",
    unitClass "index" (a scaled score, not an additive quantity).

Source YAMLs are emitted INLINE (one per written series, right after the
data file) into src/content/sources/naep/ — overwrite-always; the dir is
pipeline-owned. This replaced the one-shot _scaffold_naep.py (Plan 7).

Run: `python pipelines/naep_scores.py` (no key needed).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import _env  # noqa: F401 — harmless; NAEP needs no key

from common import cached_get, write_timeseries

PIPELINE = "naep"
BASE = "https://www.nationsreportcard.gov/DataService/GetAdhocData.aspx"
YEARS = "2003,2005,2007,2009,2011,2013,2015,2017,2019,2022,2024"

# (subject, subscale, grade, suffix, friendly metric label)
METRICS = [
    ("mathematics", "MRPCM", 4, "mathg4", "grade 4 math"),
    ("mathematics", "MRPCM", 8, "mathg8", "grade 8 math"),
    ("reading",     "RRPCM", 4, "readg4", "grade 4 reading"),
    ("reading",     "RRPCM", 8, "readg8", "grade 8 reading"),
]

# (geo_key, NAEP jurisdiction code, friendly name). National public + 50
# states + DC (all participate in state NAEP).
STATES = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"),
    ("DE", "Delaware"), ("DC", "District of Columbia"), ("FL", "Florida"),
    ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"), ("IL", "Illinois"),
    ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"), ("KY", "Kentucky"),
    ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"),
    ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"),
    ("NE", "Nebraska"), ("NV", "Nevada"), ("NH", "New Hampshire"),
    ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
    ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
    ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"), ("SC", "South Carolina"), ("SD", "South Dakota"),
    ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"), ("VT", "Vermont"),
    ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"),
    ("WI", "Wisconsin"), ("WY", "Wyoming"),
]
GEOS = [("us", "NP")] + [(abbr.lower(), abbr) for abbr, _name in STATES]

# --- Source-YAML emission (inline; Plan 7) --------------------------------
# One YAML per written series, emitted right after its data file, so
# YAML<->data parity holds by construction. Overwrite-always: the dir is
# pipeline-owned — name/description fixes belong in these templates.
# Per-state IDs (`state_<metric>_<st>`) are recognized by parseStateSourceId
# and gated behind the composer's state chip; national `us_<metric>` series
# stay default-visible and carry the education tag.
REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_DIR = REPO_ROOT / "src" / "content" / "sources" / PIPELINE

METRIC_LABEL = {suffix: label for _subj, _sub, _g, suffix, label in METRICS}
# subject + grade per suffix, for the provenance series string + audit.
METRIC_META = {suffix: (subj, g) for subj, _sub, g, suffix, _label in METRICS}
STATE_NAME_LC = {abbr.lower(): name for abbr, name in STATES}
SHORT_METRIC = {
    "mathg4": "g4 math", "mathg8": "g8 math",
    "readg4": "g4 reading", "readg8": "g8 reading",
}
NAEP_URL = "https://www.nationsreportcard.gov/"


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def write_yaml(sid: str, suffix: str, geo_key: str) -> None:
    if geo_key == "us":
        where = "the US"
        name = f"NAEP {METRIC_LABEL[suffix]} score (US)"
        short = f"NAEP {SHORT_METRIC[suffix]} (US)"
        tags = ["education", "us"]
    else:
        where = STATE_NAME_LC[geo_key]
        name = f"{where} NAEP {METRIC_LABEL[suffix]} score"
        short = f"{geo_key.upper()} NAEP {SHORT_METRIC[suffix]}"
        tags = ["education", "us-state", "us"]
    subj, grade = METRIC_META[suffix]
    # House-style copy (the 92792e9d0d acronym-scrub pass rewrote the old
    # scaffold text; this template matches the committed YAML verbatim).
    # Emitted as a PLAIN (unquoted) scalar, exactly as committed.
    desc = (
        f"Average scale score, {METRIC_LABEL[suffix]}, for {where}, from "
        f"the National Assessment of Educational Progress (NAEP) — \"the "
        f"Nation's Report Card\" (NCES). Administered identically in every "
        f"state, so scores are directly comparable across states — unlike "
        f"each state's own proficiency tests. Public-domain US government "
        f"data."
    )
    lines = [
        f"name: {_q(name)}",
        f"shortName: {_q(short)}",
        f"description: {desc}",
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
    (YAML_DIR / f"{sid}.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


def fetch(subject: str, subscale: str, grade: int, juris: str) -> list[dict]:
    params = {
        "type": "data", "subject": subject, "grade": str(grade),
        "subscale": subscale, "variable": "TOTAL", "stattype": "MN:MN",
        "jurisdiction": juris, "Year": YEARS,
    }
    body = cached_get(BASE, ttl_seconds=7 * 24 * 3600, params=params).strip()
    if not body:
        return []
    try:
        return json.loads(body).get("result", []) or []
    except (json.JSONDecodeError, AttributeError):
        return []


def run() -> int:
    written = 0
    empties: list[str] = []
    YAML_DIR.mkdir(parents=True, exist_ok=True)
    for subject, subscale, grade, suffix, _label in METRICS:
        for geo_key, juris in GEOS:
            rows = fetch(subject, subscale, grade, juris)
            pts = []
            for r in rows:
                if r.get("errorFlag") not in (0, "0", None):
                    continue
                v = r.get("value")
                year = r.get("year")
                if v is None or year is None:
                    continue
                try:
                    val = float(v)
                except (TypeError, ValueError):
                    continue
                if not (0 <= val <= 500):  # NAEP scale bounds
                    continue
                pts.append({"t": f"{int(year)}-01-01", "v": val})
            pts.sort(key=lambda p: p["t"])
            sid = f"us_{suffix}" if geo_key == "us" else f"state_{suffix}_{geo_key}"
            if len(pts) < 2:
                empties.append(sid)
                continue
            write_timeseries(PIPELINE, sid, sid, pts, unit="scale score")
            write_yaml(sid, suffix, geo_key)
            written += 1
    print(f"naep: wrote {written} series.")
    if empties:
        print(f"  {len(empties)} skipped (<2 points): {', '.join(empties[:6])}"
              + (" ..." if len(empties) > 6 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
