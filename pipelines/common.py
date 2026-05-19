"""
Shared helpers for data pipelines.

Each pipeline reads a set of source specs, fetches data, and writes versioned
JSON into ``public/data/<pipeline>/<id>.json``. The JSON format matches the
TypeScript ``SourceData`` interface in ``src/lib/data-types.ts``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "public" / "data"


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


def write_timeseries(
    pipeline: str,
    series_id: str,
    name: str,
    points: list[dict[str, Any]],
    unit: str | None = None,
    projections: dict[str, list[dict[str, Any]]] | None = None,
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

    See ``src/lib/data-types.ts`` for the TypeScript-side schema.
    """
    out = DATA_ROOT / pipeline / f"{series_id}.json"
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
) -> Path:
    """
    Write a curve JSON file. ``snapshots`` is a list of
    ``{"asOf": iso_date, "points": [{"tenor": str, "tenorMonths": int, "v": float}, ...]}``
    ordered chronologically (oldest first).
    """
    out = DATA_ROOT / pipeline / f"{series_id}.json"
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
