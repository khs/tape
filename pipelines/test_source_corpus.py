"""
Corpus-level invariants over src/content/sources/*.yaml.

These don't test a function — they walk every source YAML and check
that the data conforms to a rule we've established in past commits.
Cheap (~tenths of a second over ~10k files) and catches regressions
that a Python-function test wouldn't, like "someone edited a YAML
and now the BLS LAUS URL is back to the program homepage instead
of the series-specific Data Viewer."

Two invariants currently enforced:

  1. BLS provenance URLs land on the SPECIFIC series, not the
     program homepage. Fixed in 50f7338bda (893 YAMLs updated).
     Pre-fix: provenance.url == "https://www.bls.gov/lau/" or
     "https://www.bls.gov/sae/" — no per-series navigation.
     Post-fix: provenance.url == "https://data.bls.gov/timeseries/<id>".
     Test catches any new BLS YAML that uses the old bare URL.

  2. "world" tag stays meaningful — only on regional aggregates,
     forex pairs, cross-country breakdowns (Treasury TIC), and
     world-wide ETFs. Fixed in 543354963e (444 sources de-tagged).
     Pre-fix: every single-country data point (USA, Germany, etc.)
     was tagged "world" by the worldbank_extended pipeline / hand-
     curation, diluting the tag.

Run locally with::

    python -m unittest pipelines.test_source_corpus
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

# Lightweight inline YAML parser for the subset we care about
# (top-level scalar keys + simple lists). The repo's source YAMLs
# follow a fixed shape, so we don't need PyYAML — keeps test deps
# minimal in CI.

ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT / "src" / "content" / "sources"


def parse_yaml_lite(path: Path) -> dict:
    """Return a dict of the YAML's top-level scalar values + a
    `provenance` sub-dict + a `tags` list. Doesn't handle the full
    YAML spec — just enough for source YAMLs in this repo."""
    out: dict = {}
    cur_block: str | None = None
    tags: list[str] = []
    in_tags = False
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.rstrip()
        if not stripped or stripped.startswith("#"):
            continue
        # Top-level key (no leading whitespace).
        if not line.startswith((" ", "\t")):
            if stripped == "provenance:":
                cur_block = "provenance"
                out["provenance"] = {}
                in_tags = False
                continue
            if stripped == "tags:":
                cur_block = None
                in_tags = True
                continue
            if stripped.startswith("formatting:") or stripped.endswith(":"):
                # Nested mapping we don't care about — drop out of
                # any sub-block we were tracking.
                cur_block = None
                in_tags = False
                continue
            in_tags = False
            cur_block = None
            m = re.match(r"^([A-Za-z][A-Za-z0-9_]*):\s*(.*)$", stripped)
            if m:
                out[m.group(1)] = _scalar(m.group(2))
            continue
        # Indented — either a nested mapping value or a list item.
        if in_tags:
            m = re.match(r"^\s+-\s+(\S.*)$", stripped)
            if m:
                tags.append(_scalar(m.group(1)))
            continue
        if cur_block == "provenance":
            m = re.match(r"^\s+([A-Za-z][A-Za-z0-9_]*):\s*(.*)$", stripped)
            if m:
                out["provenance"][m.group(1)] = _scalar(m.group(2))
    out["tags"] = tags
    return out


def _scalar(s: str) -> str:
    """Strip surrounding quotes from a YAML scalar; otherwise return
    the string trimmed. Only handles the simple cases in source YAMLs.
    """
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


# --------------------------------------------------------------------
# Invariant 1: BLS provenance URLs land on the per-series Data Viewer
# --------------------------------------------------------------------

BLS_DATA_VIEWER_PREFIX = "https://data.bls.gov/timeseries/"
# URL patterns the audit FIX replaced — must never reappear.
BLS_BARE_PROGRAM_URLS = {
    "https://www.bls.gov/lau/",
    "https://www.bls.gov/sae/",
}


class BlsProvenanceUrlInvariants(unittest.TestCase):

    def test_no_bare_bls_program_url_resurfaces(self) -> None:
        """No BLS YAML's provenance.url is one of the program homepages
        we replaced in 50f7338bda. Catches a regression where a re-run
        of an older pipeline overwrites the fix."""
        bls_dir = SOURCES_DIR / "bls"
        offenders: list[str] = []
        for path in sorted(bls_dir.glob("*.yaml")):
            data = parse_yaml_lite(path)
            url = data.get("provenance", {}).get("url", "")
            if url in BLS_BARE_PROGRAM_URLS:
                offenders.append(f"{path.name}: {url}")
        self.assertEqual(offenders, [], msg=(
            "BLS YAMLs reverted to bare program-homepage URLs:\n  "
            + "\n  ".join(offenders)
        ))

    def test_bls_yamls_use_data_viewer_when_series_id_present(self) -> None:
        """Every BLS YAML with a provenance.series field should point
        at https://data.bls.gov/timeseries/<series> — the canonical
        per-series Data Viewer. Skips YAMLs without a series ID (the
        few aggregate / program-level entries that legitimately don't
        point at a series), and QCEW (Open Data Access has no per-series
        Data Viewer page — see below)."""
        bls_dir = SOURCES_DIR / "bls"
        offenders: list[str] = []
        for path in sorted(bls_dir.glob("*.yaml")):
            data = parse_yaml_lite(path)
            prov = data.get("provenance", {})
            series = prov.get("series", "")
            url = prov.get("url", "")
            if not series:
                continue
            # QCEW (provider "BLS (QCEW)", pipelines/bls_qcew.py) comes from
            # the Open Data Access CSV endpoint, where a "series" is an
            # area + ownership + industry tuple with no per-series Data
            # Viewer page. Its provenance.series is a human descriptor, not
            # a Public-Data-API timeseries ID, so the data.bls.gov/timeseries
            # invariant can't apply; it cites the QCEW program/methodology
            # home (www.bls.gov/cew/) instead, which is NOT in
            # BLS_BARE_PROGRAM_URLS (that set is the LAUS/CES homes).
            if "QCEW" in prov.get("provider", ""):
                continue
            if not url.startswith(BLS_DATA_VIEWER_PREFIX):
                offenders.append(f"{path.name}: {url}")
            elif url != f"{BLS_DATA_VIEWER_PREFIX}{series}":
                # series ID in the URL doesn't match the series field
                offenders.append(
                    f"{path.name}: url={url} doesn't match series={series}"
                )
        self.assertEqual(offenders, [], msg=(
            f"BLS YAMLs with series IDs but non-canonical URLs (expected "
            f"{BLS_DATA_VIEWER_PREFIX}<series>):\n  "
            + "\n  ".join(offenders)
        ))


# --------------------------------------------------------------------
# Invariant 2: 'world' tag scope
# --------------------------------------------------------------------

# Sources that legitimately carry the "world" tag. The cleanup in
# 543354963e dropped "world" from 444 single-country data points;
# this whitelist captures what's allowed to wear the tag.
#
# Match patterns are partial-path matches against the relative path
# of the YAML under src/content/sources. A source qualifies if any
# pattern in this list is a substring of its rel-path.
ALLOWED_WORLD_TAG_PATH_PATTERNS = (
    # Regional aggregates emitted by worldbank_extended for WB
    # composite regions — every one is a cross-country composite.
    "_africa_ssf",
    "_east_asia_pacific",
    "_europe_central_asia",
    "_europe_eu",
    "_latam",
    "_mena",
    "_north_america",
    "_south_asia",
    # True world aggregate (WB code WLD).
    "worldbank_gdp_raw/world",
    # Treasury TIC — each row is a different foreign country's
    # holdings of US Treasuries; the dataset's whole purpose is
    # the cross-country breakdown.
    "treasury_tic/",
    # Forex pairs in fred + yahoo — cross-currency by construction.
    "fred/cny_usd",
    "fred/eur_usd",
    "fred/gbp_usd",
    "fred/jpy_usd",
    "fred/usd_index",
    "yahoo/eurusd",
    "yahoo/gbpusd",
    "yahoo/usdcad",
    "yahoo/usdcny",
    "yahoo/usdinr",
    "yahoo/usdjpy",
    "yahoo/usdmxn",
    # Multi-country basket ETFs.
    "yahoo/vt.yaml",     # Total World
    "yahoo/vea.yaml",    # Developed Markets
    "yahoo/eem.yaml",    # Emerging Markets
    "yahoo/efa.yaml",    # EAFE (developed ex-US/Canada)
    "yahoo/vwo.yaml",    # FTSE Emerging
)


class WorldTagScopeInvariants(unittest.TestCase):

    def test_world_tag_only_on_known_cross_country_paths(self) -> None:
        """Every source tagged 'world' must match one of the
        ALLOWED_WORLD_TAG_PATH_PATTERNS substrings. New cross-country
        sources should explicitly extend the whitelist — the test
        failing is the signal to do that. Single-country data points
        (USA Industry, Germany CPI, Brazil GDP, ...) must NOT carry
        the tag; the cleanup in 543354963e was the corpus-wide
        de-tagging pass."""
        offenders: list[str] = []
        for path in SOURCES_DIR.rglob("*.yaml"):
            data = parse_yaml_lite(path)
            tags = data.get("tags", []) or []
            if "world" not in tags:
                continue
            rel = path.relative_to(SOURCES_DIR).as_posix()
            if not any(pat in rel for pat in ALLOWED_WORLD_TAG_PATH_PATTERNS):
                offenders.append(rel)
        # Report ALL offenders rather than failing at the first —
        # an audit run wants the full list, not a one-at-a-time
        # rediscovery loop.
        self.assertEqual(offenders, [], msg=(
            "Sources tagged 'world' that don't match any allowed "
            "cross-country pattern (these probably got the tag "
            "mistakenly — verify, then either remove 'world' from "
            "the YAML or extend ALLOWED_WORLD_TAG_PATH_PATTERNS in "
            "this test if the new source IS legitimately cross-"
            "country):\n  "
            + "\n  ".join(sorted(offenders))
        ))


if __name__ == "__main__":
    unittest.main()
