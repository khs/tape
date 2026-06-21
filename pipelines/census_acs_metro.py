"""
ACS 5-year estimates per CBSA (Metropolitan Statistical Area).

Unlike the CD pipeline (pipelines/census_acs_cd.py), which has to
crosswalk tract-level data into stable 118th-Congress districts,
the Census API exposes ACS data directly at the CBSA geography:

    geography = "metropolitan statistical area/micropolitan statistical area"

CBSA boundaries change infrequently (last major OMB revision was Bulletin
23-01, July 2023) so we can pull the contemporary-CBSA series directly
without a tract-aggregation step. Future redelineations will introduce
small comparability breaks; document those when they happen.

This pipeline reuses INDICATORS, AGG_* semantics, and the AcsVar
dataclass from census_acs_cd.py so adding an indicator to the CD
pipeline automatically extends metro coverage. AGG_SUM (tract-summed at
CD level) and AGG_MEDIAN_DIST (median-from-bins-at-tract-level) collapse
to a direct CBSA fetch here — Census publishes both as CBSA-level
values, so there's no need for the tract-aggregation step.

Outputs (per metro × per indicator):
  * public/data/acs_metro/<series>_<CBSA>.json
  * src/content/sources/acs_metro/<series>_<CBSA>.yaml

Source-ID convention: ``acs_metro/<series>_<cbsa>`` (parsed by
src/lib/geographic-regions.ts → parseMetroSourceId).

Requires CENSUS_API_KEY env var; no-ops with a status message when unset.

Run with: ``CENSUS_API_KEY=<key> python pipelines/census_acs_metro.py``.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import _env  # noqa: F401 — load .env (also imported transitively via census_acs_cd)
from common import write_timeseries
from acs_subjects import subjects_for_out_id
from census_acs_cd import (
    INDICATORS,
    ACS_VINTAGES,
    AGG_SUM,
    AGG_CD_LEVEL,
    AGG_CD_LEVEL_SUM,
    AGG_MEDIAN_DIST,
    AGG_MEDIAN_CD_DIST,
    acs_base,
    parse_value,
    weighted_median_from_bins,
)

# Reuse the metadata table from the CD-level YAML generator so per-
# indicator formatting (currency / decimals / notation / extra_tags)
# stays in sync across pipelines without a third metadata source.
from _generate_acs_sources import INDICATORS as IND_METADATA

REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSWALK_DIR = REPO_ROOT / "pipelines" / "_crosswalks"
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "acs_metro"


def load_metro_codes(path: Path) -> dict[str, tuple[str, str]]:
    """Returns {cbsa_code: (short_name, full_name)}."""
    out: dict[str, tuple[str, str]] = {}
    if not path.exists():
        print(f"  CBSA crosswalk missing: {path}", file=sys.stderr)
        return out
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            code = (row.get("cbsa_code") or "").strip()
            if not code:
                continue
            out[code] = (
                (row.get("short_name") or "").strip(),
                (row.get("name") or "").strip(),
            )
    return out


def acs_fetch(year: int, var_codes: list[str], key: str) -> list[list[str]]:
    """
    One request for every CBSA at once. Returns the response as a list
    of rows (first row = headers). Empty list on failure.
    """
    vars_csv = ",".join(var_codes)
    geo = "metropolitan%20statistical%20area/micropolitan%20statistical%20area:*"
    url = (
        f"{acs_base(year)}?get=NAME,{vars_csv}"
        f"&for={geo}&key={key}"
    )
    try:
        out = subprocess.run(
            ["curl", "-s", "-S", "--max-time", "180", "-w", "%{http_code}", url],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"    curl failed year={year}: {e}", file=sys.stderr)
        return []
    body = out.stdout
    code = body[-3:] if body[-3:].isdigit() else "???"
    payload = body[:-3] if body[-3:].isdigit() else body
    if code != "200":
        snippet = payload.strip()[:200]
        print(f"    HTTP {code} year={year}: {snippet}", file=sys.stderr)
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"    JSON parse year={year}: {e}", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def yaml_escape(s: str) -> str:
    if not s:
        return '""'
    if any(ch in s for ch in [":", "#", "&", "*", "!", "|", ">", "%", "@"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def metro_display_name(short_name: str, full_name: str) -> str:
    """
    Display label for a metro: short name + the official CBSA title's
    state suffix, e.g. ("Columbus", "Columbus, GA-AL") -> "Columbus, GA-AL"
    and ("Akron", "Akron, OH") -> "Akron, OH".

    State codes are kept BY DEFAULT (not just on collisions): many short
    names repeat across states ("Columbus", "Springfield", ...), so a
    bare city name is ambiguous in the source picker.
    """
    if "," in full_name:
        tail = full_name.split(",", 1)[1].strip()
        if tail:
            return f"{short_name}, {tail}"
    return short_name


def write_source_yaml(out_id: str, cbsa: str, short_name: str,
                      display_name: str) -> bool:
    """Generate a source YAML for a metro × indicator combo. Pulls
    formatting metadata from _generate_acs_sources.INDICATORS (keyed by
    out_id) so the per-indicator unit / decimals / notation stays
    consistent with the CD-level YAMLs. ``display_name`` (state-qualified,
    see metro_display_name) feeds the user-facing name/shortName;
    ``short_name`` (bare city) feeds the prose description, which already
    disambiguates via the CBSA code."""
    out = SOURCES_DIR / f"{out_id}_{cbsa}.yaml"
    if out.exists():
        return False
    meta = next((m for m in IND_METADATA if m["out_id"] == out_id), None)
    if meta is None:
        # Indicator missing from metadata table; skip rather than emit a
        # half-formed YAML.
        return False
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    description = (
        f"{meta['name_prefix']} for the {short_name} metropolitan "
        f"statistical area (CBSA {cbsa}). From the American Community "
        f"Survey 5-year estimates (table {meta['table']}). Released "
        f"annually."
    )
    short_label = f"{display_name} {meta['short_suffix']}"
    name_full = f"{meta['name_prefix']} — {display_name}"
    tags = ["government", "us"] + list(subjects_for_out_id(out_id))
    lines = [
        f"name: {yaml_escape(name_full)}",
        f"shortName: {yaml_escape(short_label)}",
        f"description: {yaml_escape(description)}",
        "kind: timeseries",
        "pipeline: acs_metro",
        f"dataFile: data/acs_metro/{out_id}_{cbsa}.json",
        'supportedDeltas: ["5y", "10y"]',
        f'unit: "{meta["unit"]}"',
        "formatting:",
        f"  style: {meta['fmt_style']}",
    ]
    if meta.get("currency"):
        lines.append(f"  currency: {meta['currency']}")
    lines.append(f"  decimals: {meta['decimals']}")
    if meta.get("notation"):
        lines.append(f"  notation: {meta['notation']}")
    lines.extend([
        "emphasis: change",
        "provenance:",
        "  provider: US Census Bureau (ACS 5-year)",
        f"  series: {out_id}_{cbsa}",
        "  url: https://api.census.gov/data/2022/acs/acs5",
        "  license: Public domain (US government data)",
        "tags:",
    ])
    for tag in tags:
        lines.append(f"  - {tag}")
    if meta.get("unit_class"):
        lines.append(f"unitClass: {meta['unit_class']}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    metros = load_metro_codes(CROSSWALK_DIR / "cbsa_metro.csv")
    if not metros:
        print("census_acs_metro: no metros loaded — aborting", file=sys.stderr)
        return 1

    if not key:
        print(
            "census_acs_metro: CENSUS_API_KEY not set. Writing source "
            "YAMLs only (no data files). Register a free key at "
            "https://api.census.gov/data/key_signup.html and re-run.",
            file=sys.stderr,
        )
        # When no key is set we can still pre-generate empty-shell YAMLs
        # for every indicator × CBSA so the source-collection schema
        # validates. Data lands on the next refresh with a key.
        yaml_written = 0
        for ind in INDICATORS:
            for cbsa, (short_name, full_name) in metros.items():
                display = metro_display_name(short_name, full_name)
                if write_source_yaml(ind.out_id, cbsa, short_name, display):
                    yaml_written += 1
        print(f"  wrote {yaml_written} new source YAMLs (data pending)", flush=True)
        return 0

    # Build the master variable list across all indicators (deduped).
    needed_codes: set[str] = set()
    for v in INDICATORS:
        if v.agg in (AGG_SUM, AGG_CD_LEVEL, AGG_MEDIAN_DIST):
            if v.var_code:
                needed_codes.add(v.var_code)
        elif v.agg == AGG_CD_LEVEL_SUM:
            needed_codes.update(v.sum_codes)
        elif v.agg == AGG_MEDIAN_CD_DIST:
            needed_codes.update(code for code, _, _ in v.bins)
    var_list = sorted(needed_codes)
    print(
        f"census_acs_metro: fetching {len(var_list)} variables × "
        f"{len(ACS_VINTAGES)} vintages × {len(metros)} CBSAs...",
        flush=True,
    )

    # Accumulator: {(out_id, cbsa): [{t, v}, ...]}
    series_accum: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for year in ACS_VINTAGES:
        anchor = f"{year}-12-31"
        print(f"\nFetching ACS5 vintage {year}...", flush=True)
        # Merge chunks: {cbsa: {var_code: value}}
        merged: dict[str, dict[str, float]] = {}
        for chunk_start in range(0, len(var_list), 45):
            chunk = var_list[chunk_start:chunk_start + 45]
            rows = acs_fetch(year, chunk, key)
            if not rows or len(rows) < 2:
                continue
            headers = rows[0]
            try:
                geo_col = headers.index(
                    "metropolitan statistical area/micropolitan statistical area"
                )
            except ValueError:
                print(f"  unexpected schema {year}: {headers}", file=sys.stderr)
                continue
            for row in rows[1:]:
                if len(row) < len(headers):
                    continue
                cbsa = row[geo_col]
                if cbsa not in metros:
                    continue
                if cbsa not in merged:
                    merged[cbsa] = {}
                for code in chunk:
                    try:
                        col = headers.index(code)
                    except ValueError:
                        continue
                    val = parse_value(row[col])
                    if val is not None:
                        merged[cbsa][code] = val

        if not merged:
            print(f"  no data for {year}", file=sys.stderr)
            continue

        # Apply per-indicator aggregation against each CBSA's merged row.
        for cbsa, per_var in merged.items():
            for v in INDICATORS:
                value: float | None = None
                if v.agg in (AGG_SUM, AGG_CD_LEVEL, AGG_MEDIAN_DIST):
                    value = per_var.get(v.var_code) if v.var_code else None
                elif v.agg == AGG_CD_LEVEL_SUM:
                    parts = [per_var.get(c) for c in v.sum_codes]
                    present = [p for p in parts if p is not None]
                    if present:
                        value = sum(present)
                elif v.agg == AGG_MEDIAN_CD_DIST:
                    bins_data = {
                        code: per_var[code]
                        for code, _, _ in v.bins
                        if code in per_var
                    }
                    value = weighted_median_from_bins(v.bins, bins_data)
                if value is None:
                    continue
                if v.agg in (AGG_SUM, AGG_CD_LEVEL_SUM):
                    value = round(value)
                elif v.decimals > 0:
                    value = round(value, v.decimals)
                series_accum[(v.out_id, cbsa)].append({"t": anchor, "v": value})

    # Write per-(indicator, CBSA) time series files.
    json_written = 0
    for (out_id, cbsa), points in series_accum.items():
        if not points:
            continue
        points.sort(key=lambda p: p["t"])
        short_name, full_name = metros.get(cbsa, ("", ""))
        display = metro_display_name(short_name, full_name)
        var = next((v for v in INDICATORS if v.out_id == out_id), None)
        name_prefix = var.name_prefix if var else out_id
        unit = var.unit if var else "value"
        write_timeseries(
            pipeline="acs_metro",
            series_id=f"{out_id}_{cbsa}",
            name=f"{name_prefix} — {display}",
            points=points,
            unit=unit,
        )
        json_written += 1
    print(f"\nWrote {json_written} metro × series JSON files", flush=True)

    yaml_written = 0
    for ind in INDICATORS:
        for cbsa, (short_name, full_name) in metros.items():
            if (ind.out_id, cbsa) not in series_accum:
                continue
            display = metro_display_name(short_name, full_name)
            if write_source_yaml(ind.out_id, cbsa, short_name, display):
                yaml_written += 1
    print(f"Wrote {yaml_written} new source YAMLs ({len(INDICATORS)} indicators × {len(metros)} CBSAs)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
