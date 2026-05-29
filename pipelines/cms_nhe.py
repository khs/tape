"""CMS National Health Expenditure Accounts (NHEA) — per-capita health spending.

Source
------
CMS (Centers for Medicare & Medicaid Services), Office of the Actuary,
National Health Statistics Group. The "NHE summary including share of
GDP" historical file — a public ZIP containing ``NHE<YY>_Summary.csv``:

    https://www.cms.gov/data-research/statistics-trends-and-reports/\
national-health-expenditure-data/historical
    → https://www.cms.gov/files/zip/nhe-summary-including-share-gdp-cy-1960-2024.zip

The CSV is "Table 1 — National Health Expenditures; Aggregate and Per
Capita Amounts, ...: Calendar Years 1960-2024". It has several stacked
sections (aggregate $B, annual %-change, %-distribution, PER CAPITA $,
NHE as %-GDP). We read the PER-CAPITA section only.

Identifier convention
---------------------
No per-series IDs — the data is a stacked table. The "identifier" is the
row label *within the per-capita section*. NOTE: labels like "Personal
Health Care" recur in EVERY section (amounts, %-change, %-distribution,
per-capita), so the parser anchors to the per-capita section header
("National Health Expenditures (Per Capita Amount)") and only reads rows
between it and the next "... (Percent)" section. It raises loudly if the
expected section header or a wanted row label is missing — that assertion
IS the label audit for this table-parse pipeline (cf. cbo / ssa /
usda_nass in docs/new-data-source-checklist.md), so a CMS reformat fails
the refresh instead of silently mislabelling.

Auth / rate limits
------------------
Public download, no API key. CMS's web tier 403s default User-Agents, so
we send a browser-like UA. The file is a single ~20 KB ZIP fetched once
per run; no pagination or rate concerns.

Units
-----
Per-capita amounts are in CURRENT DOLLARS, stored RAW (not billions —
the canonical-unit "currency in billions" invariant is for AGGREGATE
series; per-capita dollar amounts store raw, like the FRED per-capita
series they replace). unitClass "currency".

License / compliance
-------------------
US-government work → public domain. CMS asks for acknowledgment, which we
give via provenance. These are NATIONAL AGGREGATES only (one number per
year) — no micro-data, no PII, no re-identification surface.

Emits public/data/cms_nhe/<id>.json. Source YAMLs are hand-written under
src/content/sources/cms_nhe/ (only two series — below the ~150 threshold
where a generator pays off).

Run: ``python pipelines/cms_nhe.py``  (optionally a series-id filter,
e.g. ``python pipelines/cms_nhe.py phc_per_capita``).
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile

import _env  # noqa: F401  (sets sys.path so `common` imports)

from common import write_timeseries

PIPELINE = "cms_nhe"

# The "NHE summary including share of GDP" historical ZIP. The CY range in
# the filename advances each annual release; update it when CMS publishes
# a newer vintage (the page lists the current file). The parser is
# vintage-agnostic — it reads whatever year columns the CSV carries.
ZIP_URL = (
    "https://www.cms.gov/files/zip/"
    "nhe-summary-including-share-gdp-cy-1960-2024.zip"
)
UA = "Mozilla/5.0 (Tape data pipeline; +https://legible-markets.vercel.app)"

# Header row marker (its remaining cells are the year columns) and the
# per-capita section header (anchors us past the aggregate / %-change /
# %-distribution sections, which carry identically-named rows).
HEADER_MARKER = "Expenditure Amount"
PER_CAPITA_HEADER = "National Health Expenditures (Per Capita Amount)"

# series_id -> (human name, short name, exact stripped CSV row label
# within the per-capita section).
SERIES: list[tuple[str, str, str, str]] = [
    (
        "nhe_per_capita",
        "National health spending per capita",
        "Health $/cap (total)",
        "National Health Expenditures (Per Capita Amount)",
    ),
    (
        "phc_per_capita",
        "Personal health-care spending per capita",
        "Personal health $/cap",
        "Personal Health Care",
    ),
]


def fetch_summary_rows() -> list[list[str]]:
    """Download the NHE summary ZIP and return the CSV as parsed rows."""
    import requests  # type: ignore[import-untyped]

    resp = requests.get(ZIP_URL, headers={"User-Agent": UA}, timeout=60)
    resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    csv_name = next(
        (n for n in zf.namelist() if n.lower().endswith(".csv")), None
    )
    if csv_name is None:
        raise RuntimeError(
            f"CMS NHE: no .csv inside {ZIP_URL} (got {zf.namelist()})"
        )
    text = zf.read(csv_name).decode("utf-8-sig")  # strip any BOM
    return list(csv.reader(io.StringIO(text)))


def parse_per_capita(rows: list[list[str]]) -> dict[str, list[dict[str, object]]]:
    """Extract the wanted per-capita series as {series_id: [{t, v}, ...]}.

    Anchors to the per-capita section so the recurring "Personal Health
    Care" label resolves to the per-capita value, not the aggregate /
    percent rows. Raises on any structural surprise.
    """
    # 1. Year columns from the header row.
    header = next((r for r in rows if r and r[0].strip() == HEADER_MARKER), None)
    if header is None:
        raise RuntimeError(
            f"CMS NHE: header row {HEADER_MARKER!r} not found — format changed?"
        )
    years: list[int | None] = []
    for cell in header[1:]:
        c = cell.strip()
        years.append(int(c) if c.isdigit() else None)

    # 2. Slice the per-capita section: from its header to the next
    #    "... (Percent)" section row (NHE-as-%-of-GDP).
    start = next(
        (i for i, r in enumerate(rows) if r and r[0].strip() == PER_CAPITA_HEADER),
        None,
    )
    if start is None:
        raise RuntimeError(
            f"CMS NHE: per-capita section {PER_CAPITA_HEADER!r} not found "
            "— format changed?"
        )
    section = [rows[start]]
    for r in rows[start + 1:]:
        lab = r[0].strip() if r else ""
        if lab.endswith("(Percent)"):
            break
        section.append(r)

    # 3. Pull each wanted row, mapping value cells to their header year.
    out: dict[str, list[dict[str, object]]] = {}
    for series_id, _name, _short, label in SERIES:
        row = next((r for r in section if r and r[0].strip() == label), None)
        if row is None:
            raise RuntimeError(
                f"CMS NHE: per-capita row {label!r} not found in section "
                "— format changed?"
            )
        points: list[dict[str, object]] = []
        for k, cell in enumerate(row[1:]):
            year = years[k] if k < len(years) else None
            val = cell.strip().replace(",", "")
            if year is None or not val:
                continue
            points.append({"t": f"{year}-01-01", "v": float(val)})
        if not points:
            raise RuntimeError(f"CMS NHE: row {label!r} parsed to zero points.")
        # Value-magnitude sanity (catches a units/parse regression the
        # label audit can't): per-capita health dollars are 4-5 figures.
        latest = points[-1]["v"]
        if not (1_000 <= float(latest) <= 100_000):  # type: ignore[arg-type]
            raise RuntimeError(
                f"CMS NHE: {series_id} latest value {latest} out of sane "
                "per-capita-USD range — parse/units regression?"
            )
        out[series_id] = points
    return out


def main(argv: list[str]) -> None:
    only = set(argv)
    rows = fetch_summary_rows()
    parsed = parse_per_capita(rows)
    for series_id, name, _short, _label in SERIES:
        if only and series_id not in only:
            continue
        points = parsed[series_id]
        # merge=False: CMS republishes the full revised 1960-present
        # series each annual release, so prior-year restatements should
        # overwrite, not union with, stale values.
        path = write_timeseries(
            PIPELINE, series_id, name, points, unit="USD", merge=False
        )
        print(f"  {series_id}: {len(points)} points "
              f"({points[0]['t'][:4]}-{points[-1]['t'][:4]}, "
              f"latest ${points[-1]['v']:,.0f}) -> {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
