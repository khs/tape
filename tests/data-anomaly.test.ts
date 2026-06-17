/**
 * Anomaly gate over the REAL referenced corpus.
 *
 * Catches SURPRISING data changes / pipeline errors that the structural
 * integrity + freshness gates do not:
 *   1. an accidental unit / scale shift, the classic pipeline corruption
 *      where a series silently switches base unit (billions <-> millions =
 *      1000x = 3 decades) or a decimal slips, so the newest point is ~100x+
 *      off the prior;
 *   2. a projection produced in a DIFFERENT base unit than its own actuals
 *      (the forecast and history are built by separate code paths and can
 *      drift apart, e.g. a CBO/SSA projection in % vs a level).
 *
 * Like data-freshness, value-anomaly checks are allowlist-gated
 * (tests/data-anomaly-allowlist.json) so a genuinely-legitimate jump can be
 * accepted with a reason without disabling the gate. The threshold is
 * deliberately conservative (a >=2-decade / >=100x step, which no real
 * economic series makes between consecutive points, and only for values
 * >= 1 so sub-unit oscillations near zero do not trip it), so the gate
 * ships green on today's corpus and only fires on FUTURE corruption.
 *
 * Scope = referenced sources (a few seconds). The full catalog is the
 * scripts/audit-source-data.mjs --full job.
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
  ROOT,
  ISO_DATE,
} from "./corpus";

type Json = Record<string, any>;

// Accepted-anomaly allowlist (id -> reason); _doc is metadata, not an id.
const allowlist: Record<string, string> = (() => {
  const p = join(ROOT, "tests", "data-anomaly-allowlist.json");
  if (!existsSync(p)) return {};
  const raw = JSON.parse(readFileSync(p, "utf-8")) as Record<string, string>;
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw)) if (k !== "_doc") out[k] = v;
  return out;
})();

interface Loaded {
  id: string;
  data: Json;
}
const loaded: Loaded[] = [];
for (const s of referencedSources()) {
  if (!s.dataFile) continue;
  const fp = dataPath(s.dataFile);
  if (!existsSync(fp)) continue;
  const data = readJson(fp) as Json;
  if (!isTimeseries(data)) continue;
  loaded.push({ id: s.id, data });
}

const show = (bad: string[]) => `\n  ${bad.join("\n  ")}\n`;

/**
 * Order-of-magnitude (base-10) distance between two magnitudes. Returns 0
 * for near-zero values (log10 is undefined / unstable near 0), so a series
 * oscillating across zero is never flagged on that basis.
 */
function decadeJump(a: number, b: number): number {
  const ea = Math.abs(a) < 1e-9 ? null : Math.round(Math.log10(Math.abs(a)));
  const eb = Math.abs(b) < 1e-9 ? null : Math.round(Math.log10(Math.abs(b)));
  if (ea === null || eb === null) return 0;
  return Math.abs(ea - eb);
}

// A real unit-base error (billions<->millions, a slipped decimal on an
// index/level) involves substantial numbers; sub-1 values jumping a decade
// are small-number noise, not a base-unit corruption. Gate on the larger
// magnitude being >= 1 so those never trip.
function suspiciousJump(a: number, b: number): boolean {
  return Math.max(Math.abs(a), Math.abs(b)) >= 1 && decadeJump(a, b) >= 2;
}

describe("value anomaly: order-of-magnitude shift (referenced time-series)", () => {
  it("no >=100x jump between the last two consecutive points", () => {
    const bad: string[] = [];
    for (const l of loaded) {
      if (l.id in allowlist) continue;
      const pts = points(l.data);
      if (pts.length < 2) continue;
      const a = pts[pts.length - 2].v;
      const b = pts[pts.length - 1].v;
      if (typeof a !== "number" || typeof b !== "number") continue;
      if (suspiciousJump(a, b)) {
        bad.push(
          `${l.id}: ${a} -> ${b} (${decadeJump(a, b)}-decade jump) at ${pts[pts.length - 1].t}`,
        );
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });
});

describe("projection sanity (referenced time-series with projections)", () => {
  // Vintage keys are publication dates of a projection round. Granularity
  // varies by source: CBO publishes several times a year (YYYY-MM); the SSA
  // Trustees Report is annual (YYYY). Accept year, year-month, or full date.
  const VINTAGE = /^\d{4}(-\d{2}(-\d{2})?)?$/;

  it("projection vintages are well-formed and continue the actuals' scale", () => {
    const bad: string[] = [];
    for (const l of loaded) {
      if (l.id in allowlist) continue;
      const proj = l.data.projections as Record<string, Json[]> | undefined;
      if (!proj || typeof proj !== "object") continue;
      const vintages = Object.keys(proj);
      if (vintages.length === 0) continue;

      // (a) every vintage key is YYYY-MM(-DD)
      for (const v of vintages) {
        if (!VINTAGE.test(v)) bad.push(`${l.id}: bad projection vintage key '${v}'`);
      }

      // latest vintage by sorted key
      const latestV = [...vintages].sort()[vintages.length - 1];
      const series = proj[latestV];
      if (!Array.isArray(series) || series.length === 0) {
        bad.push(`${l.id}: projection vintage '${latestV}' empty`);
        continue;
      }

      // (b) projection points: ISO, strictly ascending, finite
      let prev = "";
      for (const p of series) {
        if (typeof p.t !== "string" || !ISO_DATE.test(p.t)) {
          bad.push(`${l.id}: projection '${latestV}' non-ISO date ${JSON.stringify(p.t)}`);
          break;
        }
        if (prev && p.t <= prev) {
          bad.push(`${l.id}: projection '${latestV}' out-of-order ${prev} -> ${p.t}`);
          break;
        }
        if (typeof p.v !== "number" || !Number.isFinite(p.v)) {
          bad.push(`${l.id}: projection '${latestV}' bad value ${JSON.stringify(p.v)} at ${p.t}`);
          break;
        }
        prev = p.t;
      }

      // (c) first projected value continues the actuals' base scale (catches
      //     a unit mismatch between the actuals pipeline and the projection)
      const hist = points(l.data);
      if (hist.length) {
        const lastActual = hist[hist.length - 1].v;
        const firstProj = series[0].v;
        if (
          typeof lastActual === "number" &&
          typeof firstProj === "number" &&
          suspiciousJump(lastActual, firstProj)
        ) {
          bad.push(
            `${l.id}: projection '${latestV}' starts ${firstProj} vs last actual ${lastActual} (${decadeJump(lastActual, firstProj)}-decade jump)`,
          );
        }
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });
});
