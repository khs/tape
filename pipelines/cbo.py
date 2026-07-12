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
CBO publishes their data exclusively as XLSX files at
cbo.gov/data/budget-economic-data, behind DataDome anti-bot
protection — direct CI fetches return HTTP 403. The workflow is
operator-driven: the operator downloads files in a browser and drops
them in ``pipelines/cbo_data/`` (committed to the repo — cbo.gov blocks CI
fetches, so the raw files are the only way this data is reproducible), then
runs this pipeline.

Manual workflow
~~~~~~~~~~~~~~~
1. Browse to https://www.cbo.gov/data/budget-economic-data
2. Each "Budget and Economic Outlook" release ships a data appendix
   under publication ID **51118** (filename
   ``51118-YYYY-MM-...-budgetprojections.xlsx`` or
   ``...-Budget-Projections.xlsx`` depending on era). Download as many
   release vintages as you want — each becomes one entry under
   ``projections`` in the output JSON.
3. Drop the files in ``pipelines/cbo_data/`` with their original
   filenames (we infer the vintage from the ``51118-YYYY-MM`` prefix).
4. Run ``python pipelines/cbo.py``.

Each Outlook file contributes:
  - The first year column ("Actual, YYYY") -> historical point in
    ``points`` for that fiscal year. When multiple vintages report
    overlapping actuals, the newest revision wins.
  - The remaining 10-11 year columns -> projection segment under
    ``projections[<YYYY-MM>]`` for that vintage.

What the parser extracts
~~~~~~~~~~~~~~~~~~~~~~~~
From the workbook's "Table 1-1" sheet (Baseline Budget Projections),
the parser walks rows looking for the "As a percentage of GDP" marker
and tracks Revenues / Outlays section headers to pluck four target
rows: revenues Total, outlays Total, "Total deficit (-)", and "Debt
held by the public". See ``parse_table_1_1`` for the gritty bits.

Supported vintages: any 51118- file whose Table 1-1 sheet uses the
standard layout (2012 onward). Older releases (.xls) work with xlrd
installed. The 2018-04 release is an outlier — it uses tables 2-2 /
2-4 instead of 1-1, and is silently skipped with a per-vintage error.

Historical coverage caveat
~~~~~~~~~~~~~~~~~~~~~~~~~~
Each 51118- Outlook only includes ONE actual year (the most recent
completed FY). With N vintages on disk you get N historical points,
sparsely spaced. For a continuous 1962-onward historical line, drop
in CBO's "Historical Budget Data" (publication ID 51134) — the parser
ignores it today but extending to cover it would be modest.

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
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Allow running as a script from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
from common import write_timeseries  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent
MANUAL_DIR = REPO_ROOT / "pipelines" / "cbo_data"


# Federal fiscal years run Oct 1 -> Sept 30. Anchor each year's value
# to its end so the renderer's "as of today" check lines up with the
# most-recent completed FY.
def fy_to_date(fy: int) -> str:
    return f"{fy}-09-30"


@dataclass
class CboSeries:
    """One headline series we pull from Table 1-1.

    Each series_id corresponds to one row in Table 1-1's % of GDP
    block. Section + label tracking in parse_table_1_1() identifies the
    right row even though "Total" appears twice in the same block
    (once under Revenues, once under Outlays).
    """

    out_id: str
    name: str


SERIES: list[CboSeries] = [
    CboSeries(
        out_id="cbo_outlays_pct_gdp",
        name="Federal outlays as % of GDP (CBO baseline)",
    ),
    CboSeries(
        out_id="cbo_revenues_pct_gdp",
        name="Federal revenues as % of GDP (CBO baseline)",
    ),
    CboSeries(
        out_id="cbo_deficit_pct_gdp",
        name="Federal deficit as % of GDP (CBO baseline)",
    ),
    CboSeries(
        out_id="cbo_debt_pct_gdp",
        name="Federal debt held by the public as % of GDP (CBO baseline)",
    ),
]


def _extract_year(cell: object) -> int | None:
    """Extract a 4-digit fiscal year from a cell value. CBO header
    cells use a mix of int years, "YYYY", and "Actual,\\nYYYY" (with
    embedded newline + label)."""
    s = str(cell).strip()
    m = re.search(r"\b(19|20|21)\d{2}\b", s)
    if not m:
        return None
    y = int(m.group(0))
    return y if 1900 <= y <= 2200 else None


def parse_table_1_1(
    df: pd.DataFrame,
) -> tuple[dict[str, list[tuple[int, float]]], int] | None:
    """Parse a CBO Outlook "Table 1-1" sheet.

    Returns ``(series_data, actual_year)`` where ``series_data`` is
    ``{series_id: [(year, value_pct_gdp), ...]}`` and ``actual_year``
    is the most-recent-completed FY (the first year column in the
    table; remaining year columns are 10- or 11-year projections).
    Returns None on parse failure.

    Table 1-1 structure (consistent across 2012-2026 vintages):
      Row N:      "Table 1-1. CBO's Baseline Budget Projections..."
      Row N+1-3:  Year header — one column per year. First year is
                  most-recent FY actual; the rest are projections.
      Row M:      "In billions of dollars" — first data block, dollar
                  amounts.
      Rows M+1+:  Revenues / Outlays / Deficit / Debt / GDP rows in
                  dollar amounts.
      Row P:      "As a percentage of (gross domestic product|GDP)" —
                  second data block, % of GDP. THIS is what we want.
      Rows P+1+:  same five-row structure, in % of GDP.

    "Total" appears twice in the % block (once under Revenues, once
    under Outlays); section tracking disambiguates.
    """
    # 1. Find year-header row: first row whose cells contain >= 5
    # four-digit years. CBO files include the year-row 1-3 rows below
    # the table-title row, so we scan from the top.
    year_row: int | None = None
    for i in range(min(20, len(df))):
        cells = df.iloc[i].tolist()
        if sum(1 for c in cells if _extract_year(c) is not None) >= 5:
            year_row = i
            break
    if year_row is None:
        return None

    # 2. Map each year-bearing column to its year. Some older releases
    # tack on multi-year SUM columns at the end ("2013-2017", "2013-2022")
    # whose header still contains a 4-digit year that re-collides with an
    # earlier annual column. Keep only the first occurrence of each year
    # so the sum columns don't double-write annual values.
    year_for_col: dict[int, int] = {}
    seen_years: set[int] = set()
    for col_idx in range(df.shape[1]):
        y = _extract_year(df.iloc[year_row, col_idx])
        if y is not None and y not in seen_years:
            year_for_col[col_idx] = y
            seen_years.add(y)
    if not year_for_col:
        return None

    # CBO convention: first year column is "actual" (most recent
    # completed FY), remaining columns are 10- or 11-year projections.
    actual_year = year_for_col[min(year_for_col.keys())]

    # 3. Locate the "as a percentage of GDP" marker row anywhere after
    # the year row. Wording shifted across releases — 2024 said
    # "As a percentage of gross domestic product", 2026 said
    # "As a percentage of GDP" — so match either. Position varies:
    # modern releases put the marker in col 0 or col 1, but pre-2018
    # releases tucked it into col 4 (the first data column). Scan
    # every column.
    pct_row: int | None = None
    for i in range(year_row + 1, len(df)):
        for j in range(df.shape[1]):
            cell = str(df.iloc[i, j]).lower()
            if "percent" in cell and ("gdp" in cell or "domestic" in cell):
                pct_row = i
                break
        if pct_row is not None:
            break
    if pct_row is None:
        return None

    # 4. Walk rows after the marker, tracking which section header
    # ("Revenues" / "Outlays") we're inside. The Totals can appear in
    # two row layouts depending on vintage:
    #
    # Modern (2021+): row's col 0 holds the label, e.g.:
    #     row N:    "Revenues"
    #     ...
    #     row N+M:  "Total"          (this is the row we want)
    #     row N+M+1:"On-budget"
    #
    # Old (2012-2016): row's col 1 holds the sub-item labels and the
    # Total row is UNLABELED (col 0 + col 1 both NaN), distinguished
    # only by being the first numeric row after the section header that
    # carries no label:
    #     row N:    "Revenues"          (col 0)
    #     row N+1:  ""        "Indiv income taxes"  (col 1 label)
    #     ...
    #     row N+5:  ""        ""        "____"         (underline marker)
    #     row N+6:  ""        ""        15.40           (THIS is Total)
    #     row N+7:  ""        ""        11.62           (On-budget)
    #
    # We detect both. ``section_total_taken`` flips once we've claimed
    # the Total for the active section, so the unlabeled On-budget /
    # Off-budget rows that follow don't get misclassified.
    section: str | None = None
    section_total_taken: bool = False
    found: dict[str, int | None] = {
        "cbo_revenues_pct_gdp": None,
        "cbo_outlays_pct_gdp": None,
        "cbo_deficit_pct_gdp": None,
        "cbo_debt_pct_gdp": None,
    }

    def _row_has_numeric_in_year_cols(row_idx: int) -> bool:
        for col_idx in year_for_col:
            v = df.iloc[row_idx, col_idx]
            try:
                f = float(str(v).replace(",", "").strip())
                if f == f:
                    return True
            except (ValueError, TypeError):
                continue
        return False

    for i in range(pct_row + 1, len(df)):
        label = str(df.iloc[i, 0]).strip().lower()
        sub_label = (
            str(df.iloc[i, 1]).strip().lower() if df.shape[1] > 1 else ""
        )
        # End of table.
        if label.startswith("back to ") or label.startswith("source") or label.startswith("note:"):
            break
        if label == "revenues":
            section = "revenues"
            section_total_taken = False
            continue
        if label == "outlays":
            section = "outlays"
            section_total_taken = False
            continue
        # Deficit + Debt rows are always labeled in col 0; the wording
        # varies (2024+: "Total deficit (-)"; 2012-2016: "Deficit (-) or
        # Surplus"). Match either.
        if (
            "total deficit" in label
            or label.startswith("deficit (-)")
        ) and found["cbo_deficit_pct_gdp"] is None:
            found["cbo_deficit_pct_gdp"] = i
            section = None
            continue
        if (
            "debt held by the public" in label
            and found["cbo_debt_pct_gdp"] is None
        ):
            found["cbo_debt_pct_gdp"] = i
            section = None
            continue
        # Modern-layout: explicit "Total" label in col 0.
        if label == "total":
            if section == "revenues" and found["cbo_revenues_pct_gdp"] is None:
                found["cbo_revenues_pct_gdp"] = i
                section_total_taken = True
            elif section == "outlays" and found["cbo_outlays_pct_gdp"] is None:
                found["cbo_outlays_pct_gdp"] = i
                section_total_taken = True
            continue
        # Old-layout: while we're inside Revenues/Outlays and haven't
        # claimed a Total yet, look for the first row that's unlabeled
        # in col 0 AND col 1 AND carries numeric data in the year
        # columns. The underline-marker rows ("____") fail the numeric
        # check so we skip them naturally.
        if (
            section in ("revenues", "outlays")
            and not section_total_taken
            and (not label or label == "nan")
            and (not sub_label or sub_label == "nan")
            and _row_has_numeric_in_year_cols(i)
        ):
            if section == "revenues":
                found["cbo_revenues_pct_gdp"] = i
            else:
                found["cbo_outlays_pct_gdp"] = i
            section_total_taken = True
            continue

    # 5. Extract year-value pairs for each found row.
    result: dict[str, list[tuple[int, float]]] = {}
    for series_id, row_idx in found.items():
        if row_idx is None:
            continue
        pairs: list[tuple[int, float]] = []
        for col_idx, year in year_for_col.items():
            v = df.iloc[row_idx, col_idx]
            try:
                v_f = float(str(v).replace(",", "").strip())
                if v_f == v_f:  # not NaN
                    pairs.append((year, v_f))
            except (ValueError, TypeError):
                continue
        if pairs:
            pairs.sort()
            result[series_id] = pairs

    return result, actual_year


def vintage_from_filename(name: str) -> str | None:
    """CBO's filenames embed the release date as ``51118-YYYY-MM-...``.
    Some older releases use four-segment form (e.g.
    ``51118-2021-02-11-budgetprojections.xlsx`` with a day component);
    we still want the YYYY-MM prefix as the vintage stamp."""
    m = re.match(r"^\d+-(\d{4}-\d{2})", name)
    return m.group(1) if m else None


def parse_historical_1a(
    df: pd.DataFrame,
) -> dict[str, list[tuple[int, float]]] | None:
    """Parse the "1a. Rev, Outlays, Surplus (GDP)" sheet of CBO's
    Historical Budget Data (publication 51134).

    Schema is much cleaner than the 51118 Outlook sheets: long-format
    with one row per fiscal year and named columns at a known position.

    Layout (consistent across releases):

      row N-1:  super-header for the multi-column "Deficit (-) or
                surplus" group (On-budget / Social Security /
                Postal Service / Total)
      row N:    primary column headers: ``[ ,Revenues,Outlays,
                On-budget,Social Security,Postal Service,Total,
                Debt held by the public]``
      row N+1+: data, col 0 = fiscal year (1962 through latest FY)

    We pick the four target columns by header text. The "Total" column
    is the TOTAL deficit (sum of the sub-deficit columns) — there is
    only one column literally labeled "Total", so the match is
    unambiguous within this sheet.
    """
    # 1. Find header row: col 1 starts with "Revenues" AND col 2 starts
    # with "Outlays". CBO's sheet titles + intro rows vary in count,
    # so we scan dynamically.
    header_row: int | None = None
    for i in range(min(20, len(df))):
        c1 = (
            str(df.iloc[i, 1]).strip().lower()
            if df.shape[1] > 1
            else ""
        )
        c2 = (
            str(df.iloc[i, 2]).strip().lower()
            if df.shape[1] > 2
            else ""
        )
        if c1.startswith("revenue") and c2.startswith("outlay"):
            header_row = i
            break
    if header_row is None:
        return None

    # 2. Pick the target columns by header text.
    col_for_series: dict[str, int] = {}
    for j in range(df.shape[1]):
        header = str(df.iloc[header_row, j]).strip().lower()
        if (
            header.startswith("revenue")
            and "cbo_revenues_pct_gdp" not in col_for_series
        ):
            col_for_series["cbo_revenues_pct_gdp"] = j
        elif (
            header.startswith("outlay")
            and "cbo_outlays_pct_gdp" not in col_for_series
        ):
            col_for_series["cbo_outlays_pct_gdp"] = j
        elif (
            header == "total"
            and "cbo_deficit_pct_gdp" not in col_for_series
        ):
            col_for_series["cbo_deficit_pct_gdp"] = j
        elif (
            "debt held by the public" in header
            and "cbo_debt_pct_gdp" not in col_for_series
        ):
            col_for_series["cbo_debt_pct_gdp"] = j

    if len(col_for_series) < 4:
        print(
            f"  parse_historical_1a: missing target columns. Found: "
            f"{list(col_for_series.keys())}. Header row labels: "
            f"{[str(df.iloc[header_row, j])[:20] for j in range(df.shape[1])]}",
            file=sys.stderr,
        )
        return None

    # 3. Walk data rows. Col 0 = fiscal year as int/string; skip
    # non-year rows (the footer source line, blank rows).
    result: dict[str, list[tuple[int, float]]] = {
        sid: [] for sid in col_for_series
    }
    for i in range(header_row + 1, len(df)):
        year_cell = df.iloc[i, 0]
        try:
            year = int(float(str(year_cell).strip()))
        except (ValueError, TypeError):
            continue
        if not (1900 <= year <= 2200):
            continue
        for sid, col_idx in col_for_series.items():
            v = df.iloc[i, col_idx]
            try:
                v_f = float(str(v).replace(",", "").strip())
                if v_f == v_f:  # not NaN
                    result[sid].append((year, v_f))
            except (ValueError, TypeError):
                continue
    return result


def main(argv: list[str] | None = None) -> int:
    wanted = set((argv or [])[1:])
    runs = [s for s in SERIES if not wanted or s.out_id in wanted]
    if not runs:
        print(
            f"No matches for {wanted}; available: {[s.out_id for s in SERIES]}",
            file=sys.stderr,
        )
        return 2

    # Auto-discover vintage files in pipelines/cbo_data/. CBO publishes
    # the Outlook's data appendix under publication ID 51118; the
    # filename always starts with ``51118-YYYY-MM-`` (sometimes followed
    # by ``-DD``) and ends with ``budgetprojections.xls`` or
    # ``Budget-Projections.xlsx`` depending on the release year.
    if not MANUAL_DIR.exists():
        print(
            f"::error::No CBO data directory at "
            f"{MANUAL_DIR.relative_to(ROOT)}. Drop the Outlook XLSX "
            f"files there (see module docstring for the manual workflow) "
            f"and re-run.",
            file=sys.stderr,
        )
        return 1

    # First pass: pick up CBO's Historical Budget Data (publication
    # 51134) if it's on disk. This gives a continuous FY1962-onward
    # series for revenues/outlays/deficit/debt — the authoritative
    # historical source, more complete than the per-Outlook "1 actual
    # year per vintage" path.
    historical_by_year: dict[str, dict[int, float]] = {
        s.out_id: {} for s in runs
    }
    historical_filename: str | None = None
    historical_files = sorted(
        MANUAL_DIR.glob("51134-*[Hh]istorical*[Bb]udget*[Dd]ata*.xls*"),
        key=lambda p: p.name,
    )
    if historical_files:
        hist_path = historical_files[-1]  # most-recent release
        historical_filename = hist_path.name
        print(f"Parsing CBO Historical Budget Data ({hist_path.name})...",
              flush=True)
        try:
            df = pd.read_excel(
                hist_path,
                sheet_name="1a. Rev, Outlays, Surplus (GDP)",
                header=None,
            )
        except ValueError as e:
            print(
                f"  no '1a. Rev, Outlays, Surplus (GDP)' sheet ({e}); "
                f"falling back to Outlook actuals only",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"  read failed: {e}; falling back to Outlook actuals only",
                  file=sys.stderr)
        else:
            parsed = parse_historical_1a(df)
            if parsed:
                for sid, pairs in parsed.items():
                    if sid not in historical_by_year:
                        continue
                    for year, v in pairs:
                        historical_by_year[sid][year] = v
                n_years = (
                    len(historical_by_year[runs[0].out_id])
                    if runs
                    else 0
                )
                print(f"  loaded {n_years} years of historical actuals",
                      flush=True)
            else:
                print(
                    f"  parse_historical_1a returned None; structure not "
                    f"as expected — falling back to Outlook actuals only",
                    file=sys.stderr,
                )

    # Second pass: 51118 Outlook files. Each contributes:
    #   - projection years (year > actual_year of that vintage)
    #     stamped under projections[<vintage>].
    #   - actual year(s) — but ONLY if no 51134 historical file
    #     supplied the data. The 51134 file is authoritative (it carries
    #     post-publication revisions), so when present we ignore the
    #     Outlook's "actual" year to avoid double-writing.
    candidates: list[tuple[str, Path]] = []
    for p in sorted(MANUAL_DIR.glob("51118-*")):
        if "budget" not in p.name.lower() or "projection" not in p.name.lower():
            continue
        if p.suffix.lower() not in (".xls", ".xlsx"):
            continue
        v = vintage_from_filename(p.name)
        if v is None:
            print(f"  could not parse vintage from {p.name}; skipping",
                  file=sys.stderr)
            continue
        candidates.append((v, p))

    if not candidates and not historical_files:
        print(
            f"::error::No CBO data files in {MANUAL_DIR.relative_to(ROOT)}. "
            f"Need at least one of:\n"
            f"  - 51134-YYYY-MM-Historical-Budget-Data.xlsx "
            f"(historical actuals back to FY1962)\n"
            f"  - 51118-YYYY-MM-*Budget-Projections*.xls(x) "
            f"(per-Outlook 10-year projections)\n"
            f"Download from https://www.cbo.gov/data/budget-economic-data.",
            file=sys.stderr,
        )
        return 1

    projections: dict[str, dict[str, list[dict]]] = {
        s.out_id: {} for s in runs
    }
    parsed_vintages = 0
    skipped_vintages: list[str] = []
    have_historical_file = bool(historical_filename)

    for vintage, p in candidates:
        print(f"Parsing CBO Outlook {vintage} ({p.name})...", flush=True)
        try:
            df = pd.read_excel(p, sheet_name="Table 1-1", header=None)
        except ValueError as e:
            # "Worksheet named 'Table 1-1' not found" — some older
            # releases used different sheet numbering (e.g. the
            # 2018-04 release has Tables 2-2, 2-4, 4-1, 4-4 instead).
            print(f"  no Table 1-1 sheet ({e}); skipping vintage",
                  file=sys.stderr)
            skipped_vintages.append(vintage)
            continue
        except Exception as e:
            print(f"  read failed: {e}", file=sys.stderr)
            skipped_vintages.append(vintage)
            continue
        parsed = parse_table_1_1(df)
        if parsed is None:
            print(f"  parse_table_1_1 returned None — structure not as expected",
                  file=sys.stderr)
            skipped_vintages.append(vintage)
            continue
        series_data, actual_year = parsed
        parsed_vintages += 1
        for spec in runs:
            pairs = series_data.get(spec.out_id, [])
            if not pairs:
                continue
            future = [(y, v) for (y, v) in pairs if y > actual_year]
            if not have_historical_file:
                # No 51134 file — fall back to per-Outlook actuals
                # to populate historical (sparse, ~1 year per vintage).
                for y, v in pairs:
                    if y <= actual_year:
                        historical_by_year[spec.out_id][y] = v
            if future:
                projections[spec.out_id][vintage] = [
                    {"t": fy_to_date(y), "v": round(v, 3)}
                    for (y, v) in future
                ]

    # Emit
    written = 0
    for spec in runs:
        hist = historical_by_year[spec.out_id]
        projs = projections[spec.out_id]
        if not hist and not projs:
            print(f"  {spec.out_id}: no data; skipping", file=sys.stderr)
            continue
        pts = sorted(
            ({"t": fy_to_date(y), "v": round(v, 3)} for y, v in hist.items()),
            key=lambda p: p["t"],
        )
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

    print(
        f"\ncbo: wrote {written} series from {parsed_vintages} parsed "
        f"Outlook vintage(s); skipped {len(skipped_vintages)} "
        f"({skipped_vintages})."
    )
    if historical_filename:
        print(f"  Historical actuals from: {historical_filename}")
    elif written:
        print(
            "  Note: no 51134 Historical Budget Data file on disk — "
            "historical line is sparse (1 datum per Outlook vintage). "
            "Drop a 51134-*-Historical-Budget-Data.xlsx into "
            "pipelines/cbo_data/ for a continuous FY1962-onward line.",
            file=sys.stderr,
        )
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
