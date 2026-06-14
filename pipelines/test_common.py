"""
Unit tests for pipelines/common.py helpers.

Two cross-cutting behaviors with survival semantics:

  - **Merge-on-write** for write_timeseries / write_curve. Existing
    on-disk points unioned with the new ones; newer values win on
    timestamp collision. Protects history if a future API restriction
    truncates a series's window.

  - **cached_get** TTL cache. Two calls with the same URL within the
    TTL only hit the network once.

Run with::

    python -m unittest pipelines.test_common

Wired into the CI workflow next to test_generators_index.py.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

# cached_get now stores HTTP responses in the shared pipeline cache
# (_cache.py); the CachedGetTests patch _cache.CACHE_ROOT to redirect it.
# Use the SAME dual-context resolver as common.py so we patch the exact module
# object cached_get uses, whether run via pytest (pipelines/ on sys.path) or
# CI's `python -m unittest pipelines.test_common` (the `pipelines` package).
try:
    import _cache
except ModuleNotFoundError:  # imported as the `pipelines` package (CI unittest)
    from pipelines import _cache

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "common.py"
spec = importlib.util.spec_from_file_location("common_under_test", MODULE_PATH)
assert spec is not None and spec.loader is not None, MODULE_PATH
common = importlib.util.module_from_spec(spec)
sys.modules["common_under_test"] = common
spec.loader.exec_module(common)


class MergePointsByTTests(unittest.TestCase):
    """Pure-function tests for _merge_points_by_t."""

    def test_union_keeps_all_unique(self) -> None:
        a = [{"t": "2020-01-01", "v": 1.0}, {"t": "2020-02-01", "v": 2.0}]
        b = [{"t": "2020-03-01", "v": 3.0}]
        out = common._merge_points_by_t(a, b)
        self.assertEqual([p["t"] for p in out],
                         ["2020-01-01", "2020-02-01", "2020-03-01"])
        self.assertEqual([p["v"] for p in out], [1.0, 2.0, 3.0])

    def test_collision_newer_wins(self) -> None:
        # Same timestamp in both — new (b) value supersedes.
        a = [{"t": "2020-01-01", "v": 1.0}, {"t": "2020-02-01", "v": 2.0}]
        b = [{"t": "2020-02-01", "v": 2.5}]
        out = common._merge_points_by_t(a, b)
        self.assertEqual([p["t"] for p in out], ["2020-01-01", "2020-02-01"])
        self.assertEqual([p["v"] for p in out], [1.0, 2.5])

    def test_empty_existing(self) -> None:
        out = common._merge_points_by_t([], [{"t": "2020-01-01", "v": 1.0}])
        self.assertEqual(out, [{"t": "2020-01-01", "v": 1.0}])

    def test_empty_new(self) -> None:
        a = [{"t": "2020-01-01", "v": 1.0}]
        out = common._merge_points_by_t(a, [])
        self.assertEqual(out, [{"t": "2020-01-01", "v": 1.0}])

    def test_window_shrink_preserves_old(self) -> None:
        # Survival case: API used to return 5 points, now returns 3.
        # Merge must keep the 2 older points that vanished from the
        # response — that's the whole point of the helper.
        existing = [
            {"t": "2020-01-01", "v": 1.0},
            {"t": "2020-02-01", "v": 2.0},
            {"t": "2020-03-01", "v": 3.0},
            {"t": "2020-04-01", "v": 4.0},
            {"t": "2020-05-01", "v": 5.0},
        ]
        new_short = [
            {"t": "2020-03-01", "v": 3.0},
            {"t": "2020-04-01", "v": 4.0},
            {"t": "2020-05-01", "v": 5.0},
        ]
        out = common._merge_points_by_t(existing, new_short)
        self.assertEqual(len(out), 5)
        self.assertEqual(out[0]["t"], "2020-01-01")  # preserved
        self.assertEqual(out[1]["t"], "2020-02-01")  # preserved

    def test_drops_points_with_no_t(self) -> None:
        # Defensive: malformed point with no t doesn't crash the merge.
        out = common._merge_points_by_t(
            [{"v": 1.0}],  # missing t — dropped
            [{"t": "2020-01-01", "v": 2.0}],
        )
        self.assertEqual(out, [{"t": "2020-01-01", "v": 2.0}])


class MergeProjectionsTests(unittest.TestCase):
    """Projections are a vintage_date -> points map. Each new vintage
    should be preserved across refreshes."""

    def test_keeps_old_vintages(self) -> None:
        existing = {
            "2024-01": [{"t": "2024-01-01", "v": 1.0}],
            "2024-07": [{"t": "2024-07-01", "v": 2.0}],
        }
        new = {"2025-01": [{"t": "2025-01-01", "v": 3.0}]}
        out = common._merge_projections(existing, new)
        assert out is not None
        self.assertEqual(set(out.keys()), {"2024-01", "2024-07", "2025-01"})

    def test_collision_new_wins(self) -> None:
        # A vintage gets restated (e.g., CBO publishes a corrected
        # version of last year's projection). New wins.
        existing = {"2024-07": [{"t": "2024-07-01", "v": 2.0}]}
        new = {"2024-07": [{"t": "2024-07-01", "v": 2.5}]}
        out = common._merge_projections(existing, new)
        assert out is not None
        self.assertEqual(out["2024-07"][0]["v"], 2.5)

    def test_both_empty_returns_none(self) -> None:
        self.assertIsNone(common._merge_projections(None, None))


class WriteTimeseriesIntegrationTests(unittest.TestCase):
    """write_timeseries with merge=True should read whatever is on disk
    and union the new points in before writing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # Point common's DATA_ROOT at the temp dir so the helper writes
        # files there instead of into the real public/data tree.
        self._orig = common.DATA_ROOT
        common.DATA_ROOT = self.tmp

    def tearDown(self) -> None:
        common.DATA_ROOT = self._orig
        self._tmp.cleanup()

    def test_fresh_write_skips_merge(self) -> None:
        # No existing file → merge is a no-op; new points written as-is.
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake series",
            [{"t": "2024-01-01", "v": 1.0}],
        )
        out = self.tmp / "fakepipe" / "fakeid.json"
        self.assertTrue(out.exists())
        body = json.loads(out.read_text())
        self.assertEqual(body["points"], [{"t": "2024-01-01", "v": 1.0}])

    def test_second_write_unions_with_first(self) -> None:
        # Simulate two refreshes — first wrote 3 points back to 2024-01;
        # second only returned 2024-02 + 2024-03 (window shrink).
        # The merged file should have all 3 points.
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake series",
            [
                {"t": "2024-01-01", "v": 1.0},
                {"t": "2024-02-01", "v": 2.0},
                {"t": "2024-03-01", "v": 3.0},
            ],
        )
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake series",
            [{"t": "2024-02-01", "v": 2.0}, {"t": "2024-03-01", "v": 3.0}],
        )
        out = self.tmp / "fakepipe" / "fakeid.json"
        body = json.loads(out.read_text())
        self.assertEqual(len(body["points"]), 3)
        ts = [p["t"] for p in body["points"]]
        self.assertEqual(ts, ["2024-01-01", "2024-02-01", "2024-03-01"])

    def test_restatement_overwrites_value(self) -> None:
        # Same timestamp, different value — new value wins (legitimate
        # provider restatement, e.g. FRED revising last month's CPI).
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake series",
            [{"t": "2024-01-01", "v": 1.0}],
        )
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake series",
            [{"t": "2024-01-01", "v": 1.1}],
        )
        body = json.loads((self.tmp / "fakepipe" / "fakeid.json").read_text())
        self.assertEqual(body["points"], [{"t": "2024-01-01", "v": 1.1}])

    def test_merge_false_overwrites_clean(self) -> None:
        # Opt-out: pipelines that intentionally replace their data
        # (derivations, recalculations) can pass merge=False.
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake series",
            [{"t": "2024-01-01", "v": 1.0}, {"t": "2024-02-01", "v": 2.0}],
        )
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake series",
            [{"t": "2024-02-01", "v": 2.5}],
            merge=False,
        )
        body = json.loads((self.tmp / "fakepipe" / "fakeid.json").read_text())
        self.assertEqual(body["points"], [{"t": "2024-02-01", "v": 2.5}])

    def test_corrupted_existing_doesnt_block_fresh_write(self) -> None:
        # If the file on disk is corrupt JSON, the helper falls back to
        # treating it as "no existing data" rather than refusing to
        # write. Operator visibility comes from the file diff in CI;
        # blocking the write would just propagate the corruption.
        out = self.tmp / "fakepipe" / "fakeid.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("not actually json {{{")
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake series",
            [{"t": "2024-01-01", "v": 1.0}],
        )
        body = json.loads(out.read_text())
        self.assertEqual(body["points"], [{"t": "2024-01-01", "v": 1.0}])

    def test_projections_merged_across_writes(self) -> None:
        # Each refresh may add a new vintage. Old vintages stay.
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake series",
            [{"t": "2024-01-01", "v": 1.0}],
            projections={"2024-01": [{"t": "2024-02-01", "v": 1.1}]},
        )
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake series",
            [{"t": "2024-01-01", "v": 1.0}],
            projections={"2025-01": [{"t": "2025-02-01", "v": 2.1}]},
        )
        body = json.loads((self.tmp / "fakepipe" / "fakeid.json").read_text())
        self.assertEqual(set(body["projections"].keys()), {"2024-01", "2025-01"})


class CachedGetTests(unittest.TestCase):
    """cached_get short-circuits when a recent cache entry is on disk.

    cached_get stores responses in the shared pipeline cache (_cache.py),
    so these tests patch ``_cache.CACHE_ROOT`` (not ``common.CACHE_ROOT``,
    which no longer exists) and freshness is the cache file's mtime."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._orig = _cache.CACHE_ROOT
        _cache.CACHE_ROOT = self.tmp

    def tearDown(self) -> None:
        _cache.CACHE_ROOT = self._orig
        self._tmp.cleanup()

    def _mock_session(self, body: str):
        sess = mock.MagicMock()
        resp = mock.MagicMock()
        resp.text = body
        resp.raise_for_status = mock.MagicMock()
        sess.get = mock.MagicMock(return_value=resp)
        return sess

    def test_first_call_fetches_and_caches(self) -> None:
        sess = self._mock_session("hello")
        body = common.cached_get(
            "https://example.test/x", ttl_seconds=3600, session=sess,
        )
        self.assertEqual(body, "hello")
        self.assertEqual(sess.get.call_count, 1)
        # Check the cache file was written (one .txt body under the cache).
        files = list(self.tmp.rglob("*.txt"))
        self.assertEqual(len(files), 1)

    def test_second_call_within_ttl_hits_cache(self) -> None:
        sess = self._mock_session("hello")
        common.cached_get(
            "https://example.test/x", ttl_seconds=3600, session=sess,
        )
        # Second call: same URL, fresh session — but the on-disk cache
        # is fresh too, so no network call should happen.
        sess2 = self._mock_session("WRONG")
        body = common.cached_get(
            "https://example.test/x", ttl_seconds=3600, session=sess2,
        )
        self.assertEqual(body, "hello")  # cached value, not sess2's
        self.assertEqual(sess2.get.call_count, 0)

    def test_expired_cache_refetches(self) -> None:
        sess = self._mock_session("old")
        common.cached_get(
            "https://example.test/x", ttl_seconds=3600, session=sess,
        )
        # Backdate the cache file's mtime so it reads as stale (freshness
        # is mtime-based now, not a JSON fetched_at field).
        cache_file = next(self.tmp.rglob("*.txt"))
        long_ago = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
        os.utime(cache_file, (long_ago, long_ago))
        # Now a new call should refetch.
        sess2 = self._mock_session("new")
        body = common.cached_get(
            "https://example.test/x", ttl_seconds=3600, session=sess2,
        )
        self.assertEqual(body, "new")
        self.assertEqual(sess2.get.call_count, 1)

    def test_different_params_get_separate_cache_keys(self) -> None:
        sess = self._mock_session("body")
        common.cached_get(
            "https://example.test/x", ttl_seconds=3600,
            params={"a": "1"}, session=sess,
        )
        common.cached_get(
            "https://example.test/x", ttl_seconds=3600,
            params={"a": "2"}, session=sess,
        )
        # Both calls hit the network (different cache keys).
        self.assertEqual(sess.get.call_count, 2)
        files = list(self.tmp.rglob("*.txt"))
        self.assertEqual(len(files), 2)


class ValidatePointsTests(unittest.TestCase):
    """validate_points is the structural gate at the single write choke
    point — malformed data must be rejected the moment a pipeline produces
    it, not discovered weeks later on the site (the data-integrity test
    suite's invariants, enforced at write time)."""

    def test_valid_points_pass(self) -> None:
        self.assertEqual(
            common.validate_points(
                [{"t": "2024-01-01", "v": 1.0}, {"t": "2024-02-01", "v": 2.5}],
            ),
            [],
        )

    def test_empty_rejected_unless_allowed(self) -> None:
        self.assertEqual(common.validate_points([]), ["no points"])
        self.assertEqual(common.validate_points([], allow_empty=True), [])

    def test_non_finite_values_flagged(self) -> None:
        for bad in (float("nan"), float("inf"), None, "5", True):
            problems = common.validate_points([{"t": "2024-01-01", "v": bad}])
            self.assertTrue(
                any("non-finite" in p for p in problems),
                f"{bad!r} should be flagged, got {problems}",
            )

    def test_non_iso_date_flagged(self) -> None:
        problems = common.validate_points(
            [{"t": "2024", "v": 1.0}, {"t": "2024-02-01", "v": 2.0}],
        )
        self.assertTrue(any("non-ISO" in p for p in problems), problems)

    def test_out_of_order_and_duplicate_flagged(self) -> None:
        desc = common.validate_points(
            [{"t": "2024-02-01", "v": 1.0}, {"t": "2024-01-01", "v": 2.0}],
        )
        self.assertTrue(any("out-of-order" in p for p in desc), desc)
        dup = common.validate_points(
            [{"t": "2024-01-01", "v": 1.0}, {"t": "2024-01-01", "v": 2.0}],
        )
        self.assertTrue(any("duplicate" in p for p in dup), dup)


class WriteTimeseriesValidationTests(unittest.TestCase):
    """A malformed fetch must NOT clobber a good on-disk file — the write
    is skipped and a warning emitted, so a broken upstream response can't
    corrupt already-shipped data."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._orig = common.DATA_ROOT
        common.DATA_ROOT = self.tmp

    def tearDown(self) -> None:
        common.DATA_ROOT = self._orig
        self._tmp.cleanup()

    def test_malformed_write_preserves_existing_file(self) -> None:
        out = self.tmp / "fakepipe" / "fakeid.json"
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake",
            [{"t": "2024-01-01", "v": 1.0}, {"t": "2024-02-01", "v": 2.0}],
        )
        good_points = json.loads(out.read_text())["points"]
        # A later refresh returns garbage (NaN). merge=False so the bad list
        # isn't masked by the union — the validator alone must block it.
        common.write_timeseries(
            "fakepipe", "fakeid", "Fake",
            [{"t": "2024-03-01", "v": float("nan")}],
            merge=False,
        )
        self.assertEqual(json.loads(out.read_text())["points"], good_points)


if __name__ == "__main__":
    unittest.main()
