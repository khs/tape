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


def _match_country_wb_gdp(sid: str) -> MatchResult:
    m = re.match(r"^worldbank_gdp_raw/([a-z_]+)$", sid)
    if not m:
        return None
    return ("country", "worldbank_gdp_raw", m.group(1))


def _match_country_wb_ext(sid: str) -> MatchResult:
    m = re.match(r"^worldbank_extended/(.+)_([a-z_]+)$", sid)
    if not m:
        return None
    return ("country", f"worldbank_extended_{m.group(1)}", m.group(2))


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
            if cl and (cl in sl or sl in cl):
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
            # Strip the geo-specific tail of descriptions too; many
            # YAMLs end with "...for New York, NY." or similar. Cap
            # length to keep the index tight.
            desc = str(spec["description"]).strip()
            # Take the first sentence if the description is long.
            if len(desc) > 280:
                cut = desc[:280].rsplit(".", 1)[0]
                desc = cut + "." if cut else desc[:280]
            bucket.description = desc
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

def build_metro_entities(used: set[str]) -> dict[str, dict[str, str]]:
    """Limit the CBSA catalog to MSAs that actually appear as a source."""
    return {
        code: {"short": meta["short"], "name": meta["name"]}
        for code, meta in CBSA_LABELS.items()
        if code in used
    }


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


def build_state_entities(used: set[str]) -> dict[str, dict[str, str]]:
    return {
        abbr: {"short": abbr, "name": STATE_ABBR_TO_NAME[abbr]}
        for abbr in sorted(used)
        if abbr in STATE_ABBR_TO_NAME
    }


def build_state_presets(entities: dict[str, dict[str, str]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for region, abbrs in STATE_REGIONS.items():
        codes = [a for a in abbrs if a in entities]
        if codes:
            out[region] = {"label": REGION_LABELS[region], "codes": codes}
    return out


def build_country_entities(used: set[str]) -> dict[str, dict[str, str]]:
    """Each country's "entity code" is its slug as encoded in source
    IDs (e.g., "united_states", "china"). Surface a human label by
    title-casing + replacing underscores."""
    return {
        slug: {
            "short": slug.replace("_", " ").title(),
            "name": slug.replace("_", " ").title(),
        }
        for slug in sorted(used)
    }


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
            presets = {}
        out["geoTypes"][geo] = {
            "label": GEO_LABELS[geo],
            "entities": entities,
            "presets": presets,
            "templates": build_templates_block(geo, templates),
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
