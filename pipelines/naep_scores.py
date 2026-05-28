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

Run: `python pipelines/naep_scores.py` (no key needed).
"""
from __future__ import annotations

import json
import sys

import _env  # noqa: F401 — harmless; NAEP needs no key

from common import cached_get

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
            from common import write_timeseries
            write_timeseries(PIPELINE, sid, sid, pts, unit="scale score")
            written += 1
    print(f"naep: wrote {written} series.")
    if empties:
        print(f"  {len(empties)} skipped (<2 points): {', '.join(empties[:6])}"
              + (" ..." if len(empties) > 6 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
