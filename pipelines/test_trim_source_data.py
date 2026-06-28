"""Tests for the M4 downsample in trim_source_data.py.

The headline guarantee: decimating an over-budget series preserves its extremes
(a one-day spike or crash deep in history must survive), keeps the recent tier
verbatim, stays under budget, stamps the approximated-flag, and is idempotent.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trim_source_data import (  # noqa: E402
    BUDGET,
    RECENT_NATIVE_DAYS,
    downsample_file,
    downsample_points,
    m4_bucket,
)


def make_daily(n: int, start: str = "1980-01-01", base: float = 100.0) -> list[dict]:
    d0 = date.fromisoformat(start)
    return [{"t": (d0 + timedelta(days=i)).isoformat(), "v": base} for i in range(n)]


class TestDownsample(unittest.TestCase):
    def test_under_budget_untouched(self):
        pts = make_daily(200)
        out, approx = downsample_points(pts)
        self.assertEqual(out, pts)
        self.assertIsNone(approx)

    def test_over_budget_preserves_extremes(self):
        n = 9000  # ~24y daily, well over budget
        pts = make_daily(n)
        pts[500]["v"] = 99999.0   # spike deep in OLD history
        pts[1500]["v"] = -50000.0  # crash deep in OLD history
        out, approx = downsample_points(pts)
        self.assertLessEqual(len(out), BUDGET)
        vals = [p["v"] for p in out]
        self.assertIn(99999.0, vals, "old spike (max) must survive decimation")
        self.assertIn(-50000.0, vals, "old crash (min) must survive decimation")
        self.assertIsNotNone(approx)

    def test_span_and_recent_preserved(self):
        pts = make_daily(9000)
        out, approx = downsample_points(pts)
        # Full span: first + last timestamps unchanged.
        self.assertEqual(out[0]["t"], pts[0]["t"])
        self.assertEqual(out[-1]["t"], pts[-1]["t"])
        # Recent tier (last 5y) kept verbatim.
        latest = date.fromisoformat(pts[-1]["t"])
        cutoff = latest - timedelta(days=RECENT_NATIVE_DAYS)
        recent_ts = {p["t"] for p in pts if date.fromisoformat(p["t"]) >= cutoff}
        out_ts = {p["t"] for p in out}
        self.assertTrue(recent_ts <= out_ts, "recent tier must be verbatim")
        self.assertEqual(approx, cutoff.isoformat())
        # Output sorted ascending by time.
        self.assertEqual(out_ts_sorted := [p["t"] for p in out], sorted(out_ts_sorted))

    def test_points_idempotent(self):
        pts = make_daily(9000)
        out, _ = downsample_points(pts)
        out2, approx2 = downsample_points(out)
        self.assertEqual(out2, out)  # already under budget → untouched
        self.assertIsNone(approx2)

    def test_m4_bucket_bounds_and_extremes(self):
        pts = make_daily(4000)
        pts[10]["v"] = 1e6
        out = m4_bucket(pts, 400)
        self.assertLessEqual(len(out), 400)
        self.assertIn(1e6, [p["v"] for p in out])

    def test_file_flag_summary_and_idempotency(self):
        pts = make_daily(9000)
        pts[500]["v"] = 99999.0
        with tempfile.TemporaryDirectory() as d:
            df = Path(d) / "x.json"
            sf = Path(d) / "x.summary.json"
            df.write_text(json.dumps({"kind": "timeseries", "points": pts}))
            sf.write_text(json.dumps({"kind": "timeseries", "latest": pts[-1]}))

            changed, before, after = downsample_file(df)
            self.assertTrue(changed)
            self.assertLessEqual(after, BUDGET)
            data = json.loads(df.read_text())
            self.assertIn("approximatedBefore", data)
            summ = json.loads(sf.read_text())
            self.assertEqual(summ.get("approximatedBefore"), data["approximatedBefore"],
                             "summary must mirror the flag")

            # Re-run: no change, flag preserved (the prior-flag branch).
            changed2, _, _ = downsample_file(df)
            self.assertFalse(changed2)
            self.assertEqual(json.loads(df.read_text())["approximatedBefore"],
                             data["approximatedBefore"])

    def test_annual_century_untouched(self):
        # 125 annual points (population-shaped) — under budget, full history kept.
        d0 = date.fromisoformat("1900-01-01")
        pts = [{"t": (d0.replace(year=1900 + i)).isoformat(), "v": 1000 + i} for i in range(125)]
        out, approx = downsample_points(pts)
        self.assertEqual(len(out), 125)
        self.assertIsNone(approx)


if __name__ == "__main__":
    unittest.main()
