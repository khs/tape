"""
Backfill ``unitClass`` on source YAML files.

Why this exists
---------------
combineOpFormatting in src/lib/derive.ts uses unitClass to pick the
output formatting + display multiplier for derived sources. Without
it, the helper falls back to formatting.style which is too coarse:
US real GDP (currency, in billions) and Case-Shiller (an index)
both report ``style: number`` so they look identical to the
style-only dispatch — even though combining them with another
source should produce different outputs.

Heuristic
---------
Resolve each source's unitClass from formatting.style + the unit
string in the YAML. Order matters; the first match wins:

  1. style is "currency" / "percent" / "bps" / "index"  → unitClass
     trivially follows.
  2. style is "number" but the unit field carries a currency hint
     ("USD", "EUR", "$", "billions USD", ...)            → currency.
  3. style is "number" with "index" in the unit          → index.
  4. style is "number" with a count-noun unit (people, jobs,
     claims, openings, permits, starts, homes sold,
     count, persons, workers, units, homes)               → count.
  5. style is "number" otherwise                          → ratio.

Idempotency: if the YAML already has unitClass, the script doesn't
overwrite it. This makes manual overrides stable across runs.

Run with: ``python pipelines/backfill_unit_class.py [--dry-run]``
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    from ruamel.yaml import YAML

    yaml_io = YAML()
    yaml_io.preserve_quotes = True
    yaml_io.indent(mapping=2, sequence=4, offset=2)
    HAVE_RUAMEL = True
except ImportError:
    import yaml as pyyaml

    yaml_io = None
    HAVE_RUAMEL = False


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_ROOT = REPO_ROOT / "src" / "content" / "sources"


COUNT_NOUNS = {
    "people",
    "persons",
    "jobs",
    "claims",
    "openings",
    "permits",
    "starts",
    "homes",
    "homes sold",
    "workers",
    "units",
    "count",
    "household",
    "households",
}


def load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if HAVE_RUAMEL:
        return yaml_io.load(text)
    return pyyaml.safe_load(text)


def dump_yaml(path: Path, data: Any) -> None:
    if HAVE_RUAMEL:
        with path.open("w", encoding="utf-8") as f:
            yaml_io.dump(data, f)
    else:
        path.write_text(
            pyyaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


def infer_unit_class(spec: dict[str, Any]) -> str:
    fmt = spec.get("formatting") or {}
    style = fmt.get("style") or "number"
    unit = (spec.get("unit") or "").lower()
    prefix = (fmt.get("prefix") or "").lower()
    suffix = (fmt.get("suffix") or "").lower()

    if style == "currency":
        return "currency"
    if style == "percent" or style == "bps":
        return "rate"
    if style == "index":
        return "index"
    # style == "number" (or anything else): use heuristics.
    if (
        "$" in prefix
        or "usd" in unit
        or "eur" in unit
        or "gbp" in unit
        or "jpy" in unit
        or "billions" in unit and any(c in unit for c in ("usd", "$"))
        or "billion" in unit and ("usd" in unit or "$" in unit)
        or "dollar" in unit
    ):
        return "currency"
    if "index" in unit:
        return "index"
    if "percent" in unit or "%" in unit or "ppt" in unit:
        return "rate"
    # Bare unit equal to (or containing) a count noun → count.
    unit_words = set(unit.split())
    if unit_words & COUNT_NOUNS or any(noun in unit for noun in COUNT_NOUNS):
        return "count"
    # Generic numeric ratio.
    return "ratio"


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    stats = {"already": 0, "updated": 0, "skipped": 0}
    by_class: dict[str, int] = {}
    for yp in sorted(SOURCES_ROOT.rglob("*.yaml")):
        try:
            spec = load_yaml(yp)
        except Exception:  # noqa: BLE001
            stats["skipped"] += 1
            continue
        if not isinstance(spec, dict):
            stats["skipped"] += 1
            continue
        if "unitClass" in spec:
            stats["already"] += 1
            cls = spec["unitClass"]
            by_class[cls] = by_class.get(cls, 0) + 1
            continue
        cls = infer_unit_class(spec)
        spec["unitClass"] = cls
        if not dry_run:
            dump_yaml(yp, spec)
        stats["updated"] += 1
        by_class[cls] = by_class.get(cls, 0) + 1

    print("=== Backfill summary ===")
    print(f"  Updated:   {stats['updated']}")
    print(f"  Already set: {stats['already']}")
    print(f"  Skipped:   {stats['skipped']}")
    print("\n=== Distribution by inferred class ===")
    for cls in sorted(by_class):
        print(f"  {cls:<10}: {by_class[cls]}")
    if dry_run:
        print("\n(dry-run; no files modified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
