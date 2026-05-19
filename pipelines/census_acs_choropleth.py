"""
Census ACS 5-year cross-sectional snapshots for choropleth maps.

The existing census_acs_cd.py pipeline produces TIME-SERIES data per
congressional district (one source per (indicator, CD), each with 13
ACS vintages). That shape is right for line charts but wrong for
choropleths, which need many regions at ONE time slice.

This pipeline writes CROSS-SECTIONAL snapshots instead. For each
(indicator, vintage, geo level), one JSON file lists every region's
value at that vintage:

  public/data/acs_state/<indicator>_<vintage>.json
  public/data/acs_county/<indicator>_<vintage>.json
  public/data/acs_tract/<state>/<indicator>_<vintage>.json
  public/data/acs_block_group/<state>/<indicator>_<vintage>.json

Format:

  {
    "geo": "county",
    "indicator": "poverty_rate",
    "vintage": "2022",
    "unit": "%",
    "decimals": 1,
    "lastUpdated": "...",
    "valueLabel": "% of population below poverty line",
    "values": {
      "01001": 12.3,    // Autauga County, AL
      "01003": 9.8,
      ...
    }
  }

GEOID convention matches the us-atlas TopoJSON: 2-digit state FIPS,
5-digit county FIPS, 11-digit tract GEOID, 12-digit block-group
GEOID. Renderer joins on this key.

Indicator definitions live in INDICATORS below. Add a new entry to
extend coverage. Each entry knows the Census variable codes and how
to combine them into a final value (e.g., poverty_rate = pop_in_poverty
/ pop_universe).

We deliberately KEEP all vintages on disk forever — the data is
small enough (state ~5KB/vintage, county ~300KB/vintage) that
shipping a multi-decade snapshot panel costs less than re-fetching
on demand, and it lets the future year-slider feature work
client-side. Stop discarding historical ACS data was an explicit
user ask after we noticed census_acs_cd.py only stored aggregated
CD values.

Run:
  python pipelines/census_acs_choropleth.py --geo state
  python pipelines/census_acs_choropleth.py --geo county
  python pipelines/census_acs_choropleth.py --geo tract --state VA
  python pipelines/census_acs_choropleth.py --geo block_group --state VA

CENSUS_API_KEY required for tract + block-group (the public anon
endpoint is rate-limited and slower). Optional for state + county
but recommended.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "public" / "data"

# ACS 5-year vintages we fetch. Matches the CD pipeline's vintage set
# so cross-references (CD + county for the same year, say) line up
# without surprises.
VINTAGES: list[str] = [
    "2010", "2011", "2012", "2013", "2014", "2015", "2016",
    "2017", "2018", "2019", "2020", "2021", "2022",
]

# State FIPS codes (2-digit). 50 states + DC. Skip Puerto Rico /
# territories — ACS coverage is patchy at the sub-state level and
# us-atlas doesn't include them by default.
STATE_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56",
}


@dataclass
class AcsIndicator:
    """One choropleth-able ACS indicator.

    A value is computed per region as `combine(values)`, where
    `values` is the dict of fetched variable codes → raw float values
    for that region. `combine` returns a single float (the value to
    color the region by) or None to skip the region.
    """
    out_id: str
    name: str
    unit: str               # "%" or "USD" — for label/legend display
    decimals: int           # display decimals (data file stores raw)
    value_label: str        # legend text e.g. "% below poverty line"
    variables: list[str]    # Census variable codes to fetch
    # Combine function. Receives {var_code: float|None}; returns the
    # display value or None to skip.
    combine: callable = field(default=lambda v: None)


def pct(numer: str, denom: str):
    """Returns a percent (0-100) of numer/denom, or None if either is
    missing or denom is zero."""
    def _combine(vals: dict[str, float | None]) -> float | None:
        n = vals.get(numer)
        d = vals.get(denom)
        if n is None or d is None or d <= 0:
            return None
        return round(100.0 * n / d, 2)
    return _combine


def direct(code: str):
    """Returns the raw fetched value, or None if missing / sentinel
    (Census returns -666666666 for "no data")."""
    def _combine(vals: dict[str, float | None]) -> float | None:
        v = vals.get(code)
        if v is None or v < -100000000:
            return None
        return v
    return _combine


# Four indicators the user asked for. Add more by following the same
# shape.
INDICATORS: list[AcsIndicator] = [
    AcsIndicator(
        out_id="poverty_rate",
        name="People in poverty",
        unit="%",
        decimals=1,
        value_label="% of population below poverty line",
        variables=["B17001_001E", "B17001_002E"],
        combine=pct("B17001_002E", "B17001_001E"),
    ),
    AcsIndicator(
        out_id="median_hh_income",
        name="Median household income",
        unit="USD",
        decimals=0,
        value_label="Median household income (USD)",
        variables=["B19013_001E"],
        combine=direct("B19013_001E"),
    ),
    AcsIndicator(
        out_id="bachelors_plus_pct",
        name="Adults 25+ with bachelor's degree or higher",
        unit="%",
        decimals=1,
        value_label="% of 25+ with bachelor's degree or higher",
        # Universe: B15003_001E (adults 25+). Numerator: B15003_022..025
        # (bachelor's, master's, professional, doctoral).
        variables=[
            "B15003_001E",
            "B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E",
        ],
        combine=lambda vals: _sum_pct_combine(vals,
            numer_codes=("B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E"),
            denom_code="B15003_001E",
        ),
    ),
    AcsIndicator(
        out_id="foreign_born_pct",
        name="Foreign-born population",
        unit="%",
        decimals=1,
        value_label="% foreign-born",
        variables=["B05002_001E", "B05002_013E"],
        combine=pct("B05002_013E", "B05002_001E"),
    ),
]


def _sum_pct_combine(vals: dict[str, float | None], numer_codes, denom_code):
    parts = []
    for c in numer_codes:
        v = vals.get(c)
        if v is None or v < -100000000:
            continue
        parts.append(v)
    d = vals.get(denom_code)
    if not parts or d is None or d <= 0:
        return None
    return round(100.0 * sum(parts) / d, 2)


def fetch_acs(year: str, geo_spec: str, in_spec: str | None,
              variables: list[str], api_key: str | None,
              timeout: int = 180) -> list[list[str]]:
    """One Census ACS API call. Returns the raw 2D table (first row =
    header). Empty list on failure. Default timeout 180s — block-group
    state-wide responses can be 10MB+ on slow Census API days."""
    base = f"https://api.census.gov/data/{year}/acs/acs5"
    get = "NAME," + ",".join(variables)
    qs = [f"get={get}", f"for={geo_spec}"]
    if in_spec:
        qs.append(f"in={in_spec}")
    if api_key:
        qs.append(f"key={api_key}")
    url = f"{base}?{'&'.join(qs)}"
    try:
        result = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", str(timeout), url],
            capture_output=True, check=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        # Include first bit of stderr/stdout so workflow logs show
        # WHY the call failed (timeout vs HTTP error vs DNS, etc.).
        stderr_head = (e.stderr or "").strip()[:200]
        stdout_head = (e.stdout or "").strip()[:200]
        print(f"    curl failed (rc={e.returncode}) for {year} / {geo_spec}: "
              f"{stderr_head} | {stdout_head}", file=sys.stderr)
        return []
    body = result.stdout
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        # Census occasionally returns HTML error pages (rate limit,
        # missing key, server error). Show the head so we can tell.
        head = body.strip()[:300].replace("\n", " ")
        print(f"    bad JSON for {year} / {geo_spec}: {head}", file=sys.stderr)
        return []


# Per-(state, vintage) county-FIPS list cache. Avoids re-querying the
# same list during per-county block-group iteration across indicators.
_COUNTIES_CACHE: dict[tuple[str, str], list[str]] = {}


def list_counties(state_fips: str, vintage: str, api_key: str | None) -> list[str]:
    """Return the 3-digit county FIPS list for a state at a vintage.
    Cached per (state_fips, vintage)."""
    key = (state_fips, vintage)
    if key in _COUNTIES_CACHE:
        return _COUNTIES_CACHE[key]
    table = fetch_acs(
        vintage, "county:*", f"state:{state_fips}",
        ["B01001_001E"], api_key, timeout=60,
    )
    if not table or len(table) < 2:
        _COUNTIES_CACHE[key] = []
        return []
    header = table[0]
    try:
        ci = header.index("county")
    except ValueError:
        _COUNTIES_CACHE[key] = []
        return []
    fips = sorted({row[ci] for row in table[1:] if row[ci]})
    _COUNTIES_CACHE[key] = fips
    return fips


def geoid_from_row(geo: str, row: list[str], header: list[str]) -> str:
    """Build the canonical GEOID (matching us-atlas TopoJSON id) from
    a returned row, regardless of column ordering."""
    idx = {col: i for i, col in enumerate(header)}
    if geo == "state":
        return row[idx["state"]]
    if geo == "county":
        return row[idx["state"]] + row[idx["county"]]
    if geo == "tract":
        return row[idx["state"]] + row[idx["county"]] + row[idx["tract"]]
    if geo == "block_group":
        return (
            row[idx["state"]] + row[idx["county"]] + row[idx["tract"]]
            + row[idx["block group"]]
        )
    raise ValueError(f"Unknown geo: {geo}")


def _rows_to_values(
    indicator: AcsIndicator, geo: str,
    table: list[list[str]],
) -> dict[str, float]:
    """Convert a raw Census API table to {GEOID: value} for one
    indicator + geo. Skips rows where the combine() returns None."""
    if not table or len(table) < 2:
        return {}
    header = table[0]
    var_indices = {v: header.index(v) for v in indicator.variables if v in header}
    out: dict[str, float] = {}
    for row in table[1:]:
        geoid = geoid_from_row(geo, row, header)
        vals: dict[str, float | None] = {}
        for v, idx in var_indices.items():
            raw = row[idx]
            try:
                vals[v] = float(raw) if raw not in (None, "", "null") else None
            except (TypeError, ValueError):
                vals[v] = None
        result = indicator.combine(vals)
        if result is not None:
            out[geoid] = result
    return out


def fetch_indicator_vintage(
    indicator: AcsIndicator,
    vintage: str,
    geo: str,
    state_fips: str | None,
    api_key: str | None,
) -> dict[str, float]:
    """Fetch one (indicator, vintage) at the given geo. Returns
    {GEOID: value}. Empty dict on failure.

    Block-group has a special path: we first try the state-wide
    `county:*` wildcard (one big call), and if that returns nothing we
    fall back to iterating counties one by one. The wildcard works on
    recent ACS5 vintages but can time out, hit response-size limits,
    or be rejected on older years — the per-county iteration is
    slower but reliable."""
    # Build the for/in clauses per geo. tract + block_group require
    # an `in` clause naming the state.
    if geo == "state":
        for_spec, in_spec = "state:*", None
    elif geo == "county":
        for_spec, in_spec = "county:*", "state:*"
    elif geo == "tract":
        if not state_fips:
            raise ValueError("tract geo needs state_fips")
        for_spec, in_spec = "tract:*", f"state:{state_fips}"
    elif geo == "block_group":
        if not state_fips:
            raise ValueError("block_group geo needs state_fips")
        return _fetch_block_group_state(
            indicator, vintage, state_fips, api_key,
        )
    else:
        raise ValueError(f"Unknown geo: {geo}")

    table = fetch_acs(vintage, for_spec, in_spec, indicator.variables, api_key)
    return _rows_to_values(indicator, geo, table)


def _fetch_block_group_state(
    indicator: AcsIndicator,
    vintage: str,
    state_fips: str,
    api_key: str | None,
) -> dict[str, float]:
    """Block-group fetcher with fast path + per-county fallback.

    Fast path: one API call with `for=block group:*&in=state:NN+county:*`,
    which the Census API supports on recent ACS5 vintages. If that
    returns empty (rejected by API, timed out, or just had no rows),
    we fall back to looping county FIPS one at a time. The per-county
    path is slower (133 calls for VA) but works on every vintage and
    won't get tripped up by per-call size limits."""
    # Block-group state-wide responses are big (~10MB for VA across all
    # vars). Bump timeout vs the default to give curl room.
    if not api_key:
        # block_group without an API key is hopeless — Census 302s
        # every request to its "Missing Key" HTML page. Log loudly so
        # the workflow operator sees this in the top-level error
        # summary instead of via per-attempt "(no data)" spam.
        print(
            f"::error::block_group fetches require CENSUS_API_KEY but "
            f"none is set. Add it to the repo secrets (used by the "
            f"refresh-demographics workflow) and re-run.",
            file=sys.stderr,
        )
        return {}
    fast = fetch_acs(
        vintage, "block group:*", f"state:{state_fips}+county:*",
        indicator.variables, api_key, timeout=300,
    )
    values = _rows_to_values(indicator, "block_group", fast)
    if values:
        return values

    # Fast path failed — iterate counties. Use a separate cheap call
    # to enumerate the county FIPS for this state at this vintage.
    counties = list_counties(state_fips, vintage, api_key)
    print(f"    block_group: fast path returned 0 rows; falling back to "
          f"per-county iteration ({len(counties)} counties)",
          file=sys.stderr, flush=True)
    if not counties:
        print(f"::error::block_group: no counties found for state "
              f"{state_fips} / {vintage} — list_counties returned empty. "
              f"Likely the CENSUS_API_KEY is set but invalid, or Census "
              f"changed an endpoint shape. Try `python pipelines/"
              f"census_acs_choropleth.py --geo county` to see if county-"
              f"level fetches also fail.",
              file=sys.stderr)
        return {}
    print(f"    block_group: fast path empty, iterating {len(counties)} counties",
          flush=True)
    out: dict[str, float] = {}
    misses = 0
    for cfips in counties:
        table = fetch_acs(
            vintage, "block group:*", f"state:{state_fips}+county:{cfips}",
            indicator.variables, api_key, timeout=60,
        )
        per_county = _rows_to_values(indicator, "block_group", table)
        if per_county:
            out.update(per_county)
        else:
            misses += 1
    if misses:
        print(f"    block_group: {misses}/{len(counties)} counties returned no data",
              file=sys.stderr)
    return out


def write_snapshot(
    indicator: AcsIndicator, geo: str, vintage: str,
    values: dict[str, float], state_code: str | None = None,
) -> Path:
    """Write a snapshot JSON file. Tract + block-group are sharded by
    state (one file per state); state + county are nationwide."""
    if geo in ("state", "county"):
        out_dir = DATA_ROOT / f"acs_{geo}"
    else:
        # tract / block_group are sharded by state code (lowercase).
        if not state_code:
            raise ValueError(f"{geo} requires state_code")
        out_dir = DATA_ROOT / f"acs_{geo}" / state_code.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{indicator.out_id}_{vintage}.json"
    body = {
        "geo": geo,
        "indicator": indicator.out_id,
        "vintage": vintage,
        "unit": indicator.unit,
        "decimals": indicator.decimals,
        "valueLabel": indicator.value_label,
        "lastUpdated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "values": {k: values[k] for k in sorted(values.keys())},
    }
    if state_code:
        body["stateCode"] = state_code
    path.write_text(json.dumps(body) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--geo", required=True,
                    choices=["state", "county", "tract", "block_group"])
    ap.add_argument("--state",
                    help=("2-letter state code (e.g. VA). Required for tract "
                          "and block_group. Pass 'all' to fetch every state."))
    ap.add_argument("--vintages", default=",".join(VINTAGES),
                    help="Comma-separated ACS-vintage years. Default: all.")
    ap.add_argument("--indicators",
                    help=("Comma-separated out_ids to fetch. Default: all 4. "
                          "Lets you re-run a single indicator without re-fetching."))
    args = ap.parse_args()

    api_key = os.environ.get("CENSUS_API_KEY") or None
    if args.geo in ("tract", "block_group") and not api_key:
        print("WARN: tract + block_group fetches without CENSUS_API_KEY may "
              "be rate-limited.", file=sys.stderr)

    vintages = [v.strip() for v in args.vintages.split(",") if v.strip()]
    selected = INDICATORS
    if args.indicators:
        wanted = {x.strip() for x in args.indicators.split(",")}
        selected = [i for i in INDICATORS if i.out_id in wanted]

    # Resolve state-sharding targets.
    if args.geo in ("tract", "block_group"):
        if not args.state:
            print("ERROR: --state required for tract / block_group", file=sys.stderr)
            return 1
        if args.state.lower() == "all":
            state_targets = list(STATE_FIPS.items())
        else:
            code = args.state.upper()
            if code not in STATE_FIPS:
                print(f"ERROR: Unknown state {code}", file=sys.stderr)
                return 1
            state_targets = [(code, STATE_FIPS[code])]
    else:
        state_targets = [(None, None)]

    total_files = 0
    attempts = 0
    no_data_count = 0
    for indicator in selected:
        for vintage in vintages:
            for state_code, state_fips in state_targets:
                attempts += 1
                where = state_code or "US"
                print(f"  {args.geo}/{where} / {indicator.out_id} / {vintage}... ",
                      end="", flush=True)
                try:
                    values = fetch_indicator_vintage(
                        indicator, vintage, args.geo, state_fips, api_key,
                    )
                except Exception as e:
                    print(f"error: {e}")
                    no_data_count += 1
                    continue
                if not values:
                    print("(no data)")
                    no_data_count += 1
                    continue
                path = write_snapshot(indicator, args.geo, vintage, values,
                                      state_code=state_code)
                print(f"{len(values)} regions → {path.relative_to(ROOT)}")
                total_files += 1
    print(f"\nWrote {total_files} snapshot file(s).")
    # Loud failure path: if EVERY attempt returned empty, the
    # likely cause is a missing/invalid CENSUS_API_KEY for the
    # endpoint (block_group requires it; the public anon endpoint
    # 302-redirects to "Missing Key" HTML which we parse-fail).
    # Print a GitHub-Actions-readable error annotation so the
    # workflow log surfaces this at top-level rather than buried in
    # the per-attempt "(no data)" spam.
    if attempts > 0 and total_files == 0:
        print(
            f"\n::error::All {attempts} fetches for "
            f"--geo {args.geo}" + (f" --state {args.state}" if args.state else "")
            + f" returned no data. Likely CENSUS_API_KEY missing or "
            f"invalid (this endpoint requires one; without it FRED's "
            f"CSV-style anon endpoint 302s to a 'Missing Key' HTML "
            f"page that fails JSON parse). Set the CENSUS_API_KEY "
            f"secret in the repo's Actions settings + re-run.",
            file=sys.stderr,
        )
        return 1
    if attempts > 0 and no_data_count > attempts * 0.5:
        print(
            f"\n::warning::{no_data_count}/{attempts} fetches returned "
            f"no data — partial coverage. Review the per-attempt log "
            f"above for the failure pattern.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
