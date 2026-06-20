"""
Consistency gate: pipelines/fred_sources.yaml (the metadata catalog the source
YAMLs are generated from) must stay aligned with fred_series.SPECS (the fetch
list). Without this, a series can be fetched-but-unsurfaced or surfaced-but-
never-refreshed (silent staleness) -- the exact failure the catalog restructure
was meant to prevent.

  - every fetched SPEC has a catalog row (YAML-backed or component:true)
  - every catalog row's series is actually fetched by SPECS
  - the fetch params a catalog row carries (series / transformation / scale /
    fetchName / fetchUnit) match the SPEC, so the fetcher could read the catalog

Run:  python -m unittest pipelines.test_fred_catalog
"""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "pipelines" / "fred_sources.yaml"


def _out_id(series: str, transformation) -> str:
    return f"{series}_{transformation.upper()}" if transformation else series


class FredCatalogConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import fred_series as fs  # sibling import (needs pipelines/ on path)
        cls.specs = {_out_id(s.series_id, s.transformation): s for s in fs.SPECS}
        cls.cat = yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or {}
        cls.cat_out = {
            _out_id(r["series"], r.get("transformation")): r
            for r in cls.cat.values()
        }

    def test_every_spec_has_a_catalog_row(self):
        missing = sorted(set(self.specs) - set(self.cat_out))
        self.assertEqual(missing, [], f"fetched but not in catalog: {missing}")

    def test_every_catalog_row_is_fetched(self):
        extra = sorted(set(self.cat_out) - set(self.specs))
        self.assertEqual(extra, [], f"in catalog but never fetched: {extra}")

    def test_fetch_params_match(self):
        bad = []
        for oid, s in self.specs.items():
            r = self.cat_out.get(oid)
            if not r:
                continue
            if (r.get("fetchName", r.get("name")) or "") != (s.name or ""):
                bad.append(f"{oid}: name")
            if (r.get("fetchUnit", r.get("unit")) or "") != (s.unit or ""):
                bad.append(f"{oid}: unit")
            if (r.get("scale", 1.0)) != getattr(s, "scale", 1.0):
                bad.append(f"{oid}: scale")
        self.assertEqual(bad, [], f"fetch-param drift: {bad[:20]}")


if __name__ == "__main__":
    unittest.main()
