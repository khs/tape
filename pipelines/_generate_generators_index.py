"""
Generators index — the catalog the composer's Generators tab reads.

Output: ``public/generators-index.json``

What it does
------------
Walks every source YAML in ``src/content/sources/``, classifies each
by ID pattern (metro / state / country), and groups siblings into
"series templates" — collections of sources that differ only by
geographic entity. For example, the ~50 sources matching
``bls/metro_unemployment_rate_<cbsa>`` collapse into one template
("Metro unemployment rate") whose ``sourceMap`` is
``{cbsa -> source-id}`` for every available MSA.

The composer's Generators tab reads this index to:
  1. List templates the user can pick from (per geo-type)
  2. Show how many entities each template covers
  3. Look up which source ID to use for each chosen entity at
     dashboard-generation time

Idempotent and fast (~few seconds even on a 20k-source library).
Runs locally via ``python pipelines/_generate_generators_index.py``;
also wired into the data-refresh workflows so the index ships fresh
with each data update.

Why a static catalog and not runtime discovery?
- Avoids ~20k YAML loads in the browser on tab open.
- Library.json is already big; another tab-specific subset shipped
  separately keeps both files focused.
- The Generators tab needs entity-name lookups (CBSA -> "New York-..."
  etc.) and region presets; baking those into the index keeps the
  composer code simple.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT / "src" / "content" / "sources"
CROSSWALKS = ROOT / "pipelines" / "_crosswalks"
OUT_PATH = ROOT / "public" / "generators-index.json"


# ---------------------------------------------------------------------
# Geographic-entity catalogs
# ---------------------------------------------------------------------

# CBSA codes + names from the existing metro-pipeline crosswalk. Used
# both for entity labels in the index and for Zillow slug → CBSA
# canonicalization below.
def load_cbsa_labels() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    path = CROSSWALKS / "cbsa_metro.csv"
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["cbsa_code"]] = {
                "short": row.get("short_name", row["cbsa_code"]),
                "name": row.get("name", row["cbsa_code"]),
                "states": row.get("states", ""),
            }
    return out


CBSA_LABELS = load_cbsa_labels()


# Country slug → label table. Built once at import time by reading
# worldbank_extended/population_*.yaml — those files exist for every
# country we cover (sovereigns + regional aggregates) and carry the
# proper human label in `name` ("Total population — United Arab
# Emirates") and `shortName` ("United Arab Emirates population"). We
# extract just the country fragment from both.
#
# Why a discovered table instead of a hand-maintained constant: keeps
# the labels in sync with the YAML source of truth whenever new
# countries are added. The pre-fix code title-cased the slug directly
# ("uae" -> "Uae", "uk" -> "Uk", "hong_kong" -> "Hong Kong" only by
# accident); reading the YAMLs avoids that whole class of bug. Hand
# overrides for slugs WITHOUT a population_*.yaml live in
# COUNTRY_LABEL_OVERRIDES below.
def load_country_labels() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    pop_dir = SOURCES_DIR / "worldbank_extended"
    if not pop_dir.exists():
        return out
    for path in sorted(pop_dir.glob("population_*.yaml")):
        slug = path.stem[len("population_"):]
        try:
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(spec, dict):
            continue
        # name format: "Total population — United Arab Emirates"
        name = str(spec.get("name") or "").strip()
        label = ""
        if " — " in name:
            label = name.split(" — ", 1)[1].strip()
        # shortName format: "United Arab Emirates population"
        short = str(spec.get("shortName") or "").strip()
        if short.endswith(" population"):
            short = short[: -len(" population")].strip()
        if not label:
            label = short or slug.replace("_", " ").title()
        if not short:
            short = label
        out[slug] = {"short": short, "name": label}
    return out


COUNTRY_LABELS = load_country_labels()

# Slugs sorted longest first — used by _match_country_wb_ext to pick
# the longest matching suffix (so "south_korea" beats "korea" and
# "europe_eu" doesn't collapse to "eu").
COUNTRY_SLUGS_BY_LEN = sorted(COUNTRY_LABELS.keys(), key=len, reverse=True)

# Hand overrides for slugs that don't appear in worldbank_extended
# population data — the smaller "countries" / "countries_gdp" /
# "worldbank_gdp_raw" pipelines use abbreviations that title-case
# poorly ("usa" -> "Usa", "uk" -> "Uk") even though the full
# worldbank_extended set has them right. We mirror the worldbank
# spellings here so the user sees one consistent label everywhere.
COUNTRY_LABEL_OVERRIDES: dict[str, dict[str, str]] = {
    "usa": {"short": "United States", "name": "United States"},
    # The slugs below are mostly redundant with COUNTRY_LABELS (their
    # worldbank_extended population YAML exists), but listing them here
    # makes the canonical capitalization survive even if a future YAML
    # rename / removal would otherwise demote them to title-cased
    # fallbacks like "Uk", "Uae", "Eu".
    "uk": {"short": "United Kingdom", "name": "United Kingdom"},
    "uae": {"short": "United Arab Emirates", "name": "United Arab Emirates"},
    "eu": {"short": "European Union", "name": "European Union"},
    "mena": {"short": "MENA", "name": "Middle East and North Africa"},
    "ssf": {"short": "Sub-Saharan Africa", "name": "Sub-Saharan Africa"},
    "latam": {"short": "Latin America & Caribbean", "name": "Latin America & Caribbean"},
    "world": {"short": "World", "name": "World (all regions)"},
}

STATE_ABBR_TO_NAME: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida",
    "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky",
    "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

# Census Bureau region groupings — used as MSA + State preset filters.
STATE_REGIONS: dict[str, list[str]] = {
    "northeast": [
        "CT", "ME", "MA", "NH", "NJ", "NY", "PA", "RI", "VT",
    ],
    "midwest": [
        "IL", "IN", "IA", "KS", "MI", "MN", "MO", "NE", "ND",
        "OH", "SD", "WI",
    ],
    "south": [
        "AL", "AR", "DE", "DC", "FL", "GA", "KY", "LA", "MD",
        "MS", "NC", "OK", "SC", "TN", "TX", "VA", "WV",
    ],
    "west": [
        "AK", "AZ", "CA", "CO", "HI", "ID", "MT", "NV", "NM",
        "OR", "UT", "WA", "WY",
    ],
}
REGION_LABELS = {
    "northeast": "Northeast", "midwest": "Midwest",
    "south": "South", "west": "West",
}

# Zillow's per-metro slugs → 5-digit CBSA. Keeping this in sync with
# pipelines/_generate_zillow_sources.py.ZILLOW_SLUG_TO_CBSA — single
# source of truth would be nice but the duplication is small and the
# two scripts have different concerns.
ZILLOW_SLUG_TO_CBSA: dict[str, str] = {
    "nyc": "35620", "la": "31080", "chicago": "16980", "dallas": "19100",
    "houston": "26420", "dc": "47900", "philadelphia": "37980",
    "miami": "33100", "atlanta": "12060", "boston": "14460",
    "sf": "41860", "seattle": "42660",
}


# ---------------------------------------------------------------------
# Source-ID pattern matchers
# ---------------------------------------------------------------------

# Each matcher returns (geo_type, template_key, entity_code) when the
# source ID matches its pattern, else None. The first successful
# matcher wins.
MatchResult = tuple[str, str, str] | None
Matcher = Callable[[str], MatchResult]


def _match_metro_usaspending(sid: str) -> MatchResult:
    m = re.match(r"^usaspending/metro_(\d{5})$", sid)
    if not m:
        return None
    return ("metro", "usaspending_metro_spending", m.group(1))


def _match_metro_bls(sid: str) -> MatchResult:
    m = re.match(r"^bls/metro_(.+)_(\d{5})$", sid)
    if not m:
        return None
    return ("metro", f"bls_metro_{m.group(1)}", m.group(2))


def _match_metro_acs(sid: str) -> MatchResult:
    m = re.match(r"^acs_metro/(.+)_(\d{5})$", sid)
    if not m:
        return None
    return ("metro", f"acs_metro_{m.group(1)}", m.group(2))


def _match_metro_zillow(sid: str) -> MatchResult:
    m = re.match(r"^zillow/(zhvi|zori)_([a-z]+)$", sid)
    if not m:
        return None
    cbsa = ZILLOW_SLUG_TO_CBSA.get(m.group(2))
    if not cbsa:
        return None
    return ("metro", f"zillow_{m.group(1)}", cbsa)


def _match_state_acs(sid: str) -> MatchResult:
    m = re.match(r"^acs_state/(.+)_([a-z]{2})$", sid)
    if not m:
        return None
    abbr = m.group(2).upper()
    if abbr not in STATE_ABBR_TO_NAME:
        return None
    return ("state", f"acs_state_{m.group(1)}", abbr)


def _match_state_fred(sid: str) -> MatchResult:
    m = re.match(r"^fred/state_(.+)_([a-z]{2})$", sid)
    if not m:
        return None
    abbr = m.group(2).upper()
    if abbr not in STATE_ABBR_TO_NAME:
        return None
    return ("state", f"fred_state_{m.group(1)}", abbr)


def _match_state_bls(sid: str) -> MatchResult:
    m = re.match(r"^bls/state_(.+)_([a-z]{2})$", sid)
    if not m:
        return None
    abbr = m.group(2).upper()
    if abbr not in STATE_ABBR_TO_NAME:
        return None
    return ("state", f"bls_state_{m.group(1)}", abbr)


def _match_state_usgs_water(sid: str) -> MatchResult:
    # usgs_water/<sector>_<state>, e.g. usgs_water/public_supply_al.
    # The "_us" national rollups fail the STATE_ABBR_TO_NAME check and
    # drop out — they're not per-state series.
    m = re.match(r"^usgs_water/(.+)_([a-z]{2})$", sid)
    if not m:
        return None
    abbr = m.group(2).upper()
    if abbr not in STATE_ABBR_TO_NAME:
        return None
    return ("state", f"usgs_water_{m.group(1)}", abbr)


def _match_state_usda_nass(sid: str) -> MatchResult:
    # usda_nass/<crop>_<metric>_<state>, e.g. usda_nass/corn_price_ia,
    # usda_nass/wheat_yield_wy. National "_us" rollups drop out via the
    # STATE_ABBR_TO_NAME guard.
    m = re.match(r"^usda_nass/(.+)_([a-z]{2})$", sid)
    if not m:
        return None
    abbr = m.group(2).upper()
    if abbr not in STATE_ABBR_TO_NAME:
        return None
    return ("state", f"usda_nass_{m.group(1)}", abbr)


def _match_country_wb_gdp(sid: str) -> MatchResult:
    m = re.match(r"^worldbank_gdp_raw/([a-z_]+)$", sid)
    if not m:
        return None
    return ("country", "worldbank_gdp_raw", m.group(1))


def _match_country_wb_ext(sid: str) -> MatchResult:
    """Match worldbank_extended/<series>_<country>. The country slug
    can contain underscores ("hong_kong", "costa_rica", "europe_eu"),
    so a regex split would slice off the last underscore-separated
    fragment and call that the country — corrupting multi-word slugs
    into "kong", "rica", "eu" etc. (commit pre-fix shipped exactly
    those bugs to prod). Instead, walk the canonical slug list
    (built once from population_*.yaml at import time) and pick the
    longest one that matches as a suffix of the source-id tail."""
    if not sid.startswith("worldbank_extended/"):
        return None
    rest = sid[len("worldbank_extended/"):]
    for slug in COUNTRY_SLUGS_BY_LEN:
        if rest.endswith("_" + slug):
            series = rest[: -len(slug) - 1]
            return ("country", f"worldbank_extended_{series}", slug)
        if rest == slug:
            return ("country", "worldbank_extended_", slug)
    return None


def _match_country_countries_gdp(sid: str) -> MatchResult:
    m = re.match(r"^countries_gdp/([a-z_]+)$", sid)
    if not m:
        return None
    return ("country", "countries_gdp", m.group(1))


def _match_country_countries(sid: str) -> MatchResult:
    m = re.match(r"^countries/([a-z_]+)$", sid)
    if not m:
        return None
    return ("country", "countries_equity_ratio", m.group(1))


MATCHERS: list[Matcher] = [
    _match_metro_usaspending,
    _match_metro_bls,
    _match_metro_acs,
    _match_metro_zillow,
    _match_state_acs,
    _match_state_fred,
    _match_state_bls,
    _match_state_usgs_water,
    _match_state_usda_nass,
    _match_country_wb_gdp,
    _match_country_wb_ext,
    _match_country_countries_gdp,
    _match_country_countries,
]


def classify_source(source_id: str) -> MatchResult:
    """Return the (geo_type, template_key, entity_code) the source ID
    belongs to — or None if it's not a per-entity series we recognize."""
    for m in MATCHERS:
        r = m(source_id)
        if r is not None:
            return r
    return None


# ---------------------------------------------------------------------
# Template-label cleanup
# ---------------------------------------------------------------------

def _entity_label_candidates(geo: str, entity: str) -> list[str]:
    """Possible human names for the entity referenced by a sample
    source. We use these to detect + strip the geo fragment from the
    source's full name."""
    candidates: list[str] = []
    if geo == "metro":
        meta = CBSA_LABELS.get(entity, {})
        if meta.get("short"):
            candidates.append(meta["short"])
        if meta.get("name"):
            # "Abilene, TX" — also try just "Abilene".
            full = meta["name"]
            candidates.append(full)
            if "," in full:
                candidates.append(full.split(",", 1)[0].strip())
    elif geo == "state":
        if entity in STATE_ABBR_TO_NAME:
            candidates.append(STATE_ABBR_TO_NAME[entity])
            candidates.append(entity)  # 2-letter abbr also gets used
    elif geo == "country":
        # Title-cased slug works for single-word countries ("australia"
        # -> "Australia") but fails on slugs whose canonical spelling
        # differs from a naïve title-case ("africa_ssf" -> "Africa Ssf"
        # vs canonical "Sub-Saharan Africa", "europe_eu" -> "Europe Eu"
        # vs canonical "European Union", "turkiye" -> "Turkiye" vs
        # canonical "Türkiye"). Pull the canonical labels from
        # COUNTRY_LABELS / COUNTRY_LABEL_OVERRIDES so the stripper sees
        # the SAME spelling the YAML uses in its name field.
        canonical = (
            COUNTRY_LABEL_OVERRIDES.get(entity)
            or COUNTRY_LABELS.get(entity)
            or {}
        )
        if canonical.get("name"):
            candidates.append(canonical["name"])
        if canonical.get("short") and canonical["short"] != canonical.get("name"):
            candidates.append(canonical["short"])
        candidates.append(entity.replace("_", " ").title())
        candidates.append(entity.replace("_", " "))
    # Dedupe while preserving order.
    seen = set()
    out: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def clean_template_description(
    raw_desc: str, geo: str, entity: str,
) -> str:
    """Strip entity-specific phrases out of a sibling YAML's description
    so the captured text reads as a template description (applies to all
    siblings) rather than an Abilene-specific or AK-specific one.

    Patterns we handle, in priority order:
      1. ``(CBSA NNNNN, OMB-defined)`` and ``(CBSA NNNNN)`` → strip
      2. ``in/for the <Metro> metropolitan statistical area`` →
         ``in/for the selected metro``
      3. ``for <STATE_ABBR> (statewide)`` →
         ``for the selected state (statewide)``
      4. ``for <Country>, annual`` → ``for the selected country, annual``
      5. Sentences like ``AK has a single congressional district, so…``
         are dropped entirely — they're an entity-specific aside that
         doesn't apply to other states.
      6. Any remaining bare entity-name occurrence → ``the selected <geo>``

    The cleanser is intentionally aggressive; an over-clean description
    is fine ("the selected state has..." reads slightly awkward but is
    accurate) whereas leaving "Abilene" in a template that applies to
    387 metros is wrong.
    """
    text = raw_desc.strip()
    cands = _entity_label_candidates(geo, entity)
    # Dedupe + longest-first so we match "New York-Newark-Jersey City"
    # before "New York".
    cands_sorted = sorted(
        {c for c in cands if c and len(c) >= 2},
        key=len, reverse=True,
    )

    geo_phrase = {
        "metro": "the selected metro",
        "state": "the selected state",
        "country": "the selected country",
    }.get(geo, "the selected entity")

    # 1. CBSA codes
    text = re.sub(r"\s*\(CBSA\s+\d+(?:,\s*OMB-defined)?\)", "", text)

    # 2. Metro-area phrasing: "in/for the X metropolitan statistical area"
    # The non-greedy match stops at " metropolitan statistical area" so
    # multi-word metro names like "Dallas-Fort Worth-Arlington" collapse.
    text = re.sub(
        r"\b(in|for)\s+the\s+[^.]*?\s+metropolitan\s+statistical\s+area\b",
        rf"\1 {geo_phrase}",
        text, flags=re.IGNORECASE,
    )

    # 3. State "(statewide)" pattern. Catches "for AK (statewide)",
    # "for AK statewide", and the rare "for AK (state-level)".
    text = re.sub(
        r"\bfor\s+[A-Z]{2}\s+\(statewide\)",
        f"for {geo_phrase} (statewide)",
        text,
    )
    text = re.sub(
        r"\bfor\s+[A-Z]{2}\s+statewide\b",
        f"for {geo_phrase} statewide",
        text,
    )

    # 5. Entity-specific asides — drop the full sentence. Detect by
    # patterns like "AK has a single congressional district" or
    # "Connecticut's eight planning regions...".
    text = re.sub(
        r"(?:^|(?<=[.!?\s]))\s*[A-Z]{2}(?:'s)?\s+(?:has|have)\s+[^.!?]*?(?:district|districts|region|regions)[^.!?]*?[.!?]",
        " ",
        text,
    )
    # Also catch full-state-name versions ("Alaska has a single...").
    for cand in cands_sorted:
        # Only run on multi-word candidates — single-letter ones produce
        # too many false positives.
        if len(cand) < 4:
            continue
        text = re.sub(
            rf"(?:^|(?<=[.!?\s]))\s*{re.escape(cand)}(?:'s)?\s+(?:has|have)\s+[^.!?]*?(?:district|districts|region|regions)[^.!?]*?[.!?]",
            " ",
            text,
        )

    # 4 + 6. Replace bare entity-name occurrences. Country case usually
    # appears as "for Australia, annual" so we run a targeted pass first.
    for cand in cands_sorted:
        text = re.sub(
            rf"\bfor\s+{re.escape(cand)}(?=[,.\s])",
            f"for {geo_phrase}",
            text,
        )
    for cand in cands_sorted:
        # Final pass for any standalone occurrence — only replace
        # candidates that are at least 3 chars long to avoid clobbering
        # common 2-letter sequences inside other words.
        if len(cand) < 3:
            continue
        text = re.sub(
            rf"\b{re.escape(cand)}\b",
            geo_phrase,
            text,
        )

    # Cleanup: collapse whitespace, fix "the the selected" if it crept in.
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\bthe\s+the\s+selected\b", "the selected", text)
    # Dedupe consecutive identical sentences (rare but possible after
    # the dropping step).
    text = re.sub(r"\.\s*\.", ".", text)

    # Cap length, prefer to break at a sentence boundary near 280.
    if len(text) > 280:
        cut = text[:280].rsplit(".", 1)[0]
        text = (cut + ".") if cut else text[:280]

    return text


def clean_template_label(
    raw_name: str, geo: str, entity: str,
) -> str:
    """Yield the series label by stripping the entity-specific bits
    from a single sibling's name.

    YAML conventions in this repo vary by pipeline:
      ``<entity> — <series>``           (BLS metro / state)
      ``<series> — <entity>``           (ACS metro)
      ``<entity> <series>``             (BLS state, no separator)
      ``Federal spending — <entity>``   (USAspending metro)

    We try em-dash splits first, picking whichever half DOESN'T match
    the entity. If there's no dash, fall back to stripping a leading
    or trailing entity-name match.
    """
    name = raw_name.strip()
    cands = _entity_label_candidates(geo, entity)

    def matches_entity(s: str) -> bool:
        sl = s.lower().strip()
        for c in cands:
            cl = c.lower()
            if not cl:
                continue
            # Short candidates (≤3 chars — state abbreviations, mostly)
            # MUST match at a word boundary, or "al" matches "total",
            # "in" matches "income", etc. — and any series whose
            # description starts with a common verb gets mis-classified
            # as the entity. The whole-string equality case is also
            # accepted because that's the canonical "the tail is JUST
            # the entity" pattern (e.g. "Median age — AL" -> tail "AL").
            if len(cl) <= 3:
                if sl == cl:
                    return True
                if re.search(rf"\b{re.escape(cl)}\b", sl):
                    return True
                continue
            if cl in sl or sl in cl:
                return True
        return False

    for sep in [" — ", " - ", " – "]:
        if sep in name:
            head, tail = name.split(sep, 1)
            if matches_entity(head):
                return tail.strip()
            if matches_entity(tail):
                return head.strip()
            # Neither half matched the entity — keep the longer half
            # (the geo fragment tends to be shorter).
            return (head if len(head) >= len(tail) else tail).strip()

    # No separator. Try stripping a leading entity name token.
    for c in cands:
        if not c:
            continue
        prefix = c + " "
        if name.lower().startswith(prefix.lower()):
            return name[len(prefix):].strip()
        # Also try trailing.
        suffix = " " + c
        if name.lower().endswith(suffix.lower()):
            return name[: -len(suffix)].strip()
        if name.lower().endswith(" " + c.lower() + ","):
            return name[: -(len(c) + 2)].strip()
    return name


# ---------------------------------------------------------------------
# YAML loading + scanning
# ---------------------------------------------------------------------

def load_yaml_quiet(path: Path) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except yaml.YAMLError:
        return None


def source_id_for(path: Path) -> str:
    """Convert ``src/content/sources/<rest>.yaml`` into the source ID
    used by library.json (forward-slash separated, no extension)."""
    rel = path.relative_to(SOURCES_DIR).with_suffix("")
    return rel.as_posix()


# Aggregate type used during scanning.
class TemplateAccum:
    __slots__ = ("name", "description", "tags", "source_map")

    def __init__(self) -> None:
        self.name: str | None = None
        self.description: str | None = None
        self.tags: set[str] = set()
        self.source_map: dict[str, str] = {}


# ---------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------

def scan_sources() -> dict[str, dict[str, TemplateAccum]]:
    """Walk every source YAML and bucket into templates."""
    by_geo: dict[str, dict[str, TemplateAccum]] = {
        "metro": defaultdict(TemplateAccum),
        "state": defaultdict(TemplateAccum),
        "country": defaultdict(TemplateAccum),
    }
    for path in SOURCES_DIR.rglob("*.yaml"):
        sid = source_id_for(path)
        m = classify_source(sid)
        if not m:
            continue
        geo, tkey, entity = m
        spec = load_yaml_quiet(path)
        if not spec:
            continue
        bucket = by_geo[geo][tkey]
        # Stash entity → source-id
        bucket.source_map[entity] = sid
        # Capture label/description/tags from the first sibling we see;
        # subsequent siblings won't overwrite (they should all describe
        # the same series anyway).
        if bucket.name is None:
            raw_name = spec.get("name") or sid
            bucket.name = clean_template_label(raw_name, geo, entity)
        if bucket.description is None and spec.get("description"):
            # Description capture: rewrite the first sibling's
            # description so the entity-specific phrases ("Abilene...",
            # "for AK (statewide)", "for Australia, annual") get
            # generalized. Without this the template's description
            # leaks whichever entity sorted first.
            bucket.description = clean_template_description(
                str(spec["description"]), geo, entity,
            )
        for t in (spec.get("tags") or []):
            t = str(t)
            # Drop entity-specific synthetic tags so the union stays
            # geo-agnostic (metro:35620 etc. belong to a single sibling).
            if t.startswith("metro:") or t.startswith("country-specific:"):
                continue
            if t in ("metro", "us-state", "country-specific"):
                continue
            bucket.tags.add(t)
    return by_geo


# ---------------------------------------------------------------------
# Output building
# ---------------------------------------------------------------------

def build_metro_entities(used: set[str]) -> dict[str, dict[str, Any]]:
    """Limit the CBSA catalog to MSAs that actually appear as a source.
    Also attaches `pop` (latest CBSA total population) so the composer's
    sort-by-population control has the data it needs."""
    pops = load_metro_populations()
    out: dict[str, dict[str, Any]] = {}
    for code, meta in CBSA_LABELS.items():
        if code not in used:
            continue
        entry: dict[str, Any] = {"short": meta["short"], "name": meta["name"]}
        pop = pops.get(code)
        if pop is not None:
            entry["pop"] = pop
        out[code] = entry
    return out


def load_metro_populations() -> dict[str, float]:
    """Latest CBSA total population, keyed by CBSA code. Reads
    public/data/acs_metro/population_<cbsa>.json. The pipeline writes
    those files for every metro the ACS API publishes a B01003 row
    for. Misses are silent."""
    out: dict[str, float] = {}
    metro_data = ROOT / "public" / "data" / "acs_metro"
    if not metro_data.exists():
        return out
    for path in metro_data.glob("population_*.json"):
        if path.name.endswith(".summary.json"):
            continue
        cbsa = path.stem[len("population_"):]
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        points = doc.get("points") or []
        if not points:
            continue
        v = points[-1].get("v")
        if isinstance(v, (int, float)):
            out[cbsa] = float(v)
    return out


def build_metro_presets(entities: dict[str, dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Region presets for the MSA picker. Region = first state listed
    in cbsa_metro.csv's `states` column. Plus a Zillow-top-12 preset."""
    out: dict[str, dict[str, Any]] = {}
    # Top 12 — the Zillow set, by descending market notoriety.
    top12 = ["35620", "31080", "16980", "19100", "26420", "47900",
             "37980", "33100", "12060", "14460", "41860", "42660"]
    top12_present = [c for c in top12 if c in entities]
    if top12_present:
        out["top12"] = {
            "label": "Top 12 (NY / LA / Chicago / ...)",
            "codes": top12_present,
            # total = canonical group size (12), preserved as a separate
            # field so the renderer shows e.g. "Top 12 (10/12)" when an
            # indicator only covers 10 of the canonical 12 metros — vs
            # "Top 12 (10/10)" which would mis-suggest full coverage.
            "total": len(top12),
        }
    # Regional presets: bucket every CBSA whose primary state is in the
    # region group.
    cbsa_region: dict[str, str] = {}
    for code in entities:
        cbsa = CBSA_LABELS.get(code, {})
        # primary state is the first abbr in "states" column (pipe-delim).
        first = (cbsa.get("states") or "").split("|", 1)[0].strip().upper()
        for region, abbrs in STATE_REGIONS.items():
            if first in abbrs:
                cbsa_region[code] = region
                break
    for region, label in REGION_LABELS.items():
        codes = sorted([c for c, r in cbsa_region.items() if r == region])
        if codes:
            out[region] = {"label": label, "codes": codes}
    return out


def build_state_entities(used: set[str]) -> dict[str, dict[str, Any]]:
    pops = load_state_populations()
    out: dict[str, dict[str, Any]] = {}
    for abbr in sorted(used):
        if abbr not in STATE_ABBR_TO_NAME:
            continue
        entry: dict[str, Any] = {"short": abbr, "name": STATE_ABBR_TO_NAME[abbr]}
        pop = pops.get(abbr)
        if pop is not None:
            entry["pop"] = pop
        out[abbr] = entry
    return out


def load_state_populations() -> dict[str, float]:
    """Latest state total population, keyed by 2-letter abbreviation
    (upper-cased to match STATE_ABBR_TO_NAME). Reads
    public/data/acs_state/population_<st>.json — the same files the
    state-atlas + Generators templates already consume."""
    out: dict[str, float] = {}
    state_data = ROOT / "public" / "data" / "acs_state"
    if not state_data.exists():
        return out
    for path in state_data.glob("population_*.json"):
        if path.name.endswith(".summary.json"):
            continue
        st_lower = path.stem[len("population_"):]
        # Snapshot files like population_2022.json (no state slug)
        # land in the same dir — skip them.
        if len(st_lower) != 2:
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        points = doc.get("points") or []
        if not points:
            continue
        v = points[-1].get("v")
        if isinstance(v, (int, float)):
            out[st_lower.upper()] = float(v)
    return out


def build_state_presets(entities: dict[str, dict[str, str]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for region, abbrs in STATE_REGIONS.items():
        codes = [a for a in abbrs if a in entities]
        if codes:
            out[region] = {"label": REGION_LABELS[region], "codes": codes}
    return out


# Country preset groups. Each lists the slugs (matching the
# worldbank_extended file naming convention) that should be included
# in the preset; the build step filters down to the slugs actually
# present in `entities` so a partial dataset doesn't crash. Order in
# the source list determines the order codes appear in the generated
# chart — kept rough-by-importance (USA first for G7 / G20 / Anglos,
# China first for BRICS, etc.) so the legend reads naturally.
COUNTRY_PRESET_DEFS: list[tuple[str, str, list[str]]] = [
    ("g7", "G7", [
        "usa", "japan", "germany", "uk", "france", "italy", "canada",
    ]),
    ("brics", "BRICS", [
        "china", "india", "brazil", "russia", "south_africa",
    ]),
    ("g20_subset", "G20 (countries)", [
        # G20 = 19 countries + EU. Of the 19, Argentina + Indonesia
        # aren't in our country set today — drop them silently. EU
        # aggregate is the `europe_eu` slug if a reader wants the
        # 20th seat. 17 of 19 still covers most macro comparisons.
        "usa", "china", "japan", "germany", "india", "uk", "france",
        "italy", "brazil", "canada", "russia", "south_korea",
        "australia", "mexico", "turkiye", "saudi_arabia",
        "south_africa",
    ]),
    ("anglosphere", "Anglosphere", [
        "usa", "uk", "canada", "australia", "new_zealand",
    ]),
    ("nordics", "Nordic countries", [
        "norway", "sweden", "finland", "denmark", "iceland",
    ]),
    ("east_asia", "East Asia + SE Asia", [
        "china", "japan", "south_korea", "hong_kong", "singapore",
        "thailand", "philippines",
    ]),
    ("north_america_n3", "North America (USA / Canada / Mexico)", [
        "usa", "canada", "mexico",
    ]),
    ("top_gdp", "Top 10 economies (by GDP)", [
        # 2024 nominal-GDP rankings (IMF April 2025). Held stable
        # year-over-year mostly; small shuffles in the 5-10 band
        # don't change the membership set.
        "usa", "china", "germany", "japan", "india", "uk", "france",
        "italy", "brazil", "canada",
    ]),
    ("top_pop", "Top countries by population", [
        # India + China + US lead unambiguously. Indonesia (NO), Pakistan
        # (NO), Nigeria (NO), Bangladesh (NO), Ethiopia (NO) — not in
        # our country set today — would otherwise round out a true
        # top-10. What's left: India, China, USA, Brazil, Russia, Mexico,
        # Japan, Philippines, in roughly that order.
        "india", "china", "usa", "brazil", "russia", "mexico",
        "japan", "philippines",
    ]),
    ("regional_aggregates", "Regional aggregates", [
        # The 7 World Bank cross-country composites the worldbank_extended
        # pipeline emits — read together they form a continent-level
        # snapshot of the indicator. Useful for "where does region X sit
        # relative to the rest of the world" framings.
        "north_america", "europe_eu", "europe_central_asia",
        "east_asia_pacific", "south_asia", "mena", "latam", "africa_ssf",
    ]),
]


def build_country_presets(entities: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build the country preset dict from COUNTRY_PRESET_DEFS, filtering
    each group's slugs down to the ones actually present in `entities`.
    A group with zero overlap is dropped entirely — the renderer's
    new Preset-radio greying logic then handles the case where every
    group is empty for a given template.

    Each entry carries a `total` = canonical (intent) group size,
    independent of how many members are in the index right now. So
    "BRICS (4/5)" reads as "4 of 5 BRICS countries" even if one of
    the 5 isn't ingested yet — the denominator anchors to the
    well-known group definition, not to our data coverage."""
    out: dict[str, dict[str, Any]] = {}
    for key, label, slugs in COUNTRY_PRESET_DEFS:
        present = [s for s in slugs if s in entities]
        if present:
            out[key] = {
                "label": label,
                "codes": present,
                "total": len(slugs),
            }
    return out


def build_country_entities(used: set[str]) -> dict[str, dict[str, Any]]:
    """Build the country entities block consumed by the composer's
    Generators tab. Each entity carries:
      short  — short display label (chip / column)
      name   — long display label (tooltip / row text)
      pop    — latest known total population (for the sort-by control)
    Label resolution: COUNTRY_LABEL_OVERRIDES wins, then COUNTRY_LABELS
    discovered from population_*.yaml, then title-cased slug as
    fallback.  Population reads the latest point in
    public/data/worldbank_extended/population_<slug>.json."""
    pops = load_country_populations()
    out: dict[str, dict[str, Any]] = {}
    for slug in sorted(used):
        if slug in COUNTRY_LABEL_OVERRIDES:
            labels = COUNTRY_LABEL_OVERRIDES[slug]
        elif slug in COUNTRY_LABELS:
            labels = COUNTRY_LABELS[slug]
        else:
            display = slug.replace("_", " ").title()
            labels = {"short": display, "name": display}
        entry: dict[str, Any] = {"short": labels["short"], "name": labels["name"]}
        pop = pops.get(slug)
        if pop is not None:
            entry["pop"] = pop
        out[slug] = entry
    return out


def load_country_populations() -> dict[str, float]:
    """Latest-point population for each country in worldbank_extended.
    Used to populate the entity's `pop` field so the composer can
    offer a sort-by-population control. Misses are silent — the
    sort UI just treats them as untransformed (alphabetical order).

    Also patches in the USA value from acs_national (since
    worldbank_extended doesn't carry a US national population series —
    the slug "usa" only shows up in worldbank_gdp_raw and countries_gdp,
    neither of which is in the country-population pipeline).
    """
    out: dict[str, float] = {}
    pop_data = ROOT / "public" / "data" / "worldbank_extended"
    if pop_data.exists():
        for path in pop_data.glob("population_*.json"):
            if path.name.endswith(".summary.json"):
                continue
            slug = path.stem[len("population_"):]
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            points = doc.get("points") or []
            if not points:
                continue
            v = points[-1].get("v")
            if isinstance(v, (int, float)):
                out[slug] = float(v)
    # USA fallback from ACS national.
    if "usa" not in out:
        us_path = ROOT / "public" / "data" / "acs_national" / "population_us.json"
        if us_path.exists():
            try:
                doc = json.loads(us_path.read_text(encoding="utf-8"))
                points = doc.get("points") or []
                if points:
                    v = points[-1].get("v")
                    if isinstance(v, (int, float)):
                        out["usa"] = float(v)
            except (OSError, json.JSONDecodeError):
                pass
    return out


def build_templates_block(
    geo: str, templates: dict[str, TemplateAccum],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tkey in sorted(templates.keys()):
        acc = templates[tkey]
        if len(acc.source_map) < 2:
            # A "template" with only one entity isn't useful for
            # mass-compose. Skip the long tail of singleton series
            # (often a pipeline that only ships one geo, like a
            # nation-only economic series misfiled under a per-geo
            # pipeline).
            continue
        out.append({
            "id": tkey,
            "label": acc.name or tkey,
            "description": acc.description or "",
            "tags": sorted(acc.tags),
            "sourceMap": dict(sorted(acc.source_map.items())),
            "count": len(acc.source_map),
        })
    # Sort templates by count (most coverage first), then label.
    out.sort(key=lambda t: (-int(t["count"]), str(t["label"])))
    return out


GEO_LABELS = {
    "metro": "US metro areas (MSA)",
    "state": "US states + DC",
    "country": "Countries",
}


# --------------------------------------------------------------------
# Profile-mode template ordering.
#
# The Generators tab has two modes:
#   * "By indicator" (existing) — one template, many entities.
#   * "Profile"      (new)       — one entity, many templates rendered
#                                  as a coherent profile section.
#
# In profile mode, the order in which tiles appear matters: a reader
# scanning "Virginia profile" should see population first, then income +
# poverty (the headline economic facts), then education, housing, age,
# labor, and so on. The canonical sequence below is hand-curated per
# geo-type. Templates not in the list are appended afterward in
# alphabetical-by-label order so newly-added series still show up
# without breaking the curated head of the list.
PROFILE_ORDER: dict[str, list[str]] = {
    "state": [
        "acs_state_population",
        "acs_state_median_hh_income",
        "bls_state_unemployment",
        "acs_state_poverty_count",
        "acs_state_bachelors_plus",
        "acs_state_masters_plus",
        "acs_state_median_home_value",
        "acs_state_median_gross_rent",
        "acs_state_owner_occupied",
        "acs_state_renter_occupied",
        "acs_state_median_age",
        "acs_state_population_65_plus",
        "acs_state_population_under_18",
        "acs_state_foreign_born",
        "acs_state_veterans",
        "acs_state_broadband_households",
        "acs_state_people_with_disability",
        "acs_state_workers_wfh",
        "acs_state_median_commute_minutes",
        "acs_state_movers_last_year",
        "acs_state_born_same_state",
        "acs_state_households_no_vehicle",
        "bls_state_payrolls",
        "fred_state_population",
    ],
    "metro": [
        "acs_metro_population",
        "usaspending_metro_spending",
        "bls_metro_unemployment",
        "bls_metro_payrolls",
        "zillow_zhvi",
        "zillow_zori",
        "acs_metro_poverty_count",
        "acs_metro_bachelors_plus",
        "acs_metro_masters_plus",
        "acs_metro_foreign_born",
        "acs_metro_median_age",
        "acs_metro_population_65_plus",
        "acs_metro_population_under_18",
        "acs_metro_workers_wfh",
        "acs_metro_median_commute_minutes",
        "acs_metro_movers_last_year",
        "acs_metro_born_same_state",
        "acs_metro_households_no_vehicle",
    ],
    "country": [
        "worldbank_extended_population",
        "worldbank_extended_gdp_current_usd",
        "worldbank_extended_gdp_per_capita_usd",
        "worldbank_gdp_raw",
        "countries_gdp",
        "countries_equity_ratio",
        "worldbank_extended_life_expectancy",
        "worldbank_extended_co2_per_capita",
        "worldbank_extended_co2_total",
        "worldbank_extended_agriculture_pct_gdp",
        "worldbank_extended_industry_pct_gdp",
        "worldbank_extended_manufacturing_pct_gdp",
        "worldbank_extended_services_pct_gdp",
    ],
}


def build_profile_order(geo: str, templates_block: list[dict[str, Any]]) -> list[str]:
    """Reconcile PROFILE_ORDER with what actually exists in templates_block.

    Drops curated IDs that the current scan didn't surface (defensive —
    if a pipeline stops emitting a template, it shouldn't appear in the
    profile preview). Appends any templates not in PROFILE_ORDER at the
    end, sorted by label so new additions slot in deterministically.
    """
    available = {t["id"]: t for t in templates_block}
    seen: set[str] = set()
    ordered: list[str] = []
    for tid in PROFILE_ORDER.get(geo, []):
        if tid in available and tid not in seen:
            ordered.append(tid)
            seen.add(tid)
    extras = sorted(
        (t for t in templates_block if t["id"] not in seen),
        key=lambda t: t.get("label", t["id"]).lower(),
    )
    ordered.extend(t["id"] for t in extras)
    return ordered


def main() -> int:
    by_geo = scan_sources()

    out: dict[str, Any] = {
        "v": 1,
        "lastUpdated": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "geoTypes": {},
    }

    for geo, templates in by_geo.items():
        used_entities: set[str] = set()
        for acc in templates.values():
            used_entities.update(acc.source_map.keys())
        if geo == "metro":
            entities = build_metro_entities(used_entities)
            presets = build_metro_presets(entities)
        elif geo == "state":
            entities = build_state_entities(used_entities)
            presets = build_state_presets(entities)
        else:
            entities = build_country_entities(used_entities)
            presets = build_country_presets(entities)
        templates_block = build_templates_block(geo, templates)
        out["geoTypes"][geo] = {
            "label": GEO_LABELS[geo],
            "entities": entities,
            "presets": presets,
            "templates": templates_block,
            # Canonical template order for profile mode (one entity,
            # many indicators). Used by the composer's Generators tab
            # when the user toggles "Profile" — emits tiles in this
            # order so e.g. "Virginia profile" reads population → income
            # → poverty → education → housing → … without each viewer
            # having to figure out a sensible ordering themselves.
            "profileOrder": build_profile_order(geo, templates_block),
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(out, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    total_templates = sum(len(g["templates"]) for g in out["geoTypes"].values())
    total_sources = sum(
        sum(t["count"] for t in g["templates"])
        for g in out["geoTypes"].values()
    )
    print(
        f"generators-index: {total_templates} templates across "
        f"{len(out['geoTypes'])} geo-types, {total_sources} source IDs "
        f"-> {OUT_PATH.relative_to(ROOT)}"
    )
    for geo, g in out["geoTypes"].items():
        print(
            f"  {geo}: {len(g['templates'])} templates, "
            f"{len(g['entities'])} entities, {len(g['presets'])} presets"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
