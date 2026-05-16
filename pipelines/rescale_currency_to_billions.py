"""
One-shot script to rescale raw-dollar pipelines to billions.

Why
---
Three pipelines (``usaspending``, ``worldbank_gdp_raw``, ``yahoo_marketcap``)
historically wrote raw-dollar values (~10^9 to 10^13) while FRED macro
series store billions (~10^4). Mixing them in a derived source's
``divide`` op produced numerically-large nonsense (CA federal $ /
US GDP ≈ 20 million instead of ~2%). Going forward the pipelines
themselves output billions; this script normalizes the EXISTING
public/data JSON + source YAML manifests so the live site benefits
without waiting for the next data refresh.

What gets rescaled
------------------
1. **Data files**: every point's ``v`` divided by 1e9 for
   ``public/data/usaspending/*.json``,
   ``public/data/worldbank_gdp_raw/*.json``,
   ``public/data/yahoo_marketcap/*.json``.
   Both the main ``<id>.json`` and the ``<id>.summary.json`` sibling
   (if present) get rescaled — summaries store points too.
2. **Source YAMLs**: ``unit`` becomes "billions USD"; ``formatting``
   becomes ``{style: currency, currency: USD, suffix: " B", decimals: 1}``
   so display reads e.g. "$486.0 B" instead of the old compact
   "$486B".

Idempotent guard: each source YAML's existing unit string is checked
before rewriting; if it already says "billions USD" we skip both the
YAML and the data file (the rescale was already applied).

Run with: ``python pipelines/rescale_currency_to_billions.py``
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

# Pipelines whose data is currently in raw USD and should be in billions.
RESCALE_FOLDERS = ["usaspending", "worldbank_gdp_raw", "yahoo_marketcap"]
SCALE_FACTOR = 1e9


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


def rescale_data_file(p: Path) -> tuple[bool, int]:
    """Divide every point's v by SCALE_FACTOR. Returns (changed, n_points)."""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False, 0
    n = 0
    if isinstance(data, dict):
        # Main timeseries file.
        if data.get("kind") == "timeseries":
            for pt in data.get("points", []) or []:
                if isinstance(pt, dict) and "v" in pt and isinstance(pt["v"], (int, float)):
                    pt["v"] = pt["v"] / SCALE_FACTOR
                    n += 1
        # Summary sibling: rescale latest, priors, sparks.
        if "latest" in data and isinstance(data["latest"], dict) and "v" in data["latest"]:
            data["latest"]["v"] = data["latest"]["v"] / SCALE_FACTOR
            n += 1
        if "priors" in data and isinstance(data["priors"], dict):
            for pt in data["priors"].values():
                if isinstance(pt, dict) and "v" in pt:
                    pt["v"] = pt["v"] / SCALE_FACTOR
                    n += 1
        if "sparks" in data and isinstance(data["sparks"], dict):
            for spark in data["sparks"].values():
                if isinstance(spark, list):
                    for pt in spark:
                        if isinstance(pt, dict) and "v" in pt:
                            pt["v"] = pt["v"] / SCALE_FACTOR
                            n += 1
    if n == 0:
        return False, 0
    p.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return True, n


def update_source_yaml(yaml_path: Path) -> str:
    """Update unit + formatting. Returns status: 'updated' / 'already' / 'skipped'."""
    try:
        spec = load_yaml(yaml_path)
    except Exception:  # noqa: BLE001
        return "skipped"
    if not isinstance(spec, dict):
        return "skipped"
    existing_unit = (spec.get("unit") or "").lower()
    if "billions" in existing_unit:
        return "already"
    spec["unit"] = "billions USD"
    # Replace formatting wholesale to drop the old compact notation.
    spec["formatting"] = {
        "style": "currency",
        "currency": "USD",
        "decimals": 1,
        "suffix": " B",
    }
    dump_yaml(yaml_path, spec)
    return "updated"


def main() -> int:
    print("=== Phase 1: source YAML updates ===")
    yaml_stats = {"updated": 0, "already": 0, "skipped": 0}
    yaml_paths: list[Path] = []
    for folder in RESCALE_FOLDERS:
        for yp in sorted((SOURCES_ROOT / folder).rglob("*.yaml")):
            yaml_paths.append(yp)
            status = update_source_yaml(yp)
            yaml_stats[status] += 1
    print(f"  {yaml_stats['updated']} YAMLs updated, "
          f"{yaml_stats['already']} already-billions (skipped), "
          f"{yaml_stats['skipped']} unparseable")

    print("\n=== Phase 2: data file rescale ===")
    # Rescale ONLY the data files whose corresponding YAML JUST got updated.
    # Already-billions sources got skipped above; their data files don't
    # need rescaling either (assumption: YAML state matches data state).
    data_stats = {"rescaled": 0, "no_change": 0, "missing": 0}
    total_points = 0
    for yp in yaml_paths:
        try:
            spec = load_yaml(yp)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(spec, dict):
            continue
        # We only want to rescale data for sources where this script
        # actually rewrote the YAML — but we just rewrote them all in
        # phase 1, so detect via: was the unit "billions USD" before?
        # Simpler: assume any non-already-billions source needs data
        # rescale too. Tracking the per-source flag would require keeping
        # state across phases; instead just check the data file's
        # current magnitude as a sanity gate.
        data_file_rel = spec.get("dataFile")
        if not data_file_rel:
            continue
        data_path = DATA_ROOT / data_file_rel
        if not data_path.exists():
            data_stats["missing"] += 1
            continue
        # Sanity check: peek at the first point's magnitude. If it's
        # already < 10^5, the data was already rescaled in a prior run.
        try:
            preview = json.loads(data_path.read_text(encoding="utf-8"))
            sample_v: float | None = None
            if isinstance(preview, dict):
                pts = preview.get("points") or []
                if pts and isinstance(pts[0], dict) and "v" in pts[0]:
                    sample_v = pts[0]["v"]
                elif "latest" in preview and isinstance(preview["latest"], dict):
                    sample_v = preview["latest"].get("v")
            if sample_v is not None and abs(sample_v) < 1e5:
                data_stats["no_change"] += 1
                continue
        except Exception:  # noqa: BLE001
            pass
        changed, n = rescale_data_file(data_path)
        if changed:
            data_stats["rescaled"] += 1
            total_points += n
        # Also rescale the .summary.json sibling if present.
        summary_path = data_path.with_name(data_path.stem + ".summary.json")
        if summary_path.exists():
            try:
                preview = json.loads(summary_path.read_text(encoding="utf-8"))
                sample_v = None
                if isinstance(preview, dict) and "latest" in preview:
                    sample_v = preview["latest"].get("v")
                if sample_v is None or abs(sample_v) >= 1e5:
                    rescale_data_file(summary_path)
            except Exception:  # noqa: BLE001
                pass

    print(
        f"  {data_stats['rescaled']} data files rescaled "
        f"({total_points:,} points), "
        f"{data_stats['no_change']} already-rescaled (skipped), "
        f"{data_stats['missing']} missing files"
    )
    print("\nDone. Re-run pipelines/build_summaries.py to regenerate any")
    print("derived summaries beyond the trivial sibling rescale.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
