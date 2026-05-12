"""
CBO (Congressional Budget Office) projections pipeline.

STATUS: blocked on access. CBO's website is behind DataDome anti-bot
protection — direct HTTP requests from CI (or any non-browser client)
return HTTP 403. We can't automate downloads of their XLSX publications
without either:

  (a) a paid scraping service that handles bot mitigation,
  (b) a manual periodic upload of the XLSX file into this repo, or
  (c) an alternative data source.

We've gone with (c) for now: cross-country government finance data
(debt-to-GDP, deficit-to-GDP) comes through OECD's SDMX endpoint
(see pipelines/oecd.py), which IS scrapeable. CBO's unique value is
*forward-looking projections* (10-year and 30-year budget outlooks),
which OECD doesn't have.

To unblock projection data, the manual path is:

  1. Visit https://www.cbo.gov/data/budget-economic-data in a browser
  2. Download the latest "10-Year Budget Projections" XLSX
  3. Save to pipelines/cbo_data/budget_projections_<YYYY-MM>.xlsx
  4. Add openpyxl to CI deps + uncomment the parser below

For now this script prints a status note and returns 0 so the GH
Actions refresh-data workflow keeps going.

Run with: ``python pipelines/cbo.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANUAL_DIR = REPO_ROOT / "pipelines" / "cbo_data"


def main() -> int:
    # If a manually-uploaded XLSX is present, parse it. Otherwise, no-op.
    xlsx_files = list(MANUAL_DIR.glob("*.xlsx")) if MANUAL_DIR.exists() else []
    if not xlsx_files:
        print(
            "cbo.py: no manual XLSX found in pipelines/cbo_data/. "
            "See module docstring for the manual upload workflow.",
            file=sys.stderr,
        )
        return 0

    # Manual-upload mode: a future implementation parses the XLSX with
    # openpyxl/pandas and writes JSON to public/data/cbo/<series>.json.
    # Stubbed here; the parsing is XLSX-layout-specific and worth a
    # focused PR rather than guessing the sheet structure.
    print(
        f"cbo.py: found {len(xlsx_files)} manual file(s) but parser not "
        "implemented. See module docstring for next steps.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
