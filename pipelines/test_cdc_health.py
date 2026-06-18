"""Unit tests for pipelines/cdc_health.py build_causes.

The leading-causes builder maps a state NAME to an abbr (silent-drop risk
if Census/NCHS footnotes a name), enforces the NCHS <20-death reliability
floor, and needs >=2 points to emit a series. These tests mock fetch_csv
and redirect the output dirs to a temp tree, then assert the parse rules.

Run with::  python -m unittest pipelines.test_cdc_health
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent

# cdc_health.py does `from common import ...` (and `import _env`) at import
# time; make the siblings resolve under `python -m unittest` from the repo
# root as well as pytest.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import common  # the real module cdc_health writes through (DATA_ROOT)

MODULE_PATH = HERE / "cdc_health.py"
spec = importlib.util.spec_from_file_location("cdc_under_test", MODULE_PATH)
assert spec is not None and spec.loader is not None, MODULE_PATH
cdc = importlib.util.module_from_spec(spec)
sys.modules["cdc_under_test"] = cdc
spec.loader.exec_module(cdc)


def _row(state, cause, year, aadr, deaths):
    return {"state": state, "cause_name": cause, "year": year,
            "aadr": str(aadr), "deaths": str(deaths)}


# Heart disease AL (2 ok years), Cancer for a FOOTNOTED "Alabama *" (must
# still map), US national, a <20-death WY suicide pair (reliability floor),
# an unmapped "Narnia", and a single-point AK series (<2 -> not written).
FIXTURE = [
    _row("Alabama", "Heart disease", "2018", 200.5, 12000),
    _row("Alabama", "Heart disease", "2019", 198.0, 11800),
    _row("Alabama *", "Cancer", "2018", 150.0, 9000),
    _row("Alabama *", "Cancer", "2019", 149.0, 8900),
    _row("United States", "Heart disease", "2018", 165.0, 600000),
    _row("United States", "Heart disease", "2019", 163.0, 590000),
    _row("Wyoming", "Suicide", "2018", 25.0, 15),   # <20 deaths -> skip
    _row("Wyoming", "Suicide", "2019", 24.0, 18),   # <20 deaths -> skip
    _row("Narnia", "Heart disease", "2018", 100.0, 5000),  # unmapped -> skip
    _row("Alaska", "Heart disease", "2018", 170.0, 800),   # single point -> not written
]


class BuildCausesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._orig_data = common.DATA_ROOT
        self._orig_yaml = cdc.YAML_DIR
        common.DATA_ROOT = self.tmp
        cdc.YAML_DIR = self.tmp / "yaml"
        self._patch = mock.patch.object(cdc, "fetch_csv", lambda ds: FIXTURE)
        self._patch.start()
        self.n = cdc.build_causes()

    def tearDown(self) -> None:
        self._patch.stop()
        common.DATA_ROOT = self._orig_data
        cdc.YAML_DIR = self._orig_yaml
        self._tmp.cleanup()

    def _data(self, sid):
        p = self.tmp / "cdc_health" / f"{sid}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def test_normal_state_series_written(self) -> None:
        d = self._data("heart_disease_aadr_al")
        self.assertIsNotNone(d)
        self.assertEqual([(p["t"], p["v"]) for p in d["points"]],
                         [("2018-12-31", 200.5), ("2019-12-31", 198.0)])

    def test_footnoted_state_name_still_maps(self) -> None:
        # "Alabama *" -> strip_footnote_marker -> Alabama -> AL.
        self.assertIsNotNone(self._data("cancer_aadr_al"))

    def test_united_states_maps_to_us(self) -> None:
        self.assertIsNotNone(self._data("heart_disease_aadr_us"))

    def test_reliability_floor_drops_small_cells(self) -> None:
        # Both WY suicide rows are <20 deaths -> no series at all.
        self.assertIsNone(self._data("suicide_aadr_wy"))

    def test_unmapped_state_dropped(self) -> None:
        self.assertIsNone(self._data("heart_disease_aadr_narnia"))

    def test_single_point_series_not_written(self) -> None:
        # AK heart disease has one year only (>=2 required).
        self.assertIsNone(self._data("heart_disease_aadr_ak"))

    def test_yaml_emitted_for_written_series(self) -> None:
        self.assertTrue((self.tmp / "yaml" / "heart_disease_aadr_al.yaml").exists())

    def test_written_count(self) -> None:
        # al heart, al cancer, us heart = 3.
        self.assertEqual(self.n, 3)


if __name__ == "__main__":
    unittest.main()
