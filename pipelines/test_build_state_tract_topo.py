"""Unit tests for pipelines/build_state_tract_topo.py download hardening.

fetch_zip must reject a non-zip response (Cloudflare can serve a stale
HTML 200 for a valid TIGER URL — observed live for tl_2025_50_bg.zip,
2026-06), retry once cache-busted, never cache a non-zip, and self-heal an
already-poisoned cache entry.

Run with::  python -m unittest pipelines.test_build_state_tract_topo
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "build_state_tract_topo.py"
spec = importlib.util.spec_from_file_location("bstt_under_test", MODULE_PATH)
assert spec is not None and spec.loader is not None, MODULE_PATH
bstt = importlib.util.module_from_spec(spec)
sys.modules["bstt_under_test"] = bstt
spec.loader.exec_module(bstt)


def _write_real_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("inner.shp", b"fake-shapefile-bytes")


def _write_html(path: Path) -> None:
    path.write_bytes(b"<html><head><title>Page not found</title></head></html>")


class IsZipTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_real_zip(self) -> None:
        p = self.tmp / "a.zip"
        _write_real_zip(p)
        self.assertTrue(bstt._is_zip(p))

    def test_html_is_not_zip(self) -> None:
        p = self.tmp / "b.zip"
        _write_html(p)
        self.assertFalse(bstt._is_zip(p))

    def test_missing_is_not_zip(self) -> None:
        self.assertFalse(bstt._is_zip(self.tmp / "nope.zip"))


class FetchZipTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._orig_cache = bstt.CACHE_DIR
        bstt.CACHE_DIR = self.tmp

    def tearDown(self) -> None:
        bstt.CACHE_DIR = self._orig_cache
        self._tmp.cleanup()

    def _html_then_zip(self):
        """Plain URL -> HTML (poisoned CDN); cache-busted URL -> real zip."""
        calls = []

        def fake(url, filename):
            calls.append(url)
            if "?cb=" in url:
                _write_real_zip(Path(filename))
            else:
                _write_html(Path(filename))

        return fake, calls

    def test_cachebust_retry_recovers(self) -> None:
        fake, calls = self._html_then_zip()
        with mock.patch.object(bstt, "urlretrieve", fake):
            out = bstt.fetch_zip("block_group", "50")
        self.assertTrue(bstt._is_zip(out))              # cached file is a real zip
        self.assertEqual(len(calls), 2)                 # plain + cache-busted
        self.assertIn("?cb=", calls[1])
        self.assertFalse((out.parent / (out.name + ".part")).exists())  # temp cleaned

    def test_all_html_raises_and_leaves_no_zip(self) -> None:
        def all_html(url, filename):
            _write_html(Path(filename))

        with mock.patch.object(bstt, "urlretrieve", all_html):
            with self.assertRaises(RuntimeError):
                bstt.fetch_zip("tract", "06")
        expected = self.tmp / f"{bstt.shapefile_stem('tract', '06')}.zip"
        self.assertFalse(expected.exists())             # no bogus .zip cached

    def test_valid_cache_hit_skips_download(self) -> None:
        good = self.tmp / f"{bstt.shapefile_stem('tract', '06')}.zip"
        _write_real_zip(good)

        def boom(url, filename):
            raise AssertionError("must not download on a valid cache hit")

        with mock.patch.object(bstt, "urlretrieve", boom):
            out = bstt.fetch_zip("tract", "06")
        self.assertEqual(out, good)

    def test_poisoned_cache_self_heals(self) -> None:
        bad = self.tmp / f"{bstt.shapefile_stem('block_group', '50')}.zip"
        _write_html(bad)                                # pre-existing cached HTML
        fake, _ = self._html_then_zip()
        with mock.patch.object(bstt, "urlretrieve", fake):
            out = bstt.fetch_zip("block_group", "50")
        self.assertTrue(bstt._is_zip(out))              # replaced with a real zip


if __name__ == "__main__":
    unittest.main()
