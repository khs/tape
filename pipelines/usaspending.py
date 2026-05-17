"""
Federal spending by state and by congressional district, annual.

Source: USAspending.gov's public API (api.usaspending.gov). No key needed
for public-data endpoints, no rate limits we've hit in practice.

The CD-level data is the unique-to-us thing: nobody else builds clean
composable time series of federal $ flowing to each congressional
district. Same data you'd see on USAspending's map, but as 435
timeseries.json files you can compose freely in our dashboards.

State-level data is in here too — same endpoint, different `geo_layer`.

Fiscal year semantics: federal FY runs Oct 1 → Sep 30. So FY2024 =
2023-10-01 through 2024-09-30. Output points are anchored at Sep 30 of
the FY (end-of-FY).

Run with: ``python pipelines/usaspending.py``.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from common import write_timeseries


USA_URL = "https://api.usaspending.gov/api/v2/search/spending_by_geography/"

# State FIPS → (abbreviation, name). Used to convert the API's "shape_code"
# like "1710" (= IL state 17 + district 10) into our file-naming pattern.
US_STATES: dict[str, tuple[str, str]] = {
    "01": ("AL", "Alabama"), "02": ("AK", "Alaska"), "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"), "06": ("CA", "California"), "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"), "10": ("DE", "Delaware"), "11": ("DC", "District of Columbia"),
    "12": ("FL", "Florida"), "13": ("GA", "Georgia"), "15": ("HI", "Hawaii"),
    "16": ("ID", "Idaho"), "17": ("IL", "Illinois"), "18": ("IN", "Indiana"),
    "19": ("IA", "Iowa"), "20": ("KS", "Kansas"), "21": ("KY", "Kentucky"),
    "22": ("LA", "Louisiana"), "23": ("ME", "Maine"), "24": ("MD", "Maryland"),
    "25": ("MA", "Massachusetts"), "26": ("MI", "Michigan"), "27": ("MN", "Minnesota"),
    "28": ("MS", "Mississippi"), "29": ("MO", "Missouri"), "30": ("MT", "Montana"),
    "31": ("NE", "Nebraska"), "32": ("NV", "Nevada"), "33": ("NH", "New Hampshire"),
    "34": ("NJ", "New Jersey"), "35": ("NM", "New Mexico"), "36": ("NY", "New York"),
    "37": ("NC", "North Carolina"), "38": ("ND", "North Dakota"), "39": ("OH", "Ohio"),
    "40": ("OK", "Oklahoma"), "41": ("OR", "Oregon"), "42": ("PA", "Pennsylvania"),
    "44": ("RI", "Rhode Island"), "45": ("SC", "South Carolina"), "46": ("SD", "South Dakota"),
    "47": ("TN", "Tennessee"), "48": ("TX", "Texas"), "49": ("UT", "Utah"),
    "50": ("VT", "Vermont"), "51": ("VA", "Virginia"), "53": ("WA", "Washington"),
    "54": ("WV", "West Virginia"), "55": ("WI", "Wisconsin"), "56": ("WY", "Wyoming"),
}

# FY range. USAspending data is available from FY2008 forward. Current
# year computed dynamically; we include the current FY even if it's
# partial — the API returns YTD totals for in-progress years.
START_FY = 2008


def call_api(geo_layer: str, start_date: str, end_date: str) -> list[dict]:
    """POST to USAspending. Returns the `results` list."""
    body = json.dumps({
        "scope": "recipient_location",
        "geo_layer": geo_layer,
        "filters": {
            "time_period": [{"start_date": start_date, "end_date": end_date}],
        },
    })
    try:
        out = subprocess.run(
            ["curl", "-s", "-S", "--max-time", "120",
             "-H", "Content-Type: application/json",
             "-X", "POST", "-d", body, USA_URL],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    curl failed ({start_date}..{end_date} {geo_layer}): {e}",
              file=sys.stderr)
        return []
    try:
        parsed = json.loads(out.stdout)
    except json.JSONDecodeError:
        print(f"    bad JSON ({start_date}..{end_date} {geo_layer})",
              file=sys.stderr)
        return []
    return parsed.get("results", []) or []


def cd_slug(shape_code: str) -> str | None:
    """
    Convert USAspending's "1710" code → our slug "il_10".
    Some codes have non-standard formats (e.g. "98" for "at-large"
    territories); return None to skip those.
    """
    if not shape_code or len(shape_code) < 3:
        return None
    fips = shape_code[:2]
    dist = shape_code[2:]
    info = US_STATES.get(fips)
    if not info:
        return None
    abbr = info[0].lower()
    # Normalize district number: "01"->"01", "10"->"10", "00" (at-large)->"al"
    if dist == "00":
        dist_slug = "al"
    else:
        try:
            dist_slug = f"{int(dist):02d}"
        except ValueError:
            return None
    return f"{abbr}_{dist_slug}"


def main() -> int:
    current_year = datetime.now(timezone.utc).year
    # Include in-progress current FY too — partial data is still useful
    # for "where we're at right now."
    end_fy = current_year + 1 if datetime.now(timezone.utc).month >= 10 else current_year

    state_points: dict[str, list[dict]] = {}
    cd_points: dict[str, list[dict]] = {}
    state_names: dict[str, str] = {}
    cd_names: dict[str, str] = {}

    for fy in range(START_FY, end_fy + 1):
        # FY{n} starts Oct 1 of year n-1, ends Sep 30 of year n.
        start = f"{fy - 1}-10-01"
        end = f"{fy}-09-30"
        anchor = f"{fy}-09-30"
        print(f"FY{fy} ({start} -> {end})...", flush=True)

        for state in call_api("state", start, end):
            code = state.get("shape_code", "")
            amount = state.get("aggregated_amount")
            if not code or amount is None:
                continue
            # Store in billions of USD so values combine sanely with the
            # FRED macro series (us_real_gdp etc. are already in billions).
            # Raw-dollar magnitudes (~10^11) blew up combineTwo divides
            # by a factor of 10^9; rescaling here is the cheapest fix.
            state_points.setdefault(code, []).append(
                {"t": anchor, "v": float(amount) / 1e9}
            )
            state_names[code] = state.get("display_name", code)

        for cd in call_api("district", start, end):
            code = cd.get("shape_code", "")
            slug = cd_slug(code)
            amount = cd.get("aggregated_amount")
            if not slug or amount is None:
                continue
            cd_points.setdefault(slug, []).append(
                {"t": anchor, "v": float(amount) / 1e9}
            )
            cd_names[slug] = cd.get("display_name", slug)

    state_written = 0
    for code, points in state_points.items():
        points.sort(key=lambda p: p["t"])
        name = state_names.get(code, code)
        # We use lowercase state code as the file slug.
        write_timeseries(
            pipeline="usaspending",
            series_id=f"state_{code.lower()}",
            name=f"Federal spending in {name}",
            points=points,
            unit="USD",
        )
        state_written += 1
    print(f"State series: {state_written}", flush=True)

    # Single-CD states (AK, DE, ND, SD, VT, WY) and DC (delegate, code
    # 98) have one congressional "district" that's the same area as the
    # state. The district-level file would carry identical numbers to
    # the state-level file (usaspending/state_<st>), and we've
    # explicitly removed the source YAMLs for those redundant ones. Skip
    # writing them here too so the pipeline doesn't re-orphan the data.
    SINGLE_CD_REDUNDANT = {
        "ak_al", "de_al", "nd_al", "sd_al", "vt_al", "wy_al", "dc_98",
    }
    cd_written = 0
    cd_skipped_redundant = 0
    for slug, points in cd_points.items():
        if slug in SINGLE_CD_REDUNDANT:
            cd_skipped_redundant += 1
            continue
        points.sort(key=lambda p: p["t"])
        name = cd_names.get(slug, slug)
        write_timeseries(
            pipeline="usaspending",
            series_id=f"district_{slug}",
            name=f"Federal spending — {name}",
            points=points,
            unit="USD",
        )
        cd_written += 1
    print(f"CD series: {cd_written} (skipped {cd_skipped_redundant} single-CD-state AL/98 redundant with state-level)", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
