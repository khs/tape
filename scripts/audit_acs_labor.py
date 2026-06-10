#!/usr/bin/env python3
"""
Audit the ACS race-unemployment YAMLs (src/content/sources/acs_labor/)
against the live S2301 variable labels.

These YAMLs are emitted inline by pipelines/census_acs_labor.py from a
fixed RACES table of hardcoded variable codes. The codes are stable
across 2015-2023, but the label TEXT format drifts between vintages
(the "Estimate" / "Unemployment rate" segments swap order), so this
audit matches labels FLEXIBLY: each code's live label must contain
"unemployment rate" AND that code's race fragment, and the YAML name
must contain the race keyword. That pins code→race in both directions —
a code↔race mixup (e.g. labeling the Asian code as Black) fails even
though both labels share "unemployment rate".

The S2301 groups metadata endpoint is anonymous (no key needed), so
this runs in CI without CENSUS_API_KEY; a committed cache lets it run
fully offline.

Usage:
  python scripts/audit_acs_labor.py
  python scripts/audit_acs_labor.py --strict --no-cache
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml as pyyaml
except ImportError:
    print("Install PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "src" / "content" / "sources" / "acs_labor"
CACHE_PATH = ROOT / "scripts" / "_acs_labor_audit_cache.json"
GROUPS_URL = "https://api.census.gov/data/2023/acs/acs1/subject/groups/S2301.json"

CODE_RE = re.compile(r"\b(S2301_C04_\d+E)\b")

# code: (race fragment that must appear in the live label, keyword that
# must appear in the YAML name) — both lowercase. "" fragment = the
# 16-and-over total line (no race breakdown). Keep in lockstep with
# pipelines/census_acs_labor.py's RACES.
EXPECTED: dict[str, tuple[str, str]] = {
    "S2301_C04_001E": ("",                  "all workers"),
    "S2301_C04_012E": ("white alone",       "white"),
    "S2301_C04_013E": ("black",             "black"),
    "S2301_C04_014E": ("american indian",   "american indian"),
    "S2301_C04_015E": ("asian",             "asian"),
    "S2301_C04_016E": ("native hawaiian",   "native hawaiian"),
    "S2301_C04_017E": ("some other race",   "some other race"),
    "S2301_C04_018E": ("two or more races", "two or more races"),
    "S2301_C04_019E": ("hispanic",          "hispanic"),
}


def fetch_labels() -> dict[str, str]:
    try:
        r = subprocess.run(["curl", "-sS", "-L", "--max-time", "30", GROUPS_URL],
                           capture_output=True, check=True)
        d = json.loads(r.stdout.decode("utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        print(f"[!] label fetch failed: {e}", file=sys.stderr)
        return {}
    vs = d.get("variables", {}) if isinstance(d, dict) else {}
    return {c: (vs.get(c, {}).get("label") or "") for c in EXPECTED}


def read_yamls() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(SOURCE_DIR.glob("*.yaml")):
        try:
            data = pyyaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"  skipping {p.name}: {e}", file=sys.stderr)
            continue
        series = (data.get("provenance") or {}).get("series", "")
        m = CODE_RE.search(series or "")
        out.append({"file": str(p.relative_to(ROOT)), "name": data.get("name", ""),
                    "code": m.group(1) if m else None})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = read_yamls()
    print(f"Auditing {len(rows)} acs_labor YAMLs...", file=sys.stderr)

    labels: dict[str, str] = {}
    if not args.no_cache and CACHE_PATH.exists():
        try:
            labels = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            labels = {}
    if not labels:
        labels = fetch_labels()
        if labels:
            CACHE_PATH.write_text(json.dumps(labels, indent=2, sort_keys=True),
                                  encoding="utf-8")

    findings: list[dict[str, Any]] = []
    for r in rows:
        code, name = r["code"], r["name"].lower()
        notes: list[str] = []
        bad = False
        if not code or code not in EXPECTED:
            bad = True
            notes.append(f"code {code!r} not in EXPECTED map")
        else:
            frag, name_kw = EXPECTED[code]
            official = (labels.get(code) or "").lower()
            if not official:
                bad = True
                notes.append(f"no live label for {code} (fetch failed + no cache?)")
            else:
                if "unemployment rate" not in official:
                    bad = True
                    notes.append(f"label not an unemployment rate: '{labels.get(code)}'")
                if frag and frag not in official:
                    bad = True
                    notes.append(f"label missing race fragment '{frag}': '{labels.get(code)}'")
                if not frag and "race and hispanic" in official:
                    bad = True
                    notes.append(f"expected the all-workers total, got a race row: '{labels.get(code)}'")
            if name_kw not in name:
                bad = True
                notes.append(f"YAML name missing '{name_kw}'")
        if bad:
            findings.append({"file": r["file"], "code": code,
                             "name": r["name"], "official": labels.get(code or ""),
                             "notes": notes})

    if args.json:
        print(json.dumps({"total": len(rows), "mismatches": len(findings),
                          "findings": findings}, indent=2))
    else:
        print(f"\nTotal: {len(rows)}  Mismatches: {len(findings)}\n")
        for f in findings[:40]:
            print(f"[!] {f['file']}  ({f['code']})")
            print(f"    yaml:     {f['name']}")
            print(f"    official: {f['official']}")
            for n in f["notes"]:
                print(f"    note:     {n}")
            print()
        if not findings:
            print("OK: every code maps to the expected race label + name.")

    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
