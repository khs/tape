"""
In-place rewriter that makes source `description` + `provenance.notes`
fields pass pipelines/audit_source_descriptions.py: strips implementation-
leak vocabulary (endpoint / fetched-via / yfinance / recompute / …) and
spells out the domain/fund acronyms that appear in a source's title.

Why in-place (not regenerate): the scaffolding generators never overwrite an
existing YAML, so the committed copy is the authoritative thing we serve.
This edits the raw text — only the `description:` / `notes:` lines change, so
key order and formatting are preserved and the diff stays reviewable.

Idempotent: a file already passing the audit is left untouched, so re-running
is a no-op. After running, `audit_source_descriptions.py --strict` should be
clean. Run:  python pipelines/fix_source_descriptions.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "src" / "content" / "sources"

sys.path.insert(0, str(ROOT / "pipelines"))
from audit_source_descriptions import ACRONYMS  # noqa: E402
import _generate_acs_sources as acs  # noqa: E402

# out_id -> indicator dict, for re-deriving acs_cd descriptions from the
# (now leak-free) template in _generate_acs_sources.description_for.
ACS_BY_ID = {ind["out_id"]: ind for ind in acs.INDICATORS}


# --------------------------------------------------------------------------
# Raw-text scalar replacement (preserves the rest of the file verbatim).
# --------------------------------------------------------------------------
def _emit_line(key: str, value: str, indent: str) -> str:
    """`<indent><key>: <value>` on one line, YAML-quoted as needed."""
    dumped = yaml.safe_dump(
        {key: value}, default_flow_style=False, allow_unicode=True, width=10**9
    ).rstrip("\n")
    return indent + dumped


def replace_scalar(text: str, key: str, new_value: str, indent: str = "") -> str:
    """Replace a scalar field (single-line OR block) with a one-line value.

    Matches the `key:` line plus any more-indented continuation lines (a
    `|`/`>` block body), so it collapses a multi-line scalar to one line.
    """
    # Key line, then any continuation lines of a block/folded scalar: lines
    # indented past `indent`, OR blank/whitespace-only lines (a blank line
    # inside a `|`/folded block is part of it — e.g. cpi_yoy's two-paragraph
    # description). Stops at the next line at the key's indent (the next key).
    pat = re.compile(
        rf"^{re.escape(indent)}{re.escape(key)}:[^\n]*\n"
        rf"(?:{re.escape(indent)}[ \t][^\n]*\n|[ \t]*\n)*",
        re.M,
    )
    if not pat.search(text):
        return text
    return pat.sub(lambda _m: _emit_line(key, new_value, indent) + "\n", text, count=1)


# --------------------------------------------------------------------------
# Acronym expansion — append a compact gloss for any glossary acronym in the
# title not already spelled out in the description. Append (rather than
# inline-substitute) keeps existing sentences intact and avoids nested
# parens like "(% of Gross Domestic Product (GDP))".
# --------------------------------------------------------------------------
# Trailing glossary parenthetical, e.g. "(ETF = exchange-traded fund;
# FTSE = Financial Times Stock Exchange.)". Requires an "=" so non-glossary
# tails like "(Alternative II)" don't match. [^()]* avoids spanning nested
# parens.
_GLOSSARY_RE = re.compile(r"\s*\(([^()]*=[^()]*)\)\s*$")


def reorder_glossary(name: str, desc: str) -> str:
    """Reorder an EXISTING trailing acronym glossary so its entries follow
    first-appearance order in the title. expand_acronyms only ever appends,
    so a glossary written in the wrong order (e.g. "ETF; FTSE" for a title
    that reads "...FTSE...ETF") would otherwise stay wrong forever. Reorders
    in place without consulting the ACRONYMS dict, so entries for acronyms
    not in the dict are preserved. Entries whose acronym isn't in the title
    sort to the end (stable)."""
    m = _GLOSSARY_RE.search(desc)
    if not m:
        return desc
    body = m.group(1).rstrip().rstrip(".")
    entries = [e.strip() for e in body.split(";") if "=" in e]
    if len(entries) < 2:
        return desc  # single entry — nothing to reorder
    def pos(entry: str) -> int:
        acr = entry.split("=", 1)[0].strip()
        mm = re.search(rf"\b{re.escape(acr)}\b", name)
        return mm.start() if mm else len(name) + 1
    ordered = sorted(entries, key=pos)
    if ordered == entries:
        return desc  # already in title order
    head = desc[: m.start()].rstrip()
    sep = " " if head.endswith((".", "!", "?")) else ". "
    return f"{head}{sep}({'; '.join(ordered)}.)"


def expand_acronyms(name: str, desc: str) -> str:
    # First normalize the order of any glossary that's already present.
    desc = reorder_glossary(name, desc)
    missing: list[tuple[int, str, str]] = []
    low = desc.lower()
    for acr, exp in ACRONYMS.items():
        m = re.search(rf"\b{re.escape(acr)}\b", name)
        if m and exp.lower() not in low:
            missing.append((m.start(), acr, exp))
    if not missing:
        return desc
    # Order the glossary by first appearance in the TITLE, not by the
    # ACRONYMS dict order. The reader meets the acronyms left-to-right
    # (e.g. "Vanguard FTSE Developed Markets ETF" → FTSE before ETF), and
    # the earlier term is usually the more specialized one that most needs
    # defining first. A trailing generic ("ETF") is the most familiar and
    # belongs last.
    missing.sort(key=lambda t: t[0])
    gloss = "; ".join(f"{a} = {e}" for _, a, e in missing)
    d = desc.rstrip()
    sep = " " if d.endswith((".", "!", "?")) else ". "
    return f"{d}{sep}({gloss}.)"


# --------------------------------------------------------------------------
# Per-provider description / notes rewriters. Each returns the cleaned value
# (or None for notes when there's nothing to change).
# --------------------------------------------------------------------------
_WB_FFILL_RE = re.compile(
    r"latest observation forward-filled to today; WB data lags by ~1 year",
    re.I,
)

# NAEP descriptions share one template; these exact substrings let us splice
# the full expansion in as flowing prose (rather than leaving a bare acronym
# or a dangling "the … is administered" fragment).
_NAEP_OLD = '. NAEP ("the Nation\'s Report Card", NCES) is administered identically'
_NAEP_NEW = (
    ', from the National Assessment of Educational Progress (NAEP), '
    '"the Nation\'s Report Card" (NCES). Administered identically'
)

# The "this is a (weak) proxy for the UMich consumer-sentiment series we
# don't ingest (copyright)" tail — must never reach a reader: it leaks the
# proxy framing, the word "ingest", and the reason. Strip it wherever it
# appears (handles both "; one of the proxies …" and ". One of the
# public-domain proxies …" forms), leaving a single closing period.
_SENTIMENT_TAIL = re.compile(
    # `public-\s*domain` because the YAML wraps "public-\n  domain", which
    # folds to "public- domain" (hyphen + space) when parsed.
    r"[;.]\s+(?:one|One) of the (?:public-\s*domain )?proxies for the UMich "
    r"consumer-sentiment series \(which we don't ingest, third-party copyright\)\.?"
)

# cpi_yoy's description is bespoke (it carried the original "Fetched via …
# endpoint" leak); pin it to the agreed wording.
_CPI_YOY_DESC = (
    "Year-over-year percent change in the headline Consumer Price Index. "
    "Monthly, available since 1948."
)

# Zillow ZHVI/ZORI descriptions end with an editorial comparison sentence
# (vs Case-Shiller / CPI Shelter) — coverage, cadence, smoothing. Cut from
# that sentence to the end (DOTALL spans the literal-block trailing newline).
_ZILLOW_TAIL = re.compile(
    r"\.\s+(?:Zillow's most-cited|Catches asking-rent).*", re.S
)


def clean_description(provider: str, path: Path, doc: dict, desc: str) -> str:
    name = str(doc.get("name", "") or "")

    # cpi_yoy: pinned wording (overrides everything).
    if provider == "fred" and path.stem == "cpi_yoy":
        return _CPI_YOY_DESC

    if provider == "acs_cd":
        out_id = ((doc.get("provenance") or {}) or {}).get("series")
        ind = ACS_BY_ID.get(out_id)
        if ind:
            slug = path.stem[len(out_id) + 1 :]
            return acs.description_for(ind, slug)
        return desc  # unknown indicator — leave for manual review

    # Strip the sentiment-proxy / "we don't ingest" / copyright tail anywhere.
    desc = _SENTIMENT_TAIL.sub(".", desc)

    if provider == "yahoo_marketcap":
        # "... (yfinance)." -> "...." (the parenthetical names our fetch lib)
        desc = re.sub(r"\s*\(yfinance\)", "", desc)
        return expand_acronyms(name, desc)

    if provider == "naep":
        # Splice the full NAEP expansion in as flowing prose.
        desc = desc.replace(_NAEP_OLD, _NAEP_NEW).replace(
            "Average NAEP scale score", "Average scale score"
        )
        return expand_acronyms(name, desc)

    if provider in ("worldbank_gdp_raw", "countries_gdp", "worldbank_extended"):
        desc = _WB_FFILL_RE.sub(
            "the most recent value is carried forward to the current date; "
            "World Bank data typically lags by about a year",
            desc,
        )
        return expand_acronyms(name, desc)

    if provider == "zillow":
        # Drop the editorial comparison tail (vs Case-Shiller / CPI Shelter:
        # coverage / cadence / smoothing) — a reader looking at the figure
        # wants what it measures, not why it beats alternatives.
        return _ZILLOW_TAIL.sub(".", desc, count=1).strip()

    # Everything else (fred, oecd, yahoo, cbo, ssa, …): acronym expansion only.
    return expand_acronyms(name, desc)


def clean_notes(provider: str, notes: str) -> str | None:
    if provider == "yahoo_marketcap":
        # "Close price × yfinance get_shares_full() forward-filled to daily."
        if "yfinance" in notes or "get_shares_full" in notes or "forward-fill" in notes:
            return "Close price × historical shares outstanding, carried forward to a daily series."
    return None


def main() -> int:
    changed = 0
    scanned = 0
    for path in sorted(SOURCES.glob("**/*.yaml")):
        provider = path.relative_to(SOURCES).parts[0]
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8")
        orig = text

        desc = str(doc.get("description", "") or "")
        if desc:
            new_desc = clean_description(provider, path, doc, desc)
            if new_desc != desc:
                text = replace_scalar(text, "description", new_desc)

        notes = str(((doc.get("provenance") or {}) or {}).get("notes", "") or "")
        if notes:
            new_notes = clean_notes(provider, notes)
            if new_notes and new_notes != notes:
                text = replace_scalar(text, "notes", new_notes, indent="  ")

        # Retire the sentiment-proxy tag — the proxies are too weak to
        # surface as a discoverable category, so drop the list item.
        text = re.sub(r"^[ \t]*-\s*sentiment-proxy[ \t]*\n", "", text, flags=re.M)

        if text != orig:
            path.write_text(text, encoding="utf-8")
            changed += 1

    print(f"Scanned {scanned} source YAMLs; rewrote {changed}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
