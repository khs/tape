"""
FEC House campaign spending by congressional district.

For each U.S. House district, the SUM of campaign disbursements (money
spent) by all candidates who ran in that district, per two-year election
cycle. One data point per cycle (a 2-year cadence — deliberately not
monthly, so the series reflects election cycles rather than where we
happen to be within one). House races only (office=H).

Source: api.open.fec.gov /v1/candidates/totals (DATAGOV_API_KEY).
Paginated per cycle; we sum `disbursements` grouped by (state, district).
Public domain (FEC).

REDISTRICTING CAVEAT: a district's number reflects the boundaries in
effect that cycle. Boundaries were redrawn after the 1990, 2000, 2010,
and 2020 censuses, so e.g. "TX-07" pre-2022 and post-2022 are not the
same geographic area. Each point is "spending in the seat numbered N
that cycle." Noted in every source description.

Units: stored in millions USD (a district's total runs ~$1-50M/cycle).
SECURITY: the key is a query param — never log the URL.

Run: python pipelines/fec_house_spending.py            (all cycles)
     python pipelines/fec_house_spending.py 2024        (one cycle, test)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from common import write_timeseries

HERE = Path(__file__).resolve().parent
SOURCES_DIR = HERE.parent / "src" / "content" / "sources" / "fec"
API = "https://api.open.fec.gov/v1/candidates/totals/"
CYCLES = list(range(1990, 2026, 2))  # 1990..2024 (18 cycles)

# Congressional-district coding to match the composer's drill-down
# convention (src/lib/congressional-districts.ts): single-member
# ("at-large") states use "al", DC's non-voting delegate uses "98",
# numbered districts use a 2-digit code. FEC's API returns "00" for
# at-large seats AND for candidates it couldn't assign to a district,
# so "00" alone is ambiguous — we disambiguate with the canonical
# at-large roster below rather than by dollar amount (some unassigned
# "00" buckets in multi-district states like IN/SC carry >$1M).
ALWAYS_AT_LARGE = {"AK", "DE", "ND", "SD", "VT", "WY"}  # single seat, every cycle 1990-2024
# Montana is the one oscillator in this window: 2 seats in the 1990 cycle,
# down to a single at-large seat for 1992–2020 (the 1990-census cut), then
# back to 2 seats (MT-01/MT-02) in 2022 — handled per-cycle below.
#
# Decennial redistricting: maps drawn from each census first took effect
# in the cycle shown. A district whose series spans one of these covers
# two different geographic areas, so we seed an editable default note.
REDISTRICTING = [
    (1992, "1990"),
    (2002, "2000"),
    (2012, "2010"),
    (2022, "2020"),
]  # (first cycle under new lines, census)

STATE_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}


def _key() -> str:
    # Prefer the environment (CI secret) so the weekly refresh works without a
    # .env file; fall back to .env for local runs.
    key = os.environ.get("DATAGOV_API_KEY", "").strip()
    if key:
        return key
    env = HERE.parent / ".env"
    if env.exists():
        m = re.search(r"^DATAGOV_API_KEY=(.*)$", env.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit("DATAGOV_API_KEY not found in env or .env")


def _get(params: list[tuple[str, str]]) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tape/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=90).read())
        except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
            if e.code in (429, 500, 502, 503) and attempt < 5:
                time.sleep(3 + 3 * attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:  # type: ignore[attr-defined]
            # FEC's API intermittently stalls / drops connections — back off + retry
            if attempt < 5:
                time.sleep(3 + 3 * attempt)
                continue
            raise
    return {}


def cycle_totals(cycle: int, key: str) -> dict[tuple[str, str], float]:
    """{(state, district2): summed disbursements} for one cycle."""
    sums: dict[tuple[str, str], float] = defaultdict(float)
    page = 1
    while True:
        data = _get([
            ("api_key", key), ("office", "H"), ("cycle", str(cycle)),
            ("per_page", "100"), ("page", str(page)), ("sort", "candidate_id"),
        ])
        results = data.get("results", []) or []
        for r in results:
            st = r.get("state")
            dist = r.get("district")
            disb = r.get("disbursements")
            if st not in STATE_NAME or dist in (None, "") or disb in (None, ""):
                continue
            try:
                d2 = f"{int(dist):02d}"
            except (TypeError, ValueError):
                continue
            sums[(st, d2)] += float(disb)
        pages = (data.get("pagination", {}) or {}).get("pages", 1)
        if page >= pages or not results:
            break
        page += 1
        time.sleep(0.3)
    return sums


def final_district_code(state: str, raw: str, cycle: int) -> str | None:
    """Map an FEC (state, raw 2-digit district, cycle) to the composer's
    CD code, or None to drop the bucket from the per-district series.

    Drops: unassigned "00" spending in multi-district states, stray
    numbered filings in single-member states, and impossible district
    numbers (>53 — California's historical max was 53). Callers still
    add every dollar to the national total; only per-CD placement drops.
    """
    single_member = (
        state == "DC"
        or state in ALWAYS_AT_LARGE
        or (state == "MT" and 1992 <= cycle <= 2020)
    )
    if raw == "00":
        if state == "DC":
            return "98"  # non-voting delegate
        return "al" if single_member else None
    try:
        n = int(raw)
    except ValueError:
        return None
    if not (1 <= n <= 53):
        return None  # district number that cannot exist
    if single_member:
        return None  # stray numbered filing in an at-large state
    return f"{n:02d}"


def main(argv: list[str] | None = None) -> int:
    key = _key()
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    cycles = CYCLES
    if argv and len(argv) > 1 and argv[1].isdigit():
        cycles = [int(argv[1])]

    # accumulate per-CD points across cycles, + a national total per cycle
    per_cd: dict[tuple[str, str], list[dict]] = defaultdict(list)
    national: list[dict] = []
    for cyc in cycles:
        sums = cycle_totals(cyc, key)
        cyc_total = 0.0
        placed = 0
        for (st, raw), disb in sums.items():
            cyc_total += disb  # every dollar counts toward the US total
            code = final_district_code(st, raw, cyc)
            if code is None:
                continue  # unassigned / impossible district — not a real seat
            per_cd[(st, code)].append({"t": f"{cyc}-01-01", "v": round(disb / 1e6, 3)})
            placed += 1
        national.append({"t": f"{cyc}-01-01", "v": round(cyc_total / 1e6, 1)})
        print(f"  cycle {cyc}: {placed} placed districts, ${cyc_total/1e9:.2f}B total")

    written = 0
    dropped_empty = 0
    for (st, code), points in sorted(per_cd.items()):
        points.sort(key=lambda p: p["t"])
        # Belt-and-suspenders: drop a series that never recorded real
        # spending (an in-state-invalid district number that slipped
        # through as $0). Real seats run millions per cycle.
        if sum(p["v"] for p in points) < 0.05:
            dropped_empty += 1
            continue
        slug = f"house_spending_{st.lower()}_{code}"
        if code == "al":
            where, disp, redistrict = f"{STATE_NAME[st]}'s at-large House district", "(at-large)", ""
        elif code == "98":
            where, disp, redistrict = f"the {STATE_NAME[st]} non-voting delegate seat", "(delegate)", ""
        else:
            where, disp = f"{STATE_NAME[st]} district {int(code)}", code
            redistrict = " District numbers reflect the boundaries in effect each cycle (redistricting redrew them after the 1990, 2000, 2010, and 2020 censuses)."
        name = f"House campaign spending — {STATE_NAME[st]} {disp}"
        # Redistricting default annotations: a numbered district with data
        # on both sides of a decennial boundary spans two different maps —
        # seed an editable note. At-large / delegate seats have no internal
        # lines, so they get none.
        ann_lines: list[str] = []
        if code not in ("al", "98"):
            years = [int(p["t"][:4]) for p in points]
            notes = [
                (f"{bnd}-01-01", f"Boundaries redrawn ({census} Census)")
                for bnd, census in REDISTRICTING
                if any(y < bnd for y in years) and any(y >= bnd for y in years)
            ]
            if notes:
                ann_lines.append("defaultAnnotations:")
                for date, label in notes:
                    ann_lines.append(f'  - date: "{date}"')
                    ann_lines.append(f'    label: "{label}"')
        write_timeseries(pipeline="fec", series_id=slug, name=name, points=points, unit="millions USD")
        (SOURCES_DIR / f"{slug}.yaml").write_text("\n".join([
            f"name: {name}",
            f"shortName: {st}-{code.upper()} campaign $",
            f"description: Total campaign disbursements by all U.S. House candidates who ran in {where}, summed per two-year election cycle, from the Federal Election Commission.{redistrict}",
            "kind: timeseries", "pipeline: fec",
            f"dataFile: data/fec/{slug}.json",
            'supportedDeltas: ["10y", "30y"]', 'unit: "millions USD"',
            "formatting:", "  style: currency", "  decimals: 1", '  suffix: "M"',
            "emphasis: change",
            *ann_lines,
            "provenance:", "  provider: FEC (Federal Election Commission)",
            f"  series: candidates/totals office=H sum(disbursements) {st}-{code.upper()}",
            "  url: https://www.fec.gov/data/",
            "  license: Public domain (US government data)",
            # No `us-cd` tag: the synthesized `congressional-district` tag
            # (parseCdSourceId in library.json) already gates these behind the
            # "States & districts" chip, matching usaspending/acs_cd CD sources.
            # A bare `us-cd` topical tag would render an empty pill (every
            # carrier is chip-hidden) and trip library.json's build-time guard.
            "tags:", "  - elections", "  - us",
            "unitClass: currency", "",
        ]), encoding="utf-8")
        written += 1

    # national total
    if len(cycles) > 1:
        national.sort(key=lambda p: p["t"])
        write_timeseries(pipeline="fec", series_id="house_spending_us_total",
                         name="House campaign spending — US total", points=national,
                         unit="millions USD")
        (SOURCES_DIR / "house_spending_us_total.yaml").write_text("\n".join([
            "name: House campaign spending — US total",
            "shortName: US House campaign $",
            "description: Total campaign disbursements by all U.S. House candidates nationwide, summed per two-year election cycle, from the Federal Election Commission.",
            "kind: timeseries", "pipeline: fec",
            "dataFile: data/fec/house_spending_us_total.json",
            'supportedDeltas: ["10y", "30y"]', 'unit: "millions USD"',
            "formatting:", "  style: currency", "  decimals: 0", '  suffix: "M"',
            "emphasis: change",
            "provenance:", "  provider: FEC (Federal Election Commission)",
            "  series: candidates/totals office=H sum(disbursements) national",
            "  url: https://www.fec.gov/data/",
            "  license: Public domain (US government data)",
            "tags:", "  - elections", "  - us", "  - macro",
            "unitClass: currency", "",
        ]), encoding="utf-8")
        written += 1

    print(f"fec_house_spending: wrote {written} series ({dropped_empty} empty dropped).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
