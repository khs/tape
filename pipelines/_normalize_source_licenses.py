"""
One-shot: normalize provenance.license across every source YAML.

The license field already exists on ~99% of sources (~20,800 of 21,000),
populated by individual pipelines. This script:

  * Fills in the missing ~200 (Yahoo Finance and SSA — both providers
    where the license text is non-obvious so the pipeline didn't bake
    one in).
  * Normalizes a handful of stylistic drift ("CC BY-4.0" vs
    "CC BY 4.0", "U.S. public domain" vs "Public domain (US
    government data)") so a license-grouped audit reads cleanly.

Canonical license strings keyed by pipeline:

  fred_series         -> "Public domain (US government data)"
                         (with EIA / Nasdaq OMX overrides for those
                         specific series)
  bls                 -> "Public domain (US government data)"
  treasury_tic        -> "Public domain (US government data)"
  cbo                 -> "Public domain (per cbo.gov copyright
                         statement)"
  ssa                 -> "Public domain (US government data)"
  acs_*               -> "Public domain (US government data)"
  usaspending         -> "Public domain (US government data)"
  derive_acs_state    -> "Public domain (US government data)"
  worldbank_*         -> "CC BY 4.0"
  oecd                -> "Reuse permitted including commercial, with
                         attribution (OECD; CC BY 4.0 since Jul 2024)"
  yahoo_quotes,
  yahoo_marketcap,
  yahoo_futures,
  countries_relative  -> "Free for personal / non-commercial use with
                         attribution. Verify yahoo.com terms for
                         commercial redistribution."
  zillow              -> "Free for public use (consumers, media,
                         analysts, academics, policymakers)"

Idempotent — running twice produces no diff after the first run.
Reads + writes YAML files in place; preserves comment-free YAML
structure via ruamel.yaml round-tripping. (Falls back to PyYAML
if ruamel isn't installed; comments may be dropped on a few files
in that case, but stylistic comments are rare on auto-generated
source YAMLs so the loss is minimal.)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Try ruamel first for round-trip fidelity (preserves comments + key
# ordering). Fall back to PyYAML which is always present.
_RUAMEL = None
try:
    from ruamel.yaml import YAML  # type: ignore[import-untyped]

    _RUAMEL = YAML()
    _RUAMEL.preserve_quotes = True
    # Default indent matches Astro content-collection convention.
    _RUAMEL.indent(mapping=2, sequence=4, offset=2)
except ImportError:
    pass

import yaml as _pyyaml


ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT / "src" / "content" / "sources"


# Canonical license per pipeline. Special overrides handled below by
# inspecting provenance.provider (FRED + EIA, FRED + Nasdaq OMX).
PIPELINE_LICENSE: dict[str, str] = {
    "fred_series": "Public domain (US government data)",
    "bls": "Public domain (US government data)",
    "bls_metro": "Public domain (US government data)",
    "treasury_tic": "Public domain (US government data)",
    "cbo": "Public domain (per cbo.gov copyright statement)",
    "ssa": "Public domain (US government data)",
    "acs_cd": "Public domain (US government data)",
    "acs_metro": "Public domain (US government data)",
    "census_acs_national": "Public domain (US government data)",
    "derive_acs_state_from_cd": "Public domain (US government data)",
    "usaspending": "Public domain (US government data)",
    "usaspending_metro": "Public domain (US government data)",
    "worldbank_gdp": "CC BY 4.0",
    "worldbank_gdp_raw": "CC BY 4.0",
    "worldbank_extended": "CC BY 4.0",
    "oecd": (
        # OECD moved to CC BY 4.0 on 2024-07-01 (commercial reuse OK
        # with attribution); pre-2024 content was already free to reuse
        # incl. commercial with citation. The old "non-commercial only"
        # string was stale + shown to users on each source page.
        # No "terms:" colon-space — keeps the value a safe unquoted
        # YAML plain scalar (matches the hand-written source files).
        "Reuse permitted including commercial, with attribution "
        "(OECD; CC BY 4.0 since Jul 2024)"
    ),
    "yahoo_quotes": (
        "Free for personal / non-commercial use with attribution. "
        "Verify yahoo.com terms for commercial redistribution."
    ),
    "yahoo_marketcap": (
        "Free for personal / non-commercial use with attribution. "
        "Verify yahoo.com terms for commercial redistribution."
    ),
    "yahoo_futures": (
        "Free for personal / non-commercial use with attribution. "
        "Verify yahoo.com terms for commercial redistribution."
    ),
    "countries_relative": (
        "Free for personal / non-commercial use with attribution. "
        "Verify yahoo.com terms for commercial redistribution."
    ),
    "zillow": (
        "Free for public use (consumers, media, analysts, academics, "
        "policymakers)"
    ),
}


def desired_license(pipeline: str, provider: str | None) -> str | None:
    """Return the canonical license string for a (pipeline, provider)
    pair, or None when we don't have a confident answer (caller skips
    those rather than guessing)."""
    base = PIPELINE_LICENSE.get(pipeline)
    if not base:
        return None
    # FRED-pipeline overrides: a few series come from EIA (free,
    # US govt) or Nasdaq OMX (re-distributed by FRED under different
    # terms). Provenance.provider on those YAMLs encodes the
    # underlying source.
    if pipeline == "fred_series" and provider:
        if "EIA" in provider:
            return "Public domain (US government data, EIA)"
        if "Nasdaq" in provider or "S&P" in provider:
            return (
                "Re-distributed by FRED under upstream provider terms; "
                "verify with the upstream provider for commercial reuse"
            )
    return base


def load_yaml(path: Path) -> dict | None:
    """Best-effort YAML load. Prefer ruamel for round-tripping; fall
    back to PyYAML when ruamel isn't installed."""
    try:
        if _RUAMEL is not None:
            return _RUAMEL.load(path.read_text(encoding="utf-8"))
        return _pyyaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def dump_yaml(path: Path, data: dict) -> None:
    """Write YAML back to disk preserving the loader's structure."""
    if _RUAMEL is not None:
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            _RUAMEL.dump(data, fh)
        return
    # PyYAML fallback. Drops comments but preserves order via Python 3.7+
    # dict insertion order semantics.
    path.write_text(
        _pyyaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def main() -> int:
    if not SOURCES_DIR.exists():
        print(f"Source dir not found: {SOURCES_DIR}", file=sys.stderr)
        return 2
    if _RUAMEL is None:
        print(
            "WARN: ruamel.yaml not installed — falling back to PyYAML. "
            "Comments in source YAMLs may be lost on rewrite. "
            "Install with: pip install ruamel.yaml",
            file=sys.stderr,
        )

    changed = 0
    unchanged = 0
    skipped = 0
    for path in sorted(SOURCES_DIR.rglob("*.yaml")):
        data = load_yaml(path)
        if not isinstance(data, dict):
            skipped += 1
            continue
        pipeline = data.get("pipeline")
        if not isinstance(pipeline, str):
            skipped += 1
            continue
        prov = data.get("provenance") or {}
        if not isinstance(prov, dict):
            skipped += 1
            continue
        provider = prov.get("provider")
        want = desired_license(pipeline, provider if isinstance(provider, str) else None)
        if want is None:
            # No canonical answer for this pipeline — preserve
            # whatever's there and move on.
            skipped += 1
            continue
        current = prov.get("license")
        if current == want:
            unchanged += 1
            continue
        # Write the new license. Ruamel preserves any other
        # provenance keys (provider, series, url, notes).
        prov["license"] = want
        data["provenance"] = prov
        dump_yaml(path, data)
        rel = path.relative_to(SOURCES_DIR)
        # Trim noise: only log files that actually flipped to keep
        # the change-log readable.
        print(f"  {rel}: {current!r} -> {want!r}"[:200])
        changed += 1

    print()
    print(
        f"Done. changed={changed} unchanged={unchanged} skipped={skipped} "
        f"total={changed + unchanged + skipped}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
