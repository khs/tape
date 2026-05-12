"""
Treasury International Capital (TIC) — foreign holdings of US Treasury
securities, by country, monthly. Published by the US Treasury Department.

The unique value here: not on FRED, not on the World Bank, not on OECD.
This is the single most-asked-about cross-border financial flow for
policy/macro audiences — "is China dumping Treasuries?", "who's funding
US deficits?", etc.

Source URL is stable across publication cycles:
    https://ticdata.treasury.gov/Publish/mfhhis01.txt

File format is tab-separated. Year-blocks are stacked vertically; within
each year block, columns are months (Dec → Jan, right-to-left order),
rows are countries. We parse all year blocks into a single per-country
time series.

Run with: ``python pipelines/treasury_tic.py``.
"""
from __future__ import annotations

import re
import subprocess
import sys

from common import write_timeseries


TIC_URL = "https://ticdata.treasury.gov/Publish/mfhhis01.txt"

# Countries to extract from the TIC file. Names match the labels in the
# TIC text file EXACTLY (quotes, commas, capitalization). Mapped to
# clean output IDs we can use in YAML manifests.
COUNTRY_MAP: dict[str, tuple[str, str]] = {
    "Japan": ("japan", "Japan"),
    "United Kingdom": ("uk", "United Kingdom"),
    "China, Mainland": ("china", "China"),
    "Belgium": ("belgium", "Belgium"),
    "Canada": ("canada", "Canada"),
    "Luxembourg": ("luxembourg", "Luxembourg"),
    "Cayman Islands": ("cayman_islands", "Cayman Islands"),
    "France": ("france", "France"),
    "Ireland": ("ireland", "Ireland"),
    "Taiwan": ("taiwan", "Taiwan"),
    "Switzerland": ("switzerland", "Switzerland"),
    "Singapore": ("singapore", "Singapore"),
    "Hong Kong": ("hong_kong", "Hong Kong"),
    "Norway": ("norway", "Norway"),
    "India": ("india", "India"),
    "Brazil": ("brazil", "Brazil"),
    "Saudi Arabia": ("saudi_arabia", "Saudi Arabia"),
    "Korea, South": ("south_korea", "South Korea"),
    "Germany": ("germany", "Germany"),
    "Mexico": ("mexico", "Mexico"),
    "Netherlands": ("netherlands", "Netherlands"),
    "Australia": ("australia", "Australia"),
    "Sweden": ("sweden", "Sweden"),
    "Israel": ("israel", "Israel"),
    "Spain": ("spain", "Spain"),
    "Italy": ("italy", "Italy"),
    "Bermuda": ("bermuda", "Bermuda"),
    "Philippines": ("philippines", "Philippines"),
    "United Arab Emirates": ("uae", "United Arab Emirates"),
    "Thailand": ("thailand", "Thailand"),
    "Kuwait": ("kuwait", "Kuwait"),
    "Poland": ("poland", "Poland"),
    "Chile": ("chile", "Chile"),
    "Colombia": ("colombia", "Colombia"),
    "Peru": ("peru", "Peru"),
    "El Salvador": ("el_salvador", "El Salvador"),
    "Grand Total": ("grand_total", "Grand total (foreign)"),
}

# Month names → calendar month number, in the order Treasury prints them
# (Dec first, then Nov, …, Jan).
MONTH_ORDER = [
    ("Dec", 12),
    ("Nov", 11),
    ("Oct", 10),
    ("Sep", 9),
    ("Aug", 8),
    ("Jul", 7),
    ("Jun", 6),
    ("May", 5),
    ("Apr", 4),
    ("Mar", 3),
    ("Feb", 2),
    ("Jan", 1),
]


def fetch_tic() -> str:
    """Download the TIC major-foreign-holders text file."""
    print(f"Fetching {TIC_URL}...", flush=True)
    result = subprocess.run(
        ["curl", "-sS", "--max-time", "60", TIC_URL],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def parse_tic(body: str) -> dict[str, list[dict]]:
    """
    Parse the TIC tab-separated file into {country_label: [{t, v}, ...]}.

    The file has stacked year-blocks. Each block starts with a "Month"
    row (Dec, Nov, Jan), then a "Country YEAR YEAR ..." row, then
    a "------" separator, then country rows until a blank line.
    """
    out: dict[str, list[dict]] = {}
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        # Look for a Country-YYYY header row.
        m = re.match(r"^Country\t(\d{4})", lines[i])
        if not m:
            i += 1
            continue
        year = int(m.group(1))
        # Move past the "------" separator row.
        i += 1
        while i < len(lines) and lines[i].strip().startswith("---"):
            i += 1
        # Skip blank rows.
        while i < len(lines) and not lines[i].strip():
            i += 1
        # Country data rows until a blank line / next year block.
        while i < len(lines):
            row = lines[i]
            if not row.strip():
                break
            if row.startswith("Country\t") or row.strip().startswith("---"):
                break
            cols = row.split("\t")
            country = cols[0].strip()
            if country not in COUNTRY_MAP:
                i += 1
                continue
            # Columns 1..12 are Dec..Jan of that year. Some values can be
            # empty strings ("---") or footnote markers; skip those.
            for idx, (_, month_num) in enumerate(MONTH_ORDER, start=1):
                if idx >= len(cols):
                    break
                raw = cols[idx].strip()
                if not raw or raw == "---" or raw == "*" or "/" in raw:
                    continue
                try:
                    v = float(raw)
                except ValueError:
                    continue
                # End-of-month date; mid-month is misleading because
                # Treasury reports end-of-month holdings explicitly.
                t = f"{year:04d}-{month_num:02d}-15"
                out.setdefault(country, []).append({"t": t, "v": v})
            i += 1
    # Sort each series chronologically.
    for pts in out.values():
        pts.sort(key=lambda p: p["t"])
    return out


def main() -> int:
    body = fetch_tic()
    by_country = parse_tic(body)
    total = 0
    for label, points in by_country.items():
        out_id, display_name = COUNTRY_MAP[label]
        if not points:
            continue
        write_timeseries(
            pipeline="treasury_tic",
            series_id=out_id,
            name=f"{display_name} — US Treasury holdings",
            points=points,
            unit="billions USD",
        )
        print(f"  {out_id}: {len(points)} points, latest {points[-1]['t']} = {points[-1]['v']}")
        total += 1
    print(f"Treasury TIC: wrote {total} series", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
