"""
Audit user-facing source copy for implementation leaks + undefined acronyms.

Two checks, run over every src/content/sources/**/*.yaml:

1. LEAK CHECK — the `description` and `provenance.notes` fields are shown to
   readers (the source page renders both). They must describe the DATA, not
   how we fetch / derive / store it. Phrases like "Fetched via FRED's
   server-side transformation=pc1 endpoint", "(yfinance)", "diff op", or
   "recompute on the client" are implementation detail that leaks our
   plumbing and — worse — reads like the file is a public, free-to-grab
   document. This check flags that vocabulary.

2. ACRONYM CHECK — if a domain or fund acronym appears in the `name` (title),
   the `description` must spell it out at least once (e.g. a title with "CPI"
   needs "Consumer Price Index" somewhere in the description). Glossary-driven
   on purpose: only the curated economic / agency / fund acronyms below are
   checked, so tickers ("AAPL"), FX-pair codes ("CNY/USD"), state codes
   ("AL-01"), and ordinary all-caps words ("PLUS", "UNDER") are never flagged
   — the title already names those.

Usage:
    python pipelines/audit_source_descriptions.py            # summary report
    python pipelines/audit_source_descriptions.py --list     # every violation
    python pipelines/audit_source_descriptions.py --provider fred
    python pipelines/audit_source_descriptions.py --strict   # exit 1 if any

The GitHub refresh workflows run this with --strict as a gate so a future
pipeline change can't quietly reintroduce leaks. Keep the glossary in sync
when a new provider introduces an acronym in its titles.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT / "src" / "content" / "sources"

# --- Leak vocabulary -------------------------------------------------------
# (compiled regex, human label). Case-insensitive. Tuned to catch fetch /
# storage / derivation mechanics WITHOUT flagging legitimate data prose:
# notably we do NOT flag bare "pipeline" (an oil/gas series can mention a
# literal pipeline) or bare "we".
_LEAK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bendpoint\b", re.I), "endpoint"),
    (re.compile(r"\bfetched\s+(?:via|from)\b", re.I), "fetched via/from"),
    (re.compile(r"\bpulled\s+from\b", re.I), "pulled from"),
    # "ingest"/"ingestion"/"we don't ingest" — how WE load the data, never
    # something a reader needs (and worse when paired with the reason, e.g.
    # "which we don't ingest, third-party copyright").
    (re.compile(r"\bingest", re.I), "ingest"),
    (re.compile(r"transformation\s*=", re.I), "transformation="),
    (re.compile(r"\b(?:server|client)-side\b", re.I), "server/client-side"),
    (re.compile(r"\bon\s+the\s+(?:client|server)\b", re.I), "on the client/server"),
    (re.compile(r"\brecomput", re.I), "recompute"),
    (re.compile(r"\bdiff\s+op\b", re.I), "diff op"),
    (re.compile(r"\bchart-level\b", re.I), "chart-level"),
    (re.compile(r"\byfinance\b", re.I), "yfinance"),
    (re.compile(r"get_shares_full", re.I), "get_shares_full()"),
    (re.compile(r"\bxbrl\b", re.I), "XBRL"),
    (re.compile(r"\bedgar\b", re.I), "EDGAR"),
    (re.compile(r"\bfredgraph\b", re.I), "fredgraph"),
    (re.compile(r"\bforward-fill(?:ed|s)?\b", re.I), "forward-fill"),
    (re.compile(r"\bbackfill(?:ed|s)?\b", re.I), "backfill"),
    (re.compile(r"\bdownsampl", re.I), "downsample"),
    (re.compile(r"\bscrape[ds]?\b", re.I), "scrape"),
    (re.compile(r"\bAPI\b"), "API"),
    (re.compile(r"\.(?:json|csv|parquet|xlsx)\b", re.I), "raw file ref"),
]

# --- Acronym glossary ------------------------------------------------------
# Domain + fund/index acronyms whose expansion must appear in the description
# when the acronym appears in the title. (Per the agreed scope: domain
# acronyms + ETF/fund/index families; tickers and FX codes are self-defining
# from the title and intentionally absent.)
ACRONYMS: dict[str, str] = {
    "GDP": "Gross Domestic Product",
    "GNI": "Gross National Income",
    "GNP": "Gross National Product",
    "CPI": "Consumer Price Index",
    "PCE": "Personal Consumption Expenditures",
    "PPI": "Producer Price Index",
    "NAEP": "National Assessment of Educational Progress",
    "JOLTS": "Job Openings and Labor Turnover Survey",
    "OASDI": "Old-Age, Survivors, and Disability Insurance",
    "TIPS": "Treasury Inflation-Protected Securities",
    "FHFA": "Federal Housing Finance Agency",
    "NBER": "National Bureau of Economic Research",
    "CBO": "Congressional Budget Office",
    "FDI": "Foreign Direct Investment",
    "LCU": "local currency units",
    "SLOOS": "Senior Loan Officer Opinion Survey",
    "ETF": "exchange-traded fund",
    "MSCI": "Morgan Stanley Capital International",
    "FTSE": "Financial Times Stock Exchange",
    "EAFE": "Europe, Australasia, and the Far East",
    "SPDR": "Standard & Poor's Depositary Receipts",
    # NB: DXY is intentionally absent — its only title ("US Dollar Index
    # (DXY)") already spells it out, so requiring a description gloss too
    # would be redundant noise.
}


def find_leaks(text: str) -> list[str]:
    """Return the labels of every leak pattern that matches `text`."""
    if not text:
        return []
    return [label for pat, label in _LEAK_PATTERNS if pat.search(text)]


def undefined_acronyms(name: str, description: str) -> list[str]:
    """Acronyms present in the title but not spelled out in the description."""
    if not name:
        return []
    desc_l = description.lower()
    out: list[str] = []
    for acr, expansion in ACRONYMS.items():
        if re.search(rf"\b{re.escape(acr)}\b", name) and expansion.lower() not in desc_l:
            out.append(acr)
    return out


class Violation:
    __slots__ = ("path", "provider", "kind", "detail")

    def __init__(self, path: Path, provider: str, kind: str, detail: str):
        self.path = path
        self.provider = provider
        self.kind = kind  # "leak-desc" | "leak-notes" | "acronym"
        self.detail = detail


def audit(provider_filter: str | None = None) -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(SOURCES_DIR.glob("**/*.yaml")):
        provider = path.relative_to(SOURCES_DIR).parts[0]
        if provider_filter and provider != provider_filter:
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - report unparseable YAML
            violations.append(Violation(path, provider, "parse-error", str(exc)[:120]))
            continue
        if not isinstance(doc, dict):
            continue
        name = str(doc.get("name", "") or "")
        desc = str(doc.get("description", "") or "")
        notes = str(((doc.get("provenance") or {}) or {}).get("notes", "") or "")

        for label in find_leaks(desc):
            violations.append(Violation(path, provider, "leak-desc", label))
        for label in find_leaks(notes):
            violations.append(Violation(path, provider, "leak-notes", label))
        for acr in undefined_acronyms(name, desc):
            violations.append(Violation(path, provider, "acronym", acr))
    return violations


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print every violation")
    ap.add_argument("--provider", help="restrict to one provider directory")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any violations")
    args = ap.parse_args()

    violations = audit(args.provider)

    # Per-provider, per-kind tally.
    by_prov_kind: dict[str, Counter[str]] = defaultdict(Counter)
    for v in violations:
        by_prov_kind[v.provider][v.kind] += 1

    print("PROVIDER             leak-desc  leak-notes  acronym  parse-err")
    print("-" * 64)
    for prov in sorted(by_prov_kind):
        c = by_prov_kind[prov]
        print(
            f"{prov:18} {c['leak-desc']:10} {c['leak-notes']:11} "
            f"{c['acronym']:8} {c['parse-error']:10}"
        )
    print("-" * 64)
    kinds = Counter(v.kind for v in violations)
    print(
        f"TOTAL: {len(violations)} violations  "
        f"(leak-desc {kinds['leak-desc']}, leak-notes {kinds['leak-notes']}, "
        f"acronym {kinds['acronym']}, parse-error {kinds['parse-error']})"
    )

    # Distinct leak labels + acronyms, for a quick sense of what's wrong.
    leak_labels = Counter(
        v.detail for v in violations if v.kind in ("leak-desc", "leak-notes")
    )
    if leak_labels:
        print("\nLeak terms:", ", ".join(f"{k}×{n}" for k, n in leak_labels.most_common()))
    acr_labels = Counter(v.detail for v in violations if v.kind == "acronym")
    if acr_labels:
        print("Undefined acronyms:", ", ".join(f"{k}×{n}" for k, n in acr_labels.most_common()))

    if args.list:
        print("\n--- violations ---")
        for v in violations:
            rel = v.path.relative_to(ROOT)
            print(f"[{v.kind}] {rel}  ::  {v.detail}")

    if args.strict and violations:
        print(f"\nFAIL: {len(violations)} description-audit violations.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
