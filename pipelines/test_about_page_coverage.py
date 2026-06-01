"""
Tests that catch "we shipped a new data provider but forgot to mention
it on the About page" — the staleness class fixed in commit
1bad93460a (about: list 7 missing providers + refresh licensing).

Discovered: the codebase had 17 distinct source-provider directories
but `about.astro` only listed 12, leaving CBO, NCES/NAEP, SSA, EIA,
Zillow, Census-State-GovFin, and Realtor.com invisible to any reader
on /about/. The fix added them; this test prevents the regression
from re-accruing as more providers are added.

How it works
------------
The test maintains a hand-curated mapping from provider-directory
name → About-page entry label. Adding a new directory under
src/content/sources/ without a mapping entry FAILS the test, forcing
the author to either:

  - Add a mapping for a new user-facing provider (and the linked
    assertion will require the new label to appear in about.astro)
  - Mark it as None (internal/helper, won't appear on About)

This is intentionally heavyweight to encourage thought: "Should the
about page mention this data source?" is the right question to
answer when adding a new directory.

Run locally with::

    python -m unittest pipelines.test_about_page_coverage

CI runs the file via ``python -m unittest`` so the audit is enforced
before merge.
"""
from __future__ import annotations

import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources"
ABOUT_PATH = REPO_ROOT / "src" / "pages" / "about.astro"


# Mapping: provider directory name → About-page entry label.
# None means "internal/helper data, not user-facing" — the directory
# exists but isn't intended to appear on /about/.
#
# When you add a new directory under src/content/sources/, you MUST
# extend this mapping. The two test methods below check both halves:
#   - test_no_uncategorized_providers: catches new dirs missing here
#   - test_all_user_facing_providers_appear_on_about: catches dirs
#     here that aren't in the about.astro user-facing prose
#
# Keep labels exactly matching the <strong>...</strong> text in
# about.astro's "Where the data comes from" section, since
# substring-match is what test_all_user_facing_providers_appear_on_about
# uses.
PROVIDER_TO_ABOUT_LABEL: dict[str, str | None] = {
    "fred": "FRED",
    "bls": "BLS",
    "cbo": "CBO",
    "usaspending": "USAspending.gov",
    "acs_cd": "Census Bureau",
    "acs_metro": "Census Bureau",
    "acs_state": "Census Bureau",
    "acs_national": "Census Bureau",
    "acs_labor": "Census Bureau",
    "acs_tract": "Census Bureau",
    "acs_county": "Census Bureau",
    "acs_block_group": "Census Bureau",
    "census_govfin": "Census Bureau",
    "naep": "NCES / NAEP",
    "edu_spending": "NCES / NAEP",
    "ssa": "SSA",
    "eia_state_energy": "EIA",
    "oecd": "OECD",
    "treasury_tic": "US Treasury",
    "worldbank_extended": "World Bank",
    "worldbank_gdp_raw": "World Bank",
    "countries_gdp": "World Bank",
    "countries_relative": "World Bank",
    "usda_nass": "USDA NASS",
    "cdc_health": "CDC / NCHS",
    "usgs_water": "USGS",
    "cms_nhe": "CMS Office of the Actuary",
    "zillow": "Zillow Research",
    "bea": "BEA",
    "fbi_crime": "FBI",
    "noaa_climate": "NOAA",
    "owid_co2": "Our World in Data",
    "yahoo": "Yahoo Finance",
    "yahoo_futures": "Yahoo Finance",
    "yahoo_marketcap": "Yahoo Finance",
    # Internal / helper data — not surfaced on /about/.
    "countries": None,  # country-label lookup table, not a data feed
    "sec_shares": None,  # SEC EDGAR shares-outstanding feed for marketcap; cited under Yahoo Finance
}


class AboutPageCoverageTest(unittest.TestCase):
    def test_no_uncategorized_providers(self) -> None:
        """Every source directory must have an entry in the mapping.

        Failing means a new provider was added under src/content/sources/
        without telling this test how it relates to the About page.
        Add an entry to PROVIDER_TO_ABOUT_LABEL above — string label for
        user-facing providers, None for internal helpers.
        """
        actual_dirs = {
            p.name for p in SOURCES_DIR.iterdir() if p.is_dir()
        }
        declared = set(PROVIDER_TO_ABOUT_LABEL.keys())
        uncategorized = sorted(actual_dirs - declared)
        self.assertFalse(
            uncategorized,
            (
                f"Source directories without an About-page mapping:\n  "
                + "\n  ".join(uncategorized)
                + "\n\nAdd each to PROVIDER_TO_ABOUT_LABEL in "
                "pipelines/test_about_page_coverage.py — string label "
                "if user-facing (and update src/pages/about.astro to "
                "match), None if internal-only."
            ),
        )

    def test_all_user_facing_providers_appear_on_about(self) -> None:
        """The /about/ page must mention every user-facing provider.

        Failing means a provider that this test considers user-facing
        (PROVIDER_TO_ABOUT_LABEL value != None) isn't named in
        about.astro. Either add the missing entry to about.astro or
        change the mapping to None if it shouldn't surface there.
        """
        about_text = ABOUT_PATH.read_text(encoding="utf-8")
        labels_to_check = {
            label
            for label in PROVIDER_TO_ABOUT_LABEL.values()
            if label is not None
        }
        missing = sorted(
            label for label in labels_to_check if label not in about_text
        )
        self.assertFalse(
            missing,
            (
                f"About page (src/pages/about.astro) missing entries:\n  "
                + "\n  ".join(missing)
                + "\n\nAdd a <li><strong>{label}</strong> — …</li> entry "
                "in the 'Where the data comes from' section, or change "
                "the corresponding PROVIDER_TO_ABOUT_LABEL value to None "
                "if this provider shouldn't surface on /about/."
            ),
        )


if __name__ == "__main__":
    unittest.main()
