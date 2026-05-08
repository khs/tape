import type { TimeSeriesData, TimeSeriesPoint } from "./data-types";

export type CombineOp = "divide" | "sum" | "diff";

const OP_LABELS: Record<CombineOp, string> = {
  divide: "÷",
  sum: "+",
  diff: "−",
};

export function combineOpLabel(op: CombineOp): string {
  return OP_LABELS[op];
}

/**
 * Combine two time series into one via a per-timestamp arithmetic op.
 *
 * The cadences may differ (daily × monthly, weekly × annual, etc.). We
 * walk the union of timestamps in chronological order, forward-filling
 * each side from its most recent observation, and emit a derived point
 * once both sides have been seen at least once.
 *
 * For "divide", any point where the divisor is zero is skipped (rather
 * than emitting Infinity / NaN).
 */
export function combineTwo(
  a: TimeSeriesData,
  b: TimeSeriesData,
  op: CombineOp,
): TimeSeriesPoint[] {
  const aMap = new Map<string, number>();
  for (const p of a.points) aMap.set(p.t, p.v);
  const bMap = new Map<string, number>();
  for (const p of b.points) bMap.set(p.t, p.v);

  // Union of timestamps, sorted chronologically.
  const all = new Set<string>();
  for (const p of a.points) all.add(p.t);
  for (const p of b.points) all.add(p.t);
  const ordered = [...all].sort();

  const out: TimeSeriesPoint[] = [];
  let lastA: number | null = null;
  let lastB: number | null = null;
  for (const t of ordered) {
    if (aMap.has(t)) lastA = aMap.get(t)!;
    if (bMap.has(t)) lastB = bMap.get(t)!;
    if (lastA === null || lastB === null) continue;
    let v: number;
    if (op === "divide") {
      if (lastB === 0) continue;
      v = lastA / lastB;
    } else if (op === "sum") {
      v = lastA + lastB;
    } else {
      v = lastA - lastB;
    }
    out.push({ t, v });
  }
  return out;
}
