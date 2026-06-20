"""
Single source of truth for fred source metadata.

Previously the data lived in fred_series.py (FredSpec: series_id/name/unit/
transformation/scale — the FETCH params) while every user-facing field
(description, tags, formatting, provenance, unitClass, ...) was hand-written in
564 separate YAMLs, free to drift from the fetcher. This module makes
pipelines/fred_sources.yaml the one catalog: it carries the fetch params AND the
metadata, keyed by source slug (the YAML filename, decoupled from the FRED
series id). fred_series.py reads it to fetch; this generator writes the YAMLs
from it; tests/fred-sources.test.ts asserts the YAMLs equal the generated form
so drift can't ship.

Only kind / pipeline / dataFile are derived (uniform for fred). provenance is
per-series hand-curated (15 providers, 14 licenses) so it is stored verbatim.

Usage:
  python pipelines/_generate_fred_sources.py --check      # round-trip proof, writes nothing
  python pipelines/_generate_fred_sources.py --write      # regenerate the 564 YAMLs
  python pipelines/_generate_fred_sources.py --bootstrap  # rebuild the catalog from YAMLs+SPECS (one-time)
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FRED_DIR = ROOT / "src" / "content" / "sources" / "fred"
CATALOG = ROOT / "pipelines" / "fred_sources.yaml"

KIND = "timeseries"
PIPELINE = "fred_series"

TOP_ORDER = [
    "name", "shortName", "description", "kind", "pipeline", "dataFile",
    "supportedDeltas", "unit", "formatting", "emphasis", "provenance",
    "tags", "unitClass", "hidden",
]
FMT_ORDER = ["style", "decimals", "notation", "scaleFactor", "suffix", "prefix", "currency"]
PROV_ORDER = ["provider", "series", "url", "license"]
# Catalog fields beyond the derived three; order kept stable for clean diffs.
ROW_META = ["name", "shortName", "description", "unit", "supportedDeltas",
            "formatting", "emphasis", "provenance", "tags", "unitClass", "hidden"]


class _Literal(str):
    """Marker: emit as a YAML literal block (|) for readable prose."""


def _lit_representer(dumper, data):
    return dumper.represent_scalar(
        "tag:yaml.org,2002:str", data, style="|" if "\n" in data else None)


yaml.SafeDumper.add_representer(_Literal, _lit_representer)


def out_id(series: str, transformation: str | None) -> str:
    return f"{series}_{transformation.upper()}" if transformation else series


def expand(row: dict) -> dict:
    """Catalog row -> full source metadata dict (derives kind/pipeline/dataFile)."""
    oid = out_id(row["series"], row.get("transformation"))
    meta: dict = {}
    meta["name"] = row["name"]
    if "shortName" in row:
        meta["shortName"] = row["shortName"]
    meta["description"] = row["description"]
    meta["kind"] = KIND
    meta["pipeline"] = PIPELINE
    meta["dataFile"] = f"data/fred/{oid}.json"
    for k in ("supportedDeltas", "unit", "formatting", "emphasis", "provenance",
              "tags", "unitClass", "hidden"):
        if k in row:
            meta[k] = row[k]
    return meta


def render(meta: dict) -> str:
    ordered: dict = {}
    for key in TOP_ORDER:
        if key not in meta:
            continue
        v = meta[key]
        if key == "description" and isinstance(v, str):
            v = _Literal(v)
        elif key == "formatting" and isinstance(v, dict):
            v = {fk: v[fk] for fk in FMT_ORDER if fk in v}
        elif key == "provenance" and isinstance(v, dict):
            v = {pk: v[pk] for pk in PROV_ORDER if pk in v}
        ordered[key] = v
    for k, v in meta.items():
        if k not in ordered:
            ordered[k] = v
    return yaml.safe_dump(ordered, sort_keys=False, default_flow_style=False,
                          allow_unicode=True, width=10**9)


def load_catalog() -> dict:
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or {}


def bootstrap() -> int:
    """One-time: build the catalog from the current YAMLs + fred_series.SPECS."""
    sys.path.insert(0, str(ROOT / "pipelines"))
    import fred_series as fs
    spec_by_out = {out_id(s.series_id, s.transformation): s for s in fs.SPECS}
    cat: dict = {}
    nomatch = []
    for f in sorted(glob.glob(str(FRED_DIR / "*.yaml"))):
        slug = Path(f).stem
        meta = yaml.safe_load(open(f, encoding="utf-8")) or {}
        df = Path(str(meta.get("dataFile", ""))).stem
        s = spec_by_out.get(df)
        if not s:
            nomatch.append(slug)
            continue
        row = {"series": s.series_id}
        if s.transformation:
            row["transformation"] = s.transformation
        if getattr(s, "scale", 1.0) != 1.0:
            row["scale"] = s.scale
        for k in ROW_META:
            if k in meta:
                row[k] = meta[k]
        # Fetch params that drive fred_series normalization but differ from the
        # DISPLAY name/unit (the fetcher needs the raw FRED unit, e.g.
        # "thousands of persons", to trigger the count rescale). Stored only
        # when they diverge, so the fetcher can read the catalog directly.
        if (s.name or "") != (meta.get("name") or ""):
            row["fetchName"] = s.name
        if (s.unit or "") != (meta.get("unit") or ""):
            row["fetchUnit"] = s.unit
        cat[slug] = row
    # SPECS that fetch data but have no source YAML (derived-chart components,
    # e.g. DC state/local government payrolls). Keep them in the catalog so it
    # is the COMPLETE fetch list; mark component:true so the generator skips
    # writing a YAML for them.
    yaml_outs = {out_id(r["series"], r.get("transformation")) for r in cat.values()}
    for s in fs.SPECS:
        o = out_id(s.series_id, s.transformation)
        if o in yaml_outs:
            continue
        crow = {"series": s.series_id, "component": True, "fetchName": s.name,
                "fetchUnit": s.unit}
        if s.transformation:
            crow["transformation"] = s.transformation
        if getattr(s, "scale", 1.0) != 1.0:
            crow["scale"] = s.scale
        cat[f"_component_{o}"] = crow
    CATALOG.write_text(
        yaml.safe_dump(cat, sort_keys=True, allow_unicode=True, width=10**9,
                       default_flow_style=False),
        encoding="utf-8")
    print(f"bootstrapped {len(cat)} rows; {len(nomatch)} no-match")
    return 1 if nomatch else 0


def check() -> int:
    cat = load_catalog()
    drift = []
    for slug, row in cat.items():
        if row.get("component"):
            continue  # fetch-only, no YAML
        gen = yaml.safe_load(render(expand(row))) or {}
        cur = yaml.safe_load((FRED_DIR / f"{slug}.yaml").read_text(encoding="utf-8")) or {}
        if gen != cur:
            diffs = {k: (cur.get(k), gen.get(k)) for k in set(cur) | set(gen)
                     if cur.get(k) != gen.get(k)}
            drift.append((slug, diffs))
    print(f"checked {len(cat)} fred sources; {len(drift)} drift vs on-disk YAML")
    for slug, diffs in drift[:20]:
        print(f"  DRIFT {slug}: {diffs}")
    return 1 if drift else 0


def write() -> int:
    cat = load_catalog()
    n = 0
    for slug, row in cat.items():
        if row.get("component"):
            continue  # fetch-only, no YAML
        (FRED_DIR / f"{slug}.yaml").write_text(render(expand(row)), encoding="utf-8")
        n += 1
    print(f"regenerated {n} fred YAMLs from the catalog")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    fn = {"--check": check, "--write": write, "--bootstrap": bootstrap}.get(mode)
    raise SystemExit(fn() if fn else (print("unknown mode") or 2))
