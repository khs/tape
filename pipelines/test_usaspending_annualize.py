"""Unit tests for the partial-FY annualization helper (audit new-#2)."""
import sys
import unittest
from pathlib import Path

# Resolve the sibling module whether run via pytest (pipelines/ on
# sys.path) or `python -m unittest pipelines.test_usaspending_annualize`
# from the repo root.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from usaspending_annualize import annualize_open_fy, open_fy_anchor  # noqa: E402


class TestAnnualizeOpenFY(unittest.TestCase):
    def _series(self, last_v):
        # FY2024, FY2025 full years, FY2026 open (anchor 2026-09-30).
        return [
            {"t": "2024-09-30", "v": 1.0},
            {"t": "2025-09-30", "v": 1.15},
            {"t": "2026-09-30", "v": last_v},
        ]

    def test_level_drop_is_annualized(self):
        pts, ann = annualize_open_fy(self._series(0.687), 2026, 7)
        # 0.687 * 12/7
        self.assertAlmostEqual(pts[-1]["v"], 0.687 * 12 / 7, places=9)
        self.assertEqual(pts[-1]["t"], "2026-09-30")
        self.assertIsNotNone(ann)
        self.assertEqual(ann["date"], "2026-09-30")
        self.assertIn("FY2026 annualized", ann["label"])
        self.assertIn("7 of 12", ann["label"])

    def test_no_drop_is_left_raw(self):
        # Partial point already above the prior full FY → no annualization
        # (annualizing would invent a spike).
        pts, ann = annualize_open_fy(self._series(1.30), 2026, 7)
        self.assertEqual(pts[-1]["v"], 1.30)
        self.assertIsNone(ann)

    def test_full_coverage_no_annualize(self):
        pts, ann = annualize_open_fy(self._series(0.687), 2026, 12)
        self.assertEqual(pts[-1]["v"], 0.687)
        self.assertIsNone(ann)

    def test_trailing_point_not_open_fy(self):
        # Last point is a closed FY (anchor != open-FY) → untouched.
        closed = [
            {"t": "2024-09-30", "v": 1.0},
            {"t": "2025-09-30", "v": 0.9},  # a real drop, but FY is closed
        ]
        pts, ann = annualize_open_fy(closed, 2026, 7)
        self.assertEqual(pts[-1]["v"], 0.9)
        self.assertIsNone(ann)

    def test_too_few_points(self):
        pts, ann = annualize_open_fy([{"t": "2026-09-30", "v": 0.5}], 2026, 7)
        self.assertIsNone(ann)
        self.assertEqual(len(pts), 1)

    def test_does_not_mutate_input(self):
        original = self._series(0.687)
        snapshot = [dict(p) for p in original]
        annualize_open_fy(original, 2026, 7)
        self.assertEqual(original, snapshot)

    def test_anchor_format(self):
        self.assertEqual(open_fy_anchor(2026), "2026-09-30")


if __name__ == "__main__":
    unittest.main()
