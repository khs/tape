"""
Audit FRED-pipeline source YAMLs against the FRED copyright status of
each series. Per FRED's Terms of Use, series come in three buckets:

  - "Copyrighted: Pre-approval required"   → must get permission from
                                              the third-party data
                                              owner before non-personal
                                              use. Most legally risky.
  - "Copyrighted: Citation required"       → OK with attribution +
                                              "via FRED" acknowledgment.
  - "Public Domain: Citation requested"    → OK with attribution.

The script can run in two modes:

  AUTHORITATIVE (with FRED_API_KEY): hits
    https://api.stlouisfed.org/fred/series/tags?series_id=<X> for each
    YAML's series. FRED tags every series with one of the copyright
    statuses above; the script reads that tag and reports.

  HEURISTIC (no key): falls back to a hand-curated table of known
    third-party series IDs (Case-Shiller, S&P 500, VIX, ICE BofA,
    Moody's, MSCI, Wilshire, Conference Board, NFIB, U Mich, Freddie
    Mac PMMS). Useful for a first cut; not authoritative — get a key
    and re-run for the real answer.

Output: a Markdown report at docs/fred-copyright-audit.md grouped by
copyright bucket, with the YAML path, declared provider, declared
license, and (if found) the FRED tag. Each entry includes an action
hint (REMOVE / RE-LICENSE / KEEP / VERIFY).

Run:  python pipelines/audit_fred_copyright.py
Optional env: FRED_API_KEY=<key from https://fred.stlouisfed.org/docs/api/api_key.html>
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "fred"
REPORT_PATH = REPO_ROOT / "docs" / "fred-copyright-audit.md"

# Tag values FRED uses for the three copyright statuses. Match on
# the "name" field (FRED's tag IDs aren't slugs — they're the
# user-visible phrase lowercased verbatim) with group_id == "cc"
# (FRED's "copyright class" tag group). The mapping below covers
# every label observed in the wild as of 2026-05. If FRED ever
# adds a new label the audit will fall through to UNKNOWN and the
# series will surface in that bucket for manual review.
COPYRIGHT_TAG_NAMES: dict[str, str] = {
    "copyrighted: pre-approval required": "PRE-APPROVAL",
    "copyrighted: citation required": "CITATION-REQUIRED",
    "public domain: citation requested": "PUBLIC-DOMAIN",
}

# Hand-curated heuristic table for offline use. Keys are FRED series IDs
# (or ID prefixes — we match both exact and prefix). Values are
# (status, owner, notes).
#
# Sources:
#   - FRED series pages, observed copyright notices.
#   - Public knowledge of which series come from which providers.
#
# This is NECESSARILY incomplete — there are ~841k series on FRED and
# this table covers the well-known third-party indexes. The
# authoritative answer requires the API.
HEURISTIC = {
    # ICE Data Indices (third-party, pre-approval typically required).
    "BAMLC0A0CM": ("PRE-APPROVAL", "ICE BofA / ICE Data Indices", "IG corporate OAS"),
    "BAMLH0A0HYM2": ("PRE-APPROVAL", "ICE BofA / ICE Data Indices", "HY corporate OAS"),
    # S&P Dow Jones Indices (third-party, pre-approval).
    "SP500": ("PRE-APPROVAL", "S&P Dow Jones Indices LLC", "S&P 500 index level"),
    "CSUSHPISA": ("PRE-APPROVAL", "S&P / CoreLogic / Case-Shiller", "National HPI"),
    # Nasdaq, Inc (third-party, pre-approval). My original heuristic
    # missed this — only surfaced after the authoritative API pass.
    "NASDAQCOM": ("PRE-APPROVAL", "Nasdaq, Inc.", "NASDAQ Composite"),
    # CBOE (third-party).
    "VIXCLS": ("PRE-APPROVAL", "Cboe Global Markets / CBOE", "VIX close"),
    # Moody's (third-party).
    "DAAA": ("PRE-APPROVAL", "Moody's Investors Service", "Aaa corporate bond yield"),
    "DBAA": ("PRE-APPROVAL", "Moody's Investors Service", "Baa corporate bond yield"),
    # U. Michigan Consumer Sentiment.
    "UMCSENT": ("PRE-APPROVAL", "University of Michigan", "Consumer sentiment"),
    # Conference Board (third-party).
    "USSLIND": ("PRE-APPROVAL", "Conference Board", "Leading index"),
    # Freddie Mac (GSE; quasi-public but still has its own terms).
    "MORTGAGE15US": ("CITATION-REQUIRED", "Freddie Mac (PMMS)", "15Y mortgage rate"),
    "MORTGAGE30US": ("CITATION-REQUIRED", "Freddie Mac (PMMS)", "30Y mortgage rate"),
    # Federal Reserve Bank of St. Louis own series (public).
    "RECPROUSM156N": ("PUBLIC-DOMAIN", "Federal Reserve Bank of St. Louis", "Smoothed recession prob"),
    # NFIB (third-party).
    "NFIBOPTI": ("PRE-APPROVAL", "NFIB", "Small business optimism"),
}

# Prefix-based heuristic for series families. Any series whose ID
# starts with one of these prefixes inherits the listed status. Only
# matches when the exact-id table above doesn't have an entry first.
HEURISTIC_PREFIXES = [
    ("BAMLC", "PRE-APPROVAL", "ICE BofA / ICE Data Indices", "Corporate bond index family"),
    ("BAMLH", "PRE-APPROVAL", "ICE BofA / ICE Data Indices", "HY corporate bond index family"),
    ("BAMLE", "PRE-APPROVAL", "ICE BofA / ICE Data Indices", "Emerging market bond index family"),
    ("CSXR", "PRE-APPROVAL", "S&P / CoreLogic / Case-Shiller", "Case-Shiller metro HPI"),
    # Public-domain federal-agency families.
    ("CPI", "PUBLIC-DOMAIN", "U.S. Bureau of Labor Statistics", "CPI family"),
    ("CUUR", "PUBLIC-DOMAIN", "U.S. Bureau of Labor Statistics", "CPI-U family"),
    ("CUUS", "PUBLIC-DOMAIN", "U.S. Bureau of Labor Statistics", "CPI-U regional"),
    ("CES", "PUBLIC-DOMAIN", "U.S. Bureau of Labor Statistics", "Establishment survey"),
    ("UNRATE", "PUBLIC-DOMAIN", "U.S. Bureau of Labor Statistics", "Unemployment rate"),
    ("GDP", "PUBLIC-DOMAIN", "U.S. Bureau of Economic Analysis", "GDP family"),
    ("DGS", "PUBLIC-DOMAIN", "U.S. Treasury", "Treasury constant maturity"),
    ("DFII", "PUBLIC-DOMAIN", "U.S. Treasury", "TIPS yield curve"),
    ("FEDFUNDS", "PUBLIC-DOMAIN", "Board of Governors of the Federal Reserve System", "Fed funds rate"),
    ("DFF", "PUBLIC-DOMAIN", "Board of Governors of the Federal Reserve System", "Fed funds daily"),
    ("HOUST", "PUBLIC-DOMAIN", "U.S. Census Bureau", "Housing starts"),
    ("ICSA", "PUBLIC-DOMAIN", "U.S. Employment & Training Administration", "Initial jobless claims"),
    ("CCSA", "PUBLIC-DOMAIN", "U.S. Employment & Training Administration", "Continued jobless claims"),
    ("PAYEMS", "PUBLIC-DOMAIN", "U.S. Bureau of Labor Statistics", "Nonfarm payrolls"),
    ("PCEPI", "PUBLIC-DOMAIN", "U.S. Bureau of Economic Analysis", "PCE price index"),
]


@dataclass
class FredSourceMeta:
    yaml_path: Path
    series_id: Optional[str]
    declared_provider: Optional[str]
    declared_license: Optional[str]
    declared_url: Optional[str]
    # Resolved status fields — populated by either API or heuristic.
    status: str = "UNKNOWN"
    owner: Optional[str] = None
    source: str = "unresolved"  # "api" or "heuristic" or "unresolved"
    notes: list[str] = field(default_factory=list)


def parse_yaml(path: Path) -> FredSourceMeta:
    """Tiny single-purpose YAML reader. We only need top-level + the
    provenance sub-keys, so a regex pass is cheaper than pulling in
    PyYAML for one script. If the YAML structure gets richer, swap
    for PyYAML."""
    text = path.read_text(encoding="utf-8")
    series = re.search(r"^\s+series:\s*(.+)$", text, flags=re.MULTILINE)
    provider = re.search(r"^\s+provider:\s*(.+)$", text, flags=re.MULTILINE)
    license_ = re.search(r"^\s+license:\s*(.+)$", text, flags=re.MULTILINE)
    url = re.search(r"^\s+url:\s*(.+)$", text, flags=re.MULTILINE)
    return FredSourceMeta(
        yaml_path=path,
        series_id=series.group(1).strip().strip('"').strip("'") if series else None,
        declared_provider=provider.group(1).strip().strip('"').strip("'") if provider else None,
        declared_license=license_.group(1).strip().strip('"').strip("'") if license_ else None,
        declared_url=url.group(1).strip().strip('"').strip("'") if url else None,
    )


def heuristic_lookup(series_id: str) -> Optional[tuple[str, str, str]]:
    """(status, owner, notes) from the curated table — exact match
    first, prefix match second. Returns None if nothing matches."""
    if series_id in HEURISTIC:
        return HEURISTIC[series_id]
    for prefix, status, owner, notes in HEURISTIC_PREFIXES:
        if series_id.startswith(prefix):
            return (status, owner, notes)
    return None


def fred_api_lookup(series_id: str, api_key: str) -> Optional[tuple[str, list[str]]]:
    """Hit /fred/series/tags and return (status, copyright_tag_names).
    Returns None on network error / unknown series. The status is
    derived from whichever copyright-class tag (group_id == "cc")
    the series carries."""
    url = (
        f"https://api.stlouisfed.org/fred/series/tags"
        f"?series_id={series_id}&api_key={api_key}&file_type=json"
    )
    try:
        with urlrequest.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        # 400 = series not found; treat as unresolved.
        if e.code in (400, 404):
            return None
        raise
    except (URLError, json.JSONDecodeError):
        return None
    # The "cc" group is FRED's copyright-class tag group. A series
    # almost always carries exactly one cc-group tag; we surface its
    # name back so the report's `notes` column shows the original
    # FRED phrasing rather than just our bucket label.
    cc_names: list[str] = []
    for t in data.get("tags", []):
        if t.get("group_id") == "cc":
            cc_names.append(t.get("name", ""))
    for name in cc_names:
        if name in COPYRIGHT_TAG_NAMES:
            return (COPYRIGHT_TAG_NAMES[name], cc_names)
    # No cc-group tag with a recognized label — return UNKNOWN so
    # the row surfaces for manual review.
    return ("UNKNOWN", cc_names)


def load_env_key() -> Optional[str]:
    """Read FRED_API_KEY from .env if present. We don't import dotenv
    to avoid the dependency; a 5-line parser handles the file fine."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return os.environ.get("FRED_API_KEY")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("FRED_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("FRED_API_KEY")


def run() -> int:
    if not SOURCES_DIR.is_dir():
        print(f"ERROR: {SOURCES_DIR} not found", file=sys.stderr)
        return 1
    api_key = load_env_key()
    metas: list[FredSourceMeta] = []
    for path in sorted(SOURCES_DIR.glob("*.yaml")):
        meta = parse_yaml(path)
        if not meta.series_id:
            meta.notes.append("missing provenance.series in YAML")
            metas.append(meta)
            continue
        # Strip any FRED CSV transformation suffix the YAML might
        # include in the series field (some YAMLs encode it as
        # "CPIAUCSL (transformation=pc1)"). The underlying series is
        # what determines copyright status; the transformation is
        # FRED-side server math.
        bare_id = re.sub(r"\s*\(.*\)$", "", meta.series_id).strip()

        if api_key:
            result = fred_api_lookup(bare_id, api_key)
            time.sleep(0.6)  # well under FRED's 120/min rate limit
            if result:
                status, tag_ids = result
                meta.status = status
                meta.source = "api"
                meta.notes.append(
                    "FRED cc tag: " + (", ".join(tag_ids) or "(none)")
                )
            else:
                meta.notes.append("FRED API returned no data for this series")
                # Fall through to heuristic as a backup.
                h = heuristic_lookup(bare_id)
                if h:
                    meta.status, meta.owner, hn = h
                    meta.source = "heuristic-fallback"
                    meta.notes.append(f"Heuristic: {hn}")
        else:
            h = heuristic_lookup(bare_id)
            if h:
                meta.status, meta.owner, hn = h
                meta.source = "heuristic"
                meta.notes.append(f"Heuristic match: {hn}")
            else:
                # No exact or prefix hit — leave UNKNOWN.
                meta.notes.append("No heuristic match; FRED API key needed")
        metas.append(meta)

    write_report(metas, used_api=bool(api_key))
    print(f"Audit written to {REPORT_PATH.relative_to(REPO_ROOT)}")
    if not api_key:
        print(
            "NOTE: no FRED_API_KEY found. Heuristic mode only.\n"
            "      For authoritative results, register at\n"
            "      https://fred.stlouisfed.org/docs/api/api_key.html\n"
            "      and add FRED_API_KEY=<key> to .env, then re-run."
        )
    return 0


ACTION_HINT = {
    # The default for third-party copyrighted series is REMOVE, not
    # "remove-or-license". Keller's compliance stance (see memory file
    # compliance_fred_no_scraping.md) is to treat FRED's terms as a
    # relationship to honor rather than a legal minimum — licensing
    # third-party data is reserved for series we genuinely can't ship
    # without, and that decision belongs to Keller, not to the audit.
    "PRE-APPROVAL": "REMOVE. (Or: ask Keller before keeping.)",
    "CITATION-REQUIRED": "KEEP. Verify citation reads 'Source: <owner> via FRED'.",
    "PUBLIC-DOMAIN": "KEEP. Verify citation acknowledges the original source.",
    "UNKNOWN": "VERIFY manually on the FRED series page; update YAML or this audit's heuristic table.",
}


def write_report(metas: list[FredSourceMeta], used_api: bool) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    by_status: dict[str, list[FredSourceMeta]] = {
        "PRE-APPROVAL": [],
        "CITATION-REQUIRED": [],
        "PUBLIC-DOMAIN": [],
        "UNKNOWN": [],
    }
    for m in metas:
        by_status.setdefault(m.status, []).append(m)

    lines: list[str] = []
    lines.append("# FRED copyright audit\n")
    lines.append(
        f"Source: {'FRED API + heuristic backup' if used_api else 'HEURISTIC ONLY (no API key)'}.\n"
    )
    lines.append(
        f"Total FRED YAMLs audited: **{len(metas)}**.\n"
    )
    lines.append(
        "Bucket meanings come from FRED's Terms of Use § III:\n"
        "  - `PRE-APPROVAL`: third-party copyrighted; needs licensor "
        "permission for anything beyond personal use.\n"
        "  - `CITATION-REQUIRED`: third-party copyrighted but usable "
        "with proper attribution.\n"
        "  - `PUBLIC-DOMAIN`: usable with citation, no permission needed.\n"
        "  - `UNKNOWN`: status not resolved; verify manually.\n"
    )
    lines.append("")
    for status in ["PRE-APPROVAL", "CITATION-REQUIRED", "PUBLIC-DOMAIN", "UNKNOWN"]:
        bucket = by_status.get(status, [])
        lines.append(f"## {status} ({len(bucket)})\n")
        lines.append(f"**Action**: {ACTION_HINT[status]}\n")
        if not bucket:
            lines.append("_(none)_\n")
            continue
        lines.append(
            "| YAML | Series | Declared provider | Declared license | Owner (resolved) | Source |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- | --- |"
        )
        for m in sorted(bucket, key=lambda x: x.yaml_path.name):
            yaml_rel = m.yaml_path.relative_to(REPO_ROOT).as_posix()
            lines.append(
                f"| `{yaml_rel}` | `{m.series_id}` | "
                f"{m.declared_provider or '—'} | {m.declared_license or '—'} | "
                f"{m.owner or '—'} | {m.source} |"
            )
        lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(run())
