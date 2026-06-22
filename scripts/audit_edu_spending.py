#!/usr/bin/env python3
"""
Audit the per-pupil-spending source YAMLs (src/content/sources/edu_spending/).

Single-metric, emitted inline by pipelines/edu_spending.py. This
local audit confirms the invariants that matter for correctness +
attribution: each source is a per-pupil USD series, and carries the
US Census Bureau (Annual Survey of School System Finances) attribution
under a public-domain license. The data was migrated off the Urban
Institute Education Data Portal to the Census summary tables directly
(see the edu_spending.py docstring: Urban's per-pupil denominator
differed ~5%, which would have put a false kink at the splice seam), so
this audit expects Census / public-domain, not the old Urban / ODC-BY.
No network call needed.

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
        # Sourced directly from the Census ASSF (F-33) summary tables, which are
        # federal public-domain data (migrated off the Urban Institute portal).
        if "census" not in provider:
            notes.append(
                f"provider must credit the US Census Bureau (ASSF): {prov.get('provider')!r}"
            )
        if "public domain" not in license_:
            notes.append(f"license must state public domain: {prov.get('license')!r}")
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
            print("OK: per-pupil USD + US Census Bureau / public-domain attribution on every source.")
    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
