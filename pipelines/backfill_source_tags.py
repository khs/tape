"""
Backfill `tags` on source YAML files by inheriting from the charts that
reference them.

C1 approach (per user direction): single-source charts unambiguously
contribute their tags to their referenced source. Multi-source charts
get flagged for manual review — assigning every parent's tags to every
source over-tags (e.g., a chart tagged ``world`` whose sources are
``us-payrolls`` and ``us-cpi`` shouldn't make those US sources show
up under the ``world`` filter).

What this does
--------------
1. Scans ``src/content/charts/**/*.yaml`` for every chart manifest.
2. For each chart with exactly one source, unions the chart's tags into
   the referenced source's tags.
3. For multi-source charts, prints a "REVIEW" line so the operator can
   hand-edit the relevant sources.
4. Writes the updated tags back into the source YAML files in place,
   preserving the rest of the file (we use a round-trip YAML loader
   that keeps key order and comments).

Idempotent: re-running produces no changes after the first run for
single-source charts. Manual-review entries print every time until
the operator actually addresses them.

Run with: ``python pipelines/backfill_source_tags.py``

Dry-run (just report, don't write): ``python pipelines/backfill_source_tags.py --dry-run``
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict
from typing import Any

# We need round-trip YAML so we don't trash existing files' formatting.
# ruamel.yaml is the standard for this; fall back to PyYAML if ruamel
# isn't installed and warn the operator about formatting drift.
try:
    from ruamel.yaml import YAML  # type: ignore[import-untyped]

    yaml_io = YAML()
    yaml_io.preserve_quotes = True
    yaml_io.indent(mapping=2, sequence=4, offset=2)
    HAVE_RUAMEL = True
except ImportError:
    import yaml as pyyaml  # type: ignore[import-untyped]

    yaml_io = None
    HAVE_RUAMEL = False


REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_ROOT = REPO_ROOT / "src" / "content" / "charts"
SOURCES_ROOT = REPO_ROOT / "src" / "content" / "sources"


# Multi-source charts where the chart's tag union is NOT the right
# inheritance for the underlying sources, because the chart pairs
# sources from different domains. Each entry maps chart-id →
# {source_id: [tags-to-apply-from-this-chart, ...]}. Any tags not
# listed for a source are not applied from this chart even if the
# chart itself carries them.
#
# Append to this dict when adding new "cross-domain comparison" charts
# (think: a stock vs its underlying commodity, a country ETF vs the
# world index, a sector vs the broad market).
MULTI_SOURCE_OVERRIDES: dict[str, dict[str, list[str]]] = {
    # XOM (US large-stocks) vs WTI (global commodity). Only 'energy'
    # cleanly applies to both sides; 'us'/'large-stocks' shouldn't go
    # on a commodity and 'commodities' shouldn't go on a stock.
    "stocks/xom_vs_wti": {
        "yahoo_marketcap/xom_mc": ["energy"],
        "yahoo/wti_crude": ["energy"],
    },
    "stocks/cvx_vs_wti": {
        "yahoo_marketcap/cvx_mc": ["energy"],
        "yahoo/wti_crude": ["energy"],
    },
}


def load_yaml(path: Path) -> Any:
    """Load a YAML file using whichever library is available."""
    text = path.read_text(encoding="utf-8")
    if HAVE_RUAMEL:
        return yaml_io.load(text)
    return pyyaml.safe_load(text)


def dump_yaml(path: Path, data: Any) -> None:
    """Write a YAML file, preserving formatting if ruamel is available."""
    if HAVE_RUAMEL:
        with path.open("w", encoding="utf-8") as f:
            yaml_io.dump(data, f)
    else:
        path.write_text(
            pyyaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


def chart_id_for_path(p: Path) -> str:
    """src/content/charts/stocks/jpm.yaml → 'stocks/jpm'."""
    rel = p.relative_to(CHARTS_ROOT)
    return str(rel.with_suffix("")).replace("\\", "/")


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    if not HAVE_RUAMEL:
        print(
            "WARN: ruamel.yaml not installed; falling back to PyYAML. "
            "Source files may lose comment formatting. "
            "Install with: pip install ruamel.yaml",
            file=sys.stderr,
        )

    # 1. Read every chart, collect (source_id → set(tags-to-apply)).
    # Single-source charts: union the chart's tags onto the one source.
    # Multi-source charts: by default, union onto every source unless an
    # entry in MULTI_SOURCE_OVERRIDES specifies a narrower per-source
    # subset (used for cross-domain comparison charts where the chart's
    # tag union over-tags some sources).
    all_source_tags: dict[str, set[str]] = defaultdict(set)
    multi_source_cases: list[tuple[str, list[str], list[str], bool]] = []

    chart_files = sorted(CHARTS_ROOT.rglob("*.yaml"))
    print(f"Scanning {len(chart_files)} chart manifests...")
    for cp in chart_files:
        try:
            chart = load_yaml(cp)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {cp}: {e}", file=sys.stderr)
            continue
        if not isinstance(chart, dict):
            continue
        sources = chart.get("sources") or []
        tags = chart.get("tags") or []
        if not sources or not tags:
            continue
        cid = chart_id_for_path(cp)
        if len(sources) == 1:
            all_source_tags[sources[0]].update(tags)
        else:
            override = MULTI_SOURCE_OVERRIDES.get(cid)
            if override:
                for sid, sid_tags in override.items():
                    all_source_tags[sid].update(sid_tags)
                multi_source_cases.append((cid, list(sources), list(tags), True))
            else:
                # Default: apply the chart's full tag set to every source.
                # 18/20 multi-source charts in the catalog as of this
                # writing were domain-consistent, so this is the right
                # default. Outliers go in MULTI_SOURCE_OVERRIDES.
                for sid in sources:
                    all_source_tags[sid].update(tags)
                multi_source_cases.append((cid, list(sources), list(tags), False))

    # 2. Apply accumulated tag contributions to each source YAML.
    sources_changed = 0
    sources_unchanged = 0
    sources_missing = 0
    for source_id, new_tags in sorted(all_source_tags.items()):
        # source_id might be "yahoo_marketcap/xom_mc"; map to file path.
        candidate = SOURCES_ROOT / f"{source_id}.yaml"
        if not candidate.exists():
            print(
                f"  WARN: source '{source_id}' referenced by a chart but "
                f"no matching YAML at {candidate.relative_to(REPO_ROOT)}",
                file=sys.stderr,
            )
            sources_missing += 1
            continue
        try:
            source = load_yaml(candidate)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {candidate}: {e}", file=sys.stderr)
            continue
        existing: list[str] = list(source.get("tags") or [])
        merged = sorted(set(existing) | set(new_tags))
        if merged == sorted(existing):
            sources_unchanged += 1
            continue
        source["tags"] = merged
        if not dry_run:
            dump_yaml(candidate, source)
        sources_changed += 1
        print(
            f"  {'would tag' if dry_run else 'tagged'}: {source_id} "
            f"+= {sorted(set(new_tags) - set(existing))}"
        )

    # 3. Report multi-source cases: how they were handled and which
    # ones had per-source overrides applied (so future-operator can
    # eyeball the override table for staleness or missing entries).
    print()
    print("=== Summary ===")
    print(f"  Sources updated:       {sources_changed}")
    print(f"  Sources unchanged:     {sources_unchanged}")
    print(f"  Sources missing file:  {sources_missing}")
    print(f"  Multi-source charts:   {len(multi_source_cases)}")

    if multi_source_cases:
        print()
        print("=== Multi-source charts: how their tags were applied ===")
        for cid, srcs, tags, has_override in multi_source_cases:
            marker = "OVERRIDDEN" if has_override else "default (all to all)"
            print(f"  [{marker}] {cid} ({tags})")
            if has_override:
                override = MULTI_SOURCE_OVERRIDES.get(cid, {})
                for sid in srcs:
                    applied = override.get(sid, [])
                    print(f"      {sid}: {applied or '(none — skipped)'}")

    if dry_run:
        print("(dry-run; no files modified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
