"""Find any chart YAML referencing a source ID that has no matching
source YAML on disk. Diagnostic — exits with rc=1 if any broken refs."""
import sys
import yaml
from pathlib import Path

src_ids: set[str] = set()
for p in Path("src/content/sources").rglob("*.yaml"):
    rel = p.relative_to("src/content/sources")
    src_ids.add(str(rel.with_suffix("")).replace("\\", "/"))

missing: list[tuple[str, str]] = []
for p in Path("src/content/charts").rglob("*.yaml"):
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(d, dict):
        continue
    for sid in (d.get("sources") or []):
        if sid not in src_ids:
            chart_id = str(
                p.relative_to("src/content/charts").with_suffix("")
            ).replace("\\", "/")
            missing.append((chart_id, sid))

if missing:
    print(f"Broken refs in {len({m[0] for m in missing})} chart(s):")
    for cid, sid in missing:
        print(f"  {cid}: missing {sid}")
    sys.exit(1)
print(f"All chart source references resolve cleanly ({len(src_ids)} sources tracked).")
