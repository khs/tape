"""
Shared on-disk cache for pipeline intermediate fetches.

Goal: don't re-hit an upstream API for data we already pulled
recently. This matters most for:
  1. Census ACS — the per-(year, state) tract fetches are the
     expensive step in pipelines/census_acs_cd.py, and old ACS5
     vintages don't revise. Caching them turns a 13-vintage ×
     51-state weekly refresh into one initial bulk-fetch
     followed by per-week incrementals for the current vintage.
  2. Zillow — CSV downloads are ~5MB each but Zillow's CSVs only
     refresh monthly, so re-fetching mid-month is pure waste.

Policy:
  - Cache lives at `pipelines/_cache/<bucket>/<key>.json` (or
    `.csv`/etc. depending on raw shape). `.gitignore` excludes
    the whole _cache/ directory.
  - Callers pass a `bucket` name (e.g., "acs_cd_tract",
    "zillow_csv") + a `key` (any string, will be sha1'd to a
    safe filename if it contains awkward characters).
  - Callers also pass `max_age_days`. If the cached file is
    older than that, the cache miss path is taken.
  - `cache_get(bucket, key, max_age_days)` → bytes | None
  - `cache_put(bucket, key, data)` → Path
  - For ACS-vintage-style permanent caching, pass max_age_days
    very large (e.g. 365 * 100); the cache will only invalidate
    on file deletion.

The cache is purely an optimization. Pipelines must still work
correctly with the cache disabled / empty.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = ROOT / "pipelines" / "_cache"


def _safe_key(key: str) -> str:
    """If the key has filesystem-hostile chars, hash it. Otherwise
    return as-is so the cache filenames are readable when grepping
    `ls pipelines/_cache/acs_cd_tract/`."""
    if all(c.isalnum() or c in "-_." for c in key) and len(key) < 100:
        return key
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def cache_path(bucket: str, key: str, suffix: str = ".json") -> Path:
    """Filesystem location for a (bucket, key) pair."""
    return CACHE_ROOT / bucket / (_safe_key(key) + suffix)


def cache_get(
    bucket: str,
    key: str,
    max_age_days: float,
    suffix: str = ".json",
) -> bytes | None:
    """Read from cache. Returns the file bytes if fresh, None if
    missing or stale. Doesn't decode — callers know what format
    they wrote."""
    p = cache_path(bucket, key, suffix)
    if not p.exists():
        return None
    age_sec = time.time() - p.stat().st_mtime
    if age_sec > max_age_days * 86400:
        return None
    try:
        return p.read_bytes()
    except OSError:
        return None


def cache_put(
    bucket: str,
    key: str,
    data: bytes | str,
    suffix: str = ".json",
) -> Path:
    """Write to cache. Returns the path so callers can log it."""
    p = cache_path(bucket, key, suffix)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        p.write_text(data, encoding="utf-8")
    else:
        p.write_bytes(data)
    return p
