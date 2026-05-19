"""
Social Security Trustees Report — historical actuals + 75-year
long-range projection for the OASDI program.

What we publish
---------------
Each annual Trustees Report carries a long-range financial projection
covering the next 75 years under three economic assumption sets
("alternatives"): low-cost (I), intermediate (II), and high-cost (III).
We publish the INTERMEDIATE-COST scenario (alternative II) — it's what
the SSA Office of the Chief Actuary presents as their best estimate
and what nearly every external commentator cites.

Each source ships in two parts:
  ``points``      — historical actuals (back to ~1970).
  ``projections`` — one map entry per Trustees Report year (vintage).
                    Each entry's array is the 75-year intermediate-cost
                    projection as published in that year's report.

Multiple vintages let a future "as of" picker show how the projection
has shifted from one year's report to the next — the headline story
for SSA solvency-watchers is that successive reports have been pushing
the trust-fund-depletion year forward and back as economic assumptions
evolve.

Headline series
---------------
  ``oasdi_cost_pct_gdp``        — Combined OASI+DI cost as % of GDP.
                                   Most-cited solvency metric.
  ``oasdi_income_pct_gdp``      — Combined cost as % of GDP. Gap with
                                   cost-rate is the funding shortfall.
  ``oasdi_workers_per_beneficiary`` — Covered workers per OASDI
                                   beneficiary. The classic "demographic
                                   pressure" indicator.

Data source
-----------
SSA Trustees Report Long-Range Estimates, published annually at
https://www.ssa.gov/oact/TR/<YEAR>/.

The Tables are HTML-rendered on SSA's site (no CSV / XLSX feed). This
pipeline uses ``pandas.read_html`` to parse them. URLs are stable
year-to-year — to add a new vintage when the next report drops,
increment ``REPORT_YEAR`` and re-run.

Direct HTTP fetches to ssa.gov return HTTP 403 even with a browser
User-Agent — they run anti-bot protection across the whole site. We
try first; on failure we fall back to operator-supplied HTML files in
``pipelines/ssa_data/``.

Manual workflow
~~~~~~~~~~~~~~~
1. Open ``https://www.ssa.gov/oact/TR/<YEAR>/<SUFFIX>.html`` in a
   browser. For the 2024 report the suffixes we need are ``lr6F8``
   (cost & income / GDP) and ``lr6F4`` (workers per beneficiary).
2. Use the browser's "Save As" → Webpage Complete (or HTML Only).
3. Save into ``pipelines/ssa_data/`` with the filename
   ``<vintage>_<suffix>.html``, e.g. ``2024_lr6F8.html``.
4. Re-run ``python pipelines/ssa.py``.

``pipelines/ssa_data/`` is gitignored — operator artifact, not part
of the repo.

Cached on disk via ``pipelines/_cache.py``: the Trustees Report
contents for a given year don't change once published, so each year's
URL response is cached effectively-permanently.

Run
---
  python pipelines/ssa.py
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Allow running as a script from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
from _cache import cache_get, cache_put  # noqa: E402
from common import write_timeseries  # noqa: E402


# Bump this when the next Trustees Report drops (typically May/June each
# year). The most recent intermediate-cost projection becomes the
# default "latest vintage" the Forecast UI Phase 2 renderer shows as
# the dashed continuation.
#
# Note on file slugs: SSA renumbered the chapter in the 2025 report
# (VI.F -> VI.G), so the per-table URL paths changed too. Older
# vintages (2024 and earlier) used lr6F8 / lr6F4; 2025 uses
# VI_G2_OASDHI_GDP.html / lr4b3.html. We point at the 2025 paths
# below; if SSA renames again, update url_suffix in TABLES.
REPORT_YEAR = 2025

# Trustees Report data tables don't change once published. Cache the
# raw HTML fetches for effectively permanent durations (cache key
# encodes the year so a new vintage doesn't pollute old ones).
CACHE_MAX_AGE_DAYS = 365.0 * 100

# Anchor every annual value to mid-year so the projection segment
# renders at a stable visual cadence.
ANCHOR_MONTH_DAY = "-07-01"


@dataclass
class SsaTableSpec:
    """One Trustees-Report HTML table to scrape."""

    out_id: str
    name: str
    unit: str
    # Path under www.ssa.gov/oact/TR/<year>/, e.g. "lr6F8.html". Tables
    # are numbered by report section.
    url_suffix: str
    # Header keyword that uniquely identifies the column we want among
    # the table's columns. Tables have alternative columns (I, II, III)
    # — match the intermediate-cost (II) column.
    value_header_pattern: re.Pattern[str]
    # Year-column header pattern. Usually just "Year".
    year_header_pattern: re.Pattern[str]
    # Multiplier applied to parsed values before write. Used when the
    # source table reports figures that need scaling (e.g., a table
    # in percent should stay in percent; one in ratio×100 -> ratio).
    scale: float


# 2025 Trustees Report — Long-Range Estimates section. SSA renamed the
# chapter from VI.F to VI.G in the 2025 release, so the per-table file
# slugs changed too:
#
#   VI_G2_OASDHI_GDP.html  (was lr6F8.html)
#     "Estimates as a Percentage of Gross Domestic Product, Calendar
#     Years 1970-2100". OASDI cost rate + income rate, with separate
#     blocks for the Low (I) / Intermediate (II) / High (III)
#     economic-assumption alternatives. We pull Intermediate.
#
#   lr4b3.html  (was lr6F4.html)
#     "Covered Workers and Beneficiaries, Calendar Years 1970-2100".
#     Demographic-pressure ratio across the three alternatives.
TABLES: list[SsaTableSpec] = [
    SsaTableSpec(
        out_id="oasdi_cost_pct_gdp",
        name="Social Security (OASDI) cost as % of GDP",
        unit="% of GDP",
        url_suffix="VI_G2_OASDHI_GDP.html",
        value_header_pattern=re.compile(r"OASDI[^|]*Cost.*Intermediate", re.I | re.S),
        year_header_pattern=re.compile(r"Year", re.I),
        scale=1.0,
    ),
    SsaTableSpec(
        out_id="oasdi_income_pct_gdp",
        name="Social Security (OASDI) income as % of GDP",
        unit="% of GDP",
        url_suffix="VI_G2_OASDHI_GDP.html",
        value_header_pattern=re.compile(r"OASDI[^|]*Income.*Intermediate", re.I | re.S),
        year_header_pattern=re.compile(r"Year", re.I),
        scale=1.0,
    ),
    SsaTableSpec(
        out_id="oasdi_workers_per_beneficiary",
        name="Covered workers per OASDI beneficiary",
        unit="workers per beneficiary",
        url_suffix="lr4b3.html",
        value_header_pattern=re.compile(r"Intermediate", re.I),
        year_header_pattern=re.compile(r"Year", re.I),
        scale=1.0,
    ),
]


MANUAL_DIR = ROOT / "pipelines" / "ssa_data"


def fetch_html(year: int, suffix: str) -> str | None:
    """
    Fetch an SSA Trustees Report HTML page. Tries the live URL first
    (cached); on the typical 403 from SSA's anti-bot we fall back to
    operator-supplied HTML files under ``pipelines/ssa_data/``. See
    module docstring for the manual workflow.
    """
    url = f"https://www.ssa.gov/oact/TR/{year}/{suffix}"
    cache_key = f"{year}_{suffix.replace('/', '_')}"
    cached = cache_get("ssa_tr_html", cache_key, CACHE_MAX_AGE_DAYS, suffix=".html")
    if cached is not None:
        return cached.decode("utf-8", errors="replace")
    try:
        import urllib.request

        # SSA blocks most non-browser UAs (403). We still try with a
        # browser UA in case the block is intermittent or scoped — but
        # the practical fallback is the manual-upload directory below.
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,*/*;q=0.8"
                ),
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
        try:
            cache_put("ssa_tr_html", cache_key, body, suffix=".html")
        except OSError as e:
            print(f"  cache write failed: {e}", file=sys.stderr)
        return body.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  url fetch failed: {url}: {e}", file=sys.stderr)

    # Fallback: operator-supplied HTML. Filename convention is
    # ``<year>_<suffix-stem>.html`` — strip the .html so both
    # ``2024_lr6F8.html`` and the legacy ``2024_lr6F8.html.html``
    # both resolve.
    if MANUAL_DIR.exists():
        stem = suffix.replace(".html", "")
        candidates = [
            MANUAL_DIR / f"{year}_{stem}.html",
            MANUAL_DIR / f"{year}_{suffix}",
            MANUAL_DIR / suffix,
        ]
        for p in candidates:
            if p.exists():
                print(f"  using manual upload: {p.name}", flush=True)
                return p.read_text(encoding="utf-8", errors="replace")
    return None


def _flatten_column(col: object) -> str:
    """Flatten a pandas MultiIndex column tuple to a single string for
    pattern-matching. read_html on SSA's tables produces MultiIndex
    columns (alternative-name on one level, value-type on another)."""
    if isinstance(col, tuple):
        # Drop unnamed levels (read_html emits 'Unnamed: 0_level_0' etc.).
        parts = [str(c) for c in col if not str(c).startswith("Unnamed:")]
        return " | ".join(parts)
    return str(col)


def parse_table(
    html: str,
    spec: SsaTableSpec,
) -> tuple[list[dict], list[dict]] | None:
    """
    Parse a Trustees Report HTML page and return (historical_points,
    projection_points) for the spec's series. Returns None if the
    table or column couldn't be located.
    """
    try:
        # read_html returns a list of every <table> on the page; the
        # long-range tables we want are usually the largest one (~130
        # rows). Pick by row-count.
        tables = pd.read_html(html, flavor="lxml")
    except Exception as e:
        print(f"  read_html failed: {e}", file=sys.stderr)
        return None
    if not tables:
        return None
    best = max(tables, key=lambda t: t.shape[0] * t.shape[1])
    cols_flat = [_flatten_column(c) for c in best.columns]
    # Locate year + value columns by regex.
    year_col_idx = next(
        (i for i, c in enumerate(cols_flat) if spec.year_header_pattern.search(c)),
        None,
    )
    value_col_idx = next(
        (i for i, c in enumerate(cols_flat) if spec.value_header_pattern.search(c)),
        None,
    )
    if year_col_idx is None or value_col_idx is None:
        print(
            f"  could not locate columns in {spec.out_id}; saw: "
            f"{cols_flat[:10]}...",
            file=sys.stderr,
        )
        return None
    historical: list[dict] = []
    projection: list[dict] = []
    for _, row in best.iterrows():
        year_raw = row.iloc[year_col_idx]
        val_raw = row.iloc[value_col_idx]
        try:
            year = int(float(str(year_raw).strip()))
        except (ValueError, TypeError):
            continue
        try:
            value = float(str(val_raw).replace(",", "").strip()) * spec.scale
        except (ValueError, TypeError):
            continue
        if not (1900 < year < 2200):
            continue
        point = {"t": f"{year}{ANCHOR_MONTH_DAY}", "v": round(value, 3)}
        # SSA's Trustees Report tables include both historical actuals
        # and projected values in the same column, with the projection
        # starting in the report year. Split on that boundary.
        if year < REPORT_YEAR:
            historical.append(point)
        else:
            projection.append(point)
    historical.sort(key=lambda p: p["t"])
    projection.sort(key=lambda p: p["t"])
    return historical, projection


def main(argv: list[str] | None = None) -> int:
    wanted = set((argv or [])[1:])
    runs = [s for s in TABLES if not wanted or s.out_id in wanted]
    if not runs:
        print(
            f"No matches for {wanted}; available: "
            f"{[s.out_id for s in TABLES]}",
            file=sys.stderr,
        )
        return 2

    # Group specs by URL suffix so we only fetch each Trustees-Report
    # page once even when multiple series come from the same table.
    by_url: dict[str, list[SsaTableSpec]] = {}
    for spec in runs:
        by_url.setdefault(spec.url_suffix, []).append(spec)

    errors = 0
    written = 0
    for suffix, specs in by_url.items():
        html = fetch_html(REPORT_YEAR, suffix)
        if html is None:
            print(f"  no HTML for {suffix}; skipping {[s.out_id for s in specs]}", file=sys.stderr)
            errors += len(specs)
            continue
        for spec in specs:
            parsed = parse_table(html, spec)
            if parsed is None:
                errors += 1
                continue
            historical, projection = parsed
            if not historical and not projection:
                print(f"  {spec.out_id}: parse produced 0 points", file=sys.stderr)
                errors += 1
                continue
            projections = (
                {str(REPORT_YEAR): projection} if projection else None
            )
            out = write_timeseries(
                pipeline="ssa",
                series_id=spec.out_id,
                name=spec.name,
                points=historical,
                unit=spec.unit,
                projections=projections,
            )
            print(
                f"  {spec.out_id}: "
                f"{len(historical)} historical + "
                f"{len(projection)} projected -> {out}",
                flush=True,
            )
            written += 1

    print(f"\nssa: wrote {written} series, {errors} errors")
    return 1 if errors and not written else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
