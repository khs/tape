"""
Companion guardrail to test_about_page_coverage.py for the Substack-
driven landing at /welcome/ — catches "new data provider added but
the COVERAGE grid never picks up a representative source from it."

Why both this AND the about-page test
-------------------------------------
/about/ enumerates every provider in prose. /welcome/ shows readers a
hand-curated grid of clickable sourceHref chips that demo each
provider's data. The two surfaces have different rot patterns:

  - /about/: easy to forget when a provider ships (about.astro is a
    text file you only edit if you remember to). Caught by
    test_about_page_coverage.

  - /welcome/: easy to under-feature a provider — even if it appears
    SOMEWHERE in the data layer, a Substack visitor scanning chips
    can't see it. Caught here.

The /welcome/ grid is intentionally a curated subset, not exhaustive.
Some providers (acs_cd, treasury_tic, edu_spending per-state) are
too niche for the hero. So the mapping declares per-provider whether
the grid should feature it. Adding a new provider forces an explicit
"is this front-page material?" decision.

Run locally with::

    python -m unittest pipelines.test_welcome_page_coverage

CI runs the file via ``python -m unittest`` so the audit is enforced
before merge.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources"
WELCOME_PATH = REPO_ROOT / "src" / "pages" / "welcome.astro"


# Mapping: provider directory name → whether the /welcome/ COVERAGE
# grid should feature at least one sourceHref from this provider.
#
# True  = "first-impression material — represent this in the grid"
# False = "not for the hero (too niche, too generated, or already
#         covered by a sibling provider in the same category)"
#
# When adding a new directory under src/content/sources/, you must
# add an entry here. The two test methods below catch both halves:
#
#   - test_no_uncategorized_providers: catches new dirs missing here
#   - test_featured_providers_appear_on_welcome: catches dirs marked
#     True that don't have a sourceHref in welcome.astro
#
# Note: this is intentionally stricter than test_about_page_coverage's
# mapping — about.astro mentions every provider in prose, but welcome's
# coverage grid is a chosen-with-care subset.
PROVIDER_FEATURED_ON_WELCOME: dict[str, bool] = {
    # Macro / fiscal / markets — yes, the home thesis of the site
    "fred": True,
    "bls": True,
    "cbo": True,
    "usaspending": True,
    "ssa": True,
    "worldbank_gdp_raw": True,
    "yahoo_futures": True,
    "yahoo_marketcap": True,
    # Recent spring-26 expansions — yes, deliberately featured
    "cdc_health": True,
    "cms_nhe": True,
    "usgs_water": True,
    "usda_nass": True,
    # Intentionally NOT on welcome (per current curation)
    # The grid is hand-picked; sub-categories that would dilute the
    # signal are surfaced via the composer instead.
    "nhtsa_fars": False,        # traffic-safety detail; via composer
    "guttmacher": False,        # abortion data; via composer + source page
    "elections": False,         # election margins; via composer + source page
    "acs_cd": False,           # 17k+ per-CD variants; too much detail
    "acs_metro": False,         # 393 MSAs × indicators; via composer
    "acs_state": False,         # surfaced via Maps tab in composer
    "acs_national": False,      # mostly used as denominators
    "acs_labor": False,         # only 3 demo states shipped so far
    "acs_tract": False,         # choropleth-only data
    "acs_county": False,        # choropleth-only data
    "acs_block_group": False,   # choropleth-only data
    "census_govfin": False,     # 50 per-state, no aggregate
    "naep": False,              # per-state only, no national line
    "edu_spending": False,      # per-state only, no national line
    "eia_state_energy": False,  # per-state only, no national line
    "eia_prices": False,        # per-state energy prices; via composer + energy charts
    "oecd": False,              # OECD G7 charts surface via composer
    "treasury_tic": False,      # foreign-holders detail; via /federal-budget/
    "worldbank_extended": False, # broader-than-GDP; rarely first stop
    "countries_gdp": False,      # already represented via worldbank_gdp_raw
    "countries_relative": False, # already represented via worldbank_gdp_raw
    "zillow": False,            # housing; not on current welcome grid (could add later)
    "owid_co2": False,          # climate/energy cross-country; via composer + energy charts
    "owid_energy": False,       # renewable-electricity share; via composer + energy charts
    "bea": False,               # per-state GDP/income detail; via composer + Maps/Generators
    "fbi_crime": False,         # per-state crime rates; via composer + government charts
    "fec": False,               # per-CD campaign spending; via composer + elections chart
    "noaa_climate": False,      # city climate series; via composer + energy charts
    "yahoo": False,             # generic ticker prices; surfaced via marketcap
    # Internal / helper data
    "countries": False,         # label lookup, not a feed
    "sec_shares": False,        # SEC EDGAR backend for marketcap
}

SOURCE_HREF_RE = re.compile(r"/source/([a-z_][a-z0-9_]*)/")


def _featured_providers_in_welcome() -> set[str]:
    """Return the set of provider dirs whose source pages are linked
    from welcome.astro's COVERAGE grid (via the sourceHref field)."""
    text = WELCOME_PATH.read_text(encoding="utf-8")
    return {m.group(1) for m in SOURCE_HREF_RE.finditer(text)}


class WelcomePageCoverageTest(unittest.TestCase):
    def test_no_uncategorized_providers(self) -> None:
        """Every source directory must have an entry in the mapping.

        Failing means a new provider directory was added without
        telling this test whether the /welcome/ COVERAGE grid should
        feature it. Add an entry to PROVIDER_FEATURED_ON_WELCOME
        with True (featured) or False (curated out).
        """
        actual_dirs = {
            p.name for p in SOURCES_DIR.iterdir() if p.is_dir()
        }
        declared = set(PROVIDER_FEATURED_ON_WELCOME.keys())
        uncategorized = sorted(actual_dirs - declared)
        self.assertFalse(
            uncategorized,
            (
                f"Source directories without a welcome-page mapping:\n  "
                + "\n  ".join(uncategorized)
                + "\n\nAdd each to PROVIDER_FEATURED_ON_WELCOME in "
                "pipelines/test_welcome_page_coverage.py — True if the "
                "COVERAGE grid should feature it, False if curated out."
            ),
        )

    def test_featured_providers_appear_on_welcome(self) -> None:
        """Every provider marked True must appear in welcome.astro.

        Failing means a provider was marked as "should be featured"
        but the COVERAGE grid doesn't link to any of its source pages.
        Either add a sourceHref item to one of the COVERAGE categories
        or change the mapping to False if you decided against featuring.
        """
        featured_declared = {
            name for name, on in PROVIDER_FEATURED_ON_WELCOME.items() if on
        }
        featured_in_file = _featured_providers_in_welcome()
        missing = sorted(featured_declared - featured_in_file)
        self.assertFalse(
            missing,
            (
                f"Providers declared featured but missing from "
                f"welcome.astro COVERAGE grid:\n  "
                + "\n  ".join(missing)
                + "\n\nAdd a sourceHref entry pointing to one of this "
                "provider's source pages, or change the mapping value to "
                "False in pipelines/test_welcome_page_coverage.py."
            ),
        )


if __name__ == "__main__":
    unittest.main()
