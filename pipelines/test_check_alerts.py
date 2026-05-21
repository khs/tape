"""Unit tests for the alert-evaluator condition logic.

The end-to-end pipeline talks to Supabase + reads source data files;
exercising that requires live services. These tests cover the pure-
function piece (evaluate_condition) which is also where the alert
LOGIC lives — get the boundary cases right here and the rest of the
pipeline is mostly plumbing.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add this directory to sys.path so test runs from either the repo
# root (`python -m unittest pipelines.test_check_alerts`) or from
# inside the pipelines/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_alerts  # noqa: E402


class EvaluateConditionTests(unittest.TestCase):
    # gt / gte / lt / lte are simple numeric comparisons. Test on
    # both sides of the threshold + at the threshold.
    def test_gt_below_threshold(self) -> None:
        self.assertFalse(check_alerts.evaluate_condition("gt", 4.0, 3.9, None))

    def test_gt_at_threshold(self) -> None:
        # gt is strict: equal is NOT triggered.
        self.assertFalse(check_alerts.evaluate_condition("gt", 4.0, 4.0, None))

    def test_gt_above_threshold(self) -> None:
        self.assertTrue(check_alerts.evaluate_condition("gt", 4.0, 4.1, None))

    def test_gte_at_threshold(self) -> None:
        # gte includes equal.
        self.assertTrue(check_alerts.evaluate_condition("gte", 4.0, 4.0, None))

    def test_lt_at_threshold(self) -> None:
        self.assertFalse(check_alerts.evaluate_condition("lt", 4.0, 4.0, None))

    def test_lt_below_threshold(self) -> None:
        self.assertTrue(check_alerts.evaluate_condition("lt", 4.0, 3.9, None))

    def test_lte_at_threshold(self) -> None:
        self.assertTrue(check_alerts.evaluate_condition("lte", 4.0, 4.0, None))

    # crosses_above needs a prior value strictly at-or-below threshold
    # AND a current value strictly above. Re-firing requires going
    # back below and crossing up again.
    def test_crosses_above_simple(self) -> None:
        # prev = 3.5 (below), cur = 4.5 (above) → fires
        self.assertTrue(
            check_alerts.evaluate_condition("crosses_above", 4.0, 4.5, 3.5),
        )

    def test_crosses_above_already_above(self) -> None:
        # prev = 4.5 (above), cur = 4.6 (still above) → does NOT fire.
        # Prevents re-firing every observation once threshold is
        # exceeded; the alert is about the TRANSITION.
        self.assertFalse(
            check_alerts.evaluate_condition("crosses_above", 4.0, 4.6, 4.5),
        )

    def test_crosses_above_no_prior(self) -> None:
        # First observation ever: no prior to compare to. Don't fire.
        self.assertFalse(
            check_alerts.evaluate_condition("crosses_above", 4.0, 5.0, None),
        )

    def test_crosses_above_prior_at_threshold(self) -> None:
        # prev exactly at threshold counts as below for crosses_above
        # (using <=). prev=4.0, cur=4.1 → fires.
        self.assertTrue(
            check_alerts.evaluate_condition("crosses_above", 4.0, 4.1, 4.0),
        )

    def test_crosses_below_simple(self) -> None:
        # prev = 4.5 (above), cur = 3.5 (below) → fires
        self.assertTrue(
            check_alerts.evaluate_condition("crosses_below", 4.0, 3.5, 4.5),
        )

    def test_crosses_below_already_below(self) -> None:
        self.assertFalse(
            check_alerts.evaluate_condition("crosses_below", 4.0, 3.4, 3.5),
        )

    def test_crosses_below_inversion_signal(self) -> None:
        # Canonical use case: 10Y-2Y spread inverting (crossing
        # below 0). prev = 0.20 (positive), cur = -0.10 (negative).
        self.assertTrue(
            check_alerts.evaluate_condition("crosses_below", 0.0, -0.10, 0.20),
        )

    # change_above measures the absolute step size between
    # consecutive observations (volatility detection).
    def test_change_above_positive(self) -> None:
        # cur - prev = +1.5; threshold 1.0 → fires.
        self.assertTrue(
            check_alerts.evaluate_condition("change_above", 1.0, 5.5, 4.0),
        )

    def test_change_above_negative(self) -> None:
        # Symmetric — a -1.5 change still trips a 1.0 threshold.
        self.assertTrue(
            check_alerts.evaluate_condition("change_above", 1.0, 4.0, 5.5),
        )

    def test_change_above_at_threshold(self) -> None:
        # Strict greater-than (matches the schema's check name).
        self.assertFalse(
            check_alerts.evaluate_condition("change_above", 1.0, 5.0, 4.0),
        )

    def test_change_above_no_prior(self) -> None:
        # No prior → can't compute a change.
        self.assertFalse(
            check_alerts.evaluate_condition("change_above", 1.0, 5.0, None),
        )

    # Unknown conditions never fire — forward-compat guard so a
    # schema migration that adds a new condition string doesn't
    # accidentally trigger old evaluator runs.
    def test_unknown_condition_does_not_fire(self) -> None:
        self.assertFalse(
            check_alerts.evaluate_condition("not_a_real_op", 4.0, 5.0, 3.0),
        )


if __name__ == "__main__":
    unittest.main()
