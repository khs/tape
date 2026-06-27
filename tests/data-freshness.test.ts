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
 *     (oecd/<cc>_cpi_yoy, ...), flag a member whose value last changed far
 *     behind its cohort's freshest sibling. Catches a fetch break within
 *     ~one release cycle, while a whole cohort that is uniformly lagged
 *     (normal release lag) does not trip. The tolerance is cadence-aware:
 *     ~3 release cycles, so an annual sibling reporting two cycles behind
 *     (routine for international stats) is fine, but a monthly sibling
 *     frozen for a year is not.
 *
 *  2. ABSOLUTE STALENESS (backstop, slow). Flag a series whose value last
 *     changed more than ABS_THRESHOLD median-cadence periods behind today
 *     (and at least FLOOR_DAYS absolute). Catches lone series with no
 *     cohort, single-point-with-projection freezes, and whole-cohort
 *     breaks the outlier check can't see. FLOOR_DAYS is generous so a
 *     genuinely-lagged monthly/quarterly series (Treasury TIC's ~6-month
 *     lag, OECD's structural country lags) never trips.
 *
 * Both signals measure from the date the VALUE last CHANGED, not the last
 * timestamp — some pipelines carry the latest value forward onto fresh
 * "today" dates (worldbank_gdp_raw/*), which would otherwise make a frozen
 * upstream permanently invisible. See corpus.ts:lastChangeDate.
 *
 * A flagged series fails UNLESS its id is in
 * tests/data-freshness-allowlist.json with a reason (upstream genuinely
 * capped or discontinued). The allowlist is ratchet-checked with
 * hysteresis: an entry is flagged for removal only once its series is
 * COMFORTABLY fresh again, so a series hovering near the threshold or
 * getting partial backfill doesn't flap the gate.
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
  lastChangeDate,
  cohortKeyFor,
  ROOT,
} from "./corpus";

const ABS_THRESHOLD = 4.5; // median-cadence multiples behind "now" (backstop)
const FLOOR_DAYS = 550; // ...and at least ~18 months behind in absolute terms
// Hard ceiling on absolute staleness, independent of cadence. The ratio rule
// above is cadence-aware (good), but for a long-cadence series it grants a huge
// grace window: 4.5 x a 5-year survey cadence is ~22 years, so a quinquennial
// series (USGS water) could silently freeze for two decades. Annual+ series are
// already caught by the 4.5x rule well before this. Nothing legitimately goes a
// full decade without its value moving, so flag anything past it regardless of
// cadence. Genuinely decade-plus-cadence sources (none today) would be
// allowlisted like any other upstream-capped series.
const MAX_ABS_STALE_DAYS = 3650; // ~10 years
const COHORT_K = 3; // cohort tolerance = this many member-cadence cycles...
const COHORT_FLOOR_DAYS = 400; // ...but at least this (so monthly siblings get slack)
const MIN_COHORT = 3;
const HYSTERESIS = 0.6; // an allowlisted series is "cruft" only when comfortably fresh

const allowlist = JSON.parse(
  readFileSync(join(ROOT, "tests", "data-freshness-allowlist.json"), "utf-8"),
) as Record<string, { reason?: string; task?: string }>;

const NOW = Date.now();
const DAY = 86_400_000;

interface Series {
  id: string;
  changeT: string;
  changeMs: number;
  daysBehind: number;
  cadenceDays: number | null;
  ratio: number | null; // null when cadence is unknown (<2 points)
}

const series: Series[] = [];
for (const s of referencedSources()) {
  if (!s.dataFile) continue;
  const fp = dataPath(s.dataFile);
  if (!existsSync(fp)) continue;
  const d = readJson(fp);
  if (!isTimeseries(d)) continue;
  const pts = points(d);
  const last = lastPoint(d);
  if (!last) continue;
  const cadenceDays = medianCadenceDays(pts);
  // Measure from the last VALUE CHANGE, not the last timestamp (carry-forward).
  const changeT = lastChangeDate(pts, cadenceDays) ?? last.t;
  const changeMs = Date.parse(changeT);
  if (Number.isNaN(changeMs)) continue;
  const daysBehind = (NOW - changeMs) / DAY;
  series.push({
    id: s.id,
    changeT,
    changeMs,
    daysBehind,
    cadenceDays,
    ratio: cadenceDays != null ? daysBehind / cadenceDays : null,
  });
}

interface Frozen {
  id: string;
  why: string;
}

// --- Signal 1: cohort outliers (member far behind its freshest sibling) ---
function cohortOutliers(): Frozen[] {
  const byCohort = new Map<string, Series[]>();
  for (const s of series) {
    const key = cohortKeyFor(s.id);
    if (!key) continue;
    const arr = byCohort.get(key);
    if (arr) arr.push(s);
    else byCohort.set(key, [s]);
  }
  const out: Frozen[] = [];
  for (const [key, members] of byCohort) {
    if (members.length < MIN_COHORT) continue;
    const freshest = members.reduce((a, b) => (b.changeMs > a.changeMs ? b : a));
    for (const m of members) {
      const tolDays = Math.max(COHORT_FLOOR_DAYS, COHORT_K * (m.cadenceDays ?? 365));
      const behindDays = (freshest.changeMs - m.changeMs) / DAY;
      if (behindDays > tolDays) {
        out.push({
          id: m.id,
          why: `value last moved ${Math.round(behindDays)}d behind its cohort '${key}' (freshest sibling: ${freshest.changeT}; this: ${m.changeT})`,
        });
      }
    }
  }
  return out;
}

// --- Signal 2: absolute staleness (backstop) ------------------------------
function absoluteStale(): Frozen[] {
  return series
    .filter(
      (s) =>
        s.daysBehind > FLOOR_DAYS &&
        (s.ratio == null ||
          s.ratio > ABS_THRESHOLD ||
          s.daysBehind > MAX_ABS_STALE_DAYS),
    )
    .map((s) => ({
      id: s.id,
      why:
        s.ratio == null
          ? `value last moved ${s.changeT}, ${Math.round(s.daysBehind)}d ago (cadence unknown — <2 historical points)`
          : s.daysBehind > MAX_ABS_STALE_DAYS && s.ratio <= ABS_THRESHOLD
            ? `value last moved ${s.changeT}, ${Math.round(s.daysBehind)}d ago (past the ${MAX_ABS_STALE_DAYS}d absolute ceiling; ${Math.round(s.cadenceDays!)}d cadence)`
            : `value last moved ${s.changeT}, ${Math.round(s.daysBehind)}d ago (~${s.ratio.toFixed(1)}x its ${Math.round(s.cadenceDays!)}d cadence)`,
    }));
}

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
    const byId = new Map(series.map((s) => [s.id, s]));
    // Hysteresis: only demand removal once a series is COMFORTABLY fresh,
    // so one near the threshold (or getting partial backfill) doesn't flap.
    const comfortablyFresh = (s: Series) =>
      s.ratio == null
        ? s.daysBehind < FLOOR_DAYS * HYSTERESIS
        : s.ratio < ABS_THRESHOLD * HYSTERESIS;
    const cruft = Object.keys(allowlist).filter((id) => {
      if (id === "_doc") return false;
      const s = byId.get(id);
      return s != null && !frozen.has(id) && comfortablyFresh(s);
    });
    expect(
      cruft,
      `\nThese allowlist entries are referenced and comfortably fresh again (fixed) — remove them ` +
        `from tests/data-freshness-allowlist.json:\n  ${cruft.join("\n  ")}\n`,
    ).toEqual([]);
  });
});
