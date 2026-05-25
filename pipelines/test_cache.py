"""
Tests for pipelines/_cache.py.

The cache is purely an optimization (per the module docstring) — but
when it's wrong it's wrong in a way that's hard to debug: stale data
served as fresh, or an apparent "API not responding" because a
silently-failing cache read masked the real fetch path. These tests
lock down freshness behavior, safe-key sanitization, and the
write/read round-trip.
"""
from __future__ import annotations

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

# Import the module under a name we can patch on. Importing the
# functions directly would bypass the patched CACHE_ROOT.
from pipelines import _cache


class SafeKeyTests(unittest.TestCase):
    """`_safe_key` returns the key as-is for filesystem-friendly
    inputs (so `ls pipelines/_cache/...` is grepable), and a SHA1
    hash otherwise."""

    def test_alphanumeric_keys_pass_through(self):
        self.assertEqual(_cache._safe_key("acs_2020_va"), "acs_2020_va")
        self.assertEqual(_cache._safe_key("foo.bar"), "foo.bar")
        self.assertEqual(_cache._safe_key("foo-bar"), "foo-bar")
        self.assertEqual(_cache._safe_key("abc123"), "abc123")

    def test_keys_with_slashes_are_hashed(self):
        # Slashes would create nested directories that the cache
        # doesn't expect — hash to avoid the filesystem confusion.
        out = _cache._safe_key("foo/bar")
        self.assertEqual(len(out), 40)  # SHA1 hex
        self.assertTrue(all(c in "0123456789abcdef" for c in out))

    def test_keys_with_spaces_are_hashed(self):
        out = _cache._safe_key("foo bar baz")
        self.assertEqual(len(out), 40)

    def test_long_keys_are_hashed(self):
        # Boundary: length 100+ triggers the hash. 99 is fine, 100 hashed.
        ninety_nine = "a" * 99
        hundred = "a" * 100
        self.assertEqual(_cache._safe_key(ninety_nine), ninety_nine)
        self.assertNotEqual(_cache._safe_key(hundred), hundred)
        self.assertEqual(len(_cache._safe_key(hundred)), 40)

    def test_hashing_is_deterministic(self):
        # Same input → same hash. Otherwise the cache would miss
        # itself across runs.
        self.assertEqual(
            _cache._safe_key("foo/bar baz"),
            _cache._safe_key("foo/bar baz"),
        )

    def test_dot_and_underscore_pass_through(self):
        # These are filesystem-safe and grep-friendly.
        self.assertEqual(
            _cache._safe_key("acs_5yr_2022.s24"), "acs_5yr_2022.s24"
        )


class CachePathTests(unittest.TestCase):
    """`cache_path` joins the bucket + safe-key + suffix under the
    cache root. Verifies the structural contract without writing
    any files."""

    def test_path_under_cache_root(self):
        p = _cache.cache_path("zillow_csv", "metro_zhvi_2024_06")
        self.assertEqual(p.parent.name, "zillow_csv")
        self.assertEqual(p.name, "metro_zhvi_2024_06.json")
        # Lives somewhere under the cache root.
        self.assertIn("_cache", p.parts)

    def test_custom_suffix(self):
        p = _cache.cache_path("acs", "key1", suffix=".csv")
        self.assertTrue(p.name.endswith(".csv"))

    def test_hostile_key_in_path_is_sanitized(self):
        # Path filename should never contain the literal '/' from the
        # input key.
        p = _cache.cache_path("bucket", "weird/key")
        self.assertNotIn("/", p.name.replace(".json", ""))


class CacheRoundTripTests(unittest.TestCase):
    """Read-after-write returns the same bytes; missing entries return
    None; stale entries return None. Uses a temp dir for CACHE_ROOT
    so the real cache is untouched."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Patch CACHE_ROOT for the duration of the test.
        self._patch = mock.patch.object(
            _cache, "CACHE_ROOT", Path(self.tmp.name)
        )
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_write_then_read_returns_same_bytes(self):
        data = b'{"hello": "world"}'
        _cache.cache_put("test_bucket", "key1", data)
        self.assertEqual(
            _cache.cache_get("test_bucket", "key1", max_age_days=1),
            data,
        )

    def test_write_string_then_read_returns_utf8_bytes(self):
        # The contract: cache_put accepts bytes OR str, but cache_get
        # always returns bytes. Verifies the UTF-8 encoding step.
        _cache.cache_put("test_bucket", "key_str", "résumé €")
        out = _cache.cache_get("test_bucket", "key_str", max_age_days=1)
        self.assertEqual(out, "résumé €".encode("utf-8"))

    def test_missing_entry_returns_none(self):
        self.assertIsNone(
            _cache.cache_get("test_bucket", "nope", max_age_days=1)
        )

    def test_missing_bucket_returns_none(self):
        # No prior write for this bucket → no directory exists either.
        self.assertIsNone(
            _cache.cache_get("never_made", "key", max_age_days=1)
        )

    def test_stale_entry_returns_none(self):
        # Write, backdate the file's mtime past max_age, read should
        # return None (cache miss path).
        _cache.cache_put("test_bucket", "old_key", b"old_data")
        p = _cache.cache_path("test_bucket", "old_key")
        # Backdate to 2 days ago.
        old_ts = time.time() - (2 * 86400)
        os.utime(p, (old_ts, old_ts))
        self.assertIsNone(
            _cache.cache_get("test_bucket", "old_key", max_age_days=1.0)
        )

    def test_fresh_entry_within_max_age_returns_data(self):
        _cache.cache_put("test_bucket", "fresh_key", b"fresh_data")
        # max_age large enough to count as fresh.
        self.assertEqual(
            _cache.cache_get(
                "test_bucket", "fresh_key", max_age_days=365
            ),
            b"fresh_data",
        )

    def test_permanent_caching_via_huge_max_age(self):
        # ACS-vintage usage: pass max_age_days = 365*100 to mean
        # "never expires, only on file deletion".
        _cache.cache_put("acs", "permanent", b"vintage_data")
        out = _cache.cache_get("acs", "permanent", max_age_days=36500)
        self.assertEqual(out, b"vintage_data")

    def test_zero_max_age_makes_everything_stale(self):
        # Boundary: max_age = 0 means "any cache hit is stale". The
        # file exists, but reading it returns None because age > 0.
        _cache.cache_put("test_bucket", "k", b"d")
        # Slight time elapsed between put and get is enough for
        # age > 0 to be true, but ensure with a tiny sleep.
        time.sleep(0.01)
        self.assertIsNone(
            _cache.cache_get("test_bucket", "k", max_age_days=0)
        )

    def test_put_creates_bucket_directory(self):
        # cache_put on a never-before-seen bucket must mkdir the parent.
        _cache.cache_put("brand_new_bucket", "k", b"d")
        self.assertTrue(
            (_cache.CACHE_ROOT / "brand_new_bucket").is_dir()
        )

    def test_put_returns_the_written_path(self):
        # Callers log the returned path. It should match cache_path.
        path = _cache.cache_put("b", "k", b"d")
        self.assertEqual(path, _cache.cache_path("b", "k"))
        self.assertTrue(path.exists())

    def test_put_overwrites_existing_entry(self):
        _cache.cache_put("b", "same_key", b"v1")
        _cache.cache_put("b", "same_key", b"v2")
        self.assertEqual(
            _cache.cache_get("b", "same_key", max_age_days=1), b"v2"
        )

    def test_round_trip_works_with_hostile_keys(self):
        # The cache must remain correct end-to-end when the key was
        # SHA1'd at write time AND read time. The key itself is the
        # caller's responsibility — both calls hash to the same name.
        _cache.cache_put("b", "weird/key with spaces", b"data")
        out = _cache.cache_get(
            "b", "weird/key with spaces", max_age_days=1
        )
        self.assertEqual(out, b"data")


if __name__ == "__main__":
    unittest.main()
