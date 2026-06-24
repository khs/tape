"""
Property-based (Hypothesis) fuzz of the merge-on-write + point-order invariants
in common.py -- the exact class that produced the bea/personal_income merge bug
(two date ranges concatenated, so the file's last element / `latest` went stale
while newer data sat earlier in the array).

For ANY two well-formed point lists (overlapping, unsorted, duplicate dates),
_merge_points_by_t must produce a strictly-ascending, deduped,
validate_points-clean series that loses no dates, invents none, and lets the
`new` list win on a timestamp collision.

Run with::
    python -m unittest pipelines.test_merge_points_fuzz   (or pytest)
"""
from __future__ import annotations

import os
import unittest
from datetime import date

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Two modes. The default GATE run is derandomized at a modest example count, so a
# given commit always gets the same verdict (a non-deterministic gate can fail an
# unrelated push when a fresh draw trips a latent bug). The weekly DEEP run
# (env FUZZ_DEEP=1, in .github/workflows/weekly-safety.yml) re-randomizes and does
# ~25x the examples to hunt genuinely new counterexamples; a failure there is a
# signal to open an issue, not a blocked deploy.
# suppress_health_check(too_slow): a cold first draw (Hypothesis warmup) can blow
# the per-draw budget on a busy box; it's a generation-speed flake, not a property
# failure. deadline=None keeps a slow draw from flaking either mode.
_DEEP = os.environ.get("FUZZ_DEEP") == "1"
_S = settings(
    max_examples=10_000 if _DEEP else 400,
    derandomize=not _DEEP,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

try:
    from common import _merge_points_by_t, validate_points
except ModuleNotFoundError:  # imported as the `pipelines` package (CI unittest)
    from pipelines.common import _merge_points_by_t, validate_points

# A well-formed point: ISO YYYY-MM-DD date + a finite numeric value. Zero-padded
# ISO dates sort lexically == chronologically, which both the merge sort and
# validate_points's `t <= prev` check rely on.
_iso = st.dates(min_value=date(1900, 1, 1), max_value=date(2100, 12, 31)).map(date.isoformat)
_finite = st.floats(allow_nan=False, allow_infinity=False)
_points = st.lists(st.fixed_dictionaries({"t": _iso, "v": _finite}), max_size=60)


class MergePointsFuzz(unittest.TestCase):
    @given(_points, _points)
    @_S
    def test_output_is_always_structurally_valid(self, a, b):
        # The invariant the renderer + integrity gates depend on, and the one the
        # personal_income merge bug violated: strictly ascending, no duplicates.
        self.assertEqual(validate_points(_merge_points_by_t(a, b), allow_empty=True), [])

    @given(_points, _points)
    @_S
    def test_is_idempotent(self, a, b):
        merged = _merge_points_by_t(a, b)
        self.assertEqual(_merge_points_by_t(merged, merged), merged)

    @given(_points, _points)
    @_S
    def test_preserves_exactly_the_union_of_dates(self, a, b):
        merged = _merge_points_by_t(a, b)
        self.assertEqual(
            {p["t"] for p in merged},
            {p["t"] for p in a} | {p["t"] for p in b},
        )

    @given(_points, _points)
    @_S
    def test_new_wins_on_date_collision(self, a, b):
        merged = {p["t"]: p["v"] for p in _merge_points_by_t(a, b)}
        # `new` (b) wins; within b, the last occurrence of a date wins (dict assign),
        # mirroring the merge loop's `for p in new: merged[t] = p`.
        b_last = {p["t"]: p["v"] for p in b}
        for t, v in b_last.items():
            self.assertEqual(merged[t], v)


if __name__ == "__main__":
    unittest.main()
