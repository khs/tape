"""
OECD cross-country comparison pipeline. STUB.

What OECD publishes that beats what we already have from FRED + World Bank:
* Quarterly real GDP by country, harmonized methodology — better
  apples-to-apples than mixing FRED (US BEA) with World Bank (annual).
* Harmonized unemployment rates across all OECD members.
* Consumer prices (CPI) by country, monthly, comparable definition.
* General government debt-to-GDP ratios.
* Productivity (GDP per hour worked) by country.

Why this is a stub: OECD's stats API (the old OECD.Stat) returns SDMX-XML
which is painful to parse without a dedicated SDMX library. The newer
OECD Data Explorer has JSON endpoints but URL patterns are still under
flux as of late 2025. To do this right:

  1. Pick the JSON-API base URL — currently
     ``https://sdmx.oecd.org/public/rest/data/<dataflow>/<key>?format=jsondata``
     for the new explorer.
  2. Resolve dataflow identifiers — e.g. "DSD_NAMAIN10@DF_QNA" for
     Quarterly National Accounts. These are documented in the OECD
     Data Explorer UI's "developer" panel for each dataset.
  3. Loop over a curated set of countries (G7 + a few others) and write
     one file per (indicator, country).

Recommended starter set:
  A. Quarterly real GDP, indexed to 100 at a common reference quarter
     for G7 + China + India. Lets you ship a "G7 GDP since 2008" chart.
  B. Harmonized unemployment rates for G7 — better than country-by-
     country comparisons from disparate national statistics offices.
  C. Government debt-to-GDP, annual, OECD members. Direct policy-debate
     ammunition.

For now this script does nothing. When implementing, output to:
    public/data/oecd/<indicator>_<country>.json
with matching manifests at src/content/sources/oecd/.

Run with: ``python pipelines/oecd.py``.
"""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "oecd.py: not implemented yet. See module docstring for the build plan "
        "and recommended priority order.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
