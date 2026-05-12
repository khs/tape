"""
Weekly snapshot of public/data into public/data/_archive/<YYYY-MM-DD>/...

Why: the pitch claims "citation-ready," which only holds up if a researcher
who cites a chart in March can resolve the same numbers in October. Live
data files in public/data/<pipeline>/<id>.json get overwritten every
refresh — FRED revises monthly economic series, Yahoo restates after
splits and dividends, etc. — so the live URL is a moving target.

The fix is cheap: copy everything into a dated archive directory once a
week, right after the refresh. Storage is dollars-per-month; integrity is
priceless when a Brookings analyst points at a chart in a footnote.

Run with: ``python pipelines/snapshot_data.py``. Idempotent — if today's
snapshot already exists it short-circuits, so re-running the workflow on
the same day doesn't double-archive.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import DATA_ROOT

ARCHIVE_DIR = DATA_ROOT / "_archive"

# Directories under public/data that we DON'T snapshot:
#   _archive itself (would recurse), and anything that looks like a hidden
#   or admin dir. Everything else (yahoo, fred, worldbank_gdp, ...) gets
#   mirrored as-is.
SKIP_DIRS = {"_archive"}


def main() -> int:
    if not DATA_ROOT.exists():
        print(f"No data root at {DATA_ROOT}; nothing to snapshot.", file=sys.stderr)
        return 1

    today = datetime.now(timezone.utc).date().isoformat()
    dest_root = ARCHIVE_DIR / today

    if dest_root.exists():
        print(f"Snapshot for {today} already exists at {dest_root}; skipping.")
        return 0

    copied = 0
    for child in DATA_ROOT.iterdir():
        if not child.is_dir() or child.name in SKIP_DIRS:
            continue
        dest = dest_root / child.name
        shutil.copytree(child, dest)
        n = sum(1 for _ in dest.rglob("*.json"))
        copied += n
        print(f"  archived {child.name}/ ({n} files)")

    print(f"Snapshot {today}: {copied} files copied to {dest_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
