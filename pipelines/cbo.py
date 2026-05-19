"""
CBO (Congressional Budget Office) — Budget & Economic Outlook
projections + Historical Budget Data.

What we publish
---------------
Four headline fiscal-policy series, each carrying both history and the
most recently published 10-year projection (multiple vintages stack
under ``projections`` so the Forecast UI's eventual Phase-3 picker can
show successive Outlooks side-by-side):

  ``cbo_outlays_pct_gdp``   — Total federal outlays as % of GDP.
  ``cbo_revenues_pct_gdp``  — Total federal revenues as % of GDP.
  ``cbo_deficit_pct_gdp``   — Federal deficit as % of GDP (positive = deficit).
  ``cbo_debt_pct_gdp``      — Federal debt held by the public as % of GDP.

Why this is awkward
-------------------
CBO publishes their data exclusively as XLSX files behind their website
at cbo.gov/data/budget-economic-data. cbo.gov sits behind DataDome
anti-bot protection — direct HTTP requests from CI return HTTP 403. We
try anyway (sometimes the block is intermittent or scoped to particular
ASNs); if the fetch fails, we fall back to operator-supplied XLSX files
in ``pipelines/cbo_data/``.

Manual workflow
~~~~~~~~~~~~~~~
1. Browse to https://www.cbo.gov/data/budget-economic-data
2. Download the relevant XLSX files. Each goes into ``pipelines/cbo_data/``
   with a filename that encodes the vintage:
     - ``historical_<YYYY-MM>.xlsx`` — Historical Budget Data
     - ``outlook_<YYYY-MM>.xlsx``    — 10-Year Budget Projections (any
       Outlook release; one per release date)
3. Re-run ``python pipelines/cbo.py``. Each present file becomes one
   data refresh; vintages accumulate across CBO releases.

The directory is gitignored — see the ``pipelines/cbo_data/`` block in
``.gitignore``. Files there are operator artifacts, not part of the
repo.

License
-------
Per https://www.cbo.gov/about/copyright — "All CBO publications and the
data underlying them are in the public domain unless otherwise noted."

Run
---
  python pipelines/cbo.py
"""
from __future__ import annotations

import re
import sys
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pandas as pd

# Allow running as a script from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
from _cache import cache_get, cache_put  # noqa: E402
from common import write_timeseries  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent
MANUAL_DIR = REPO_ROOT / "pipelines" / "cbo_data"

# CBO XLSX content for a given release vintage doesn't change.
CACHE_MAX_AGE_DAYS = 365.0 * 100


# Federal fiscal years run Oct 1 -> Sept 30. Anchor each year's value
# to its end so the renderer's "as of today" check lines up with the
# most-recent completed FY.
def fy_to_date(fy: int) -> str:
    return f"{fy}-09-30"


@dataclass
class CboRelease:
    """One Outlook release whose projections we want to ingest as a
    distinct vintage."""

    # ISO month string, e.g. "2025-01". Used as the projection vintage
    # key in the output JSON.
    vintage: str
    # Filename on cbo.gov, used both for the download URL and the
    # manual-mode lookup. Update when CBO publishes a new outlook.
    projection_filename: str


# Most recent CBO Outlooks. Append new entries when fresh releases drop;
# older entries stay so the projections map accumulates history. The
# url-fetch path tries each entry; whichever ones succeed (or have a
# manual-mode XLSX present in cbo_data/) become vintages in the output.
RELEASES: list[CboRelease] = [
    CboRelease(vintage="2025-01", projection_filename="61104-2025-01-budget-projections.xlsx"),
    CboRelease(vintage="2024-06", projection_filename="61104-2024-06-budget-projections.xlsx"),
    CboRelease(vintage="2024-02", projection_filename="51119-2024-02-budget-projections.xlsx"),
]

# Historical Budget Data — pulled separately because CBO publishes it
# on a different cadence than the Outlook.
HISTORICAL_FILENAME = "51134-2025-01-Historical-Budget-Data.xlsx"
HISTORICAL_VINTAGE = "2025-01"


@dataclass
class CboSeries:
    out_id: str
    name: str
    # Row-label regex, matched case-insensitively against the first
    # text-bearing column of each row in the workbook.
    row_pattern: re.Pattern[str]


SERIES: list[CboSeries] = [
    CboSeries(
        out_id="cbo_outlays_pct_gdp",
        name="Federal outlays as % of GDP (CBO baseline)",
        row_pattern=re.compile(r"^\s*(Total\s+)?Outlays\s*$", re.I),
    ),
    CboSeries(
        out_id="cbo_revenues_pct_gdp",
        name="Federal revenues as % of GDP (CBO baseline)",
        row_pattern=re.compile(r"^\s*(Total\s+)?Revenues\s*$", re.I),
    ),
    CboSeries(
        out_id="cbo_deficit_pct_gdp",
        name="Federal deficit as % of GDP (CBO baseline)",
        # Headline row is "Deficit" or "Deficit (-) or Surplus".
        row_pattern=re.compile(r"^\s*Deficit", re.I),
    ),
    CboSeries(
        out_id="cbo_debt_pct_gdp",
        name="Federal debt held by the public as % of GDP (CBO baseline)",
        row_pattern=re.compile(r"^\s*Debt\s+Held\s+by\s+the\s+Public\s*$", re.I),
    ),
]


def fetch_xlsx(vintage: str, filename: str) -> bytes | None:
    """
    Try the URL first (cached), then fall back to ``pipelines/cbo_data/``
    for an operator-supplied copy. Manual filenames can be either the
    exact cbo.gov filename or our shorter ``outlook_<vintage>.xlsx``
    convention.
    """
    cache_key = f"{vintage}_{filename}"
    cached = cache_get("cbo_xlsx", cache_key, CACHE_MAX_AGE_DAYS, suffix=".xlsx")
    if cached is not None:
        return cached

    url = f"https://www.cbo.gov/system/files/{vintage}/{filename}"
    try:
        # Use a browser-like User-Agent. CBO's DataDome sometimes blocks
        # bare urllib UAs; sometimes it doesn't. No silver bullet; we
        # try, and fall through to manual mode on 403.
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet,*/*;q=0.8"
                ),
            },
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read()
        try:
            cache_put("cbo_xlsx", cache_key, body, suffix=".xlsx")
        except OSError as e:
            print(f"  cache write failed: {e}", file=sys.stderr)
        return body
    except Exception as e:
        print(f"  url fetch failed ({url}): {e}", file=sys.stderr)

    # Fallback: operator-supplied file. Look for either the exact CBO
    # filename or our short-vintage convention.
    if MANUAL_DIR.exists():
        candidates = [
            MANUAL_DIR / filename,
            MANUAL_DIR / f"outlook_{vintage}.xlsx",
            MANUAL_DIR / f"historical_{vintage}.xlsx",
        ]
        for p in candidates:
            if p.exists():
                print(f"  using manual upload: {p.name}", flush=True)
                return p.read_bytes()
    return None


def _extract_year(col: object) -> int | None:
    """Extract a 4-digit fiscal year from a column header. CBO tables
    mix int years, "YYYY", and "FY YYYY" headers."""
    s = str(col).strip()
    m = re.search(r"\b(19|20|21)\d{2}\b", s)
    return int(m.group(0)) if m else None


def _looks_like_pct_gdp_sheet(df: pd.DataFrame) -> bool:
    """Heuristic: the % GDP table contains our headline row labels
    (Outlays / Revenues / Deficit / Debt) with at least 5
    fiscal-year-shaped column headers."""
    if df.shape[0] < 5 or df.shape[1] < 5:
        return False
    year_cols = sum(1 for c in df.columns if _extract_year(c) is not None)
    if year_cols < 5:
        return False
    first_col = df.iloc[:, 0].astype(str)
    return any(
        first_col.str.match(spec.row_pattern, na=False).any()
        for spec in SERIES
    )


def find_pct_gdp_sheet(workbook: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    """Pick the sheet that looks like the % of GDP summary table."""
    by_name = sorted(
        workbook.items(),
        key=lambda kv: (
            0 if "gdp" in kv[0].lower() else 1,
            0 if "percent" in kv[0].lower() else 1,
            kv[0],
        ),
    )
    for _, df in by_name:
        if _looks_like_pct_gdp_sheet(df):
            return df
    return None


def parse_series_row(
    df: pd.DataFrame,
    spec: CboSeries,
) -> list[tuple[int, float]] | None:
    """Find the row matching ``spec.row_pattern`` and return
    [(year, value), ...] pairs from year-headered columns."""
    first_col = df.iloc[:, 0].astype(str)
    matches = first_col.str.match(spec.row_pattern, na=False)
    if not matches.any():
        return None
    row = df[matches].iloc[0]
    out: list[tuple[int, float]] = []
    for col, val in row.items():
        year = _extract_year(col)
        if year is None:
            continue
        try:
            v = float(str(val).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
        out.append((year, v))
    out.sort(key=lambda p: p[0])
    return out


def parse_workbook(body: bytes) -> dict[str, list[tuple[int, float]]] | None:
    """Open an XLSX and return {out_id: [(year, value), ...]} per
    series, or None on parse failure."""
    try:
        sheets = pd.read_excel(BytesIO(body), sheet_name=None, header=0)
    except Exception as e:
        print(f"  read_excel failed: {e}", file=sys.stderr)
        return None
    target = find_pct_gdp_sheet(sheets)
    if target is None:
        print(
            f"  could not locate %-GDP sheet; sheets present: "
            f"{list(sheets.keys())}",
            file=sys.stderr,
        )
        return None
    out: dict[str, list[tuple[int, float]]] = {}
    for spec in SERIES:
        pairs = parse_series_row(target, spec)
        if pairs:
            out[spec.out_id] = pairs
    return out if out else None


def main(argv: list[str] | None = None) -> int:
    wanted = set((argv or [])[1:])
    runs = [s for s in SERIES if not wanted or s.out_id in wanted]
    if not runs:
        print(
            f"No matches for {wanted}; available: {[s.out_id for s in SERIES]}",
            file=sys.stderr,
        )
        return 2

    # Per-series aggregators. Each series eventually carries:
    #   historical[id] = list of {t, v} actuals
    #   projections[id] = {vintage_str: list of {t, v}}
    historical: dict[str, list[dict]] = {s.out_id: [] for s in runs}
    projections: dict[str, dict[str, list[dict]]] = {s.out_id: {} for s in runs}

    # --- Historical actuals
    print(f"Fetching CBO Historical Budget Data ({HISTORICAL_FILENAME})...", flush=True)
    hist_body = fetch_xlsx(HISTORICAL_VINTAGE, HISTORICAL_FILENAME)
    if hist_body is None:
        print(
            "WARNING: could not fetch historical data; series will only "
            "have projections (if any).",
            file=sys.stderr,
        )
    else:
        parsed = parse_workbook(hist_body)
        if parsed:
            for spec in runs:
                for year, v in parsed.get(spec.out_id, []):
                    historical[spec.out_id].append(
                        {"t": fy_to_date(year), "v": round(v, 3)}
                    )

    # --- Projections — one vintage per Outlook release
    successful_vintages = 0
    for rel in RELEASES:
        print(f"Fetching CBO Outlook {rel.vintage} ({rel.projection_filename})...", flush=True)
        body = fetch_xlsx(rel.vintage, rel.projection_filename)
        if body is None:
            continue
        parsed = parse_workbook(body)
        if not parsed:
            continue
        successful_vintages += 1
        rel_year = int(rel.vintage[:4])
        for spec in runs:
            pairs = parsed.get(spec.out_id, [])
            if not pairs:
                continue
            proj_pts: list[dict] = []
            for year, v in pairs:
                if year >= rel_year:
                    proj_pts.append({"t": fy_to_date(year), "v": round(v, 3)})
            if proj_pts:
                projections[spec.out_id][rel.vintage] = proj_pts

    # --- Emit
    written = 0
    for spec in runs:
        pts = historical[spec.out_id]
        projs = projections[spec.out_id]
        # Dedupe historical by date.
        seen: dict[str, dict] = {p["t"]: p for p in pts}
        pts = sorted(seen.values(), key=lambda p: p["t"])
        if not pts and not projs:
            print(f"  {spec.out_id}: no data; skipping", file=sys.stderr)
            continue
        out = write_timeseries(
            pipeline="cbo",
            series_id=spec.out_id,
            name=spec.name,
            points=pts,
            unit="% of GDP",
            projections=projs if projs else None,
        )
        print(
            f"  {spec.out_id}: {len(pts)} historical + "
            f"{len(projs)} vintage(s) of projections -> {out}",
            flush=True,
        )
        written += 1

    print(f"\ncbo: wrote {written} series across {successful_vintages} Outlook vintages")
    if not written:
        print(
            "If all fetches failed, try the manual workflow: download the "
            "XLSX files from https://www.cbo.gov/data/budget-economic-data "
            "into pipelines/cbo_data/ and re-run.",
            file=sys.stderr,
        )
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
