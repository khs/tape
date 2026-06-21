"""US election returns — MIT Election Data + Science Lab (MEDSL), Harvard Dataverse.

All MEDSL returns are CC0 (public domain). They sit behind a REQUIRED Dataverse
guestbook (guestbookID 458): a plain GET of /api/access/datafile/<id> fails even
with an API token. The working non-interactive flow (token in .env as
HDV_API_KEY):
  1. POST /api/access/datafile/<id>[?format=original] with header
     X-Dataverse-key and JSON body {"guestbookResponse": {}} (name/email default
     to the token's account) -> returns {"data": {"signedUrl": "..."}}.
  2. GET that signedUrl -> the file bytes.
File ids change on every dataset version, so we resolve the current id by
filename from the dataset JSON rather than hard-coding it.

Datasets (verified 2026-06):
  president-state  doi:10.7910/DVN/42MVDX  1976-2024  (non-ingested CSV)
  president-county doi:10.7910/DVN/VOQCHQ  2000-2024  (ingested -> ?format=original)
  senate-state     doi:10.7910/DVN/PEJ5QU  1976-2024  (ingested)
  house-cd         doi:10.7910/DVN/IG0UN2  1976-2024  (ingested)

This module currently emits the PRESIDENT two-party MARGIN choropleths (state +
county) as map data the ChartMap renderer joins to the state / county TopoJSON
by GEOID, one file per election year so the dialog's year slider can scrub
1976->2024 (state) and 2000->2024 (county). Margin = (Dem - Rep) / total * 100,
so a red<->blue diverging scale pivots at 0. County totals sum over the `mode`
column (a candidate's county votes are split across election-day / early /
absentee rows); county_fips is numeric and zero-padded to a 5-digit GEOID.

Run: `python pipelines/elections.py president`  (needs HDV_API_KEY).
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import _env  # noqa: F401 — loads .env (HDV_API_KEY)

from common import utc_now_iso, write_timeseries
from nhtsa_fars import FIPS_STATE

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "pipelines" / "_cache" / "elections"
STATE_MAP_DIR = REPO_ROOT / "public" / "data" / "acs_state"
COUNTY_MAP_DIR = REPO_ROOT / "public" / "data" / "acs_county"
CD_MAP_DIR = REPO_ROOT / "public" / "data" / "acs_cd"

DATAVERSE = "https://dataverse.harvard.edu"
# (doi, filename, ingested) per office file. Resolve the live datafile id by
# filename from the dataset JSON so a version bump doesn't break the pipeline.
SOURCES = {
    "president_state": ("doi:10.7910/DVN/42MVDX", "1976-2024-president.csv", False),
    "president_county": ("doi:10.7910/DVN/VOQCHQ", "countypres_2000-2024.tab", True),
    "senate_state": ("doi:10.7910/DVN/PEJ5QU", "1976-2024-senate-state.tab", True),
    "house_cd": ("doi:10.7910/DVN/IG0UN2", "1976-2024-house.tab", True),
    # Governor: MEDSL ships NO governor returns file, so build_governor derives
    # state margins from the State Precinct-Level Returns (one ~1-2 GB CSV per
    # cycle; filter office=GOVERNOR, sum votes over precinct/county/mode). 2018+
    # share a standardized schema. 2016 (DVN/GSZG1O) uses an older un-standardized
    # layout (raw office strings, a `party` column, state_postal) and is left out
    # for now; every state with a 2016 race also votes in 2020/2024, so no state
    # is lost.
    "governor_2018": ("doi:10.7910/DVN/ZFXEJU", "STATE_precinct_general.csv", False),
    "governor_2020": ("doi:10.7910/DVN/OKL2K1", "STATE_precinct_general.csv", False),
    "governor_2022": ("doi:10.7910/DVN/OAARCY", "STATE_precinct_general.csv", False),
    "governor_2024": ("doi:10.7910/DVN/DODOBJ", "STATE_precinct_general.csv", False),
}
SOURCE_URL = "https://electionlab.mit.edu/data"


# --- Dataverse download (guestbook-POST -> signed URL) ---------------------

def _require_token() -> str:
    import os
    tok = os.environ.get("HDV_API_KEY")
    if not tok:
        print("ERROR: HDV_API_KEY not set (Harvard Dataverse API token).",
              file=sys.stderr)
        raise SystemExit(2)
    return tok


def _resolve_file_id(doi: str, filename: str, tok: str) -> int:
    import requests
    url = f"{DATAVERSE}/api/datasets/:persistentId/?persistentId={doi}"
    j = requests.get(url, headers={"X-Dataverse-key": tok}, timeout=60).json()
    for f in j["data"]["latestVersion"]["files"]:
        if f["dataFile"].get("filename") == filename:
            return f["dataFile"]["id"]
    raise RuntimeError(f"{filename} not found in {doi}")


def fetch_source(key: str) -> Path:
    """Download a MEDSL file to the gitignored cache, returning its path.
    Cached after the first pull (election data is biennial/quadrennial)."""
    doi, filename, ingested = SOURCES[key]
    out = CACHE_DIR / f"{key}.csv"
    if out.exists() and out.stat().st_size > 5000:
        return out
    import requests
    tok = _require_token()
    fid = _resolve_file_id(doi, filename, tok)
    post = f"{DATAVERSE}/api/access/datafile/{fid}" + ("?format=original" if ingested else "")
    r = requests.post(
        post, headers={"X-Dataverse-key": tok, "Content-Type": "application/json"},
        data=json.dumps({"guestbookResponse": {}}), timeout=300,
    )
    r.raise_for_status()
    signed = r.json()["data"]["signedUrl"]
    g = requests.get(signed, timeout=600)
    g.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out.write_bytes(g.content)
    print(f"[elections] downloaded {key} ({len(g.content)} bytes)")
    return out


def _fetch_precinct(key: str) -> Path:
    """Stream a large (~1-2 GB) MEDSL precinct file to the gitignored cache.
    Unlike fetch_source (which holds the whole body in memory) this streams to
    disk via iter_content, so a 2 GB CSV never sits in RAM. Cached after the
    first pull; writes to a .part temp and renames so a half-download isn't
    mistaken for a complete cache."""
    doi, filename, ingested = SOURCES[key]
    out = CACHE_DIR / f"{key}.csv"
    if out.exists() and out.stat().st_size > 1_000_000:
        return out
    import requests
    tok = _require_token()
    fid = _resolve_file_id(doi, filename, tok)
    post = f"{DATAVERSE}/api/access/datafile/{fid}" + ("?format=original" if ingested else "")
    r = requests.post(
        post, headers={"X-Dataverse-key": tok, "Content-Type": "application/json"},
        data=json.dumps({"guestbookResponse": {}}), timeout=300,
    )
    r.raise_for_status()
    signed = r.json()["data"]["signedUrl"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    n = 0
    with requests.get(signed, timeout=1800, stream=True) as g:
        g.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in g.iter_content(1 << 20):
                if chunk:
                    fh.write(chunk)
                    n += len(chunk)
    tmp.replace(out)
    print(f"[elections] downloaded {key} ({n} bytes)")
    return out


def _stream_rows(path: Path):
    """Yield dict rows from a multi-GB CSV without slurping it into memory
    (build_governor reads ~1-2 GB precinct files this way)."""
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        yield from csv.DictReader(fh)


def _rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _f(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _write_map(out_dir: Path, indicator: str, vintage: str, value_label: str,
               values: dict, unit: str = "pp", decimals: int = 1) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "geo": "county" if out_dir is COUNTY_MAP_DIR else "state",
        "indicator": indicator, "vintage": vintage,
        "unit": unit, "decimals": decimals, "valueLabel": value_label,
        "lastUpdated": utc_now_iso(), "values": values,
    }
    (out_dir / f"{indicator}_{vintage}.json").write_text(
        json.dumps(payload), encoding="utf-8")


# --- President ------------------------------------------------------------

def _margin(dem: float, rep: float, total: float) -> float | None:
    """Two-party margin in percentage points of the total vote: (D-R)/total*100.
    Positive = Democratic lean (blue), negative = Republican (red)."""
    if not total:
        return None
    return round((dem - rep) / total * 100, 1)


def build_president() -> int:
    n = 0

    # ---- STATE (1976-2024): one margin map per election year ----
    rows = _rows(fetch_source("president_state"))
    # {year: {st_fips2: {"D": v, "R": v, "T": total}}}
    by_year: dict[str, dict[str, dict[str, float]]] = {}
    for r in rows:
        yr = (r.get("year") or "").strip()
        fips = (r.get("state_fips") or "").strip().zfill(2)
        party = (r.get("party_simplified") or "").strip()
        cv = _f(r.get("candidatevotes"))
        tv = _f(r.get("totalvotes"))
        if not yr or not fips or cv is None or tv is None:
            continue
        d = by_year.setdefault(yr, {}).setdefault(fips, {"D": 0.0, "R": 0.0, "T": tv})
        d["T"] = tv  # totalvotes is the statewide total, repeated per row
        if party == "DEMOCRAT":
            d["D"] += cv
        elif party == "REPUBLICAN":
            d["R"] += cv
    for yr, geo in by_year.items():
        values = {}
        for fips, v in geo.items():
            m = _margin(v["D"], v["R"], v["T"])
            if m is not None:
                values[fips] = m
        if values:
            _write_map(STATE_MAP_DIR, "pres_margin", yr,
                       f"Presidential margin, {yr} (Dem minus Rep, pp of total)",
                       values)
            n += 1

    # ---- COUNTY (2000-2024): sum over `mode`, zero-pad FIPS ----
    crows = _rows(fetch_source("president_county"))
    cby_year: dict[str, dict[str, dict[str, float]]] = {}
    for r in crows:
        yr = (r.get("year") or "").strip()
        fips = (r.get("county_fips") or "").strip()
        if fips and "." in fips:
            fips = fips.split(".")[0]
        try:
            fips = f"{int(fips):05d}"
        except (TypeError, ValueError):
            continue
        # Drop non-county pseudo-FIPS: MEDSL reports Kansas City, MO as a
        # separate 7-digit pseudo-county (2938000) that joins no TopoJSON.
        # (Alaska's 5-digit '0200x' house-district codes pass this length
        # check but still don't join, so AK renders blank at county level.)
        if len(fips) != 5:
            continue
        party = (r.get("party") or "").strip()
        cv = _f(r.get("candidatevotes"))
        tv = _f(r.get("totalvotes"))
        if not yr or cv is None or tv is None:
            continue
        d = cby_year.setdefault(yr, {}).setdefault(fips, {"D": 0.0, "R": 0.0, "T": 0.0})
        d["T"] = tv  # totalvotes is the county total, repeated per row
        if party == "DEMOCRAT":
            d["D"] += cv
        elif party == "REPUBLICAN":
            d["R"] += cv
    for yr, geo in cby_year.items():
        values = {}
        for fips, v in geo.items():
            m = _margin(v["D"], v["R"], v["T"])
            if m is not None:
                values[fips] = m
        if values:
            _write_map(COUNTY_MAP_DIR, "pres_margin_county", yr,
                       f"Presidential margin by county, {yr} (Dem minus Rep, pp)",
                       values)
            n += 1

    print(f"[elections] president: wrote {n} margin choropleth files.")
    return n


def _party_dr(p: str | None) -> str | None:
    """Fold a party label to 'D' / 'R' / None. Covers the state-party variants
    that would otherwise mis-zero a margin: Minnesota's Democratic-Farmer-Labor
    and Independent-Republican, North Dakota's Democratic-NPL."""
    p = (p or "").strip().upper()
    if p in ("DEMOCRAT", "DEMOCRATIC-FARMER-LABOR", "DEMOCRATIC-NPL"):
        return "D"
    if p in ("REPUBLICAN", "INDEPENDENT-REPUBLICAN"):
        return "R"
    return None


def _gen_nonspecial(r: dict) -> bool:
    """A general-election, non-special row. stage/special are CASE-MIXED in the
    MEDSL files (2022/2024 uppercase, earlier lowercase), so lower() first."""
    if (r.get("stage") or "").strip().lower() != "gen":
        return False
    return (r.get("special") or "").strip().lower() != "true"


def build_senate() -> int:
    """Per-state Senate two-party margin choropleths, one file per election year
    (sparse: only the ~third of states whose seat is up appears each cycle)."""
    rows = [r for r in _rows(fetch_source("senate_state")) if _gen_nonspecial(r)]
    by_year: dict[str, dict[str, dict[str, float]]] = {}
    for r in rows:
        yr = (r.get("year") or "").strip()
        fips = (r.get("state_fips") or "").strip().zfill(2)
        dr = _party_dr(r.get("party_simplified"))
        cv = _f(r.get("candidatevotes"))
        tv = _f(r.get("totalvotes"))
        if not yr or not fips or cv is None or tv is None:
            continue
        d = by_year.setdefault(yr, {}).setdefault(fips, {"D": 0.0, "R": 0.0, "T": tv})
        d["T"] = tv
        if dr == "D":
            d["D"] += cv
        elif dr == "R":
            d["R"] += cv
    n = 0
    for yr, geo in by_year.items():
        values = {f: _margin(v["D"], v["R"], v["T"]) for f, v in geo.items()}
        values = {f: m for f, m in values.items() if m is not None}
        if values:
            _write_map(STATE_MAP_DIR, "sen_margin", yr,
                       f"Senate margin, {yr} (Dem minus Rep, pp of total)", values)
            n += 1
    print(f"[elections] senate: wrote {n} margin choropleth files.")
    return n


def _cd_geoid(state_fips: str, district: str, state_po: str) -> str | None:
    """4-char CD GEOID = STATEFP(2) + CD118FP(2). MEDSL codes both at-large and
    DC's delegate as district '0'; Census uses '00' for at-large and '98' for
    DC's non-voting delegate, so DC must be special-cased or its polygon won't
    join the cd118 TopoJSON."""
    try:
        st = f"{int(state_fips):02d}"
    except (TypeError, ValueError):
        return None
    cd2 = "98" if (state_po or "").strip().upper() == "DC" else None
    if cd2 is None:
        try:
            cd2 = f"{int(district):02d}"
        except (TypeError, ValueError):
            return None
    return f"{st}{cd2}"


def build_house() -> int:
    """Per-congressional-district House two-party margin choropleths, one file
    per election year, keyed by 4-char CD GEOID for the cd118 TopoJSON. The
    cb_2023 districts only match 2022/2024 numbering, so the chart defaults to
    2024 (earlier years still write but pre-2022 districts mis-join)."""
    rows = [r for r in _rows(fetch_source("house_cd")) if _gen_nonspecial(r)]
    by_year: dict[str, dict[str, dict[str, float]]] = {}
    for r in rows:
        yr = (r.get("year") or "").strip()
        geoid = _cd_geoid(r.get("state_fips"), r.get("district"), r.get("state_po"))
        dr = _party_dr(r.get("party"))
        cv = _f(r.get("candidatevotes"))
        tv = _f(r.get("totalvotes"))
        if not yr or not geoid or cv is None or tv is None:
            continue
        d = by_year.setdefault(yr, {}).setdefault(geoid, {"D": 0.0, "R": 0.0, "T": tv})
        d["T"] = tv
        if dr == "D":
            d["D"] += cv
        elif dr == "R":
            d["R"] += cv
    CD_MAP_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for yr, geo in by_year.items():
        values = {g: _margin(v["D"], v["R"], v["T"]) for g, v in geo.items()}
        values = {g: m for g, m in values.items() if m is not None}
        if values:
            # House CD maps live in acs_cd/ (the renderer's geo:'cd' dataDirSeg).
            payload = {
                "geo": "cd", "indicator": "house_margin", "vintage": yr,
                "unit": "pp", "decimals": 1,
                "valueLabel": f"House margin by district, {yr} (Dem minus Rep, pp)",
                "lastUpdated": utc_now_iso(), "values": values,
            }
            (CD_MAP_DIR / f"house_margin_{yr}.json").write_text(
                json.dumps(payload), encoding="utf-8")
            n += 1
    print(f"[elections] house: wrote {n} CD margin choropleth files.")
    return n


# Precinct rows include ballot-artifact "candidates" (blank / under / over
# votes) that must not inflate the denominator, and they label some Democratic
# nominees only in party_detailed (MN's DFL, VT's DEM/PROG fusion line) while
# party_simplified files them under OTHER. _dr_precinct folds both columns.
_GOV_NON_CANDIDATE = {
    "BLANK VOTES", "BLANK", "UNDER VOTES", "UNDERVOTES", "OVER VOTES",
    "OVERVOTES", "EXHAUSTED", "EXHAUSTED BALLOTS", "TOTAL", "TOTAL VOTES",
    "SCATTERING", "SCATTER", "NONE OF THESE CANDIDATES", "VOID", "REJECTED",
}


def _is_governor_office(office: str | None) -> bool:
    """True for the governorship, including the joint "Governor / Lieutenant
    Governor" ticket some states (IA 2018, MT, ND) label as one office. Excludes
    a lone "LIEUTENANT GOVERNOR" race and Massachusetts's "GOVERNOR'S COUNCIL"."""
    o = (office or "").strip().upper()
    if o == "GOVERNOR":
        return True
    if "COUNCIL" in o:
        return False
    return o.startswith("GOVERNOR") and "LIEUTENANT" in o


def _dr_precinct(party_simplified: str | None,
                 party_detailed: str | None) -> str | None:
    s = (party_simplified or "").strip().upper()
    d = (party_detailed or "").strip().upper()
    if d.startswith("DEMOCRAT") or d in ("DEM/PROG", "PROG/DEM") or s == "DEMOCRAT":
        return "D"
    if d.startswith("REPUBLICAN") or s == "REPUBLICAN":
        return "R"
    return None


# Races where the precinct file carries no party label at all (both columns
# blank), so _dr_precinct can't decide. Researched per case, matched by surname
# substring, and consulted ONLY when the party columns fail. Populated as such
# states surface across cycles (e.g. New Mexico ships blank party columns).
_GOV_CANDIDATE_PARTY: dict[tuple[str, str], str] = {
    ("NM", "LUJAN GRISHAM"): "D",   # 2018 + 2022  Michelle Lujan Grisham (D)
    ("NM", "RONCHETTI"): "R",       # 2022  Mark Ronchetti (R)
    ("NM", "PEARCE"): "R",          # 2018  Steve Pearce (R)
}


def _gov_override_dr(state_po: str | None, candidate: str | None) -> str | None:
    po = (state_po or "").strip().upper()
    c = (candidate or "").strip().upper()
    for (st, name), dr in _GOV_CANDIDATE_PARTY.items():
        if st == po and name in c:
            return dr
    return None


def _gov_state_margin(cands: dict[str, dict]) -> float | None:
    """State two-party margin (pp of total) from per-candidate {v, dr} tallies.

    When only one major party fielded a nominee, a non-major candidate who is
    the other half of the top two and cleared 20% of the vote stands in for the
    absent major party (Alaska-style independents who are the de-facto
    opposition). Where no such second candidate exists (e.g. WY 2022, a lone
    Republican over a sub-20% Libertarian) the state is omitted rather than
    painted with a misleading near-100-point margin."""
    total = sum(c["v"] for c in cands.values())
    if total <= 0:
        return None
    d = sum(c["v"] for c in cands.values() if c["dr"] == "D")
    r = sum(c["v"] for c in cands.values() if c["dr"] == "R")
    if d > 0 and r > 0:
        return round((d - r) / total * 100, 1)
    if (d > 0) == (r > 0):  # both zero: no major-party nominee at all
        return None
    ranked = sorted(cands.values(), key=lambda c: c["v"], reverse=True)
    if len(ranked) < 2:
        return None
    first, second = ranked[0], ranked[1]
    present = "D" if d > 0 else "R"
    # The lone major nominee and a >20% non-major must be the top two; promote
    # that non-major into the empty major slot (works whichever one led).
    if first["dr"] == present and second["dr"] is None and second["v"] > 0.20 * total:
        promoted = second["v"]
    elif first["dr"] is None and first["v"] > 0.20 * total and second["dr"] == present:
        promoted = first["v"]
    else:
        return None
    return round(((d if present == "D" else promoted)
                  - (promoted if present == "D" else r)) / total * 100, 1)


def build_governor() -> int:
    """Per-state Governor two-party margin choropleths, one file per cycle.

    MEDSL publishes no governor *returns* file, so margins are derived from the
    State Precinct-Level Returns (one ~1-2 GB CSV per cycle): keep general,
    non-special office=GOVERNOR rows and sum `votes` over precinct / county /
    mode up to a state two-party margin (same (D-R)/total convention as the
    other offices). Coverage 2018-2024 (the standardized-schema precinct files;
    see SOURCES for why 2016 is excluded). Sparse like senate: only states
    electing a governor that cycle appear, so each state still gets ~2 cycles
    across the slider.

    Set GOV_YEARS=2022,2024 to restrict which cycles are (down)loaded."""
    import os
    want = {y.strip() for y in (os.environ.get("GOV_YEARS") or "").split(",") if y.strip()}
    n = 0
    for yr in ("2018", "2020", "2022", "2024"):
        key = f"governor_{yr}"
        if key not in SOURCES or (want and yr not in want):
            continue
        # Per-candidate tallies (not raw D/R buckets) so a candidate's fusion
        # lines fold into one total (e.g. NY's Working Families row for the
        # Democratic nominee) and so _gov_state_margin can rank candidates for
        # the >20% non-major rule. agg[fips][candidate] = {"v": votes, "dr": …}.
        agg: dict[str, dict[str, dict]] = {}
        for r in _stream_rows(_fetch_precinct(key)):
            if not _is_governor_office(r.get("office")):
                continue
            if not _gen_nonspecial(r):
                continue
            cand = (r.get("candidate") or "").strip().upper()
            if not cand or cand in _GOV_NON_CANDIDATE:
                continue  # blank / under / over votes aren't cast for the office
            fips = (r.get("state_fips") or "").strip()
            try:
                fips = f"{int(float(fips)):02d}"
            except (TypeError, ValueError):
                continue
            v = _f(r.get("votes"))
            if v is None:
                continue
            dr = _dr_precinct(r.get("party_simplified"), r.get("party_detailed"))
            if dr is None:
                dr = _gov_override_dr(r.get("state_po"), cand)
            c = agg.setdefault(fips, {}).setdefault(cand, {"v": 0.0, "dr": None})
            c["v"] += v
            if dr is not None:
                c["dr"] = dr  # any party-bearing line fixes the candidate's side
        values = {}
        for f, cands in agg.items():
            m = _gov_state_margin(cands)
            if m is not None:
                values[f] = m
        if values:
            _write_map(STATE_MAP_DIR, "gov_margin", yr,
                       f"Governor margin, {yr} (Dem minus Rep, pp of total)", values)
            n += 1
            print(f"[elections] governor {yr}: {len(values)} states")
        else:
            print(f"[elections] governor {yr}: no GOVERNOR rows (schema mismatch?)")
    print(f"[elections] governor: wrote {n} margin choropleth files.")
    return n


# --- Per-geo margin TIMESERIES (state politics + CD House) ----------------
# Pivots the per-year choropleth margin maps (written by the builders above,
# already committed on disk) into one timeseries source per geography per
# office, so election margins are filterable like any other state/CD series.
# Positive = Democratic lean, negative = Republican (see _margin). No re-fetch:
# reads the existing public/data choropleth JSONs.

SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "elections"
_USPS_BY_FIPS = {f"{k:02d}": v[0] for k, v in FIPS_STATE.items()}
_NAME_BY_FIPS = {f"{k:02d}": v[1] for k, v in FIPS_STATE.items()}

# (indicator, map_dir, geo, id_prefix, office_label, name_prefix, short_word,
#  supportedDeltas, years_note)
_TS_OFFICES = [
    ("pres_margin", STATE_MAP_DIR, "state", "pres_margin", "presidential",
     "Presidential margin", "pres", ["10y", "30y"],
     "Presidential elections, 1976 to 2024."),
    ("sen_margin", STATE_MAP_DIR, "state", "sen_margin", "US Senate",
     "Senate margin", "Senate", ["10y", "30y"],
     "US Senate general elections (excluding special elections), 1976 to 2024; "
     "a state appears only in the cycles its seat was up."),
    ("gov_margin", STATE_MAP_DIR, "state", "gov_margin", "gubernatorial",
     "Gubernatorial margin", "gov", ["5y", "10y"],
     "Gubernatorial general elections, 2018 to 2024."),
    ("house_margin", CD_MAP_DIR, "cd", "house_margin", "US House",
     "House margin", "House", ["1y", "5y"],
     "US House general elections on 2023 (118th Congress) district boundaries, "
     "2022 and 2024."),
]


def _ts_yaml_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _dist_label(dst: str) -> str:
    if dst == "al":
        return "at-large"
    if dst == "98":
        return "delegate"
    try:
        return str(int(dst))
    except ValueError:
        return dst


def _write_ts_yaml(sid: str, name: str, short: str, desc: str,
                   deltas: list[str], office_label: str) -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    dl = ", ".join(f'"{d}"' for d in deltas)
    lines = [
        f"name: {_ts_yaml_str(name)}",
        f"shortName: {_ts_yaml_str(short)}",
        f"description: {_ts_yaml_str(desc)}",
        "kind: timeseries",
        "pipeline: elections",
        f"dataFile: data/elections/{sid}.json",
        f"supportedDeltas: [{dl}]",
        'unit: "pp"',
        "emphasis: level",
        "formatting:",
        "  style: number",
        "  decimals: 1",
        '  suffix: " pp"',
        "provenance:",
        "  provider: MEDSL (MIT Election Data and Science Lab)",
        f"  series: {_ts_yaml_str(office_label + ' two-party margin (D-R), pp of total vote')}",
        "  url: https://electionlab.mit.edu/data",
        "  license: CC0 (MEDSL via Harvard Dataverse)",
        "tags:",
        "  - elections",
        "  - us",
        "",
    ]
    (SOURCES_DIR / f"{sid}.yaml").write_text("\n".join(lines), encoding="utf-8")


def build_timeseries() -> int:
    import glob
    n = 0
    for ind, mdir, geo, idp, office, nprefix, sword, deltas, ynote in _TS_OFFICES:
        acc: dict[str, dict[str, float]] = {}
        for fp in sorted(glob.glob(str(mdir / f"{ind}_*.json"))):
            year = Path(fp).stem[len(ind) + 1:]
            if not year.isdigit():
                continue
            payload = json.loads(Path(fp).read_text(encoding="utf-8"))
            for gk, v in (payload.get("values") or {}).items():
                if v is not None:
                    acc.setdefault(gk, {})[year] = v
        for gk, yrs in sorted(acc.items()):
            if geo == "state":
                usps = _USPS_BY_FIPS.get(gk)
                if not usps:
                    continue
                geo_name = _NAME_BY_FIPS[gk]
                sid = f"{idp}_{usps}"
                name = f"{nprefix} — {geo_name}"
                short = f"{geo_name} {sword} margin"
                geo_label = geo_name
            else:
                fips2, cd2 = gk[:2], gk[2:]
                usps = _USPS_BY_FIPS.get(fips2)
                if not usps:
                    continue
                dst = "al" if cd2 == "00" else cd2
                geo_name = _NAME_BY_FIPS[fips2]
                sid = f"{idp}_{usps}_{dst}"
                name = f"{nprefix} — {geo_name} {_dist_label(dst)}"
                short = f"{usps.upper()}-{dst.upper()} House margin"
                geo_label = f"{geo_name} ({_dist_label(dst)})"
            pts = [{"t": f"{y}-12-31", "v": yrs[y]} for y in sorted(yrs)]
            desc = (
                "Two-party vote margin (Democratic minus Republican) as a share "
                "of the total vote, in percentage points, for the "
                f"{office} race in {geo_label}, by election year. Positive values "
                "lean Democratic, negative Republican. Computed from MEDSL (MIT "
                "Election Data and Science Lab) returns via Harvard Dataverse. "
                f"{ynote}"
            )
            write_timeseries("elections", sid, name, pts, unit="pp", merge=False)
            _write_ts_yaml(sid, name, short, desc, deltas, office)
            n += 1
    print(f"elections timeseries: wrote {n} sources")
    return n


BUILDERS = {
    "president": build_president,
    "senate": build_senate,
    "house": build_house,
    "governor": build_governor,
    "timeseries": build_timeseries,
}


def main() -> int:
    argv = sys.argv[1:]
    names = [a for a in argv if a in BUILDERS] or list(BUILDERS)
    total = sum(BUILDERS[name]() for name in names)
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
