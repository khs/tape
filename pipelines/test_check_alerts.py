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


class LoadLatestObservationSafetyTests(unittest.TestCase):
    """The evaluator runs under the service role and reads YAML files
    based on a user-controlled source_id. A malicious source_id like
    "../../../etc/passwd" must NOT escape src/content/sources/.

    These tests don't exercise the success path (that requires a live
    YAML + JSON on disk) — they only verify the guard rejects bad
    input cleanly.
    """

    def test_empty_string_rejected(self) -> None:
        self.assertIsNone(check_alerts.load_latest_observation(""))

    def test_relative_traversal_rejected(self) -> None:
        # The leading "../" doesn't match SAFE_SOURCE_ID (must start
        # with [a-zA-Z0-9_]) — guard hits before any FS access.
        self.assertIsNone(
            check_alerts.load_latest_observation("../../../etc/passwd")
        )

    def test_leading_slash_rejected(self) -> None:
        self.assertIsNone(
            check_alerts.load_latest_observation("/etc/passwd")
        )

    def test_dot_prefix_rejected(self) -> None:
        # A leading dot would let "./foo" or "..foo" slip past the
        # eye but `.` isn't in the start-character class.
        self.assertIsNone(
            check_alerts.load_latest_observation(".secret")
        )

    def test_embedded_traversal_rejected(self) -> None:
        # "fred/../../../etc/passwd" — slash + dots in the middle.
        # The regex allows ./- in the body BUT the resolve()
        # relative_to() check after that catches escape attempts.
        self.assertIsNone(
            check_alerts.load_latest_observation("fred/../../../etc/passwd")
        )

    def test_null_byte_rejected(self) -> None:
        # Null-byte injection sometimes truncates filenames in C-level
        # filesystem code. Python's pathlib raises on null bytes;
        # confirm we return None cleanly.
        self.assertIsNone(
            check_alerts.load_latest_observation("fred/cpi\x00.yaml")
        )

    def test_well_formed_source_id_not_rejected_by_regex(self) -> None:
        # Sanity check: the guard regex itself accepts a normal source
        # ID like "fred/cpi_yoy". The function still returns None
        # because no YAML exists at that path in the test runner,
        # but the regex check is what we're verifying here.
        self.assertIsNotNone(check_alerts.SAFE_SOURCE_ID.match("fred/cpi_yoy"))
        self.assertIsNotNone(
            check_alerts.SAFE_SOURCE_ID.match("acs_cd/median_household_income")
        )
        self.assertIsNotNone(
            check_alerts.SAFE_SOURCE_ID.match("worldbank_extended/ind1")
        )


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


class FireInWindowTests(unittest.TestCase):
    """Windowed evaluation — walk EVERY new observation, not just the
    endpoints. This is the weekly-eval-on-daily-series fix: a crossing
    that happened (and maybe reverted) between two weekly runs must
    still fire."""

    def test_empty_window_no_fire(self) -> None:
        self.assertIsNone(check_alerts.fire_in_window("gt", 4.0, [], 3.0))

    def test_gt_reports_most_recent_qualifying_point(self) -> None:
        win = [("2024-01-02", 4.5), ("2024-01-03", 4.7)]
        self.assertEqual(
            check_alerts.fire_in_window("gt", 4.0, win, 3.0),
            ("2024-01-03", 4.7),
        )

    def test_gt_fires_on_intermediate_even_if_latest_below(self) -> None:
        # Latest point dipped back below threshold, but an intermediate
        # point was above — a latest-vs-last-seen check would miss it.
        win = [("2024-01-02", 4.5), ("2024-01-03", 3.8)]
        self.assertEqual(
            check_alerts.fire_in_window("gt", 4.0, win, 3.0),
            ("2024-01-02", 4.5),
        )

    def test_crosses_above_midwindow_then_revert_still_fires(self) -> None:
        # THE regression this fixes. Crossed up to 5.0 then back to 3.5
        # within one weekly window. Endpoint comparison (anchor 3.0 vs
        # latest 3.5) sees no crossing; the walk catches it at 5.0.
        win = [("2024-01-02", 5.0), ("2024-01-03", 3.5)]
        self.assertEqual(
            check_alerts.fire_in_window("crosses_above", 4.0, win, 3.0),
            ("2024-01-02", 5.0),
        )

    def test_crosses_above_already_above_no_fire(self) -> None:
        # anchor_prev above threshold + window stays above → no crossing.
        win = [("2024-01-02", 5.0), ("2024-01-03", 5.5)]
        self.assertIsNone(
            check_alerts.fire_in_window("crosses_above", 4.0, win, 4.5),
        )

    def test_crosses_above_rearms_within_window(self) -> None:
        # cross up (d2), dip below (d3, re-arm), cross up again (d4).
        # The rolling prev re-arms; the LAST crossing is reported.
        win = [
            ("2024-01-02", 5.0),
            ("2024-01-03", 3.5),
            ("2024-01-04", 4.8),
        ]
        self.assertEqual(
            check_alerts.fire_in_window("crosses_above", 4.0, win, 3.0),
            ("2024-01-04", 4.8),
        )

    def test_crosses_above_first_run_no_anchor(self) -> None:
        # Baseline first run: window = [latest], anchor None → a
        # crosses_above can't fire (no prior to cross from).
        self.assertIsNone(
            check_alerts.fire_in_window(
                "crosses_above", 4.0, [("2024-01-03", 5.0)], None,
            ),
        )

    def test_crosses_below_within_window(self) -> None:
        win = [("2024-01-02", 4.5), ("2024-01-03", 3.5)]
        self.assertEqual(
            check_alerts.fire_in_window("crosses_below", 4.0, win, 4.2),
            ("2024-01-03", 3.5),
        )

    def test_change_above_step_inside_window(self) -> None:
        # A +1.5 day-over-day step (anchor 4.0 → 5.5) trips a 1.0
        # threshold even though the rest of the window is flat.
        win = [("2024-01-02", 5.5), ("2024-01-03", 5.6)]
        self.assertEqual(
            check_alerts.fire_in_window("change_above", 1.0, win, 4.0),
            ("2024-01-02", 5.5),
        )


class LoadDerivedLatestObservationTests(unittest.TestCase):
    """Migration 0007 added derived_spec to alert_rules. The evaluator
    aligns A and B by date and emits the latest (t, A op B) pair.

    These tests stub _load_points to return synthetic series so the
    test doesn't depend on real source YAML/JSON.
    """

    def setUp(self) -> None:
        self._orig_load_points = check_alerts._load_points

    def tearDown(self) -> None:
        check_alerts._load_points = self._orig_load_points

    def _stub_points(
        self, by_id: dict[str, list[dict[str, float | str]]]
    ) -> None:
        def stub(source_id: str):
            return by_id.get(source_id)
        check_alerts._load_points = stub  # type: ignore[assignment]

    def test_divide_aligns_by_date(self) -> None:
        self._stub_points({
            "fred/cpi": [
                {"t": "2024-01-01", "v": 3.0},
                {"t": "2024-02-01", "v": 3.2},
                {"t": "2024-03-01", "v": 3.4},
            ],
            "fred/dgs10": [
                {"t": "2024-01-01", "v": 4.0},
                {"t": "2024-02-01", "v": 4.0},
                {"t": "2024-03-01", "v": 4.25},
            ],
        })
        obs = check_alerts.load_derived_latest_observation(
            {"a": "fred/cpi", "op": "divide", "b": "fred/dgs10"},
        )
        self.assertEqual(obs, ("2024-03-01", 3.4 / 4.25))

    def test_sum_and_diff(self) -> None:
        self._stub_points({
            "a": [{"t": "2024-01-01", "v": 10.0}],
            "b": [{"t": "2024-01-01", "v": 3.0}],
        })
        sum_obs = check_alerts.load_derived_latest_observation(
            {"a": "a", "op": "sum", "b": "b"},
        )
        self.assertEqual(sum_obs, ("2024-01-01", 13.0))
        diff_obs = check_alerts.load_derived_latest_observation(
            {"a": "a", "op": "diff", "b": "b"},
        )
        self.assertEqual(diff_obs, ("2024-01-01", 7.0))

    def test_observations_returns_full_aligned_series(self) -> None:
        # load_derived_observations returns the whole aligned series;
        # the *_latest wrapper just takes its last element.
        self._stub_points({
            "a": [{"t": "2024-01-01", "v": 1.0}, {"t": "2024-02-01", "v": 2.0}],
            "b": [{"t": "2024-01-01", "v": 10.0}, {"t": "2024-02-01", "v": 20.0}],
        })
        series = check_alerts.load_derived_observations(
            {"a": "a", "op": "sum", "b": "b"},
        )
        self.assertEqual(series, [("2024-01-01", 11.0), ("2024-02-01", 22.0)])

    def test_alignment_uses_intersection_of_dates(self) -> None:
        # A has Mar 1 but B doesn't; the derived series' latest is
        # therefore the latest date both have data for (Feb 1).
        self._stub_points({
            "a": [
                {"t": "2024-01-01", "v": 1.0},
                {"t": "2024-02-01", "v": 2.0},
                {"t": "2024-03-01", "v": 3.0},
            ],
            "b": [
                {"t": "2024-01-01", "v": 10.0},
                {"t": "2024-02-01", "v": 20.0},
                # no March
            ],
        })
        obs = check_alerts.load_derived_latest_observation(
            {"a": "a", "op": "sum", "b": "b"},
        )
        self.assertEqual(obs, ("2024-02-01", 22.0))

    def test_divide_by_zero_skips_that_timestamp(self) -> None:
        self._stub_points({
            "a": [
                {"t": "2024-01-01", "v": 1.0},
                {"t": "2024-02-01", "v": 2.0},
            ],
            "b": [
                {"t": "2024-01-01", "v": 5.0},
                {"t": "2024-02-01", "v": 0.0},
            ],
        })
        # Feb is the latest A∩B date but B=0, so that point is
        # skipped. Result is Jan's derived value.
        obs = check_alerts.load_derived_latest_observation(
            {"a": "a", "op": "divide", "b": "b"},
        )
        self.assertEqual(obs, ("2024-01-01", 0.2))

    def test_returns_none_when_no_dates_overlap(self) -> None:
        self._stub_points({
            "a": [{"t": "2024-01-01", "v": 1.0}],
            "b": [{"t": "2024-02-01", "v": 2.0}],
        })
        obs = check_alerts.load_derived_latest_observation(
            {"a": "a", "op": "sum", "b": "b"},
        )
        self.assertIsNone(obs)

    def test_returns_none_when_either_source_missing(self) -> None:
        self._stub_points({"a": [{"t": "2024-01-01", "v": 1.0}]})
        obs = check_alerts.load_derived_latest_observation(
            {"a": "a", "op": "sum", "b": "b"},
        )
        self.assertIsNone(obs)

    def test_invalid_op_returns_none(self) -> None:
        self._stub_points({
            "a": [{"t": "2024-01-01", "v": 1.0}],
            "b": [{"t": "2024-01-01", "v": 2.0}],
        })
        obs = check_alerts.load_derived_latest_observation(
            {"a": "a", "op": "multiply", "b": "b"},
        )
        self.assertIsNone(obs)

    def test_missing_keys_returns_none(self) -> None:
        self.assertIsNone(check_alerts.load_derived_latest_observation({}))
        self.assertIsNone(
            check_alerts.load_derived_latest_observation({"a": "x"}),
        )
        # type-ignore: deliberately passing a non-dict to assert the
        # defensive branch.
        self.assertIsNone(
            check_alerts.load_derived_latest_observation("nope"),  # type: ignore[arg-type]
        )


if __name__ == "__main__":
    unittest.main()
