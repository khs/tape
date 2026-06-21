"""Canonical ACS indicator-stem -> topical-subject map (single source of truth).

The ACS providers (acs_cd, acs_metro, acs_state) historically tagged every
source only ['government', 'us'] (+ a thin real-estate/labor domain tag), so
their demographics / income / housing / labor content was invisible to topical
filtering. This map assigns each indicator STEM (the out_id, i.e. the source-id
minus its trailing geography slug) to one or more subjects.

Used by:
  - pipelines/retag_acs_subjects.py  (one-time in-place retag of existing YAMLs)
  - the three ACS emitters (future YAMLs / refresh backfills carry the subjects):
      _generate_acs_sources.py (acs_cd, and acs_metro via shared import),
      derive_acs_state_from_cd.py (acs_state).

Rulings (owner, 2026-06): gini -> income; educational attainment (adults_25plus
/ bachelors / masters) -> demographics AND income; WFH + commute -> housing;
health-insurance coverage -> health. The base ['government', 'us'] tags are kept
as-is; subjects are ADDED (replacing only the old real-estate/labor domain tag).
"""

from __future__ import annotations

# stem -> tuple of subject tags
SUBJECTS_BY_STEM: dict[str, tuple[str, ...]] = {
    # --- demographics ---
    "population": ("demographics",),
    "population_65_plus": ("demographics",),
    "population_under_18": ("demographics",),
    "median_age": ("demographics",),
    "foreign_born": ("demographics",),
    "pct_foreign_born": ("demographics",),
    "born_same_state": ("demographics",),
    "movers_last_year": ("demographics",),
    "mobility_universe": ("demographics",),
    "pct_movers": ("demographics",),
    "veterans": ("demographics",),
    "people_with_disability": ("demographics",),
    "people_disability_universe": ("demographics",),
    "pct_disability": ("demographics",),
    # --- health (insurance coverage) ---
    "people_uninsured": ("health",),
    "insurance_universe": ("health",),
    "pct_uninsured": ("health",),
    # --- educational attainment: demographics AND income (owner ruling) ---
    "adults_25plus": ("demographics", "income"),
    "bachelors_plus": ("demographics", "income"),
    "masters_plus": ("demographics", "income"),
    "pct_bachelors": ("demographics", "income"),
    "pct_masters": ("demographics", "income"),
    # --- income (gini -> income, owner ruling) ---
    "median_hh_income": ("income",),
    "gini_index": ("income",),
    "poverty_count": ("income",),
    "households_above_200k": ("income",),
    "households_below_25k": ("income",),
    "households_total_income": ("income",),
    "pct_households_above_200k": ("income",),
    "pct_households_below_25k": ("income",),
    # --- housing (WFH + commute -> housing, owner ruling) ---
    "median_home_value": ("housing",),
    "median_gross_rent": ("housing",),
    "median_year_built": ("housing",),
    "owner_occupied": ("housing",),
    "renter_occupied": ("housing",),
    "broadband_households": ("housing",),
    "households_no_vehicle": ("housing",),
    "households_total_vehicle": ("housing",),
    "pct_no_vehicle": ("housing",),
    "workers_wfh": ("housing",),
    "workers_total_commute": ("housing",),
    "pct_workers_wfh": ("housing",),
    "median_commute_minutes": ("housing",),
    # --- labor ---
    "workers_manufacturing": ("labor",),
    "workers_total_industry": ("labor",),
    "pct_manufacturing": ("labor",),
}

# Stems sorted longest-first so longest-prefix matching picks the most specific
# (e.g. "population_65_plus" before "population").
_STEMS_LONGEST_FIRST = sorted(SUBJECTS_BY_STEM, key=len, reverse=True)


def subjects_for_out_id(out_id: str) -> tuple[str, ...]:
    """Exact out_id (stem) lookup, used by the emitters which know the stem."""
    return SUBJECTS_BY_STEM.get(out_id, ())


def subjects_for_filename(stem_with_geo: str) -> tuple[str, ...] | None:
    """Resolve a source-id / filename (stem + trailing geo slug, no extension)
    to its subjects by longest-prefix match. Returns None if no stem matches
    (so callers can flag unmapped indicators)."""
    for stem in _STEMS_LONGEST_FIRST:
        if stem_with_geo == stem or stem_with_geo.startswith(stem + "_"):
            return SUBJECTS_BY_STEM[stem]
    return None
