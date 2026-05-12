"""
CBO (Congressional Budget Office) projections pipeline. STUB.

What CBO publishes that's interesting for a DC policy audience:
* Long-Term Budget Outlook (annual): debt/GDP, primary deficit projections,
  Social Security and Medicare cost projections, all out to ~30 years.
* The Budget and Economic Outlook (annual + updates): 10-year deficit,
  receipts and outlays by category, GDP and inflation projections.
* Monthly Budget Review: month-over-month receipts/outlays vs. prior year.

Why this is a stub: CBO does not publish a clean API. Their data tables
are XLSX files attached to PDF reports. To do this right we need to:

  1. Identify the canonical URL for each indicator (these change each
     publication cycle; CBO doesn't keep stable URLs).
  2. Fetch the XLSX (`requests` + `openpyxl`).
  3. Pick out the right sheet + cell range (they're not consistent
     across reports).
  4. Map rows to {t: year-end-iso, v: float}.

Recommended sources to wire up first, in priority order:
  A. Federal debt held by the public, % of GDP — from the LTBO base case.
     URL pattern: cbo.gov/publication/<id>/long-term-budget-outlook-data
     (rotates annually; current 2025 publication is at .../56598 or similar)
  B. Primary deficit, % of GDP — same LTBO data tables, "Primary deficit"
     row.
  C. Social Security and Medicare combined spending, % of GDP — same source,
     "Major mandatory" rows.

For now this script does nothing. When implementing, model the structure
on `worldbank_gdp.py` (single-pipeline, multiple series via `CountrySpec`
dataclass + `write_timeseries`). The output should be:

    public/data/cbo/<series>.json  -> { kind: "timeseries", points: [...] }

And matching `src/content/sources/cbo/<series>.yaml` manifests so the
composer picks them up.

Run with: ``python pipelines/cbo.py``.
"""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "cbo.py: not implemented yet. See module docstring for the build plan "
        "and recommended priority order.",
        file=sys.stderr,
    )
    # Returning 0 (not an error) so the GH Actions refresh-data workflow
    # keeps going with continue-on-error semantics. When this is built out,
    # flip to real work.
    return 0


if __name__ == "__main__":
    sys.exit(main())
