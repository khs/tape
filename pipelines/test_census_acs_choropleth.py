"""Unit tests for the share-indicator reliability floor in the ACS
choropleth pipeline. The floor (MIN_PCT_DENOM) suppresses percentages
computed over a universe too small to be stable — the micro-tracts and
empty "park" special-use tracts that otherwise paint 0% / 100% noise on
the tract + block-group maps. Populated institutional tracts (a prison's
~1,900 residents) clear the floor and are kept."""
import sys
import unittest
from pathlib import Path

# Resolve the sibling module whether run via pytest (pipelines/ on
# sys.path) or `python -m unittest pipelines.test_census_acs_choropleth`
# from the repo root.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from census_acs_choropleth import (  # noqa: E402
    MIN_PCT_DENOM,
    _sum_pct_combine,
    pct,
)


class TestReliabilityFloor(unittest.TestCase):
    def test_pct_suppresses_universe_below_floor(self):
        f = pct("num", "den")
        # A clean ratio is still dropped when the universe is too small.
        self.assertIsNone(f({"num": 5.0, "den": MIN_PCT_DENOM - 1.0}))
        # Zero / negative universe -> None (subsumed by the floor).
        self.assertIsNone(f({"num": 0.0, "den": 0.0}))
        self.assertIsNone(f({"num": 1.0, "den": None}))

    def test_pct_keeps_universe_at_or_above_floor(self):
        f = pct("num", "den")
        self.assertEqual(f({"num": 25.0, "den": float(MIN_PCT_DENOM)}), 25.0)
        # A genuine 0% over a large universe (e.g. a prison) is kept, not
        # suppressed — the floor targets unreliability, not extreme values.
        self.assertEqual(f({"num": 0.0, "den": 1896.0}), 0.0)

    def test_sum_pct_combine_respects_floor(self):
        num = ("a", "b")
        self.assertIsNone(
            _sum_pct_combine({"a": 2.0, "b": 1.0, "d": MIN_PCT_DENOM - 1.0}, num, "d")
        )
        self.assertEqual(
            _sum_pct_combine({"a": 30.0, "b": 10.0, "d": 200.0}, num, "d"), 20.0
        )
        # All numerator cells are the Census "no data" sentinel -> None.
        self.assertIsNone(
            _sum_pct_combine(
                {"a": -666666666.0, "b": -666666666.0, "d": 300.0}, num, "d"
            )
        )


if __name__ == "__main__":
    unittest.main()
