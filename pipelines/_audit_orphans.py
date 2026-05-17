"""Find orphans on either side of the source → data mapping.

  - "Orphan YAMLs"  — source YAML whose dataFile doesn't exist on disk.
                       Chart that loads this source will fail at render
                       time with empty data.
  - "Orphan data"   — JSON file under public/data/ that no source YAML
                       points at. Pure repo bloat; can be deleted.

Skips public/data/_archive/ (historical snapshots, intentionally kept).
Skips .summary.json sibling files (those are auto-generated from the
main data files and don't need their own source-side registration).

Exits 0 always; prints findings for human review.
"""
import re
import sys
from pathlib import Path

ROOT = Path(".")
SRC_ROOT = ROOT / "src" / "content" / "sources"
DATA_ROOT = ROOT / "public" / "data"

# 1. Walk sources, collect dataFile paths.
yaml_to_data: dict[Path, Path] = {}
for yaml_path in SRC_ROOT.rglob("*.yaml"):
    text = yaml_path.read_text(encoding="utf-8")
    m = re.search(r"^dataFile:\s*(\S+)", text, re.M)
    if not m:
        continue
    yaml_to_data[yaml_path] = ROOT / "public" / m.group(1)

# 2. Orphan YAMLs: YAML whose data file doesn't exist.
orphan_yamls = []
for yaml_path, data_path in yaml_to_data.items():
    if not data_path.exists():
        orphan_yamls.append((yaml_path, data_path))

# 3. Walk data files (skip _archive + .summary.json), collect set.
referenced_data: set[Path] = set(yaml_to_data.values())
orphan_data: list[Path] = []
for data_path in DATA_ROOT.rglob("*.json"):
    if "_archive" in data_path.parts:
        continue
    if data_path.name.endswith(".summary.json"):
        continue
    if data_path not in referenced_data:
        orphan_data.append(data_path)

print(f"=== {len(orphan_yamls)} source YAMLs with missing data files ===")
for yaml_path, data_path in sorted(orphan_yamls)[:30]:
    print(f"  YAML: {yaml_path.relative_to(ROOT)}")
    print(f"  -> missing: {data_path.relative_to(ROOT)}")
if len(orphan_yamls) > 30:
    print(f"  ... and {len(orphan_yamls)-30} more")

print()
print(f"=== {len(orphan_data)} data files with no source YAML pointing at them ===")
# Group by directory for readability.
from collections import Counter
by_dir = Counter(str(p.parent.relative_to(DATA_ROOT)) for p in orphan_data)
for dirname, count in by_dir.most_common(10):
    print(f"  {dirname}/: {count} orphans")
if len(orphan_data) <= 20:
    print()
    for p in sorted(orphan_data):
        print(f"  {p.relative_to(ROOT)}")
