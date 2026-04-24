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
) -> Path:
    """
    Write a timeseries JSON file. ``points`` is a list of ``{"t": iso_date, "v": float}``
    ordered chronologically (oldest first).
    """
    out = DATA_ROOT / pipeline / f"{series_id}.json"
    _write_json(
        out,
        {
            "id": series_id,
            "name": name,
            "kind": "timeseries",
            "unit": unit,
            "lastUpdated": utc_now_iso(),
            "points": points,
        },
    )
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
