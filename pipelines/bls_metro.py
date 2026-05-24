"""
BLS state-and-area employment/unemployment per CBSA.

BLS publishes metro-area labor data via two programs that we tap:

  * LAUS (Local Area Unemployment Statistics) — monthly unemployment
    rate per Metropolitan Statistical Area. Series-ID format:
        LAUMT + <state-FIPS 2> + <CBSA-code 5> + 00000 + <measure 3>
    where measure 003 = unemployment rate. The "state FIPS" is the
    primary state that BLS associates with the metro — for multi-state
    metros it's the first state in the CBSA title.

  * CES State and Area Employment — monthly total nonfarm employment
    per MSA. Series-ID format:
        SMU + <state-FIPS 2> + <CBSA-code 5> + 00000000 + <measure 2>
    where measure 01 = "All Employees, In Thousands". (CES has many
    industry slices; we pull only the total here.)

Outputs (per metro × per series):
  * public/data/bls/metro_<series>_<CBSA>.json
  * src/content/sources/bls/metro_<series>_<CBSA>.yaml

Source-ID convention: ``bls/metro_<series>_<cbsa>`` (parsed by
src/lib/geographic-regions.ts → parseMetroSourceId).

BLS unregistered API caps: 25 series/query, 10 years/query, 25
queries/day per IP. With 2 series × ~387 metros that's ~774 series,
batched 25 at a time = ~31 requests — comfortably within the daily
quota for a weekly refresh.

Run with: ``python pipelines/bls_metro.py``.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from common import write_timeseries

REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSWALK_DIR = REPO_ROOT / "pipelines" / "_crosswalks"
SOURCES_DIR = REPO_ROOT / "src" / "content" / "sources" / "bls"

BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


@dataclass
class MetroSeriesSpec:
    series_id: str  # full BLS series ID
    out_id: str  # data/bls/<out_id>.json
    label: str  # human-facing chart name
    short_name: str  # ticker-style short
    unit: str
    unit_class: str  # currency | count | rate | index | ratio
    fmt_style: str  # number | percent | currency
    fmt_decimals: int
    pipeline_series_kind: str  # "unemployment" | "payrolls" — for source ID parsing


@dataclass
class CbsaMetro:
    code: str
    short_name: str
    name: str
    primary_state_fips: str
    primary_state_abbr: str


def load_metros(path: Path) -> list[CbsaMetro]:
    out: list[CbsaMetro] = []
    if not path.exists():
        print(f"  CBSA crosswalk missing: {path}", file=sys.stderr)
        return out
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            code = (row.get("cbsa_code") or "").strip()
            fips = (row.get("primary_state_fips") or "").strip()
            if not code or not fips:
                continue
            out.append(CbsaMetro(
                code=code,
                short_name=(row.get("short_name") or "").strip(),
                name=(row.get("name") or "").strip(),
                primary_state_fips=fips,
                primary_state_abbr=(row.get("primary_state_abbr") or "").strip(),
            ))
    return out


def metro_specs(metros: list[CbsaMetro]) -> list[MetroSeriesSpec]:
    """One unemployment + one payrolls series per metro."""
    out: list[MetroSeriesSpec] = []
    for m in metros:
        # LAUMT format: 5-char prefix + 2 FIPS + 5 CBSA + 5 zeros + 3 measure = 20
        laus_id = f"LAUMT{m.primary_state_fips}{m.code}00000003"
        out.append(MetroSeriesSpec(
            series_id=laus_id,
            out_id=f"metro_unemployment_{m.code}",
            label=f"{m.short_name} — unemployment rate",
            short_name=f"{m.short_name} unemployment",
            unit="%",
            unit_class="rate",
            fmt_style="percent",
            fmt_decimals=1,
            pipeline_series_kind="unemployment",
        ))
        # SMU format: 3-char prefix + 2 FIPS + 5 CBSA + 8 zeros + 2 measure = 20
        ces_id = f"SMU{m.primary_state_fips}{m.code}0000000001"
        out.append(MetroSeriesSpec(
            series_id=ces_id,
            out_id=f"metro_payrolls_{m.code}",
            label=f"{m.short_name} — nonfarm payroll employment",
            short_name=f"{m.short_name} payrolls",
            unit="thousands of persons",
            unit_class="count",
            fmt_style="number",
            fmt_decimals=0,
            pipeline_series_kind="payrolls",
        ))
    return out


def fetch_bls(series_ids: list[str]) -> dict[str, list[dict]]:
    """POST to BLS API with up to 25 series. Returns {series_id: rows}."""
    if not series_ids:
        return {}
    if len(series_ids) > 25:
        raise ValueError("BLS API caps at 25 series per request")
    end_year = datetime.now(timezone.utc).year
    start_year = end_year - 9  # 10 years inclusive (unregistered cap)
    payload = {
        "seriesid": series_ids,
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    body = json.dumps(payload)
    result = subprocess.run(
        [
            "curl", "-sS", "--max-time", "120",
            "-H", "Content-Type: application/json",
            "-d", body, BLS_URL,
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    parsed = json.loads(result.stdout)
    if parsed.get("status") != "REQUEST_SUCCEEDED":
        msg = parsed.get("message", ["unknown error"])
        raise RuntimeError(f"BLS API: {msg}")
    out: dict[str, list[dict]] = {}
    for s in parsed.get("Results", {}).get("series", []):
        sid = s.get("seriesID", "")
        out[sid] = s.get("data", [])
    return out


def bls_period_to_iso(year: str, period: str) -> str | None:
    """M01-M12 → mid-month; Q01-Q04 → mid-quarter; A01 → year-end."""
    try:
        y = int(year)
    except (ValueError, TypeError):
        return None
    if period.startswith("M"):
        m = int(period[1:])
        if not 1 <= m <= 12:
            return None
        return f"{y:04d}-{m:02d}-15"
    if period.startswith("Q"):
        q = int(period[1:])
        if not 1 <= q <= 4:
            return None
        m = q * 3
        return f"{y:04d}-{m:02d}-15"
    if period.startswith("A"):
        return f"{y:04d}-12-31"
    return None


def yaml_escape(s: str) -> str:
    if not s:
        return '""'
    if any(ch in s for ch in [":", "#", "&", "*", "!", "|", ">", "%", "@"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def write_source_yaml(spec: MetroSeriesSpec, metro: CbsaMetro) -> bool:
    out = SOURCES_DIR / f"{spec.out_id}.yaml"
    if out.exists():
        return False
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    if spec.pipeline_series_kind == "unemployment":
        description = (
            f"Headline unemployment rate for the {metro.short_name} "
            f"metropolitan statistical area (CBSA {metro.code}). Monthly, "
            "not seasonally adjusted. From BLS Local Area Unemployment "
            "Statistics (LAUS)."
        )
        provider = "BLS (LAUS)"
        # BLS Data Viewer URL: lands the reader on a chart + downloads
        # + metadata + related-series for THIS specific series, not the
        # LAUS program homepage which has no per-series navigation.
        # Backfilled across the existing YAML corpus in the same change
        # that updated this pipeline.
        url = f"https://data.bls.gov/timeseries/{spec.series_id}"
    else:
        description = (
            f"Total nonfarm payroll employment for the {metro.short_name} "
            f"metropolitan statistical area (CBSA {metro.code}). Monthly, "
            "seasonally adjusted. From BLS Current Employment Statistics "
            "(CES) state-and-area program."
        )
        provider = "BLS (CES State and Area)"
        url = f"https://data.bls.gov/timeseries/{spec.series_id}"
    lines = [
        f"name: {yaml_escape(spec.label)}",
        f"shortName: {yaml_escape(spec.short_name)}",
        f"description: {yaml_escape(description)}",
        "kind: timeseries",
        "pipeline: bls",
        f"dataFile: data/bls/{spec.out_id}.json",
        'supportedDeltas: ["1m", "ytd", "1y", "5y", "10y"]',
        f'unit: "{spec.unit}"',
        "formatting:",
        f"  style: {spec.fmt_style}",
        f"  decimals: {spec.fmt_decimals}",
        "emphasis: change",
        "provenance:",
        f"  provider: {yaml_escape(provider)}",
        f"  series: {spec.series_id}",
        f"  url: {url}",
        "  license: Public domain (US government data)",
        f"unitClass: {spec.unit_class}",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    metros = load_metros(CROSSWALK_DIR / "cbsa_metro.csv")
    if not metros:
        print("bls_metro: no metros loaded — aborting", file=sys.stderr)
        return 1
    specs = metro_specs(metros)
    # Index by series id for label lookups; metro per spec for YAMLs.
    metro_by_code = {m.code: m for m in metros}
    spec_metro: dict[str, CbsaMetro] = {}
    for spec in specs:
        cbsa = spec.out_id.split("_")[-1]
        m = metro_by_code.get(cbsa)
        if m:
            spec_metro[spec.out_id] = m

    # Write source YAMLs up front so the composer surfaces every metro
    # even if data fetches partially fail.
    yaml_written = 0
    for spec in specs:
        m = spec_metro.get(spec.out_id)
        if m and write_source_yaml(spec, m):
            yaml_written += 1
    print(f"Wrote {yaml_written} new source YAMLs", flush=True)

    # Batch up to 25 series per request.
    batches = [specs[i:i + 25] for i in range(0, len(specs), 25)]
    all_data: dict[str, list[dict]] = {}
    for batch in batches:
        ids = [s.series_id for s in batch]
        print(f"Fetching BLS batch: {len(ids)} series", flush=True)
        try:
            data = fetch_bls(ids)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue
        all_data.update(data)

    json_written = 0
    for spec in specs:
        rows = all_data.get(spec.series_id, [])
        if not rows:
            continue
        points: list[dict] = []
        for row in reversed(rows):  # BLS returns newest-first
            iso = bls_period_to_iso(row.get("year", ""), row.get("period", ""))
            if iso is None:
                continue
            try:
                v = float(row.get("value", ""))
            except (TypeError, ValueError):
                continue
            points.append({"t": iso, "v": v})
        if not points:
            continue
        spec_unit = spec.unit
        # Same count-rescale convention as pipelines/bls.py: payrolls
        # come back in thousands; rescale to raw jobs so combineTwo's
        # per-capita derivation produces sensible numbers.
        if "thousand" in spec.unit.lower():
            points = [{"t": p["t"], "v": p["v"] * 1000.0} for p in points]
            spec_unit = "jobs" if "payroll" in spec.label.lower() else "count"
        write_timeseries(
            pipeline="bls",
            series_id=spec.out_id,
            name=spec.label,
            points=points,
            unit=spec_unit,
        )
        json_written += 1
    print(f"Wrote {json_written} metro × series JSON files", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
