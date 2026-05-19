#!/usr/bin/env python3
"""
Top-level runner: invokes each provider-specific audit script in
sequence and reports a consolidated pass/fail.

Use this in CI / pre-commit. Individual audits (audit_fred_series.py,
audit_worldbank_indicators.py, audit_yahoo_tickers.py, …) can be
run on their own for finer iteration.

Exit codes:
  0 — every provider audit passed
  1 — at least one provider audit failed (in --strict mode)
  2 — couldn't even run one of the audits (script missing, etc.)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"

# Order of execution. Each entry: (label, script-relative-path,
# args-to-pass). Add new providers here when their audit lands.
PROVIDERS = [
    ("FRED",         "audit_fred_series.py",         []),
    ("World Bank",   "audit_worldbank_indicators.py", []),
    ("Yahoo",        "audit_yahoo_tickers.py",        []),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="Pass --strict to each provider audit; exit 1 "
                         "on any audit's --strict failure.")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    any_failed = False
    for label, script, extra in PROVIDERS:
        path = SCRIPTS_DIR / script
        if not path.exists():
            print(f"[!] missing audit script: {script}", file=sys.stderr)
            return 2
        cmd = [sys.executable, str(path), *extra]
        if args.strict:
            cmd.append("--strict")
        if args.no_cache:
            cmd.append("--no-cache")
        print(f"\n========== {label} ==========", flush=True)
        rc = subprocess.run(cmd).returncode
        if rc != 0:
            any_failed = True
            print(f"[{label}] audit failed (exit {rc})", file=sys.stderr)

    print("\n========== Summary ==========")
    if any_failed:
        print("[!] At least one provider audit reported mismatches.")
        return 1 if args.strict else 0
    print("OK: all provider audits clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
