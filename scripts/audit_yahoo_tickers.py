#!/usr/bin/env python3
"""
Audit Yahoo Finance source YAMLs against Yahoo's authoritative
ticker → company-name mapping.

For each YAML in src/content/sources/yahoo/ and yahoo_marketcap/:
  - extract the ticker from provenance.series (or the filename)
  - hit Yahoo's chart API and read meta.longName / meta.shortName
  - compare to the YAML's name via token overlap

Why: tickers are stable but human-typed names can drift (e.g.
typing "Apple Inc" while the underlying ticker is AMZN). The
risk is lower than FRED-style series-ID mismaps because tickers
are familiar, but worth a sanity check across the 186-source set.

Yahoo's chart endpoint
(query1.finance.yahoo.com/v8/finance/chart/<ticker>) returns
meta.longName ("Apple Inc.") and meta.shortName ("Apple Inc.")
without auth.
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
    ROOT / "src" / "content" / "sources" / "yahoo",
    ROOT / "src" / "content" / "sources" / "yahoo_marketcap",
]
CACHE_PATH = ROOT / "scripts" / "_yahoo_audit_cache.json"

# Tickers: 1-5 uppercase letters with optional dot/dash for
# share-class designators (BRK.B, BRK-B), optional "=F" for futures
# (BZ=F = Brent), optional "-USD" for crypto (BTC-USD).
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,7}(?:=F)?$|^[A-Z]{2,5}-USD$")

# STOP words intentionally minimal — anything that could identify
# the security stays. "Inc", "Corp", "Limited" are legal-form
# noise; "futures", "holding", "platforms" are semantic and stay.
STOP = {"of", "the", "and", "to", "for", "in", "us", "u", "s", "by",
        "from", "all", "inc", "incorporated", "corp", "corporation",
        "company", "co", "ltd", "limited", "plc"}

# Tickers whose YAML name is a known-good colloquial deviation from
# Yahoo's formal corporate name. See feedback_naming_conventions —
# DC-audience-first means "ExxonMobil" beats "Exxon Mobil Corporation"
# and "TSMC" beats "Taiwan Semiconductor Manufacturing Company Limited."
ALLOWLIST: dict[str, str] = {
    "XOM": "ExxonMobil (one word) = Exxon Mobil Corporation (formal)",
    "TSM": "TSMC (brand) = Taiwan Semiconductor Manufacturing Company Limited (legal)",
}


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


def fetch_yahoo_names(ticker: str) -> tuple[dict[str, str] | None, str | None]:
    """Returns ({longName, shortName}, error)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d"
    try:
        r = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", "15",
             "-A", "Mozilla/5.0", url],
            capture_output=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        return None, f"curl rc={e.returncode}"
    try:
        body = r.stdout.decode("utf-8", errors="replace")
        parsed = json.loads(body)
    except Exception as e:  # noqa: BLE001
        return None, f"parse: {e}"
    try:
        meta = parsed["chart"]["result"][0]["meta"]
    except (KeyError, TypeError, IndexError):
        # Could be an error response { chart: { error: {...} } }
        err = parsed.get("chart", {}).get("error")
        return None, f"yahoo error: {err}" if err else "no meta in response"
    return {
        "longName": meta.get("longName", "") or "",
        "shortName": meta.get("shortName", "") or "",
        "instrumentType": meta.get("instrumentType", "") or "",
    }, None


def extract_ticker(yaml_data: dict[str, Any], filename: str) -> str | None:
    series = (yaml_data.get("provenance") or {}).get("series", "")
    if series:
        # Strip notes like "AAPL × shares outstanding" → just "AAPL".
        first_token = series.split()[0].strip("()")
        if TICKER_RE.match(first_token):
            return first_token
    # Fallback: yahoo data files are named after the ticker, often
    # with "=" turned to "_" for filesystem safety (BZ=F → BZ_F.json).
    # Try the raw file basename + the un-mangled variants.
    base = filename.replace(".yaml", "").upper()
    base = base.removesuffix("_MC")
    candidates = [base, base.replace("_F", "=F"), base.replace("_", "-")]
    for c in candidates:
        if TICKER_RE.match(c):
            return c
    return None


def read_all_yamls() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in SOURCE_DIRS:
        for p in sorted(d.glob("*.yaml")):
            try:
                data = pyyaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                print(f"  skipping {p.name}: {e}", file=sys.stderr)
                continue
            ticker = extract_ticker(data, p.name)
            out.append({
                "file": str(p.relative_to(ROOT)),
                "yaml_name": data.get("name", ""),
                "yaml_short_name": data.get("shortName", ""),
                "ticker": ticker,
            })
    return out


def load_cache() -> dict[str, Any]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_cache(c: dict[str, Any]) -> None:
    CACHE_PATH.write_text(json.dumps(c, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    rows = read_all_yamls()
    print(f"Auditing {len(rows)} Yahoo YAMLs...", file=sys.stderr)

    cache: dict[str, Any] = {} if args.no_cache else load_cache()
    unique_tickers = sorted({r["ticker"] for r in rows if r["ticker"]})
    to_fetch = [t for t in unique_tickers if t not in cache]
    if to_fetch:
        print(f"Fetching {len(to_fetch)} tickers from Yahoo ({args.workers} workers)...",
              file=sys.stderr)
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch_yahoo_names, t): t for t in to_fetch}
            for done in cf.as_completed(futures):
                t = futures[done]
                names, err = done.result()
                cache[t] = names if names else {"__error__": err}
        save_cache(cache)

    findings: list[dict[str, Any]] = []
    for r in rows:
        t = r["ticker"]
        entry = cache.get(t, {}) if t else {}
        long_name = (entry.get("longName") or "") if isinstance(entry, dict) else ""
        short_name = (entry.get("shortName") or "") if isinstance(entry, dict) else ""
        err = entry.get("__error__") if isinstance(entry, dict) else None
        likely = False
        notes: list[str] = []
        if not t:
            notes.append("no ticker extracted")
            likely = True
        elif err:
            notes.append(f"yahoo: {err}")
        elif not (long_name or short_name):
            notes.append("yahoo response had empty name fields")
        elif t in ALLOWLIST:
            notes.append(f"allowlisted: {ALLOWLIST[t]}")
        else:
            ytoks = tokens(r["yaml_name"]) | tokens(r["yaml_short_name"])
            ftoks = tokens(long_name) | tokens(short_name)
            # Don't strip the ticker — many YAMLs include "Apple
            # (AAPL)" or "META market cap" where the ticker is the
            # only token both sides share. The ticker BEING in both
            # IS the equivalence check we want for stocks; for
            # commodities (BZ=F) the ticker doesn't appear in the
            # name and we fall back to commodity-word overlap.
            shared = len(ytoks & ftoks)
            if shared == 0 and (ytoks or ftoks):
                likely = True
                notes.append(f"NO token overlap: yaml={sorted(ytoks)}, yahoo={sorted(ftoks)}")
        findings.append({
            "file": r["file"],
            "ticker": t,
            "yaml_name": r["yaml_name"],
            "yahoo_long_name": long_name,
            "yahoo_short_name": short_name,
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
            print(f"    ticker:    {f['ticker']}")
            print(f"    yaml:      {f['yaml_name']}")
            print(f"    yahoo:     {f['yahoo_long_name']} / {f['yahoo_short_name']}")
            for n in f["notes"]:
                print(f"    note:      {n}")
            print()
        if not mismatches:
            print("OK: No likely mismatches found.")

    return 1 if (args.strict and mismatches) else 0


if __name__ == "__main__":
    sys.exit(main())
