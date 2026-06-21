"""One-time in-place retag of ACS source YAMLs with topical subjects.

The ACS emitters skip-if-exists (never rewrite an existing YAML's tags), so this
script rewrites only the `tags:` block of every src/content/sources/{acs_cd,
acs_metro,acs_state}/*.yaml, setting tags = [government, us] + canonical
subjects (from pipelines/acs_subjects.py, keyed by indicator stem). It REPLACES
the old domain tag (real-estate / labor) with the canonical subject set, so
e.g. a housing indicator moves real-estate -> housing and commute moves
labor -> housing, per the owner's rulings. Line-based (no YAML reflow) to keep
the diff to just the tags block.

  python pipelines/retag_acs_subjects.py            # dry-run (report only)
  python pipelines/retag_acs_subjects.py --apply    # rewrite files
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acs_subjects import subjects_for_filename  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DIRS = ["acs_cd", "acs_metro", "acs_state", "acs_national"]
BASE = ["government", "us"]


def new_tag_block(subjects: tuple[str, ...]) -> list[str]:
    tags = list(BASE) + [s for s in subjects if s not in BASE]
    return ["tags:"] + [f"  - {t}" for t in tags]


def rewrite(text: str, subjects: tuple[str, ...]) -> tuple[str, str]:
    """Return (new_text, shape) where shape describes the tags layout found."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    shape = "none"
    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        if stripped == "tags:" or stripped == "tags: []" or stripped.startswith("tags: ["):
            shape = "inline-empty" if stripped != "tags:" else "block"
            out.extend(new_tag_block(subjects))
            i += 1
            while i < len(lines) and lines[i].startswith("  - "):
                shape = "block"
                i += 1
            continue
        out.append(ln)
        i += 1
    if shape == "none":
        # No tags: line — insert before the first trailing scalar field
        # (unitClass/hidden/derivedFrom) or at end (before trailing blank line).
        anchors = ("unitClass:", "hidden:", "derivedFrom:")
        idx = next((k for k, l in enumerate(out) if l.startswith(anchors)), None)
        block = new_tag_block(subjects)
        if idx is None:
            while out and out[-1] == "":
                out.pop()
            out.extend(block)
            out.append("")
        else:
            out[idx:idx] = block
    return "\n".join(out), shape


def main() -> int:
    apply = "--apply" in sys.argv
    by_subject = Counter()
    by_shape = Counter()
    unmapped: Counter = Counter()
    changed = 0
    total = 0
    for d in DIRS:
        ddir = REPO / "src" / "content" / "sources" / d
        for f in sorted(ddir.glob("*.yaml")):
            total += 1
            stem_geo = f.stem
            subjects = subjects_for_filename(stem_geo)
            if subjects is None:
                # record the leading token group for diagnosis
                unmapped[stem_geo.rsplit("_", 2)[0]] += 1
                continue
            for s in subjects:
                by_subject[s] += 1
            text = f.read_text(encoding="utf-8")
            new_text, shape = rewrite(text, subjects)
            by_shape[shape] += 1
            if new_text != text:
                changed += 1
                if apply:
                    f.write_text(new_text, encoding="utf-8")
    print(f"{'APPLIED' if apply else 'DRY-RUN'}: {total} files, {changed} would change")
    print("subject tag adds:", dict(by_subject))
    print("tags-block shapes:", dict(by_shape))
    if unmapped:
        print(f"\nUNMAPPED ({sum(unmapped.values())} files) — fix acs_subjects.py:")
        for stem, n in unmapped.most_common():
            print(f"  {stem}: {n}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
