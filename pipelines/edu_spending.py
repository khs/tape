"""
K-12 current spending per pupil, by state + US — NCES Common Core of
Data (CCD) school-district finance (F-33), via the Urban Institute
Education Data Portal API.

Per-pupil current spending is the standard cross-state school-funding
comparison: total current expenditure on elementary-secondary education
divided by fall enrollment. We compute it from the district-level CCD
finance file aggregated to the state.

Source: U.S. Dept. of Education, NCES Common Core of Data (public
domain). Delivered through the Urban Institute Education Data Portal
(educationdata.urban.org), a free public research API. We cite both.

API shape (the summaries endpoint aggregates districts; ask for one
state at a time grouped by year, since summing all states at once times
out 504):
  /api/v1/school-districts/ccd/finance/summaries
    ?var=exp_current_elsec_total&stat=sum&by=year&fips=6
  -> results: [{year, fips, exp_current_elsec_total}, ...]
Same for enrollment_fall_responsible. per-pupil = spending / enrollment.

Units: raw dollars per pupil (e.g. 14671), like a price — NOT the
billions convention used for aggregate-currency totals. unit "USD",
unitClass "currency". National = sum(state spending)/sum(state
enrollment) per year, computed here.

Source YAMLs are emitted INLINE (one per written series, right after the
data file) into src/content/sources/edu_spending/ — overwrite-always; the
dir is pipeline-owned. This replaced the one-shot _scaffold_edu_spending.py
(Plan 7). Attribution (per the provider ToS sweep): the underlying data is
NCES Common Core of Data (F-33), public domain, delivered via the Urban
Institute Education Data Portal under ODC-BY 1.0 — which requires citing
both Urban and the dataset. We credit both.

Run: `python pipelines/edu_spending.py` (no key; Urban API is open).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import _env  # noqa: F401

from common import cached_get, write_timeseries

PIPELINE = "edu_spending"
BASE = "https://educationdata.urban.org/api/v1/school-districts/ccd/finance/summaries"
SPEND_VAR = "exp_current_elsec_total"
ENROLL_VAR = "enrollment_fall_responsible"

# Urban uses numeric FIPS. 50 states + DC.
STATES: dict[int, tuple[str, str]] = {
    1: ("AL", "Alabama"), 2: ("AK", "Alaska"), 4: ("AZ", "Arizona"),
    5: ("AR", "Arkansas"), 6: ("CA", "California"), 8: ("CO", "Colorado"),
    9: ("CT", "Connecticut"), 10: ("DE", "Delaware"),
    11: ("DC", "District of Columbia"), 12: ("FL", "Florida"),
    13: ("GA", "Georgia"), 15: ("HI", "Hawaii"), 16: ("ID", "Idaho"),
    17: ("IL", "Illinois"), 18: ("IN", "Indiana"), 19: ("IA", "Iowa"),
    20: ("KS", "Kansas"), 21: ("KY", "Kentucky"), 22: ("LA", "Louisiana"),
    23: ("ME", "Maine"), 24: ("MD", "Maryland"), 25: ("MA", "Massachusetts"),
    26: ("MI", "Michigan"), 27: ("MN", "Minnesota"), 28: ("MS", "Mississippi"),
    29: ("MO", "Missouri"), 30: ("MT", "Montana"), 31: ("NE", "Nebraska"),
    32: ("NV", "Nevada"), 33: ("NH", "New Hampshire"), 34: ("NJ", "New Jersey"),
    35: ("NM", "New Mexico"), 36: ("NY", "New York"), 37: ("NC", "North Carolina"),
    38: ("ND", "North Dakota"), 39: ("OH", "Ohio"), 40: ("OK", "Oklahoma"),
    41: ("OR", "Oregon"), 42: ("PA", "Pennsylvania"), 44: ("RI", "Rhode Island"),
    45: ("SC", "South Carolina"), 46: ("SD", "South Dakota"), 47: ("TN", "Tennessee"),
    48: ("TX", "Texas"), 49: ("UT", "Utah"), 50: ("VT", "Vermont"),
    51: ("VA", "Virginia"), 53: ("WA", "Washington"), 54: ("WV", "West Virginia"),
    55: ("WI", "Wisconsin"), 56: ("WY", "Wyoming"),
}


# --- Source-YAML emission (inline; Plan 7) --------------------------------
# One YAML per written series, emitted right after its data file, so
# YAML<->data parity holds by construction. Overwrite-always: the dir is
# pipeline-owned — name/description fixes belong in these templates.
# Per-state IDs (`state_perpupil_<st>`) are gated behind the composer's
# state chip; `us_perpupil` stays default-visible.
REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_DIR = REPO_ROOT / "src" / "content" / "sources" / PIPELINE

STATE_NAME_LC = {abbr.lower(): name for abbr, name in STATES.values()}
URBAN_URL = "https://educationdata.urban.org/"
# ODC-BY requires citing Urban + the dataset; this is the license string
# users see on each source page.
LICENSE = ("ODC-BY 1.0 — NCES Common Core of Data (public domain) via "
           "Urban Institute Education Data Portal; cite both")


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def write_yaml(sid: str, geo_key: str) -> None:
    if geo_key == "us":
        name = "K-12 spending per pupil (US)"
        short = "US per-pupil K-12"
        where = "the US"
        tags = ["education", "fiscal", "us"]
    else:
        where = STATE_NAME_LC[geo_key]
        name = f"{where} K-12 spending per pupil"
        short = f"{geo_key.upper()} per-pupil K-12"
        tags = ["education", "fiscal", "us-state", "us"]
    desc = (
        f"Current spending per pupil on K-12 public education in {where}, "
        f"total current expenditure divided by fall enrollment. NCES Common "
        f"Core of Data (F-33 school-system finance), via the Urban Institute "
        f"Education Data Portal."
    )
    lines = [
        f"name: {_q(name)}",
        f"shortName: {_q(short)}",
        f"description: {_q(desc)}",
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
        f"  license: {_q(LICENSE)}",
        "tags:",
    ]
    for t in tags:
        lines.append(f"  - {t}")
    lines.append("unitClass: currency")
    (YAML_DIR / f"{sid}.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


def fetch_by_year(var: str, fips: int) -> dict[int, float]:
    params = {"var": var, "stat": "sum", "by": "year", "fips": str(fips)}
    body = cached_get(BASE, ttl_seconds=7 * 24 * 3600, params=params).strip()
    if not body:
        return {}
    try:
        res = json.loads(body).get("results", [])
    except (json.JSONDecodeError, AttributeError):
        return {}
    out: dict[int, float] = {}
    for r in res:
        y, v = r.get("year"), r.get(var)
        if y is None or v is None:
            continue
        try:
            out[int(y)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def run() -> int:
    written = 0
    nat_spend: dict[int, float] = {}
    nat_enroll: dict[int, float] = {}
    YAML_DIR.mkdir(parents=True, exist_ok=True)

    for fips, (abbr, _name) in STATES.items():
        spend = fetch_by_year(SPEND_VAR, fips)
        enroll = fetch_by_year(ENROLL_VAR, fips)
        pts = []
        for year in sorted(spend):
            s, e = spend.get(year), enroll.get(year)
            if not s or not e or e <= 0 or s <= 0:
                continue
            pts.append({"t": f"{year}-06-30", "v": round(s / e, 2)})
            nat_spend[year] = nat_spend.get(year, 0.0) + s
            nat_enroll[year] = nat_enroll.get(year, 0.0) + e
        if len(pts) >= 2:
            sid = f"state_perpupil_{abbr.lower()}"
            write_timeseries(PIPELINE, sid, sid, pts, unit="USD")
            write_yaml(sid, abbr.lower())
            written += 1

    nat_pts = [
        {"t": f"{y}-06-30", "v": round(nat_spend[y] / nat_enroll[y], 2)}
        for y in sorted(nat_spend) if nat_enroll.get(y, 0) > 0
    ]
    if len(nat_pts) >= 2:
        write_timeseries(PIPELINE, "us_perpupil", "us_perpupil", nat_pts, unit="USD")
        write_yaml("us_perpupil", "us")
        written += 1

    print(f"edu_spending: wrote {written} per-pupil series.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
