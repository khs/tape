"""
Fetch Zillow Research data — home value (ZHVI) + rent (ZORI) indices.

Zillow publishes a structured set of CSV files at
files.zillowstatic.com/research/public_csvs/. No auth, no rate limit
in practice (they warn that CSV paths can change, so this pipeline
should be re-checked if a future run starts 404-ing).

We pull two indices at two geographies:
  - ZHVI (Zillow Home Value Index) — typical home value, monthly
    smoothed seasonal-adjusted.
  - ZORI (Zillow Observed Rent Index) — typical observed rent,
    repeat-rent weighted to housing stock.

Both at:
  - National (one US-wide value per month back to ~2000)
  - Top metros by population (~12 to cover DC + the big six markets
    + a few regional cities). Each metro is one source.

Output structure:
  public/data/zillow/<slug>.json   — one file per (index, geo)
                                       e.g. zhvi_national.json,
                                       zhvi_nyc.json, zori_dc.json

Source YAMLs are hand-authored in src/content/sources/zillow/ —
24 sources total, each pointing at one of the JSON files.

License: Per zillow.com/research/data/, "all data accessed and
downloaded from this page is free for public use by consumers,
media, analysts, academics and policymakers."

Run:
  python pipelines/zillow.py            # all
  python pipelines/zillow.py zhvi       # just home value
  python pipelines/zillow.py zori       # just rent
"""
from __future__ import annotations

import csv
import io
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow running as a script from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
from _cache import cache_get, cache_put  # noqa: E402
from common import write_timeseries  # noqa: E402

# Zillow's CSVs refresh monthly. Cache for 24h: a same-day re-run
# (e.g., dev iteration) skips the ~5MB download per index family.
# A real workflow refresh that's a month or more between runs
# will always go fetch (the cache will be stale).
CACHE_MAX_AGE_DAYS = 1.0

# Top US metros we surface. Zillow's "RegionName" column uses the
# canonical "City, ST" form (multi-CBSA metros prefixed with the
# primary city). Slugs are lowercase, hyphen-free for cleaner
# source-ID filenames.
METRO_LIST: list[tuple[str, str]] = [
    # (slug, Zillow RegionName)
    ("nyc", "New York, NY"),
    ("la", "Los Angeles, CA"),
    ("chicago", "Chicago, IL"),
    ("dallas", "Dallas, TX"),
    ("houston", "Houston, TX"),
    ("dc", "Washington, DC"),
    ("philadelphia", "Philadelphia, PA"),
    ("miami", "Miami, FL"),
    ("atlanta", "Atlanta, GA"),
    ("boston", "Boston, MA"),
    ("sf", "San Francisco, CA"),
    ("seattle", "Seattle, WA"),
]

# Zillow's CSV URL conventions. "uc_sfrcondo" = single-family +
# condo combined; "tier_0.33_0.67" = the 33rd-67th percentile band
# (Zillow's typical-value definition); "sm_sa_month" = smoothed,
# seasonally adjusted, monthly. ZORI uses "smoothed_month" instead.
ZHVI_METRO_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zhvi/"
    "Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
)
ZORI_METRO_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zori/"
    "Metro_zori_uc_sfrcondomfr_sm_month.csv"
)


@dataclass
class ZillowFetch:
    index_key: str  # "zhvi" or "zori"
    url: str
    human_label: str  # "Zillow Home Value Index"


FETCHES = [
    ZillowFetch("zhvi", ZHVI_METRO_URL, "Zillow Home Value Index"),
    ZillowFetch("zori", ZORI_METRO_URL, "Zillow Observed Rent Index"),
]


def download_csv(url: str) -> list[dict[str, str]]:
    """Fetch a CSV and return list of row dicts. Caches the raw
    CSV bytes for 24h — Zillow refreshes monthly so a same-day
    re-run (dev iteration, or CI retry) doesn't burn the
    download."""
    # Cache key = URL basename. Filesystem-safe; one Zillow CSV
    # per cache file.
    key = Path(url).name
    cached = cache_get("zillow_csv", key, CACHE_MAX_AGE_DAYS, suffix=".csv")
    if cached is not None:
        print(f"  cache hit: {key}", flush=True)
        body = cached.decode("utf-8", errors="replace")
    else:
        print(f"  fetching {url}", flush=True)
        r = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", "60", url],
            capture_output=True, check=True,
        )
        body_bytes = r.stdout
        cache_put("zillow_csv", key, body_bytes, suffix=".csv")
        body = body_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(body))
    return list(reader)


def row_to_points(row: dict[str, str]) -> list[dict[str, float | str]]:
    """Pivot a Zillow row from wide (one column per month) to
    long (list of {t, v}). Date columns look like 2000-01-31."""
    pts: list[dict[str, float | str]] = []
    for k, v in row.items():
        # Date columns are YYYY-MM-DD; skip the non-date metadata
        # columns (RegionID, SizeRank, RegionName, RegionType,
        # StateName).
        if not k or len(k) != 10 or k[4] != "-" or k[7] != "-":
            continue
        if v is None or v == "":
            continue
        try:
            pts.append({"t": k, "v": float(v)})
        except (TypeError, ValueError):
            continue
    return pts


def main(argv: list[str] | None = None) -> int:
    selected = set((argv or [])[1:])
    runs = [f for f in FETCHES if not selected or f.index_key in selected]
    if not runs:
        print(f"No matches for {selected}; available: zhvi, zori", file=sys.stderr)
        return 2

    total = 0
    for fetch in runs:
        rows = download_csv(fetch.url)
        if not rows:
            print(f"  {fetch.index_key}: empty CSV", file=sys.stderr)
            continue
        print(f"  {fetch.index_key}: {len(rows)} rows in CSV", flush=True)

        # Build a name → row lookup so we can find the metros we want.
        by_name: dict[str, dict[str, str]] = {
            row.get("RegionName", "").strip(): row for row in rows
        }

        # National row: Zillow exposes a single "United States" row in
        # the metro CSV at RegionType=country. Use that as our
        # national series so we don't fetch a separate file.
        national = next(
            (r for r in rows if r.get("RegionType") == "country"),
            None,
        )
        if national:
            pts = row_to_points(national)
            out = write_timeseries(
                pipeline="zillow",
                series_id=f"{fetch.index_key}_national",
                name=f"{fetch.human_label} — US national",
                points=pts,
                unit="USD" if fetch.index_key == "zhvi" else "USD/mo",
            )
            print(f"    national: {len(pts)} points -> {out}")
            total += 1

        # Per-metro:
        for slug, region_name in METRO_LIST:
            row = by_name.get(region_name)
            if not row:
                print(f"    {slug} ({region_name}): NOT FOUND in CSV", file=sys.stderr)
                continue
            pts = row_to_points(row)
            if not pts:
                print(f"    {slug}: 0 points", file=sys.stderr)
                continue
            out = write_timeseries(
                pipeline="zillow",
                series_id=f"{fetch.index_key}_{slug}",
                name=f"{fetch.human_label} — {region_name}",
                points=pts,
                unit="USD" if fetch.index_key == "zhvi" else "USD/mo",
            )
            print(f"    {slug}: {len(pts)} points -> {out}")
            total += 1

    print(f"\nWrote {total} Zillow data files.")
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
