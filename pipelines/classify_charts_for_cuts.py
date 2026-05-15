"""
Classify every chart manifest as KEEP or CUT-CANDIDATE for the
Phase-3 catalog trim.

Goal
----
Most "charts" in the catalog today are single-source wrappers that
the new composer's Sources tab can recreate in one click. Those are
dead weight in the Pregenerated-charts tab — they bury the actually-
curated multi-source / dual-axis / rebased / op'd / annotated charts
under a wall of bare wrappers.

Heuristic
---------
A chart is KEPT if ANY of:

  * sources.length > 1 (multi-source composition)
  * op is set (divide / sum / diff — derived-series chart)
  * normalize is "rebase" or "dual-axis"
  * scale is "log"
  * rightAxisSources is set
  * seriesLabels is set
  * emphasis is "change" (default is "level")
  * blurb is set (curator commentary)
  * defaultDelta differs from the schema default "1m"
  * Referenced by any preset dashboard's `charts` list (in
    src/content/dashboards/*.mdx frontmatter or its sections) —
    these stay because the dashboard depends on them, regardless
    of how minimal their YAML looks.

Everything else is a CUT-CANDIDATE: a single-source chart with no
editorial config that nothing curated references. The composer's
Sources tab can recreate it in one click.

The script does NOT delete anything. It prints two lists for the
operator to review. Actual deletion is a separate manual step
(``git rm <list of paths>``) or a follow-on script gated on
explicit confirmation.

Run with: ``python pipelines/classify_charts_for_cuts.py``
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

try:
    from ruamel.yaml import YAML  # type: ignore[import-untyped]
    yaml_io = YAML(typ="safe")
    HAVE_RUAMEL = True
except ImportError:
    import yaml as pyyaml  # type: ignore[import-untyped]
    yaml_io = None
    HAVE_RUAMEL = False


REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_ROOT = REPO_ROOT / "src" / "content" / "charts"
DASHBOARDS_ROOT = REPO_ROOT / "src" / "content" / "dashboards"

SCHEMA_DEFAULT_DELTA = "1m"  # src/content/config.ts charts schema default


def load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if HAVE_RUAMEL:
        return yaml_io.load(text)
    return pyyaml.safe_load(text)


def chart_id_for_path(p: Path) -> str:
    rel = p.relative_to(CHARTS_ROOT)
    return str(rel.with_suffix("")).replace("\\", "/")


def extract_frontmatter(path: Path) -> str | None:
    """Pull the YAML frontmatter block out of an MDX dashboard file."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    return m.group(1) if m else None


def referenced_chart_ids() -> set[str]:
    """Every chart ID mentioned in any preset dashboard's charts: list."""
    refs: set[str] = set()
    for dpath in sorted(DASHBOARDS_ROOT.rglob("*.mdx")):
        fm = extract_frontmatter(dpath)
        if not fm:
            continue
        try:
            data = (
                yaml_io.load(fm)
                if HAVE_RUAMEL
                else pyyaml.safe_load(fm)
            )
        except Exception as e:  # noqa: BLE001
            print(f"  WARN: couldn't parse frontmatter for {dpath.name}: {e}", file=sys.stderr)
            continue
        if not isinstance(data, dict):
            continue
        # Top-level `charts: [...]`
        for cid in (data.get("charts") or []):
            if isinstance(cid, str):
                refs.add(cid)
        # `sections: [{ charts: [...] }, ...]`
        for sec in (data.get("sections") or []):
            if not isinstance(sec, dict):
                continue
            for cid in (sec.get("charts") or []):
                if isinstance(cid, str):
                    refs.add(cid)
    return refs


def is_editorially_nontrivial(chart: dict[str, Any]) -> tuple[bool, str]:
    """Return (kept, reason). reason is empty when it's a cut candidate."""
    sources = chart.get("sources") or []
    if len(sources) != 1:
        return True, f"multi-source ({len(sources)} sources)"
    if chart.get("op"):
        return True, f"op={chart['op']}"
    normalize = chart.get("normalize")
    if normalize and normalize != "raw":
        return True, f"normalize={normalize}"
    if chart.get("scale") == "log":
        return True, "scale=log"
    if chart.get("rightAxisSources"):
        return True, "rightAxisSources set"
    if chart.get("seriesLabels"):
        return True, "seriesLabels set"
    if chart.get("emphasis") and chart["emphasis"] != "level":
        return True, f"emphasis={chart['emphasis']}"
    if chart.get("blurb"):
        return True, "has blurb"
    delta = chart.get("defaultDelta")
    if delta and delta != SCHEMA_DEFAULT_DELTA:
        return True, f"defaultDelta={delta}"
    return False, ""


def main() -> int:
    refs = referenced_chart_ids()
    print(f"Found {len(refs)} chart IDs referenced by preset dashboards.")

    chart_files = sorted(CHARTS_ROOT.rglob("*.yaml"))
    keep: list[tuple[str, str]] = []  # (chart_id, reason)
    cut_candidates: list[str] = []

    for cp in chart_files:
        try:
            chart = load_yaml(cp)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {cp}: {e}", file=sys.stderr)
            continue
        if not isinstance(chart, dict):
            continue
        cid = chart_id_for_path(cp)
        # Referenced-by-dashboard short-circuits keep.
        if cid in refs:
            keep.append((cid, "referenced by a preset dashboard"))
            continue
        kept, reason = is_editorially_nontrivial(chart)
        if kept:
            keep.append((cid, reason))
        else:
            cut_candidates.append(cid)

    print()
    print(f"=== Keep: {len(keep)} ===")
    # Group by reason for scanning.
    by_reason: dict[str, list[str]] = {}
    for cid, reason in keep:
        by_reason.setdefault(reason, []).append(cid)
    for reason in sorted(by_reason.keys()):
        items = by_reason[reason]
        print(f"\n  [{reason}] ({len(items)} charts)")
        for cid in items:
            print(f"    {cid}")

    print()
    print(f"=== Cut candidates: {len(cut_candidates)} ===")
    print(
        "These are single-source wrapper charts with no editorial config\n"
        "and no preset dashboard references. The composer's Sources tab\n"
        "recreates each in one click. Review the list; if good to cut:\n"
        f"\n    cd {REPO_ROOT}\n"
    )
    if cut_candidates:
        # Emit the git rm command split across lines for easy review.
        paths = [
            f"src/content/charts/{cid}.yaml" for cid in cut_candidates
        ]
        print("    git rm \\")
        for p in paths[:-1]:
            print(f"      {p} \\")
        print(f"      {paths[-1]}")
    print()
    print("(this script doesn't delete anything.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
