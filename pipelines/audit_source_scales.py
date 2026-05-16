"""
Audit source scales: load every source's latest data point and report
its magnitude alongside the declared unit + formatting. Flags pairs
that look implausible for what the unit claims.

Why this exists
---------------
combineTwo() in the renderer doesn't know about units. It just divides /
sums / subtracts the numerical values. If two sources are in different
implicit bases (one in raw dollars, the other in millions; one in
percent, the other in basis points), the result is numerically correct
but semantically wrong — and there's no warning.

Concrete example that triggered this audit: USAspending state-level
federal spending is in raw dollars (~5×10^11). FRED real GDP is in
billions of chained 2017 dollars (~2×10^4). Naive divide gives
~10^7, which the user described as "ludicrously high" — and they're
right. The actual share-of-GDP would be ~2% if both were in the same
base.

What this prints
----------------
For each source YAML in src/content/sources/, the script loads the
matching public/data/<dataFile>, finds the latest point, and prints:

  source_id  |  latest_value  |  unit  |  formatting style  |  verdict

The verdict is a heuristic flag:
  -  ok         — magnitude plausible for the stated unit
  -  CHECK      — magnitude looks unusual; eyeball it
  -  HUGE       — > 10^9 (likely raw dollars stored without bn/M scaling)
  -  TINY       — < 0.0001 with no obvious sub-unit (likely a bug)

Groups by pipeline/folder so similar sources are adjacent for scanning.

Run with: ``python pipelines/audit_source_scales.py``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    from ruamel.yaml import YAML
    yaml_io = YAML(typ="safe")
    HAVE_RUAMEL = True
except ImportError:
    import yaml as pyyaml
    yaml_io = None
    HAVE_RUAMEL = False


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_ROOT = REPO_ROOT / "src" / "content" / "sources"
DATA_ROOT = REPO_ROOT / "public"


def load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if HAVE_RUAMEL:
        return yaml_io.load(text)
    return pyyaml.safe_load(text)


def latest_point(data_file_rel: str) -> tuple[float | None, str | None]:
    """Load JSON and return (latest_value, latest_date)."""
    p = DATA_ROOT / data_file_rel
    if not p.exists():
        return None, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None, None
    if data.get("kind") != "timeseries":
        return None, None
    pts = data.get("points") or []
    if not pts:
        return None, None
    last = pts[-1]
    return last.get("v"), last.get("t")


def classify(value: float, unit: str, fmt_style: str) -> str:
    """Heuristic plausibility check for the (value, unit) pair."""
    if value is None:
        return "no-data"
    if value == 0:
        return "zero"
    abs_v = abs(value)

    # Percent-style: should be 0-100 (or a touch over for niche cases).
    if fmt_style == "percent" or "%" in unit.lower():
        if 0 < abs_v < 100:
            return "ok"
        if abs_v <= 200:
            return "ok (>100% — unusual but possible)"
        return "CHECK percent looks too high"

    # Index-style: typically 50-500 (CPI, market indices).
    if fmt_style == "index" or "index" in unit.lower():
        if 1 < abs_v < 10000:
            return "ok"
        return "CHECK index out of typical range"

    # Currency / numerical magnitude bands.
    if abs_v >= 1e12:
        return "HUGE (>= 1T — raw value? expected compact?)"
    if abs_v >= 1e9:
        return "HUGE (>= 1B — raw value? expected M/B scaling?)"
    if abs_v < 1e-4:
        return "TINY (< 0.0001 — sub-unit lost in conversion?)"

    return "ok"


def main() -> int:
    yaml_files = sorted(SOURCES_ROOT.rglob("*.yaml"))
    print(f"Auditing {len(yaml_files)} sources...\n")

    # (folder, rows) so output groups by pipeline-style folder.
    grouped: dict[str, list[tuple[str, float | None, str, str, str, str]]] = {}
    for yp in yaml_files:
        try:
            spec = load_yaml(yp)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(spec, dict):
            continue
        data_file = spec.get("dataFile")
        if not data_file:
            continue
        rel = yp.relative_to(SOURCES_ROOT)
        sid = str(rel.with_suffix("")).replace("\\", "/")
        folder = rel.parts[0] if len(rel.parts) > 0 else "_root"
        unit = spec.get("unit") or ""
        fmt = spec.get("formatting") or {}
        fmt_style = fmt.get("style") or "number"
        value, date = latest_point(data_file)
        verdict = classify(value, unit, fmt_style) if value is not None else "no-data"
        grouped.setdefault(folder, []).append((sid, value, unit, fmt_style, date or "", verdict))

    # Pretty print.
    flagged: list[str] = []
    for folder in sorted(grouped.keys()):
        rows = grouped[folder]
        rows.sort(key=lambda r: r[0])
        print(f"\n=== {folder} ({len(rows)} sources) ===")
        for sid, value, unit, fmt_style, date, verdict in rows:
            v_str = "n/a" if value is None else f"{value:>18,.4g}"
            marker = "" if verdict.startswith("ok") else "  <-- " + verdict
            print(f"  {sid:<48}  {v_str}  {unit:<16}  {fmt_style:<10}{marker}")
            if marker:
                flagged.append(f"{sid}: latest={value} unit='{unit}' style={fmt_style}  → {verdict}")

    print("\n\n=== Flagged for review ===")
    if not flagged:
        print("  (none — every source's latest magnitude fits its declared unit)")
    else:
        for line in flagged:
            print(f"  {line}")
    print(f"\nTotal: {len(flagged)} flagged.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
