"""
Shared helpers for data pipelines.

Each pipeline reads a set of source specs, fetches data, and writes versioned
JSON into ``public/data/<pipeline>/<id>.json``. The JSON format matches the
TypeScript ``SourceData`` interface in ``src/lib/data-types.ts``.

Two cross-cutting behaviors live here and benefit every pipeline that calls
``write_timeseries`` / ``write_curve``:

  - **Merge-on-write.** A pipeline's "new" points list is unioned with whatever
    is already on disk before the file is written. If a future API restriction
    truncates a series's window (Yahoo dropping free-tier deep history,
    FRED's older revisions falling off the public endpoint, etc.) we still
    keep the older points we'd previously fetched. Newer values win on
    timestamp collisions, so legitimate restatements still flow through.

  - **Optional response cache.** ``cached_get`` is a thin shim around HTTP
    GET with a TTL-keyed on-disk cache. It stores responses in the shared
    pipeline cache (``pipelines/_cache/`` via ``_cache.py``) so there is
    ONE on-disk cache for the whole pipeline layer rather than a second
    parallel store. Useful for local iteration (re-running a pipeline twice
    in an hour doesn't double-tax the upstream API); not as useful in CI
    where runs are weekly. Pipelines opt in by replacing their direct
    ``requests.get(url)`` with ``cached_get(url, ttl_seconds=...)``.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "public" / "data"

# Bucket name under the shared pipeline cache (pipelines/_cache/, owned by
# _cache.py) where cached_get stashes HTTP responses. Keeping HTTP responses
# in the same store as the artifact cache means there's a single on-disk
# cache directory for the whole pipeline layer.
_HTTP_CACHE_BUCKET = "http"


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _read_existing_payload(path: Path) -> dict[str, Any] | None:
    """Return the existing JSON payload at ``path`` if any, else None.
    Swallows read / parse errors so a corrupted file doesn't block the
    fresh write — we'd rather write a clean payload than refuse to."""
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _merge_points_by_t(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Union two timeseries point lists keyed by ``t`` (ISO date). Newer
    list wins on timestamp collision so legitimate provider restatements
    flow through; everything else from the existing list is preserved.
    Result is sorted chronologically (oldest first)."""
    merged: dict[str, dict[str, Any]] = {}
    for p in existing:
        t = p.get("t")
        if isinstance(t, str):
            merged[t] = p
    for p in new:
        t = p.get("t")
        if isinstance(t, str):
            merged[t] = p
    return [merged[k] for k in sorted(merged.keys())]


def _merge_projections(
    existing: dict[str, list[dict[str, Any]]] | None,
    new: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, list[dict[str, Any]]] | None:
    """Projections are a vintage_date -> [{t, v}] map. Each refresh may
    add a new vintage (latest CBO publication, latest Trustees Report).
    Older vintages stay on disk forever so the "as of" picker can flip
    between historical perspectives — losing them on overwrite would
    forfeit half the point of the forecast-bearing series.

    Merge rule: each vintage is owned by whoever provided it most
    recently. If both `existing` and `new` carry a vintage with the
    same key, the `new` list wins (legitimate restatement of an
    already-published vintage)."""
    if not existing and not new:
        return None
    out: dict[str, list[dict[str, Any]]] = {}
    if existing:
        out.update(existing)
    if new:
        out.update(new)
    return {k: out[k] for k in sorted(out)} if out else None


def write_timeseries(
    pipeline: str,
    series_id: str,
    name: str,
    points: list[dict[str, Any]],
    unit: str | None = None,
    projections: dict[str, list[dict[str, Any]]] | None = None,
    *,
    merge: bool = True,
) -> Path:
    """
    Write a timeseries JSON file. ``points`` is a list of ``{"t": iso_date, "v": float}``
    ordered chronologically (oldest first).

    ``projections`` is an optional map of ``vintage_date -> [{t, v}]`` for
    forecast-bearing sources (CBO outlook, SSA Trustees Report, market
    futures curves, etc.). Each vintage is the forecast that was
    published on that date; multiple vintages can live side-by-side so
    a future "as of" picker (Phase 3) can show historical perspectives.
    The renderer's Phase 2 behavior is to draw the latest vintage as a
    dashed extension after the last historical point.

    ``merge`` defaults to True: existing on-disk points are unioned with
    the new ones before write, preserving history if a future API
    restriction truncates the upstream series. Pipelines that
    intentionally REPLACE their data (e.g., a re-derivation that
    invalidates older points) can pass merge=False to opt out.

    See ``src/lib/data-types.ts`` for the TypeScript-side schema.
    """
    out = DATA_ROOT / pipeline / f"{series_id}.json"
    if merge:
        prior = _read_existing_payload(out)
        if prior is not None:
            prior_points = prior.get("points")
            if isinstance(prior_points, list):
                points = _merge_points_by_t(prior_points, points)
            prior_projections = prior.get("projections")
            if isinstance(prior_projections, dict) or projections:
                merged_projections = _merge_projections(
                    prior_projections if isinstance(prior_projections, dict) else None,
                    projections,
                )
                projections = merged_projections
    payload: dict[str, Any] = {
        "id": series_id,
        "name": name,
        "kind": "timeseries",
        "unit": unit,
        "lastUpdated": utc_now_iso(),
        "points": points,
    }
    if projections:
        # Sort the vintage keys so JSON diffs across runs are stable
        # (Python dicts preserve insertion order; pipelines that build
        # vintages in some non-deterministic order shouldn't show up
        # as gratuitous noise in CI diffs).
        payload["projections"] = {k: projections[k] for k in sorted(projections)}
    _write_json(out, payload)
    return out


def write_curve(
    pipeline: str,
    series_id: str,
    name: str,
    snapshots: list[dict[str, Any]],
    unit: str | None = None,
    *,
    merge: bool = True,
) -> Path:
    """
    Write a curve JSON file. ``snapshots`` is a list of
    ``{"asOf": iso_date, "points": [{"tenor": str, "tenorMonths": int, "v": float}, ...]}``
    ordered chronologically (oldest first).

    ``merge`` (default True) unions snapshots by ``asOf`` date with the
    existing on-disk file — same survival semantics as the timeseries
    variant. Each new snapshot from the same asOf date replaces the
    older one (legitimate restatement); historical snapshots from
    earlier asOf dates are preserved.
    """
    out = DATA_ROOT / pipeline / f"{series_id}.json"
    if merge:
        prior = _read_existing_payload(out)
        if prior is not None:
            prior_snapshots = prior.get("snapshots")
            if isinstance(prior_snapshots, list):
                # Snapshots are keyed by asOf rather than t, but the
                # merge mechanic is otherwise identical.
                merged: dict[str, dict[str, Any]] = {}
                for s in prior_snapshots:
                    k = s.get("asOf")
                    if isinstance(k, str):
                        merged[k] = s
                for s in snapshots:
                    k = s.get("asOf")
                    if isinstance(k, str):
                        merged[k] = s
                snapshots = [merged[k] for k in sorted(merged)]
    _write_json(
        out,
        {
            "id": series_id,
            "name": name,
            "kind": "curve",
            "unit": unit,
            "lastUpdated": utc_now_iso(),
            "snapshots": snapshots,
        },
    )
    return out


def cached_get(
    url: str,
    *,
    ttl_seconds: int,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    session: Any = None,
    timeout: float = 30.0,
) -> str:
    """HTTP GET with a TTL-keyed on-disk cache.

    Why: pipelines run weekly in CI (where the cache doesn't help much —
    last fetch was 7 days ago) but ALSO run frequently from the laptop
    during development. The local cache means hammering a pipeline
    while iterating doesn't hammer the upstream API.

    Storage: the shared pipeline cache (``_cache.py``). The response body is
    stored at ``pipelines/_cache/http/<key>.txt`` where ``key`` is the
    SHA-256 of ``url + sorted(params) + sorted(headers)`` — so different
    params/headers get distinct cache entries. Freshness is the cache
    file's age: ``ttl_seconds`` is converted to days for ``_cache.cache_get``
    (which compares against the file's mtime). The file's mtime is its fetch
    time, so the two are equivalent.

    Returns the response body as text. Raises on HTTP error.

    Pipelines using this should pass a session if they have one (it
    keeps connection pooling). Default uses ``requests.get`` directly.
    """
    # The shared on-disk cache. Lazy-imported (like `requests` below) so
    # merely importing common.py doesn't require pipelines/ to be on the
    # path; cached_get is only called from within a running pipeline /
    # test where it is.
    from _cache import cache_get, cache_put

    canon_params = "&".join(
        f"{k}={v}" for k, v in sorted((params or {}).items())
    )
    canon_headers = "&".join(
        f"{k}={v}" for k, v in sorted((headers or {}).items())
    )
    key_input = f"{url}|{canon_params}|{canon_headers}".encode("utf-8")
    key = hashlib.sha256(key_input).hexdigest()

    cached = cache_get(
        _HTTP_CACHE_BUCKET, key, max_age_days=ttl_seconds / 86400.0, suffix=".txt",
    )
    if cached is not None:
        return cached.decode("utf-8")

    # Lazy-import `requests` here so the CI test environment (which
    # passes a fake session and never hits this branch) doesn't need
    # the dep installed. Local pipeline runs that call cached_get
    # without a session do need `requests` available — but those
    # already do for the rest of the pipeline machinery.
    if session is None:
        import requests  # type: ignore[import-untyped]

        s = requests
    else:
        s = session
    resp = s.get(url, params=dict(params) if params else None,
                 headers=dict(headers) if headers else None,
                 timeout=timeout)
    resp.raise_for_status()
    body = resp.text

    cache_put(_HTTP_CACHE_BUCKET, key, body, suffix=".txt")
    return body
