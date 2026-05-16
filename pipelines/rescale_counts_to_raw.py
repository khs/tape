"""
One-shot script to rescale FRED count-style series from "thousands" to
raw counts.

Why
---
Mirror of pipelines/rescale_currency_to_billions.py for the count axis.
After this script + the currency rescale, derived sources that pair
a currency (billions USD) with a count (raw people / jobs / homes /
claims) can produce a numerically-meaningful per-unit value: e.g.
``CA federal $ / US population = $486B / 332M people = $1,463/person``,
in canonical units, with no implicit-scale gymnastics in the renderer.

What changes
------------
For each FRED source whose ``unit`` contains "thousand" (61 of them as
of writing — state populations, payrolls, housing starts, claims,
JOLTS openings):

  * Data file values × 1000.
  * ``unit`` rewritten to the natural noun (people / jobs / claims /
    homes / starts) inferred from the source ID.
  * Formatting: compact notation, decimals 0, no prefix/suffix. So
    a state population of 39_500_000 displays as "39.5M" not "39M"
    via Intl's compact mode.

Idempotency: sources whose unit already lacks "thousand" are skipped,
including data files (the rescale_currency script's same approach).

Run with: ``python pipelines/rescale_counts_to_raw.py``
"""
from __future__ import annotations

import json
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
DATA_ROOT = REPO_ROOT / "public"
SCALE_FACTOR = 1e3


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


# Heuristic: infer the natural noun for the canonical unit from the
# source ID. Falls back to "count" for anything unmatched.
NOUN_BY_KEYWORD: list[tuple[str, str]] = [
    ("population", "people"),
    ("payrolls", "jobs"),
    ("employment", "jobs"),
    ("claims", "claims"),
    ("openings", "openings"),
    ("permits", "permits"),
    ("starts", "starts"),
    ("sales", "homes sold"),
]


def infer_unit(source_id: str) -> str:
    sid_lower = source_id.lower()
    for keyword, noun in NOUN_BY_KEYWORD:
        if keyword in sid_lower:
            return noun
    return "count"


def rescale_data_file(p: Path) -> tuple[bool, int]:
    """Divide every point's v by SCALE_FACTOR — actually multiply, here."""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False, 0
    n = 0
    if isinstance(data, dict):
        if data.get("kind") == "timeseries":
            for pt in data.get("points", []) or []:
                if isinstance(pt, dict) and "v" in pt and isinstance(pt["v"], (int, float)):
                    pt["v"] = pt["v"] * SCALE_FACTOR
                    n += 1
        if "latest" in data and isinstance(data["latest"], dict) and "v" in data["latest"]:
            data["latest"]["v"] = data["latest"]["v"] * SCALE_FACTOR
            n += 1
        if "priors" in data and isinstance(data["priors"], dict):
            for pt in data["priors"].values():
                if isinstance(pt, dict) and "v" in pt:
                    pt["v"] = pt["v"] * SCALE_FACTOR
                    n += 1
        if "sparks" in data and isinstance(data["sparks"], dict):
            for spark in data["sparks"].values():
                if isinstance(spark, list):
                    for pt in spark:
                        if isinstance(pt, dict) and "v" in pt:
                            pt["v"] = pt["v"] * SCALE_FACTOR
                            n += 1
    if n == 0:
        return False, 0
    p.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return True, n


def main() -> int:
    print("=== Phase 1: source YAML updates ===")
    yaml_paths: list[Path] = []
    updated = 0
    skipped = 0
    for yp in sorted(SOURCES_ROOT.rglob("*.yaml")):
        try:
            spec = load_yaml(yp)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(spec, dict):
            continue
        unit = str(spec.get("unit") or "")
        if "thousand" not in unit.lower():
            continue
        # Idempotency guard: don't double-rescale.
        yaml_paths.append(yp)
        source_id = str(yp.relative_to(SOURCES_ROOT).with_suffix("")).replace(
            "\\", "/"
        )
        spec["unit"] = infer_unit(source_id)
        spec["formatting"] = {
            "style": "number",
            "decimals": 0,
            "notation": "compact",
        }
        dump_yaml(yp, spec)
        updated += 1
    print(f"  {updated} YAMLs updated")

    print("\n=== Phase 2: data file rescale ===")
    rescaled = 0
    no_change = 0
    missing = 0
    total_points = 0
    for yp in yaml_paths:
        try:
            spec = load_yaml(yp)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(spec, dict):
            continue
        data_file_rel = spec.get("dataFile")
        if not data_file_rel:
            continue
        data_path = DATA_ROOT / data_file_rel
        if not data_path.exists():
            missing += 1
            continue
        # Sanity: peek at the first point to avoid double-rescale.
        try:
            preview = json.loads(data_path.read_text(encoding="utf-8"))
            sample_v = None
            if isinstance(preview, dict):
                pts = preview.get("points") or []
                if pts and isinstance(pts[0], dict) and "v" in pts[0]:
                    sample_v = pts[0]["v"]
            if sample_v is not None and abs(sample_v) > 1e6:
                # Already in raw count magnitude.
                no_change += 1
                continue
        except Exception:  # noqa: BLE001
            pass
        changed, n = rescale_data_file(data_path)
        if changed:
            rescaled += 1
            total_points += n
        summary_path = data_path.with_name(data_path.stem + ".summary.json")
        if summary_path.exists():
            try:
                preview = json.loads(summary_path.read_text(encoding="utf-8"))
                sample_v = None
                if isinstance(preview, dict) and "latest" in preview:
                    sample_v = preview["latest"].get("v")
                if sample_v is None or abs(sample_v) <= 1e6:
                    rescale_data_file(summary_path)
            except Exception:  # noqa: BLE001
                pass

    print(
        f"  {rescaled} data files rescaled ({total_points:,} points), "
        f"{no_change} skipped (already raw), {missing} missing"
    )
    print("\nDone. Re-run pipelines/build_summaries.py for clean summary regen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
