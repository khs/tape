"""
Unit tests for pipelines/bea.py point construction.

Regression coverage for the personal_income_virginia corruption: the
pipeline used to emit points in BEA API row order, and
common.write_timeseries only sorts when merging with an existing file,
so a fresh write could ship unsorted points (2014→2025 followed by
1959→2013) whose summary then served a stale 2013 "latest".
points_from_rows must therefore ALWAYS return ascending-by-t points,
deduped by year with the later row winning.

No network: points_from_rows is a pure function over BEA Data rows.

Run with::

    python -m pytest pipelines/test_bea.py
    python -m unittest pipelines.test_bea
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

# bea.py does `from common import write_timeseries` at import time; make
# sure the sibling resolves whether we run via pytest (pipelines/ on
# sys.path) or `python -m unittest pipelines.test_bea` from the repo root.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

MODULE_PATH = HERE / "bea.py"
spec = importlib.util.spec_from_file_location("bea_under_test", MODULE_PATH)
assert spec is not None and spec.loader is not None, MODULE_PATH
bea = importlib.util.module_from_spec(spec)
sys.modules["bea_under_test"] = bea
spec.loader.exec_module(bea)


def _row(year: str, value: str, unit_mult: str = "6") -> dict:
    return {"TimePeriod": year, "DataValue": value, "UNIT_MULT": unit_mult}


AGG = bea.INDICATORS[2]   # SAINC1 line 1, personal_income, to_billions=True
PC = bea.INDICATORS[3]    # SAINC1 line 3, pc_personal_income, raw dollars


class PointsFromRowsTests(unittest.TestCase):
    def test_out_of_order_rows_come_back_ascending(self) -> None:
        # The exact corruption shape: a modern run ahead of the
        # historical run in API row order.
        rows = [_row("2024", "1"), _row("2025", "2"),
                _row("1959", "3"), _row("2013", "4")]
        pts = bea.points_from_rows(AGG, rows)
        ts = [p["t"] for p in pts]
        self.assertEqual(ts, sorted(ts))
        self.assertEqual(ts, ["1959-01-01", "2013-01-01",
                              "2024-01-01", "2025-01-01"])
        # Last element is the max date — what build_summaries serves
        # as "latest" and trim_source_data anchors its cutoff on.
        self.assertEqual(pts[-1]["t"], max(ts))

    def test_duplicate_year_keeps_later_row(self) -> None:
        # Restatement rule: later-fetched row wins, mirroring
        # common._merge_points_by_t.
        rows = [_row("2020", "100"), _row("2021", "110"), _row("2020", "105")]
        pts = bea.points_from_rows(AGG, rows)
        self.assertEqual([p["t"] for p in pts], ["2020-01-01", "2021-01-01"])
        self.assertAlmostEqual(pts[0]["v"], 105e6 / 1e9)

    def test_suppressed_and_malformed_rows_skipped(self) -> None:
        rows = [
            _row("2019", "(NA)"),
            _row("2020", "(D)"),
            {"TimePeriod": "", "DataValue": "5", "UNIT_MULT": "6"},
            {"TimePeriod": "2022", "DataValue": None, "UNIT_MULT": "6"},
            _row("2021", "1,234.5"),
        ]
        pts = bea.points_from_rows(AGG, rows)
        self.assertEqual([p["t"] for p in pts], ["2021-01-01"])
        self.assertAlmostEqual(pts[0]["v"], 1234.5e6 / 1e9)

    def test_unit_conversion_aggregate_vs_per_capita(self) -> None:
        # Aggregates: DataValue * 10**UNIT_MULT dollars -> billions.
        agg = bea.points_from_rows(AGG, [_row("2024", "398579.8", "6")])
        self.assertAlmostEqual(agg[0]["v"], 398.5798)
        # Per-capita: raw dollar level, UNIT_MULT 0, no rescale.
        pc = bea.points_from_rows(PC, [_row("2024", "61234", "0")])
        self.assertAlmostEqual(pc[0]["v"], 61234.0)

    def test_empty_rows_give_empty_points(self) -> None:
        self.assertEqual(bea.points_from_rows(AGG, []), [])


if __name__ == "__main__":
    unittest.main()
