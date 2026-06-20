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

from common import utc_now_iso

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


BUILDERS = {
    "president": build_president,
    "senate": build_senate,
    "house": build_house,
}


def main() -> int:
    argv = sys.argv[1:]
    names = [a for a in argv if a in BUILDERS] or list(BUILDERS)
    total = sum(BUILDERS[name]() for name in names)
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
