#!/usr/bin/env python3
"""
Audit every fred/*.yaml source against FRED's authoritative series
title. For each YAML we hold:
  - `provenance.series`: the FRED series ID
  - `name` / `shortName` / `description`: our human-readable label

For each series ID, fetch FRED's series page, extract the
official title, and report mismatches between what FRED calls it
and what our YAML calls it.

Why: the May 2026 federal-spending bug — Social Security tooltips
showed Unemployment Insurance numbers because four YAMLs were
pointing at the wrong NIPA Table 3.12 lines (W825 vs W823, etc.).
Nothing in our pipeline previously checked that the FRED ID
matched the human label. This is that check, runnable on demand
or in CI.

Usage:
  python scripts/audit_fred_series.py
  python scripts/audit_fred_series.py --strict   # exit 1 on mismatches
  python scripts/audit_fred_series.py --json     # machine-readable

Implementation notes:
- Probe the public FRED HTML page (no auth needed). The <title>
  tag carries the form "Display title (SERIES_ID) | FRED | St. Louis Fed".
- Concurrent fetches via ThreadPoolExecutor; ~145 series at 4
  workers runs in under a minute on a residential connection.
- Caches results in scripts/_fred_audit_cache.json so re-runs
  don't re-hammer FRED. Pass --no-cache to bypass.
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
FRED_DIR = ROOT / "src" / "content" / "sources" / "fred"
CACHE_PATH = ROOT / "scripts" / "_fred_audit_cache.json"

# Series whose YAML label is a known-good common-parlance shorthand
# for FRED's formal title. Reviewed by hand against FRED's series
# page; the audit-script's token-overlap heuristic flags these
# because the formal NIPA / BLS / Fed titles are long and don't
# share short-name words with the everyday term. Keep this list
# small and grow it deliberately — every addition is a promise
# that "yes, I checked, this YAML is correctly labeled."
ALLOWLIST: dict[str, str] = {
    # CCSA: BLS's "Continued Claims (Insured Unemployment)" is the
    # standard "continuing jobless claims" series.
    "CCSA": "Continuing jobless claims = Continued Claims (Insured Unemployment) — BLS UI weekly release",
    # PCEPILFE / PCEPI: BEA's chain-type price indices. "Core PCE"
    # and "headline PCE" are the universal shorthand in macro coverage.
    "PCEPILFE": "Core PCE price index = PCE Excluding Food and Energy chain-type price index",
    "PCEPI": "Headline PCE price index = PCE Chain-type Price Index",
    # WALCL: H.4.1 Wednesday-level total assets. "Fed balance sheet"
    # is the universally-used shorthand for this exact series.
    "WALCL": "Fed balance sheet = H.4.1 Total Assets, Wednesday Level",
    # U6RATE: BLS labor-utilization U-6 measure. The official title
    # is a paragraph; "U-6 unemployment rate" is the standard label.
    "U6RATE": "U-6 unemployment rate = the full BLS broader-measure formula",
    # GDP: BEA's "Gross Domestic Product" (current-dollar). We label it
    # "US GDP (nominal)" to disambiguate from the real-GDP series GDPC1 —
    # the acronym shares no word-tokens with the spelled-out FRED title,
    # so the overlap heuristic needs this explicit pass.
    "GDP": "US GDP (nominal) = Gross Domestic Product, current dollars (BEA)",
    # A191RL1Q225SBEA: BEA real GDP expressed as % change from the prior
    # quarter (SAAR) — the headline quarterly growth number. FRED's title
    # is just "Real Gross Domestic Product" (the growth aspect lives in the
    # units field), so the YAML's "growth rate" shorthand needs a pass.
    "A191RL1Q225SBEA": "Real GDP growth rate = Real Gross Domestic Product, % change SAAR (BEA)",
    # USSTHPI (pre-existing): FHFA's flagship "All-Transactions House Price
    # Index for the United States." The YAML uses the common short label
    # "FHFA national home price index" — same series, unambiguous.
    "USSTHPI": "FHFA national home price index = All-Transactions House Price Index for the US (FHFA)",
    # MEDCPIM158SFRBCLE: Cleveland Fed's median CPI. FRED's title spells
    # out "Median Consumer Price Index"; we use the universal "Median CPI"
    # shorthand, which shares only the "median" token with the formal title.
    "MEDCPIM158SFRBCLE": "Median CPI = Median Consumer Price Index (Federal Reserve Bank of Cleveland)",
}

# A few normalizations to compare YAML names to FRED titles
# fairly. FRED uses formal NIPA-style titles ("Personal current
# transfer receipts: Government social benefits to persons: Social
# security") while our YAMLs use plain English ("Federal Social
# Security benefits"). These are equivalent — we just need to
# recognize that.
SUFFIX_STRIP = " | FRED | St. Louis Fed"
TITLE_RE = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE)
TITLE_AND_ID_RE = re.compile(r"^(?P<title>.+?)\s*\((?P<sid>[A-Z0-9_]+)\)\s*$")


def normalize(text: str) -> str:
    """Lowercase + collapse whitespace + strip noise words so the
    similarity test isn't tripped by trivial spacing differences."""
    if not text:
        return ""
    s = text.lower()
    s = re.sub(r"[—–\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(text: str) -> set[str]:
    """Word-set view for crude name similarity scoring."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def fetch_fred_title(series_id: str) -> tuple[str | None, str | None]:
    """Returns (display_title, error). display_title is FRED's
    official human label (without the " (SERIES_ID) | FRED ..."
    suffix) or None on failure."""
    url = f"https://fred.stlouisfed.org/series/{series_id}"
    try:
        r = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", "20", url],
            capture_output=True, check=True,  # bytes, not text — FRED pages
            # contain UTF-8 chars that cp1252 (Windows default) can't decode
        )
    except subprocess.CalledProcessError as e:
        return None, f"curl failed (rc={e.returncode})"
    try:
        body = r.stdout.decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return None, f"decode failed: {e}"
    m = TITLE_RE.search(body)
    if not m:
        return None, "no <title> tag found"
    raw = m.group(1).strip()
    raw = raw.replace(SUFFIX_STRIP, "").strip()
    # Strip the parenthesized series ID at the end.
    am = TITLE_AND_ID_RE.match(raw)
    if am:
        title = am.group("title").strip()
        if am.group("sid") != series_id:
            return title, f"title's parenthesized ID ({am.group('sid')}) ≠ requested ({series_id})"
        return title, None
    # Some pages don't have the ID-in-parens form. Treat the
    # whole title as the display.
    return raw, None


def read_all_yamls() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(FRED_DIR.glob("*.yaml")):
        try:
            data = pyyaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"  skipping {p.name}: {e}", file=sys.stderr)
            continue
        series = (data.get("provenance") or {}).get("series", "")
        # Strip any FRED transformation suffix (e.g.
        # "CPIAUCSL (transformation=pc1)") so we audit the
        # underlying series.
        bare = series.split(" ")[0] if series else ""
        out.append({
            "file": p.name,
            "yaml_name": data.get("name", ""),
            "yaml_short_name": data.get("shortName", ""),
            "yaml_description": (data.get("description") or "").strip(),
            "series_id_full": series,
            "series_id": bare,
            "data_file": data.get("dataFile", ""),
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
    ap.add_argument("--strict", action="store_true",
                    help="Exit 1 if any mismatches are reported.")
    ap.add_argument("--no-cache", action="store_true",
                    help="Bypass the cache and re-fetch every series.")
    ap.add_argument("--json", action="store_true",
                    help="Print machine-readable JSON instead of human report.")
    ap.add_argument("--workers", type=int, default=4,
                    help="Concurrent fetches. Default 4.")
    args = ap.parse_args()

    rows = read_all_yamls()
    print(f"Auditing {len(rows)} FRED YAMLs ({len({r['series_id'] for r in rows})} unique series)...",
          file=sys.stderr)

    cache: dict[str, str] = {} if args.no_cache else load_cache()

    unique_ids = sorted({r["series_id"] for r in rows if r["series_id"]})
    to_fetch = [s for s in unique_ids if s not in cache]
    if to_fetch:
        print(f"Fetching {len(to_fetch)} from FRED ({args.workers} workers)...",
              file=sys.stderr)
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch_fred_title, sid): sid for sid in to_fetch}
            for done in cf.as_completed(futures):
                sid = futures[done]
                title, err = done.result()
                if title is None:
                    cache[sid] = f"__error__: {err}"
                else:
                    cache[sid] = title
        save_cache(cache)

    findings: list[dict[str, Any]] = []
    for r in rows:
        sid = r["series_id"]
        fred_title = cache.get(sid, "")
        likely_mismatch = False
        notes: list[str] = []
        if fred_title.startswith("__error__"):
            notes.append(fred_title)
        elif sid in ALLOWLIST:
            # Known-good shorthand; skip the token check.
            notes.append(f"allowlisted: {ALLOWLIST[sid]}")
        else:
            ytoks = tokens(r["yaml_name"]) | tokens(r["yaml_short_name"])
            ftoks = tokens(fred_title)
            # Filter out common words that don't add identifying info.
            STOP = {"of", "the", "and", "to", "for", "in", "us", "u", "s",
                    "by", "from", "all", "rate", "index", "level", "per",
                    "total", "current", "expenditures", "consumption",
                    "payments", "receipts"}
            ytoks -= STOP
            ftoks -= STOP
            overlap = ytoks & ftoks
            shared = len(overlap)
            yaml_only = ytoks - ftoks
            if shared == 0 and (ytoks or ftoks):
                likely_mismatch = True
                notes.append(f"NO token overlap: yaml uses {sorted(ytoks)}, fred uses {sorted(ftoks)}")
            elif shared < 2 and len(ytoks) >= 3 and len(ftoks) >= 3:
                likely_mismatch = True
                notes.append(f"weak overlap ({shared} tokens): yaml={sorted(ytoks)}, fred={sorted(ftoks)}, yaml-only={sorted(yaml_only)}")
        findings.append({
            "file": r["file"],
            "series_id": sid,
            "yaml_name": r["yaml_name"],
            "fred_title": fred_title,
            "likely_mismatch": likely_mismatch,
            "notes": notes,
        })

    mismatches = [f for f in findings if f["likely_mismatch"]]

    if args.json:
        print(json.dumps({
            "total": len(findings),
            "mismatches": len(mismatches),
            "findings": findings,
        }, indent=2))
    else:
        print(f"\nTotal: {len(findings)}  Likely mismatches: {len(mismatches)}\n")
        for f in mismatches:
            print(f"[!] {f['file']}")
            print(f"    series: {f['series_id']}")
            print(f"    yaml:   {f['yaml_name']}")
            print(f"    FRED:   {f['fred_title']}")
            for n in f["notes"]:
                print(f"    note:   {n}")
            print()
        if not mismatches:
            print("OK: No likely mismatches found.")

    if args.strict and mismatches:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
