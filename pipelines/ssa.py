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
   browser. For the 2025 report the suffixes we need are ``lr6g4``
   (cost & income / GDP) and ``lr4b3`` (workers per beneficiary).
   (For the 2024 report they were ``lr6F8`` and ``lr6F4``.)
2. Use the browser's "Save As" → Webpage Complete (or HTML Only).
3. Save into ``pipelines/ssa_data/`` with the filename
   ``<vintage>_<suffix>.html``, e.g. ``2025_lr6g4.html``.
4. Re-run ``python pipelines/ssa.py``.

``pipelines/ssa_data/`` is COMMITTED to the repo — ssa.gov 403s CI
fetches, so the saved HTML is the only way this data is reproducible.

Cached on disk via ``pipelines/_cache.py``: the Trustees Report
contents for a given year don't change once published, so each year's
URL response is cached effectively-permanently.

Run
---
  python pipelines/ssa.py
"""
from __future__ import annotations

import io
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
# lr6g4.html / lr4b3.html. We point at the 2025 paths below; if SSA
# renames again, update url_suffix in TABLES.
#
# CAUTION: the report body ALSO carries an in-chapter version of the
# GDP table (VI_G2_OASDHI_GDP.html in 2025) that looks right but
# contains PROJECTIONS ONLY — no "Historical data:" section. Pointing
# at it produces series with empty ``points``. Always use the
# "Long-Range Estimates" (lrXXX) pages, indexed at
# https://www.ssa.gov/oact/TR/<YEAR>/lrIndex.html — those include the
# historical actuals back to 1970.
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
    # Substring keywords that should ALL appear (case-insensitive) in
    # an HTML filename for it to be considered a manual-upload match
    # for this table. Lets the operator save the page with whatever
    # filename their browser defaults to (typically the page <title>)
    # rather than needing a specific naming convention. First file
    # whose name contains every keyword in this list is picked.
    filename_keywords: list[str]


# 2025 Trustees Report — Long-Range Estimates section. SSA renamed the
# chapter from VI.F to VI.G in the 2025 release, so the per-table file
# slugs changed too:
#
#   lr6g4.html  (was lr6F8.html)
#     "OASDI and HI Annual Income, Cost, and Balance as a Percentage
#     of GDP". Historical actuals back to 1970 plus the Low (I) /
#     Intermediate (II) / High (III) alternative projections to 2100.
#     We pull Historical + Intermediate. (NOT VI_G2_OASDHI_GDP.html —
#     that in-chapter table is projections-only; see the slug caution
#     above REPORT_YEAR.)
#
#   lr4b3.html  (was lr6F4.html)
#     "Covered Workers and Beneficiaries, Calendar Years 1970-2100".
#     Demographic-pressure ratio across the three alternatives.
# Note on alternatives + the value_header_pattern: SSA's pages put
# Low-cost / Intermediate / High-cost projections on the SAME table,
# split into ROW sections labeled "Intermediate:" / "Low-cost:" /
# "High-cost:" (or "Historical data:" for actuals). Columns DON'T
# carry the alternative label. So the value-header regex below picks
# the metric column (e.g. "OASDI Cost"); the parser tracks the
# active row-section and only collects rows from Historical + the
# Intermediate sections, discarding Low-cost and High-cost.
TABLES: list[SsaTableSpec] = [
    SsaTableSpec(
        out_id="oasdi_cost_pct_gdp",
        name="Social Security (OASDI) cost as % of GDP",
        unit="% of GDP",
        url_suffix="lr6g4.html",
        # Column header (pandas-flattened): "Percentage of GDP | OASDI | Cost b"
        value_header_pattern=re.compile(r"OASDI.*Cost", re.I | re.S),
        year_header_pattern=re.compile(r"Calendar year", re.I),
        scale=1.0,
        # Matches "OASDI and HI Annual Income, Cost, and Balance as a
        # Percentage of GDP — 2025 OASDI Trustees Report.html" — the
        # default filename a browser saves the page under (from its
        # <title>).
        filename_keywords=["percentage", "gdp"],
    ),
    SsaTableSpec(
        out_id="oasdi_income_pct_gdp",
        name="Social Security (OASDI) income as % of GDP",
        unit="% of GDP",
        # Same page + filename as oasdi_cost_pct_gdp: lr6g4.html carries
        # income, cost, AND balance as % of GDP (historical + projection).
        # Must NOT be the in-chapter VI_G2_OASDHI_GDP.html, which is
        # projections-only and was the original empty-points bug.
        url_suffix="lr6g4.html",
        # Column header: "Percentage of GDP | OASDI | Income"
        value_header_pattern=re.compile(r"OASDI.*Income", re.I | re.S),
        year_header_pattern=re.compile(r"Calendar year", re.I),
        scale=1.0,
        filename_keywords=["percentage", "gdp"],
    ),
    SsaTableSpec(
        out_id="oasdi_workers_per_beneficiary",
        name="Covered workers per OASDI beneficiary",
        unit="workers per beneficiary",
        url_suffix="lr4b3.html",
        # Pre-computed ratio column in the workers/beneficiaries table.
        # Full flattened header: "Covered workers per OASDI beneficiary
        # | Covered workers per OASDI beneficiary".
        value_header_pattern=re.compile(
            r"Covered\s+workers\s+per\s+OASDI\s+beneficiary",
            re.I | re.S,
        ),
        year_header_pattern=re.compile(r"Calendar year", re.I),
        scale=1.0,
        # Matches "Covered Workers and Beneficiaries — 2025 OASDI
        # Trustees Report.html".
        filename_keywords=["covered workers", "beneficiaries"],
    ),
]


MANUAL_DIR = ROOT / "pipelines" / "ssa_data"


def fetch_html(
    year: int,
    suffix: str,
    filename_keywords: list[str] | None = None,
) -> bytes | None:
    """
    Fetch an SSA Trustees Report HTML page as raw bytes. Tries the
    live URL first (cached); on the typical 403 from SSA's anti-bot
    we fall back to operator-supplied HTML files under
    ``pipelines/ssa_data/``. See module docstring for the manual
    workflow.

    Returns bytes (not str) because ``pandas.read_html`` via lxml
    refuses unicode strings that contain an in-document encoding
    declaration — and SSA's pages always include one. Passing the
    raw bytes lets lxml honor the declared encoding.

    ``filename_keywords``: optional list of substrings that must ALL
    appear (case-insensitive) in a candidate HTML filename for it to
    match. Lets the operator save the page with whatever filename
    their browser defaults to (typically the page <title>) rather
    than needing to rename to the SSA URL slug.
    """
    url = f"https://www.ssa.gov/oact/TR/{year}/{suffix}"
    cache_key = f"{year}_{suffix.replace('/', '_')}"
    cached = cache_get("ssa_tr_html", cache_key, CACHE_MAX_AGE_DAYS, suffix=".html")
    if cached is not None:
        return cached
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
        return body
    except Exception as e:
        print(f"  url fetch failed: {url}: {e}", file=sys.stderr)

    # Fallback: operator-supplied HTML. We try three discovery
    # strategies in order:
    #
    #   1. Exact-slug filenames matching SSA's URL convention,
    #      optionally prefixed with the report year:
    #        2025_lr6g4.html, 2025_lr4b3.html, etc.
    #   2. Browser-default filenames identified by keyword: any
    #      *.html file in MANUAL_DIR whose lowercase name contains
    #      every keyword in ``filename_keywords``. Lets the operator
    #      save without renaming — browsers default to the page
    #      <title>, which for these tables is descriptive enough.
    #
    # Strategy 1 wins if multiple files match because it's more
    # explicit; if it misses, strategy 2 covers it.
    if MANUAL_DIR.exists():
        stem = suffix.replace(".html", "")
        exact_candidates = [
            MANUAL_DIR / f"{year}_{stem}.html",
            MANUAL_DIR / f"{year}_{suffix}",
            MANUAL_DIR / suffix,
        ]
        for p in exact_candidates:
            if p.exists():
                print(f"  using manual upload: {p.name}", flush=True)
                return p.read_bytes()
        if filename_keywords:
            kws_lower = [kw.lower() for kw in filename_keywords]
            for p in MANUAL_DIR.glob("*.html"):
                name_lower = p.name.lower()
                if all(kw in name_lower for kw in kws_lower):
                    print(
                        f"  using manual upload by keyword match: {p.name} "
                        f"(matched {filename_keywords})",
                        flush=True,
                    )
                    return p.read_bytes()
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


def _try_year(cell: object) -> int | None:
    """Parse a 4-digit year from a cell value. Returns None for
    non-year cells (section labels, summary spans like '2025-99',
    blanks, etc.). Strict: requires the whole cell to be a single
    year value, not a year embedded in a longer string."""
    s = str(cell).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    # Must be a bare year (or "2025.0" — pandas parses int cells as
    # floats sometimes). Range spans like "2025-99" should not match
    # because they're cumulative-summary markers we want to skip.
    try:
        y = int(float(s))
    except (ValueError, TypeError):
        return None
    return y if 1900 < y < 2200 else None


def parse_table(
    html_bytes: bytes,
    spec: SsaTableSpec,
) -> tuple[list[dict], list[dict]] | None:
    """
    Parse a Trustees Report HTML page and return ``(historical_points,
    projection_points)`` for the spec's series. Returns None if the
    table or column couldn't be located.

    Structure SSA uses on these pages:
      - One big HTML <table> with multiple ROW SECTIONS labeled
        ``Historical data:``, ``Intermediate:``, ``Low-cost:``,
        ``High-cost:``. Each section repeats the same columns.
      - Some sections (the GDP page especially) end with a
        ``Summarized rates:`` rollup with rows labeled ``25-year``,
        ``50-year``, ``75-year`` — those are cumulative summary stats
        we skip.
      - The year column is sometimes col 0, sometimes col 1
        (depending on whether the leftmost level is a label-cell).
        We try each row's first two cells.

    We collect rows ONLY from the ``Historical data`` and
    ``Intermediate`` sections — that's the central-estimate scenario
    SSA's Office of the Chief Actuary presents as best-estimate.
    """
    try:
        # read_html on a bytes input lets lxml respect any in-document
        # encoding declaration (SSA's saved pages include one); passing
        # a unicode str triggers "Unicode strings with encoding
        # declaration are not supported".
        tables = pd.read_html(io.BytesIO(html_bytes), flavor="lxml")
    except Exception as e:
        print(f"  read_html failed: {e}", file=sys.stderr)
        return None
    if not tables:
        return None
    best = max(tables, key=lambda t: t.shape[0] * t.shape[1])
    cols_flat = [_flatten_column(c) for c in best.columns]
    value_col_idx = next(
        (
            i
            for i, c in enumerate(cols_flat)
            if spec.value_header_pattern.search(c)
        ),
        None,
    )
    if value_col_idx is None:
        print(
            f"  could not locate value column in {spec.out_id}; "
            f"value pattern was r'{spec.value_header_pattern.pattern}', "
            f"saw columns: {cols_flat}",
            file=sys.stderr,
        )
        return None

    historical: list[dict] = []
    projection: list[dict] = []
    # Section state: "historical" | "intermediate" | "skip" (low/high
    # cost OR a summarized-rates rollup we're walking past). Begins as
    # None until we see the first labeled section row; rows before any
    # section label are ignored.
    section: str | None = None
    SKIP_KEYWORDS = (
        "low-cost",
        "high-cost",
        "summarized",
        "25-year",
        "50-year",
        "75-year",
    )
    for _, row in best.iterrows():
        # Identify any section-label text in the leading cells.
        leading_cells = [str(row.iloc[j]).strip() for j in range(min(2, best.shape[1]))]
        label = ""
        for cell in leading_cells:
            if cell.lower() not in ("", "nan"):
                label = cell
                break
        ll = label.lower()
        if ll.startswith("historical data"):
            section = "historical"
            continue
        if ll.startswith("intermediate"):
            section = "intermediate"
            continue
        if any(ll.startswith(kw) for kw in SKIP_KEYWORDS):
            section = "skip"
            continue
        if section not in ("historical", "intermediate"):
            continue
        # Find year in the first two columns — whichever has a bare
        # 4-digit year wins. Skip cells that look like multi-year
        # range labels ("2025-99") since they're rollup markers.
        year: int | None = None
        for j in range(min(2, best.shape[1])):
            cand = _try_year(row.iloc[j])
            if cand is not None:
                year = cand
                break
        if year is None:
            continue
        val_raw = row.iloc[value_col_idx]
        try:
            value = float(str(val_raw).replace(",", "").strip()) * spec.scale
        except (ValueError, TypeError):
            continue
        if value != value:  # NaN
            continue
        point = {"t": f"{year}{ANCHOR_MONTH_DAY}", "v": round(value, 3)}
        # The "historical" section carries actuals; the "intermediate"
        # section carries the central-estimate projection. Use that
        # to split, rather than comparing year < REPORT_YEAR (which
        # double-counts: historical actuals overlap the report year).
        if section == "historical":
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
        # Specs sharing a URL also share filename keywords (we pick
        # the first spec's; they're identical when same URL).
        keywords = specs[0].filename_keywords if specs else None
        html = fetch_html(REPORT_YEAR, suffix, filename_keywords=keywords)
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
