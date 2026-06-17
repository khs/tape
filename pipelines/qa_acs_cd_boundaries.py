"""
QA gate: verify our crosswalk-aggregated acs_cd district values match the
Census Bureau's OWN published figures on the same 118th-Congress
boundaries.

Why this exists: the acs_cd pipeline aggregates ACS *tract* data up to
118th-Congress districts via pipelines/_crosswalks. If the crosswalk is on
the wrong boundaries (it silently carried 116th districts until the cd118
fix), the rebuilt district values diverge wildly from Census's published
118th-CD numbers — e.g. a 251% gap on median home value — purely from the
boundary mismatch. On the correct 118th crosswalk the gap collapses to a
few percent (bin-interpolated medians) / ~1-2% (summed counts).

For 2022 ACS 5-year, Census publishes congressional-district data DIRECTLY
on 118th boundaries, so it's an independent ground truth. We fetch three
headline tables and compare against our acs_cd JSON at the 2022 point:

    B01003_001E  total population        -> acs_cd/population_<slug>
    B19013_001E  median household income -> acs_cd/median_hh_income_<slug>
    B25077_001E  median home value       -> acs_cd/median_home_value_<slug>

Counts must match within COUNT_TOL; medians (re-interpolated from
distribution bins on our side) within MEDIAN_TOL. Exits non-zero if any
sampled district breaches tolerance.

Key-gated: needs CENSUS_API_KEY (loaded from .env via _env). Without it the
script skips with exit 0 so CI on a keyless runner doesn't fail.

Run with:  python pipelines/qa_acs_cd_boundaries.py [STATEFIPS ...]
(default sample: NC TX MT CA FL — a redrawn gainer, the +2 gainer, the
former at-large, the -1 loser, and another gainer.)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import _env  # noqa: F401 — load .env so CENSUS_API_KEY is available

REPO_ROOT = Path(__file__).resolve().parent.parent
ACS_CD_DIR = REPO_ROOT / "public" / "data" / "acs_cd"

FIPS2AB = {
    "01": "al", "02": "ak", "04": "az", "05": "ar", "06": "ca", "08": "co",
    "09": "ct", "10": "de", "11": "dc", "12": "fl", "13": "ga", "15": "hi",
    "16": "id", "17": "il", "18": "in", "19": "ia", "20": "ks", "21": "ky",
    "22": "la", "23": "me", "24": "md", "25": "ma", "26": "mi", "27": "mn",
    "28": "ms", "29": "mo", "30": "mt", "31": "ne", "32": "nv", "33": "nh",
    "34": "nj", "35": "nm", "36": "ny", "37": "nc", "38": "nd", "39": "oh",
    "40": "ok", "41": "or", "42": "pa", "44": "ri", "45": "sc", "46": "sd",
    "47": "tn", "48": "tx", "49": "ut", "50": "vt", "51": "va", "53": "wa",
    "54": "wv", "55": "wi", "56": "wy",
}

DEFAULT_SAMPLE = ["37", "48", "30", "06", "12"]  # NC TX MT CA FL

# (table, our out_id, kind, tolerance fraction)
CHECKS = [
    ("B01003_001E", "population", "count", 0.02),
    ("B19013_001E", "median_hh_income", "median", 0.08),
    ("B25077_001E", "median_home_value", "median", 0.08),
]


def fetch_census_cd(state_fips: str, key: str) -> dict[str, dict[str, float]]:
    """{cd_code: {table: value}} for one state's 118th CDs (2022 ACS5)."""
    gets = ",".join(c[0] for c in CHECKS)
    url = (
        f"https://api.census.gov/data/2022/acs/acs5?get={gets}"
        f"&for=congressional%20district:*&in=state:{state_fips}&key={key}"
    )
    out = subprocess.run(
        ["curl", "-sS", "--max-time", "60", url],
        capture_output=True, check=True, text=True,
    )
    rows = json.loads(out.stdout)
    header = rows[0]
    cd_col = header.index("congressional district")
    by_cd: dict[str, dict[str, float]] = {}
    for row in rows[1:]:
        rec = dict(zip(header, row))
        cd = rec[header[cd_col]]
        vals: dict[str, float] = {}
        for table, _out_id, _kind, _tol in CHECKS:
            try:
                v = float(rec[table])
            except (TypeError, ValueError):
                continue
            # Census uses large negative sentinels (-666666666) for
            # suppressed/non-applicable medians; skip those.
            if v < 0:
                continue
            vals[table] = v
        by_cd[cd] = vals
    return by_cd


def our_value(out_id: str, slug: str) -> float | None:
    p = ACS_CD_DIR / f"{out_id}_{slug}.json"
    if not p.exists():
        return None
    pts = json.loads(p.read_text())["points"]
    for pt in reversed(pts):
        if str(pt["t"]).startswith("2022"):
            return float(pt["v"])
    return None


def main() -> int:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        print("qa_acs_cd_boundaries: CENSUS_API_KEY not set; skipping.")
        return 0
    states = [a for a in sys.argv[1:] if a.isdigit()] or DEFAULT_SAMPLE
    failures: list[str] = []
    n_checked = 0
    for fips in states:
        ab = FIPS2AB.get(fips)
        if not ab:
            continue
        census = fetch_census_cd(fips, key)
        print(f"\n=== {ab.upper()} (state {fips}): {len(census)} districts ===")
        for cd in sorted(census):
            if cd in ("00", "98", "ZZ"):
                slug = f"{ab}_al" if cd == "00" else f"{ab}_{cd}"
            else:
                slug = f"{ab}_{int(cd):02d}"
            for table, out_id, kind, tol in CHECKS:
                truth = census[cd].get(table)
                if truth is None:
                    continue
                ours = our_value(out_id, slug)
                if ours is None:
                    failures.append(f"{slug} {out_id}: MISSING our data")
                    print(f"  {slug} {out_id:18s}: MISSING our data")
                    continue
                n_checked += 1
                dev = abs(ours - truth) / truth if truth else 0.0
                flag = "OK" if dev <= tol else "!!FAIL!!"
                if dev > tol:
                    failures.append(
                        f"{slug} {out_id}: ours={ours:,.0f} census={truth:,.0f} "
                        f"dev={dev*100:.1f}% > {tol*100:.0f}%"
                    )
                print(f"  {slug} {out_id:18s}: ours={ours:>12,.0f} "
                      f"census={truth:>12,.0f}  dev={dev*100:5.1f}%  {flag}")
    print(f"\nchecked {n_checked} (district x indicator) pairs; "
          f"{len(failures)} failures")
    if failures:
        print("\nFAILURES:")
        for f in failures[:40]:
            print("  -", f)
        return 1
    print("\nPASS: rebuilt acs_cd matches Census's published 2022 118th-CD "
          "figures within tolerance (boundaries are correct).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
