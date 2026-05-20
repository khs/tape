"""
Periodic snapshot of public/data into public/data/_archive/<YYYY-MM-DD>/...

Why: the pitch claims "citation-ready," which only holds up if a researcher
who cites a chart in March can resolve the same numbers in October. Live
data files in public/data/<pipeline>/<id>.json get overwritten every
refresh — FRED revises monthly economic series, Yahoo restates after
splits and dividends, etc. — so the live URL is a moving target.

Cadence: WEEKLY (skips if the most-recent existing snapshot is less than
SNAPSHOT_MIN_DAYS old). Originally ran on every refresh, which committed
~45,000 new files per snapshot and pushed the public/ file count over
the Vercel build's function-tracer memory ceiling.

Retention: prune snapshots older than SNAPSHOT_RETENTION_DAYS. Keeps
the historical record bounded — anyone citing a snapshot URL gets
roughly two months of resolvable history; older citations 404 and the
researcher falls back to git history (which retains every snapshot
the workflow ever wrote).

Run with: ``python pipelines/snapshot_data.py``. Idempotent — if a
recent-enough snapshot already exists, short-circuits without
re-copying.
"""
from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import DATA_ROOT

ARCHIVE_DIR = DATA_ROOT / "_archive"

# Directories under public/data that we DON'T snapshot:
#   _archive itself (would recurse), and anything that looks like a hidden
#   or admin dir. Everything else (yahoo, fred, worldbank_gdp, ...) gets
#   mirrored as-is.
SKIP_DIRS = {"_archive"}

# How long since the most-recent snapshot before we make a new one.
# 7 days = "fresh weekly cadence on the schedule the GH Actions runs on";
# also tolerates manual workflow re-runs without burning a slot every
# time. The first refresh post-window will create a new snapshot.
SNAPSHOT_MIN_DAYS = 7

# Snapshots older than this get pruned at the end of the run. Sized
# to keep the on-deploy footprint roughly 8-10 snapshots — each is
# ~45,000 JSON files and Vercel's static-deploy + function-tracer
# memory has historically tripped past ~250,000 files in public/.
# Citations against pruned vintages can still be reconstructed from
# git history (this script's own commits) if anyone needs them.
SNAPSHOT_RETENTION_DAYS = 60


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def list_existing_snapshots() -> list[tuple[Path, datetime]]:
    """Return (dir_path, parsed_date) for every existing snapshot dir,
    newest first. Non-date-named dirs are ignored."""
    if not ARCHIVE_DIR.exists():
        return []
    out: list[tuple[Path, datetime]] = []
    for child in ARCHIVE_DIR.iterdir():
        if not child.is_dir():
            continue
        if not _DATE_RE.match(child.name):
            continue
        try:
            d = datetime.strptime(child.name, "%Y-%m-%d").replace(
                tzinfo=timezone.utc,
            )
        except ValueError:
            continue
        out.append((child, d))
    out.sort(key=lambda p: p[1], reverse=True)
    return out


def main() -> int:
    if not DATA_ROOT.exists():
        print(f"No data root at {DATA_ROOT}; nothing to snapshot.", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    today_iso = now.date().isoformat()
    dest_root = ARCHIVE_DIR / today_iso

    if dest_root.exists():
        print(f"Snapshot for {today_iso} already exists at {dest_root}; skipping.")
        return 0

    # Cadence check: skip if a snapshot from the past SNAPSHOT_MIN_DAYS
    # days already exists. This is what flipped the cadence from
    # "every refresh" to "weekly" — the workflow can run daily and only
    # the first run per window writes a snapshot.
    existing = list_existing_snapshots()
    if existing:
        newest_dir, newest_date = existing[0]
        age_days = (now - newest_date).days
        if age_days < SNAPSHOT_MIN_DAYS:
            print(
                f"Most-recent snapshot {newest_dir.name} is {age_days} day(s) "
                f"old (< {SNAPSHOT_MIN_DAYS}). Skipping new snapshot.",
            )
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

    print(f"Snapshot {today_iso}: {copied} files copied to {dest_root}")

    # Retention prune. Drop any snapshot older than the retention
    # cutoff so the on-deploy file count stays bounded. Done AFTER the
    # write so a failure during copy doesn't leave us snapshot-less.
    cutoff = now - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    pruned = 0
    for dir_path, parsed_date in list_existing_snapshots():
        if parsed_date < cutoff:
            shutil.rmtree(dir_path)
            print(f"  pruned old snapshot: {dir_path.name} "
                  f"(> {SNAPSHOT_RETENTION_DAYS} days)")
            pruned += 1
    if pruned:
        print(f"Pruned {pruned} snapshot(s) older than {SNAPSHOT_RETENTION_DAYS} days.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
