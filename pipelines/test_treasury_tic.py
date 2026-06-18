"""Unit tests for pipelines/treasury_tic.py parse_tic.

The TIC parser is a stacked-year-block state machine over a tab-separated
file; a past commit (8b1dd5ebab) silently dropped China + South Korea. These
tests pin: the multi-year block walk, the Dec->Jan column order, value-skip
rules (---/*/footnote), the double-quoted "China, Mainland" label, trailing
footnote-marker stripping, and a guard that China + South Korea survive.

Run with::  python -m unittest pipelines.test_treasury_tic
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

# treasury_tic.py does `from common import ...` at import time; make the
# sibling resolve whether run via pytest (pipelines/ on sys.path) or
# `python -m unittest pipelines.test_treasury_tic` from the repo root.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

MODULE_PATH = HERE / "treasury_tic.py"
spec = importlib.util.spec_from_file_location("tic_under_test", MODULE_PATH)
assert spec is not None and spec.loader is not None, MODULE_PATH
tic = importlib.util.module_from_spec(spec)
sys.modules["tic_under_test"] = tic
spec.loader.exec_module(tic)

# Two stacked year-blocks. Columns are Dec..Jan (12). Exercises: a "---"
# hole (Japan Sep), a "*" footnote in a value (Grand Total Nov), a quoted
# comma label (China), a trailing footnote marker on a name (Israel *), an
# unmapped country (Narnia, must be dropped), and South Korea ("Korea,
# South") which a past bug dropped.
FIXTURE = "\n".join([
    "Major Foreign Holders of Treasury Securities (preamble, ignored)",
    "",
    "Country\t2024\t2024\t2024\t2024\t2024\t2024\t2024\t2024\t2024\t2024\t2024\t2024",
    "--------",
    "Japan\t1100.5\t1090.0\t1085.2\t---\t1080.0\t1075.0\t1070.0\t1065.0\t1060.0\t1055.0\t1050.0\t1045.0",
    '"China, Mainland"\t780.1\t779.0\t778.0\t777.0\t776.0\t775.0\t774.0\t773.0\t772.0\t771.0\t770.0\t769.0',
    "Korea, South\t125.0\t124.0\t123.0\t122.0\t121.0\t120.0\t119.0\t118.0\t117.0\t116.0\t115.0\t114.0",
    "Israel *\t55.0\t54.0\t53.0\t52.0\t51.0\t50.0\t49.0\t48.0\t47.0\t46.0\t45.0\t44.0",
    "Grand Total\t8500.0\t*\t8490.0\t8480.0\t8470.0\t8460.0\t8450.0\t8440.0\t8430.0\t8420.0\t8410.0\t8400.0",
    "Narnia\t1.0\t2.0\t3.0\t4.0\t5.0\t6.0\t7.0\t8.0\t9.0\t10.0\t11.0\t12.0",
    "",
    "Country\t2023\t2023\t2023\t2023\t2023\t2023\t2023\t2023\t2023\t2023\t2023\t2023",
    "--------",
    "Japan\t1000.0\t999.0\t998.0\t997.0\t996.0\t995.0\t994.0\t993.0\t992.0\t991.0\t990.0\t989.0",
    "",
])


class ParseTicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.out = tic.parse_tic(FIXTURE)

    def test_only_mapped_countries(self) -> None:
        self.assertIn("Japan", self.out)
        self.assertIn("Grand Total", self.out)
        self.assertNotIn("Narnia", self.out)  # not in COUNTRY_MAP -> dropped

    def test_china_and_south_korea_survive(self) -> None:
        # Regression guard for the 8b1dd5ebab silent-drop.
        self.assertIn("China, Mainland", self.out)   # quoted comma label
        self.assertIn("Korea, South", self.out)
        self.assertTrue(self.out["China, Mainland"])
        self.assertTrue(self.out["Korea, South"])

    def test_footnote_marked_name_still_maps(self) -> None:
        # "Israel *" must strip to "Israel" and map (the hardening).
        self.assertIn("Israel", self.out)
        self.assertEqual(len(self.out["Israel"]), 12)

    def test_dec_to_jan_dates_and_values(self) -> None:
        jp = {p["t"]: p["v"] for p in self.out["Japan"]}
        self.assertEqual(jp["2024-12-15"], 1100.5)  # col 1 = Dec
        self.assertEqual(jp["2024-01-15"], 1045.0)  # col 12 = Jan
        self.assertNotIn("2024-09-15", jp)          # the "---" hole skipped

    def test_value_skips(self) -> None:
        # Japan has one "---" -> 11 of 12 months for 2024.
        jp2024 = [p for p in self.out["Japan"] if p["t"].startswith("2024")]
        self.assertEqual(len(jp2024), 11)
        # Grand Total has a "*" in Nov -> 11 of 12.
        self.assertEqual(len(self.out["Grand Total"]), 11)

    def test_multi_year_blocks_merge_and_sort(self) -> None:
        # Japan spans 2023 + 2024, chronologically ascending.
        ts = [p["t"] for p in self.out["Japan"]]
        self.assertEqual(ts, sorted(ts))
        self.assertTrue(any(t.startswith("2023") for t in ts))
        self.assertTrue(any(t.startswith("2024") for t in ts))


if __name__ == "__main__":
    unittest.main()
