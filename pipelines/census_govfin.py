"""
State government finances — Census Annual Survey of State Government
Finances (timeseries dataset ``govsstatefin``), per state + US total.

Scope note: this is the **state** government layer only — it does NOT
include local-government or federal spending. The Census "State and
Local Government Finances" combined product lives in the generic
``timeseries/govs`` dataset (opaque EP#### line codes, GOVTYPE
filtering); ``govsstatefin`` is the clean, reliable, well-labeled
state-government slice covering 2012-2024 annually. Local-government
per-state finance is a future follow-up.

DC is excluded: the District has a unified municipal government and is
not reported in State Government Finances (the API returns empty for
``state:11``). The state-level government-employment scaffolder drops
DC for the same reason.

API quirks worth remembering (cost real time to discover):
  - You MUST include CATEGORY in the ``get`` clause. Without it the
    API returns only the 21 revenue line codes (CATEGORY 01) and
    silently omits all expenditure rows (75 codes total with it).
    Including GOVTYPE in ``get``, conversely, restricts to revenue.
  - The ``AGG_DESC=<codes>`` predicate filter returns an EMPTY body —
    don't filter server-side; fetch all line codes and filter here.
  - Omitting YEAR returns every year (2012-2024) for the geography.
  - ``for=state:*`` (wildcard) returns only 50 states (no DC) and only
    the revenue subset; we iterate explicit FIPS instead.

Units: the API reports AMOUNT in thousands of dollars ($1,000). We
follow the repo's canonical-currency invariant and store BILLIONS
(divide by 1e6), matching usaspending / worldbank / marketcap. unit
string "billions USD".

Run: ``python pipelines/census_govfin.py``  (needs CENSUS_API_KEY in
.env, though the dataset also serves anonymously at a lower rate).
"""
from __future__ import annotations

import json
import os
import sys

import _env  # noqa: F401 — loads .env so CENSUS_API_KEY is available locally

from common import cached_get, write_timeseries

PIPELINE = "census_govfin"
BASE_URL = "https://api.census.gov/data/timeseries/govsstatefin"

# 50 states. DC (FIPS 11) intentionally omitted — not reported in
# State Government Finances (see module docstring).
STATES: list[tuple[str, str, str]] = [
    ("AL", "01", "Alabama"), ("AK", "02", "Alaska"),
    ("AZ", "04", "Arizona"), ("AR", "05", "Arkansas"),
    ("CA", "06", "California"), ("CO", "08", "Colorado"),
    ("CT", "09", "Connecticut"), ("DE", "10", "Delaware"),
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

# (suffix, AGG_DESC code, headline-noun, blurb). The blurb is shared
# across the national + per-state YAMLs the scaffolder writes; the
# scaffolder splices in the scope ("California's" / "all 50") and the
# common Census-program sentence. Codes verified against the
# AGG_DESC_LABEL attribute on the live API.
AGGREGATES: list[tuple[str, str, str, str]] = [
    (
        "totrev", "SF0001", "total revenue",
        "All revenue — taxes, federal and local transfers, current "
        "charges, and insurance-trust receipts",
    ),
    (
        "totexp", "SF0132", "total expenditure",
        "All spending, every fund: general government services plus "
        "utility, liquor-store, and insurance-trust outlays",
    ),
    (
        "genexp", "SF0133", "general expenditure",
        "Core public-service spending — excludes utility, liquor-store, "
        "and insurance-trust (pension) outlays, so it tracks day-to-day "
        "government activity",
    ),
    (
        "welfexp", "SF0353", "public-welfare expenditure",
        "Direct public-welfare spending; the large majority is state "
        "Medicaid outlays, making this the single biggest line in most "
        "state budgets",
    ),
    (
        "hwyexp", "SF0281", "highway expenditure",
        "Direct spending on regular highways — state DOT construction, "
        "maintenance, and operations (excludes toll facilities). Unlike "
        "K-12 (funded by states but spent by local districts), highways "
        "are a function states largely build and run directly",
    ),
]

# The five codes we keep, for client-side filtering of the full row set.
WANTED_CODES = {agg[1] for agg in AGGREGATES}
CODE_TO_SUFFIX = {agg[1]: agg[0] for agg in AGGREGATES}


def fetch_geo(for_clause: str, api_key: str | None) -> list[list[str]]:
    """Fetch every line code / year for one geography. Returns the raw
    rows (header included). CATEGORY in `get` is load-bearing (see
    module docstring)."""
    params: dict[str, str] = {
        "get": "AMOUNT,AGG_DESC,YEAR,CATEGORY",
        "for": for_clause,
    }
    if api_key:
        params["key"] = api_key
    body = cached_get(BASE_URL, ttl_seconds=6 * 3600, params=params)
    body = body.strip()
    if not body:
        return []
    try:
        rows = json.loads(body)
    except json.JSONDecodeError:
        return []
    return rows if isinstance(rows, list) and rows else []


def points_by_code(rows: list[list[str]]) -> dict[str, list[dict]]:
    """Group a geography's rows into {suffix: [{t, v}]} for our five
    aggregates. AMOUNT ($1,000) → billions. Fiscal year anchored to
    June 30 (modal state FY-end)."""
    if not rows:
        return {}
    hdr = rows[0]
    try:
        ai, di, yi = hdr.index("AMOUNT"), hdr.index("AGG_DESC"), hdr.index("YEAR")
    except ValueError:
        return {}
    out: dict[str, list[dict]] = {}
    for r in rows[1:]:
        code = r[di]
        if code not in WANTED_CODES:
            continue
        raw = r[ai]
        try:
            billions = int(raw) / 1_000_000
        except (TypeError, ValueError):
            continue
        year = r[yi]
        out.setdefault(CODE_TO_SUFFIX[code], []).append(
            {"t": f"{year}-06-30", "v": billions}
        )
    for suffix in out:
        out[suffix].sort(key=lambda p: p["t"])
    return out


def run() -> int:
    api_key = os.environ.get("CENSUS_API_KEY") or None
    if not api_key:
        print(
            "WARN: CENSUS_API_KEY not set — querying govsstatefin "
            "anonymously (works, but rate-limited).",
            file=sys.stderr,
        )

    written = 0
    empties: list[str] = []

    # National (US total = sum across state governments).
    nat = points_by_code(fetch_geo("us:1", api_key))
    for suffix, _code, noun, _blurb in AGGREGATES:
        pts = nat.get(suffix, [])
        if not pts:
            empties.append(f"us_{suffix}")
            continue
        write_timeseries(
            PIPELINE,
            f"us_{suffix}",
            f"State governments' {noun} (US total)",
            pts,
            unit="billions USD",
        )
        written += 1

    # Per state.
    for abbr, fips, name in STATES:
        by_code = points_by_code(fetch_geo(f"state:{fips}", api_key))
        for suffix, _code, noun, _blurb in AGGREGATES:
            pts = by_code.get(suffix, [])
            sid = f"state_{suffix}_{abbr.lower()}"
            if not pts:
                empties.append(sid)
                continue
            write_timeseries(
                PIPELINE,
                sid,
                f"{name} state government {noun}",
                pts,
                unit="billions USD",
            )
            written += 1

    print(f"census_govfin: wrote {written} series.")
    if empties:
        print(f"  {len(empties)} empty (skipped): {', '.join(empties[:8])}"
              + (" ..." if len(empties) > 8 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
