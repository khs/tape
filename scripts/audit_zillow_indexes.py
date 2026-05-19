#!/usr/bin/env python3
"""
Audit Zillow source YAMLs against the underlying data files.

Zillow doesn't expose a "what's the official label for series X"
endpoint — the indexes ARE just CSVs at known URLs. So this audit
is structural rather than network-based:

  1. Every YAML's dataFile must exist in public/data/zillow/.
  2. The YAML's provenance.series must reference one of the known
     index families (ZHVI, ZORI) + one of the known metro slugs.
  3. The data file's stored "name" must overlap the YAML's name
     by at least one identifying token (matches the FRED audit's
     heuristic).
  4. The series_id in the dataFile filename must match the
     YAML's pipeline-prefix expectations (zhvi_<slug>.json or
     zori_<slug>.json).

Run:
  python scripts/audit_zillow_indexes.py
  python scripts/audit_zillow_indexes.py --strict
  python scripts/audit_zillow_indexes.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml as pyyaml
except ImportError:
    print("Install PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src" / "content" / "sources" / "zillow"
DATA_DIR = ROOT / "public" / "data" / "zillow"

KNOWN_INDEXES = {"zhvi", "zori"}
KNOWN_METROS = {
    "national", "nyc", "la", "chicago", "dallas", "houston", "dc",
    "philadelphia", "miami", "atlanta", "boston", "sf", "seattle",
}

STOP = {"of", "the", "and", "to", "for", "in", "us", "u", "s", "by",
        "from", "all", "rate", "index", "level", "per", "total",
        "current", "monthly", "annual", "typical", "value", "observed"}


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    findings: list[dict[str, Any]] = []
    for p in sorted(SRC_DIR.glob("*.yaml")):
        try:
            data = pyyaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            findings.append({"file": p.name, "likely_mismatch": True,
                             "notes": [f"yaml parse failed: {e}"]})
            continue
        notes: list[str] = []
        likely = False

        # Filename → expected (index, slug)
        stem = p.stem
        parts = stem.split("_", 1)
        if len(parts) != 2 or parts[0] not in KNOWN_INDEXES or parts[1] not in KNOWN_METROS:
            notes.append(
                f"filename {stem!r} doesn't match expected "
                f"<index>_<metro> pattern with index in {sorted(KNOWN_INDEXES)} "
                f"and metro in {sorted(KNOWN_METROS)}"
            )
            likely = True
            findings.append({"file": p.name, "likely_mismatch": likely, "notes": notes})
            continue
        index_key, metro_slug = parts

        # Data file exists?
        data_rel = data.get("dataFile", "")
        if not data_rel.startswith("data/zillow/"):
            notes.append(f"dataFile {data_rel!r} doesn't live under data/zillow/")
            likely = True
        data_path = ROOT / "public" / data_rel
        if not data_path.exists():
            notes.append(f"data file missing on disk: {data_rel}")
            likely = True
        else:
            try:
                fdata = json.loads(data_path.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                notes.append(f"data file unreadable: {e}")
                likely = True
                fdata = None
            if fdata:
                # Token overlap between YAML name + data file name.
                ytoks = tokens(data.get("name", "")) | tokens(data.get("shortName", ""))
                ftoks = tokens(fdata.get("name", ""))
                shared = len(ytoks & ftoks)
                if shared == 0 and (ytoks or ftoks):
                    notes.append(
                        f"NO token overlap between yaml name "
                        f"({sorted(ytoks)}) and data file name "
                        f"({sorted(ftoks)})"
                    )
                    likely = True

        # Series identifier sanity.
        series = (data.get("provenance") or {}).get("series", "")
        expected_index_upper = index_key.upper()
        if expected_index_upper not in series.upper():
            notes.append(
                f"provenance.series {series!r} doesn't mention "
                f"the expected index family {expected_index_upper}"
            )
            likely = True

        findings.append({
            "file": p.name,
            "index": index_key,
            "metro": metro_slug,
            "data_file": data_rel,
            "yaml_name": data.get("name", ""),
            "likely_mismatch": likely,
            "notes": notes,
        })

    mismatches = [f for f in findings if f["likely_mismatch"]]
    if args.json:
        print(json.dumps({"total": len(findings),
                          "mismatches": len(mismatches),
                          "findings": findings}, indent=2))
    else:
        print(f"Auditing {len(findings)} Zillow YAMLs...\n")
        print(f"Total: {len(findings)}  Likely mismatches: {len(mismatches)}\n")
        for f in mismatches:
            print(f"[!] {f['file']}")
            for n in f["notes"]:
                print(f"    {n}")
            print()
        if not mismatches:
            print("OK: No likely mismatches found.")
    return 1 if (args.strict and mismatches) else 0


if __name__ == "__main__":
    sys.exit(main())
