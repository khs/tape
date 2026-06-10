#!/usr/bin/env python3
"""
Audit the EIA state electricity-generation YAMLs
(src/content/sources/eia_state_energy/).

These YAMLs are emitted inline by pipelines/eia_state_energy.py
from a fixed FUELS table. EIA's fuel-type codes (NG, COW, NUC, WND,
SUN, HYC, ALL) are permanent identifiers — they don't get renumbered
the way Census subject-table columns do — so unlike the Census audits
this one needs no live provider call. The meaningful risk is an
emitter bug that pairs a fuel code with the wrong fuel word in the
name (e.g. a `fueltypeid=COW` source titled "... wind ..."). This audit
catches exactly that: for each YAML it extracts the fuel code from
provenance.series and asserts the name carries that fuel's keyword and
none of the other fuels' keywords.

Usage:
  python scripts/audit_eia_state_energy.py
  python scripts/audit_eia_state_energy.py --strict --json
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
SOURCE_DIR = ROOT / "src" / "content" / "sources" / "eia_state_energy"
CODE_RE = re.compile(r"fueltypeid=(\w+)")

# code: the fuel keyword that MUST appear in the YAML name. Keep in
# lockstep with pipelines/eia_state_energy.py's FUELS.
CODE_KEYWORD: dict[str, str] = {
    "ALL": "net generation",
    "NG": "natural gas",
    "COW": "coal",
    "NUC": "nuclear",
    "WND": "wind",
    "SUN": "solar",
    "HYC": "hydro",
}
# Fuel words that, if present in the name, indicate a specific fuel —
# used to flag a name carrying a DIFFERENT fuel than its code.
FUEL_WORDS = {"natural gas", "coal", "nuclear", "wind", "solar", "hydro"}


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
        series = (data.get("provenance") or {}).get("series", "")
        m = CODE_RE.search(series or "")
        code = m.group(1) if m else None
        notes: list[str] = []
        if not code or code not in CODE_KEYWORD:
            notes.append(f"no known fueltypeid in provenance.series ({series!r})")
        else:
            kw = CODE_KEYWORD[code]
            if kw not in name:
                notes.append(f"name missing '{kw}' for code {code}: {data.get('name')!r}")
            # For a specific fuel, no OTHER fuel word should appear.
            if code != "ALL":
                others = {w for w in FUEL_WORDS if w != kw and w in name}
                # "natural gas" contains "gas"; "coal" etc. are distinct.
                if others:
                    notes.append(f"name for {code} also mentions other fuel(s): {sorted(others)}")
        if notes:
            findings.append({"file": p.name, "name": data.get("name"),
                             "code": code, "notes": notes})

    if args.json:
        print(json.dumps({"total": total, "mismatches": len(findings),
                          "findings": findings}, indent=2))
    else:
        print(f"\nTotal: {total}  Mismatches: {len(findings)}\n")
        for f in findings[:40]:
            print(f"[!] {f['file']}  ({f.get('code')})")
            for n in f["notes"]:
                print(f"    {n}")
        if not findings:
            print("OK: every fuel code matches its name's fuel keyword.")

    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
