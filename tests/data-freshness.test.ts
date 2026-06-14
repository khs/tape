/**
 * Data-freshness gate: the freeze detector.
 *
 * oecd/jpn_cpi_yoy was frozen ~5 years before a human spot-check noticed:
 * the data was perfectly well-formed (passed every structural check) but
 * its upstream fetch had silently stopped advancing it. This suite makes
 * that class a CI merge failure.
 *
 * Two signals, because they catch different failure modes:
 *
 *  1. COHORT OUTLIER (sharp, early). For country/geo sibling families
 *     (oecd/<cc>_cpi_yoy, ...), flag a member whose last point is far
 *     behind its cohort's freshest sibling. This is the Japan signature
 *     and catches a fetch break within ~one release cycle, while ignoring
 *     a whole cohort that is uniformly lagged (normal release lag, e.g.
 *     OECD life-expectancy all at 2023 — not a break).
 *
 *  2. ABSOLUTE STALENESS (backstop, slow). Flag a series whose last point
 *     is more than ABS_THRESHOLD median-cadence periods behind today (and
 *     at least FLOOR_DAYS in absolute terms). Catches lone series with no
 *     cohort and whole-cohort breaks the outlier check can't see. The
 *     threshold is high so normal annual lag (~3 yrs) never trips it.
 *
 * A flagged series fails the gate UNLESS its id is in
 * tests/data-freshness-allowlist.json with a reason (upstream genuinely
 * capped or discontinued). The allowlist is ratchet-checked: an entry that
 * is no longer frozen must be removed, so the list cannot rot.
 */
import { describe, it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import {
  referencedSources,
  dataPath,
  readJson,
  isTimeseries,
  points,
  lastPoint,
  medianCadenceDays,
  cohortKeyFor,
  ROOT,
} from "./corpus";

const ABS_THRESHOLD = 4.5; // cadence multiples behind "now" (backstop)
const FLOOR_DAYS = 270; // ...and at least this many absolute days behind
const COHORT_BEHIND_DAYS = 400; // member this far behind its freshest sibling = outlier
const MIN_COHORT = 3;

const allowlist = JSON.parse(
  readFileSync(join(ROOT, "tests", "data-freshness-allowlist.json"), "utf-8"),
) as Record<string, { reason?: string; task?: string }>;

const NOW = Date.now();

interface Series {
  id: string;
  lastT: string;
  lastMs: number;
  daysBehind: number;
  cadenceDays: number;
  ratio: number;
}

const series: Series[] = [];
for (const s of referencedSources()) {
  if (!s.dataFile) continue;
  const fp = dataPath(s.dataFile);
  if (!existsSync(fp)) continue;
  const d = readJson(fp);
  if (!isTimeseries(d)) continue;
  const last = lastPoint(d);
  const cadenceDays = medianCadenceDays(points(d));
  if (!last || cadenceDays == null) continue;
  const lastMs = Date.parse(last.t);
  if (Number.isNaN(lastMs)) continue;
  const daysBehind = (NOW - lastMs) / 86_400_000;
  series.push({
    id: s.id,
    lastT: last.t,
    lastMs,
    daysBehind,
    cadenceDays,
    ratio: daysBehind / cadenceDays,
  });
}

// --- Signal 1: cohort outliers (member far behind its freshest sibling) ---
interface Frozen {
  id: string;
  why: string;
}
function cohortOutliers(): Frozen[] {
  const byCohort = new Map<string, Series[]>();
  for (const s of series) {
    const key = cohortKeyFor(s.id);
    if (!key) continue;
    (byCohort.get(key) ?? byCohort.set(key, []).get(key)!).push(s);
  }
  const out: Frozen[] = [];
  for (const [key, members] of byCohort) {
    if (members.length < MIN_COHORT) continue;
    const freshest = members.reduce((a, b) => (b.lastMs > a.lastMs ? b : a));
    for (const m of members) {
      if (freshest.lastMs - m.lastMs > COHORT_BEHIND_DAYS * 86_400_000) {
        out.push({
          id: m.id,
          why: `${Math.round((freshest.lastMs - m.lastMs) / 86_400_000)}d behind its cohort '${key}' (freshest sibling ends ${freshest.lastT}; this ends ${m.lastT})`,
        });
      }
    }
  }
  return out;
}

// --- Signal 2: absolute staleness (backstop) ------------------------------
function absoluteStale(): Frozen[] {
  return series
    .filter((s) => s.daysBehind > FLOOR_DAYS && s.ratio > ABS_THRESHOLD)
    .map((s) => ({
      id: s.id,
      why: `last ${s.lastT}, ${Math.round(s.daysBehind)}d behind (~${s.ratio.toFixed(1)}x its ${Math.round(s.cadenceDays)}d cadence)`,
    }));
}

// Merge both signals into a per-id reason.
const frozen = new Map<string, string>();
for (const f of [...cohortOutliers(), ...absoluteStale()]) {
  frozen.set(f.id, frozen.has(f.id) ? `${frozen.get(f.id)}; ${f.why}` : f.why);
}

describe("data freshness (referenced time-series)", () => {
  it("no referenced series is frozen unless explicitly allowlisted", () => {
    const offenders = [...frozen.entries()].filter(([id]) => !allowlist[id]);
    const msg = offenders.map(([id, why]) => `${id}: ${why}`);
    expect(
      offenders.map(([id]) => id),
      `\nFROZEN referenced series NOT in the allowlist. Find the current upstream series and ` +
        `fix the pipeline (like the COICOP-2018 fix for Japan CPI), or — if the upstream is ` +
        `genuinely capped/discontinued — add the id to tests/data-freshness-allowlist.json with ` +
        `a reason:\n  ${msg.join("\n  ")}\n`,
    ).toEqual([]);
  });

  it("every allowlist entry is still frozen + referenced (no stale cruft)", () => {
    const referenced = new Set(series.map((s) => s.id));
    const cruft = Object.keys(allowlist).filter(
      (id) => id !== "_doc" && referenced.has(id) && !frozen.has(id),
    );
    expect(
      cruft,
      `\nThese allowlist entries are referenced but no longer frozen (fixed, or cadence changed) ` +
        `— remove them from tests/data-freshness-allowlist.json:\n  ${cruft.join("\n  ")}\n`,
    ).toEqual([]);
  });
});
