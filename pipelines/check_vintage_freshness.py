"""Vintage-availability watcher: warn when a newer annual-data vintage is
published upstream than the one our pipelines are pinned to.

Why this exists: ACS 5-year sat ~1.5 years stale (pinned at 2022) because
nothing flagged the 2023/2024 releases. The data-freshness gate
(tests/data-freshness.test.ts) can't catch it — it only scans
chart-REFERENCED series and, by design, tolerates a uniformly-lagged annual
cohort under ~4.5x cadence (see [[data-integrity-gates]]). So these
hardcoded-vintage pipelines (census_acs_cd ACS_VINTAGES, census_acs_labor
YEARS, build_state_tract_topo TIGER_YEAR) need a human to bump them each
release. This probes the upstream catalogs for a vintage newer than our
pinned max and prints a ::warning:: so the bump doesn't get forgotten.

Reads the pinned values FROM the pipelines (single source of truth), so it
can't drift from what they actually use. Network probes hit only static
catalog endpoints (no API key needed).

Run:
    python pipelines/check_vintage_freshness.py            # warn-only (exit 0)
    python pipelines/check_vintage_freshness.py --strict   # exit 1 if behind
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

# Read pinned vintages from the pipelines themselves.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_state_tract_topo as tiger  # noqa: E402
import census_acs_cd  # noqa: E402
import census_acs_labor  # noqa: E402


def url_ok(url: str) -> bool | None:
    """True if the URL returns 2xx, False on a 404, None if the check itself
    failed (network/None => we don't warn, to avoid false alarms)."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        # Some static servers reject HEAD (405) — fall back to a GET.
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return 200 <= r.status < 300
        except Exception:
            return None
    except Exception:
        return None


# (label, pinned_max, url-template for the NEXT vintage)
def _checks() -> list[tuple[str, int, str, str]]:
    acs5_max = max(census_acs_cd.ACS_VINTAGES)
    acs1_max = max(census_acs_labor.YEARS)
    tiger_max = tiger.TIGER_YEAR
    return [
        ("ACS 5-year (census_acs_cd.ACS_VINTAGES + choropleth VINTAGES)",
         acs5_max,
         f"https://api.census.gov/data/{acs5_max + 1}/acs/acs5/variables.json",
         "bump census_acs_cd.ACS_VINTAGES + the census_acs_choropleth*.py VINTAGES lists"),
        ("ACS 1-year (census_acs_labor.YEARS)",
         acs1_max,
         f"https://api.census.gov/data/{acs1_max + 1}/acs/acs1/variables.json",
         "append the year to census_acs_labor.YEARS"),
        ("TIGER boundaries (build_state_tract_topo.TIGER_YEAR)",
         tiger_max,
         f"https://www2.census.gov/geo/tiger/TIGER{tiger_max + 1}/TRACT/",
         "bump build_state_tract_topo.TIGER_YEAR + rerun the topojson build"),
    ]


def main(argv: list[str] | None = None) -> int:
    strict = "--strict" in (argv or sys.argv[1:])
    behind = 0
    unknown = 0
    for label, pinned, next_url, fix in _checks():
        nxt = pinned + 1
        ok = url_ok(next_url)
        if ok is True:
            behind += 1
            print(f"::warning::{label}: pinned at {pinned} but {nxt} is "
                  f"PUBLISHED upstream. To refresh: {fix}.")
        elif ok is None:
            unknown += 1
            print(f"  {label}: pinned at {pinned}; could not check {nxt} "
                  f"(network?). Skipped.")
        else:
            print(f"  {label}: current (pinned {pinned}, {nxt} not yet published).")
    print(f"\nvintage check: {behind} source(s) behind, {unknown} uncheckable.")
    return 1 if (strict and behind) else 0


if __name__ == "__main__":
    raise SystemExit(main())
