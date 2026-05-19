#!/usr/bin/env python3
"""
Audit World Bank source YAMLs against the WB API's official
indicator names.

For each YAML in src/content/sources/worldbank_extended/ and
src/content/sources/worldbank_gdp_raw/:
  - extract the indicator code (e.g. NV.AGR.TOTL.ZS) from the
    provenance.series field
  - fetch the official indicator name from WB's public API
  - compare against the YAML's name via token overlap (same
    heuristic as audit_fred_series.py)

Why: same shape of risk as the FRED bug — the WB indicator code
is opaque and easy to mistype, the YAML name is hand-written, and
nothing else catches a divergence. ~426 hand-written labels
across the two WB pipelines.

Usage:
  python scripts/audit_worldbank_indicators.py
  python scripts/audit_worldbank_indicators.py --strict
  python scripts/audit_worldbank_indicators.py --json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
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
SOURCE_DIRS = [
    ROOT / "src" / "content" / "sources" / "worldbank_extended",
    ROOT / "src" / "content" / "sources" / "worldbank_gdp_raw",
]
CACHE_PATH = ROOT / "scripts" / "_worldbank_audit_cache.json"

# Indicator codes like "NV.AGR.TOTL.ZS" — uppercase + dots + digits.
INDICATOR_RE = re.compile(r"\b([A-Z]+\.[A-Z]+(?:\.[A-Z0-9]+)+)\b")

# Token-overlap STOP words — same set as the FRED audit so the
# heuristic stays consistent across providers.
STOP = {"of", "the", "and", "to", "for", "in", "us", "u", "s", "by",
        "from", "all", "rate", "index", "level", "per", "total",
        "current", "expenditures", "consumption", "payments",
        "receipts", "value", "added", "annual", "world"}


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


def fetch_wb_name(indicator_code: str) -> tuple[str | None, str | None]:
    """Returns (indicator_name, error). WB's v2 indicator endpoint
    returns a JSON array; [0] is pagination, [1] is the result list."""
    url = f"https://api.worldbank.org/v2/indicator/{indicator_code}?format=json"
    try:
        r = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", "15", url],
            capture_output=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        return None, f"curl rc={e.returncode}"
    try:
        body = r.stdout.decode("utf-8", errors="replace")
        parsed = json.loads(body)
    except Exception as e:  # noqa: BLE001
        return None, f"parse: {e}"
    if not isinstance(parsed, list) or len(parsed) < 2:
        return None, "unexpected shape"
    results = parsed[1]
    if not results or not isinstance(results, list):
        return None, "no results"
    name = results[0].get("name")
    return (name.strip() if isinstance(name, str) else None), None


def extract_indicator_code(yaml_data: dict[str, Any]) -> str | None:
    """The WB indicator code lives in provenance.series, often
    formatted as "NV.AGR.TOTL.ZS / AUS" (code + country code). Strip
    the country half if present."""
    series = (yaml_data.get("provenance") or {}).get("series", "")
    if not series:
        return None
    # Try the obvious form first.
    m = INDICATOR_RE.search(series.split("/")[0])
    if m:
        return m.group(1)
    # Fallback: search description.
    desc = yaml_data.get("description") or ""
    m = INDICATOR_RE.search(desc)
    return m.group(1) if m else None


def read_all_yamls() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in SOURCE_DIRS:
        for p in sorted(d.glob("*.yaml")):
            try:
                data = pyyaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                print(f"  skipping {p.name}: {e}", file=sys.stderr)
                continue
            code = extract_indicator_code(data)
            out.append({
                "file": str(p.relative_to(ROOT)),
                "yaml_name": data.get("name", ""),
                "yaml_short_name": data.get("shortName", ""),
                "indicator_code": code,
            })
    return out


def load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_cache(c: dict[str, str]) -> None:
    CACHE_PATH.write_text(json.dumps(c, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    rows = read_all_yamls()
    print(f"Auditing {len(rows)} World Bank YAMLs...", file=sys.stderr)

    cache: dict[str, str] = {} if args.no_cache else load_cache()
    unique_codes = sorted({r["indicator_code"] for r in rows if r["indicator_code"]})
    to_fetch = [c for c in unique_codes if c not in cache]
    if to_fetch:
        print(f"Fetching {len(to_fetch)} indicators from WB API ({args.workers} workers)...",
              file=sys.stderr)
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch_wb_name, c): c for c in to_fetch}
            for done in cf.as_completed(futures):
                code = futures[done]
                name, err = done.result()
                cache[code] = name if name else f"__error__: {err}"
        save_cache(cache)

    findings: list[dict[str, Any]] = []
    for r in rows:
        code = r["indicator_code"]
        wb_name = cache.get(code, "") if code else ""
        likely = False
        notes: list[str] = []
        if not code:
            notes.append("no indicator code found in provenance.series or description")
            likely = True
        elif wb_name.startswith("__error__"):
            notes.append(wb_name)
        else:
            ytoks = tokens(r["yaml_name"]) | tokens(r["yaml_short_name"])
            ftoks = tokens(wb_name)
            shared = len(ytoks & ftoks)
            # WB indicators are country-agnostic ("GDP (constant 2015
            # US$)") but our YAMLs add a country qualifier ("Australia
            # real GDP"). Threshold of 1 shared identifying token is
            # the right gate here — the country word is YAML-only by
            # design. Any indicator with ZERO overlap is a real bug:
            # NY.GDP.MKTP.KD-labeled-as-population would have zero
            # overlap (gdp vs population).
            if shared == 0 and (ytoks or ftoks):
                likely = True
                notes.append(f"NO token overlap: yaml={sorted(ytoks)}, wb={sorted(ftoks)}")
        findings.append({
            "file": r["file"],
            "indicator": code,
            "yaml_name": r["yaml_name"],
            "wb_name": wb_name,
            "likely_mismatch": likely,
            "notes": notes,
        })

    mismatches = [f for f in findings if f["likely_mismatch"]]

    if args.json:
        print(json.dumps({"total": len(findings), "mismatches": len(mismatches),
                          "findings": findings}, indent=2))
    else:
        print(f"\nTotal: {len(findings)}  Likely mismatches: {len(mismatches)}\n")
        for f in mismatches:
            print(f"[!] {f['file']}")
            print(f"    indicator: {f['indicator']}")
            print(f"    yaml:      {f['yaml_name']}")
            print(f"    WB:        {f['wb_name']}")
            for n in f["notes"]:
                print(f"    note:      {n}")
            print()
        if not mismatches:
            print("OK: No likely mismatches found.")

    return 1 if (args.strict and mismatches) else 0


if __name__ == "__main__":
    sys.exit(main())
