"""Unit tests for the ACS CD pipeline's stable-geography machinery:
multi-code bin medians, vintage-keyed bin schedules, the chunked
robust tract fetch, and the INDICATORS-list invariants the metro +
national pipelines depend on."""
import sys
import unittest
from pathlib import Path

# Resolve the sibling module whether run via pytest (pipelines/ on
# sys.path) or `python -m unittest pipelines.test_census_acs_cd`
# from the repo root.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from census_acs_cd import (  # noqa: E402
    AGG_CD_LEVEL,
    AGG_CD_LEVEL_SUM,
    AGG_MEDIAN_CD_DIST,
    AGG_MEDIAN_DIST,
    AGG_PCT,
    AGG_SUM,
    B01001_AGE_BINS,
    CD_BASIS_TRACT,
    CD_BASIS_TRACT_MEDIAN,
    INDICATORS,
    AcsVar,
    bin_cell_codes,
    fetch_tract_robust,
    resolve_cd_bins,
    weighted_median_from_bins,
)

BY_ID = {v.out_id: v for v in INDICATORS}


class TestWeightedMedianFromBins(unittest.TestCase):
    def test_single_code_interpolation(self):
        bins = [("A", 0, 10), ("B", 10, 20), ("C", 20, 30)]
        # total 8, target 4 → 1 into B's 6 → 10 + (4-3)/6*10
        med = weighted_median_from_bins(bins, {"A": 3, "B": 6, "C": -1})
        self.assertAlmostEqual(med, 10 + (1 / 6) * 10)

    def test_multi_code_cells_merge_into_one_bin(self):
        # Male + female cells of the same bracket must merge BEFORE
        # interpolation: two same-bounds entries walked sequentially
        # interpolate differently whenever the target falls inside the
        # bracket (vs exactly on its edge).
        counts = {"M": 10, "F": 10, "C": 5}
        merged = [(("M", "F"), 0, 10), ("C", 10, 20)]
        med = weighted_median_from_bins(merged, counts)
        # total 25, target 12.5 → 12.5/20 of the way through bin 1
        self.assertAlmostEqual(med, 6.25)
        # The buggy sequential encoding would land at 2.5 instead.
        split = [("M", 0, 10), ("F", 0, 10), ("C", 10, 20)]
        med_split = weighted_median_from_bins(split, counts)
        self.assertAlmostEqual(med_split, 2.5)
        self.assertNotAlmostEqual(med, med_split)

    def test_zero_total_returns_none(self):
        self.assertIsNone(weighted_median_from_bins([("A", 0, 10)], {}))
        self.assertIsNone(weighted_median_from_bins([("A", 0, 10)], {"A": 0}))


class TestBinSchedules(unittest.TestCase):
    def test_year_built_era_resolution(self):
        v = BY_ID["median_year_built"]
        eras = {
            2010: (2005, 2012), 2011: (2005, 2012),
            2012: (2010, 2015), 2014: (2010, 2015),
            2015: (2014, 2021), 2020: (2014, 2021),
            2021: (2020, 2026), 2022: (2020, 2026),
        }
        for year, (lo, hi) in eras.items():
            bins = resolve_cd_bins(v, year)
            self.assertEqual((bins[-1][1], bins[-1][2]), (lo, hi),
                             f"vintage {year}")

    def test_value_and_rent_schema_switch_at_2015(self):
        self.assertEqual(len(resolve_cd_bins(BY_ID["median_home_value"], 2014)), 24)
        self.assertEqual(len(resolve_cd_bins(BY_ID["median_home_value"], 2015)), 26)
        self.assertEqual(len(resolve_cd_bins(BY_ID["median_gross_rent"], 2014)), 21)
        self.assertEqual(len(resolve_cd_bins(BY_ID["median_gross_rent"], 2015)), 24)

    def test_before_first_vintage_resolves_empty(self):
        v = AcsVar("x", "", "x", "u", 0, AGG_CD_LEVEL,
                   cd_basis=CD_BASIS_TRACT_MEDIAN,
                   cd_bin_schedule=[(2015, [("A", 0, 1)])])
        self.assertEqual(resolve_cd_bins(v, 2014), [])
        self.assertEqual(resolve_cd_bins(v, 2015), [("A", 0, 1)])

    def test_all_schedules_ascending_and_positive_width(self):
        for v in INDICATORS:
            for first_year, bins in v.cd_bin_schedule:
                lows = [b[1] for b in bins]
                self.assertEqual(lows, sorted(lows), (v.out_id, first_year))
                for _, lo, hi in bins:
                    self.assertGreater(hi, lo, (v.out_id, first_year))

    def test_age_bins_contiguous_with_46_cells(self):
        codes = [c for cell, _, _ in B01001_AGE_BINS
                 for c in bin_cell_codes(cell)]
        self.assertEqual(len(codes), 46)
        self.assertEqual(len(set(codes)), 46)
        for a, b in zip(B01001_AGE_BINS, B01001_AGE_BINS[1:]):
            self.assertEqual(a[2], b[1])

    def test_rent_bins_exclude_subtotal_and_no_cash_rent(self):
        # Median gross rent universe = cash renters: bin cells must not
        # include the 001 total, the 002 cash-rent subtotal, or the
        # final "No cash rent" cell of either era (024 pre-2015 / 027).
        v = BY_ID["median_gross_rent"]
        for year, banned in ((2014, {"B25063_001E", "B25063_002E", "B25063_024E"}),
                             (2022, {"B25063_001E", "B25063_002E", "B25063_027E"})):
            codes = {c for cell, _, _ in resolve_cd_bins(v, year)
                     for c in bin_cell_codes(cell)}
            self.assertFalse(codes & banned, (year, codes & banned))


class TestFetchTractRobust(unittest.TestCase):
    def test_chunks_merge_and_poisoned_var_is_isolated(self):
        # 60 codes forces two chunks; "BAD" poisons any request that
        # includes it (the Census API 400s the whole call), so the
        # binary split must drop ONLY it.
        codes = [f"V{i:03d}" for i in range(59)] + ["BAD"]
        calls = []

        def fake_fetch(year, sub, fips, key):
            calls.append(list(sub))
            if "BAD" in sub:
                return {}
            return {"t1": {c: 1.0 for c in sub}}

        merged = fetch_tract_robust(2022, codes, "51", "k", _fetch=fake_fetch)
        self.assertEqual(set(merged), {"t1"})
        self.assertEqual(len(merged["t1"]), 59)  # every good var survived
        self.assertNotIn("BAD", merged["t1"])
        self.assertTrue(any(len(c) > 1 for c in calls))  # chunked
        self.assertIn(["BAD"], calls)  # isolated down to the lone var

    def test_empty_codes_no_calls(self):
        def boom(*a):  # pragma: no cover - must not be reached
            raise AssertionError("fetch called for empty code list")
        self.assertEqual(fetch_tract_robust(2022, [], "51", "k", _fetch=boom), {})


class TestIndicatorInvariants(unittest.TestCase):
    def test_cd_level_leftovers_are_only_untracted_tables(self):
        leftovers = sorted(
            v.out_id for v in INDICATORS
            if not v.cd_basis
            and v.agg in (AGG_CD_LEVEL, AGG_CD_LEVEL_SUM, AGG_MEDIAN_CD_DIST)
        )
        self.assertEqual(
            leftovers, ["gini_index", "workers_class_universe", "workers_government"],
        )

    def test_pct_pairs_share_geo_basis(self):
        def basis(v):
            return "tract" if (v.cd_basis or v.agg == AGG_SUM) else "cd"
        for v in INDICATORS:
            if v.agg != AGG_PCT:
                continue
            self.assertEqual(
                basis(BY_ID[v.numerator_id]), basis(BY_ID[v.denominator_id]),
                v.out_id,
            )

    def test_tract_indicators_have_codes_or_bins(self):
        for v in INDICATORS:
            if v.cd_basis == CD_BASIS_TRACT:
                self.assertTrue(v.var_code or v.sum_codes, v.out_id)
            elif v.cd_basis == CD_BASIS_TRACT_MEDIAN:
                self.assertTrue(v.cd_bin_schedule, v.out_id)
                self.assertEqual(v.cd_bin_schedule[0][0], 2010, v.out_id)

    def test_metro_national_contract(self):
        # The metro/national pipelines fetch each indicator directly at
        # their own geography keyed off `agg` — they need var_code for
        # the single-cell strategies, sum_codes for cell sums, and bins
        # with PLAIN string codes for their distribution medians.
        for v in INDICATORS:
            if v.agg in (AGG_SUM, AGG_CD_LEVEL, AGG_MEDIAN_DIST):
                self.assertTrue(v.var_code, v.out_id)
            elif v.agg == AGG_CD_LEVEL_SUM:
                self.assertTrue(v.sum_codes, v.out_id)
            elif v.agg == AGG_MEDIAN_CD_DIST:
                self.assertTrue(v.bins, v.out_id)
                for cell, _, _ in v.bins:
                    self.assertIsInstance(cell, str, v.out_id)

    def test_table_availability_gates(self):
        self.assertEqual(BY_ID["people_uninsured"].first_tract_vintage, 2013)
        self.assertEqual(BY_ID["insurance_universe"].first_tract_vintage, 2013)
        self.assertEqual(BY_ID["people_with_disability"].first_tract_vintage, 2012)
        self.assertEqual(BY_ID["people_disability_universe"].first_tract_vintage, 2012)


if __name__ == "__main__":
    unittest.main()
