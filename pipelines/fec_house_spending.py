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
effect that cycle. Boundaries were redrawn after the 2010 and 2020
censuses, so e.g. "TX-07" pre-2022 and post-2022 are not the same
geographic area. Each point is "spending in the seat numbered N that
cycle." Noted in every source description.

Units: stored in millions USD (a district's total runs ~$1-50M/cycle).
SECURITY: the key is a query param — never log the URL.

Run: python pipelines/fec_house_spending.py            (all cycles)
     python pipelines/fec_house_spending.py 2024        (one cycle, test)
"""
from __future__ import annotations

import json
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
CYCLES = list(range(2008, 2026, 2))  # 2008..2024

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
    m = re.search(r"^DATAGOV_API_KEY=(.*)$", (HERE.parent / ".env").read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit("DATAGOV_API_KEY not found in .env")
    return m.group(1).strip().strip('"').strip("'")


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
        for (st, d2), disb in sums.items():
            per_cd[(st, d2)].append({"t": f"{cyc}-01-01", "v": round(disb / 1e6, 3)})
            cyc_total += disb
        national.append({"t": f"{cyc}-01-01", "v": round(cyc_total / 1e6, 1)})
        print(f"  cycle {cyc}: {len(sums)} districts, ${cyc_total/1e9:.2f}B total")

    written = 0
    for (st, d2), points in sorted(per_cd.items()):
        points.sort(key=lambda p: p["t"])
        slug = f"house_spending_{st.lower()}_{d2}"
        dist_label = "at-large" if d2 == "00" else f"district {int(d2)}"
        name = f"House campaign spending — {STATE_NAME[st]} {('(at-large)' if d2=='00' else d2)}"
        write_timeseries(pipeline="fec", series_id=slug, name=name, points=points, unit="millions USD")
        (SOURCES_DIR / f"{slug}.yaml").write_text("\n".join([
            f"name: {name}",
            f"shortName: {st}-{d2} campaign $",
            f"description: Total campaign disbursements by all U.S. House candidates who ran in {STATE_NAME[st]} {dist_label}, summed per two-year election cycle, from the Federal Election Commission. District numbers reflect the boundaries in effect each cycle (redistricting redrew them after the 2010 and 2020 censuses).",
            "kind: timeseries", "pipeline: fec",
            f"dataFile: data/fec/{slug}.json",
            'supportedDeltas: ["10y", "30y"]', 'unit: "millions USD"',
            "formatting:", "  style: currency", "  decimals: 1", '  suffix: "M"',
            "emphasis: change",
            "provenance:", "  provider: FEC (Federal Election Commission)",
            f"  series: candidates/totals office=H sum(disbursements) {st}-{d2}",
            "  url: https://www.fec.gov/data/",
            "  license: Public domain (US government data)",
            "tags:", "  - elections", "  - us", "  - us-cd",
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

    print(f"fec_house_spending: wrote {written} series.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
