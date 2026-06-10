#!/usr/bin/env python3
"""
Audit the per-pupil-spending source YAMLs (src/content/sources/edu_spending/).

Single-metric, emitted inline by pipelines/edu_spending.py. This
local audit confirms the invariants that matter for correctness +
attribution: each source is a per-pupil USD series, and (per the
provider ToS sweep) carries the required NCES + Urban Institute / ODC-BY
attribution. No network call needed.

Usage:
  python scripts/audit_edu_spending.py
  python scripts/audit_edu_spending.py --strict --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml as pyyaml
except ImportError:
    print("Install PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "src" / "content" / "sources" / "edu_spending"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    findings: list[dict[str, Any]] = []
    total = 0
    for p in sorted(SOURCE_DIR.glob("*.yaml")):
        total += 1
        try:
            data = pyyaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            findings.append({"file": p.name, "notes": [f"unreadable: {e}"]})
            continue
        name = (data.get("name") or "").lower()
        prov = data.get("provenance") or {}
        provider = (prov.get("provider") or "").lower()
        license_ = (prov.get("license") or "").lower()
        notes: list[str] = []
        if "per pupil" not in name:
            notes.append(f"name missing 'per pupil': {data.get('name')!r}")
        if data.get("unit") != "USD":
            notes.append(f"unit not USD: {data.get('unit')!r}")
        # ToS-sweep requirement: NCES data via Urban, ODC-BY, cite both.
        if "urban" not in provider or "nces" not in provider:
            notes.append(f"provider must credit NCES + Urban: {prov.get('provider')!r}")
        if "odc-by" not in license_:
            notes.append(f"license must state ODC-BY: {prov.get('license')!r}")
        if notes:
            findings.append({"file": p.name, "notes": notes})

    if args.json:
        print(json.dumps({"total": total, "mismatches": len(findings),
                          "findings": findings}, indent=2))
    else:
        print(f"\nTotal: {total}  Mismatches: {len(findings)}\n")
        for f in findings[:40]:
            print(f"[!] {f['file']}: {f['notes']}")
        if not findings:
            print("OK: per-pupil USD + NCES/Urban/ODC-BY attribution on every source.")
    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
