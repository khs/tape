/**
 * Chart annotations — text labels pinned to specific dates on the
 * dialog plot. The FT / NYT / Bloomberg editorial convention: a thin
 * vertical guide at "2008-09-15" with the label "Lehman collapse"
 * floating at the top of the plot, so a reader scanning a 30-year
 * macro chart can see at-a-glance where the major shocks landed.
 *
 * Each annotation is just (date, label, optional position). Stored
 * on chart YAML, inline-chart spec, and chartOverride — same shape
 * in all three so the composer + curated dashboards + saved
 * dashboards round-trip identically.
 *
 * Authoring format on the composer side: a textarea where each line
 * is `YYYY-MM-DD: label`. parseAnnotationLines() below normalizes
 * that into the schema's array shape; format() goes the other way
 * for editing existing annotations.
 */

export interface Annotation {
  /** ISO YYYY-MM-DD date the label pins to. */
  date: string;
  /** Display text. Plain text — no HTML pass-through (the renderer
   *  escapes when emitting). */
  label: string;
  /** Vertical placement on the plot. Default "above" — the label
   *  floats just under the window pills. "below" parks it near the
   *  x-axis baseline, useful for alternating dense annotations so
   *  they don't visually collide. */
  position?: "above" | "below";
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Parse a textarea body of `YYYY-MM-DD: label` lines into a list of
 * Annotation objects. Each line:
 *
 *   2008-09-15: Lehman collapse
 *   2020-03-15: COVID lockdown
 *   2022-03-16: Fed pivot
 *
 * Whitespace-only lines and lines starting with `#` (comments) are
 * skipped. Malformed lines (no `:`, bad date) are dropped with a
 * warning visible only via the optional `onError` callback — the
 * parser is forgiving so a partial textarea state doesn't crash
 * the composer's preview render.
 *
 * Trailing-pipe suffix sets the position:
 *
 *   2020-03-15: COVID lockdown | below
 *
 * Any other token after `|` is ignored; the convention is
 * forward-compatible with a future "color" / "style" knob.
 */
export function parseAnnotationLines(
  text: string,
  onError?: (lineNumber: number, line: string, reason: string) => void,
): Annotation[] {
  if (!text) return [];
  const out: Annotation[] = [];
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const trimmed = raw.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith("#")) continue;
    const colon = trimmed.indexOf(":");
    if (colon < 0) {
      onError?.(i + 1, raw, "missing colon between date and label");
      continue;
    }
    const datePart = trimmed.slice(0, colon).trim();
    const rest = trimmed.slice(colon + 1).trim();
    if (!DATE_RE.test(datePart)) {
      onError?.(i + 1, raw, `not a YYYY-MM-DD date: ${datePart}`);
      continue;
    }
    // Optional `| position` suffix.
    let label = rest;
    let position: Annotation["position"] | undefined;
    const pipe = rest.lastIndexOf("|");
    if (pipe >= 0) {
      const token = rest.slice(pipe + 1).trim().toLowerCase();
      if (token === "above" || token === "below") {
        position = token;
        label = rest.slice(0, pipe).trim();
      }
    }
    if (!label) {
      onError?.(i + 1, raw, "empty label");
      continue;
    }
    out.push(position ? { date: datePart, label, position } : { date: datePart, label });
  }
  return out;
}

/**
 * Inverse of parseAnnotationLines — turn a list of Annotations back
 * into a textarea-friendly string. Used by the composer when seeding
 * the textarea from an existing chart's saved annotations.
 */
export function formatAnnotationLines(anns: Annotation[]): string {
  if (!anns || anns.length === 0) return "";
  return anns
    .map((a) =>
      a.position
        ? `${a.date}: ${a.label} | ${a.position}`
        : `${a.date}: ${a.label}`,
    )
    .join("\n");
}

/**
 * "Annotations outside the current dialog window" summary — pure helper
 * used by ChartController to fill the small in-dialog notice. Counts
 * annotations whose date falls outside the visible [startMs, endMs]
 * domain and picks the smallest standard window that would cover every
 * off-window date.
 *
 * `windowDaysList` is `[{key, days}]` for the chart's supported
 * windows, smallest-first. The renderer passes
 * `supported.map(w => ({ key: w, days: DELTA_DAYS[w] }))`. We keep the
 * helper free of the DELTA_DAYS lookup so it stays as easy to unit-
 * test as parseAnnotationLines.
 *
 * Returns:
 *   - count: number of annotations outside [startMs, endMs].
 *   - recommendedKey: the smallest window-key wide enough to include
 *     every off-window annotation, or null when no window covers them
 *     (e.g., the annotation is older than the longest standard window).
 */
export function annotationsHiddenSummary(
  annotations: Annotation[] | undefined,
  domainMs: [number, number],
  windowDaysList: ReadonlyArray<{ key: string; days: number }>,
  nowMs: number = Date.now(),
): { count: number; recommendedKey: string | null } {
  if (!annotations || annotations.length === 0) {
    return { count: 0, recommendedKey: null };
  }
  const [startMs, endMs] = domainMs;
  const offWindow: Annotation[] = [];
  for (const a of annotations) {
    const ms = new Date(a.date).getTime();
    if (ms < startMs || ms > endMs) offWindow.push(a);
  }
  if (offWindow.length === 0) {
    return { count: 0, recommendedKey: null };
  }
  // We only suggest windows wide enough to reach the OLDEST off-window
  // annotation — that's the binding constraint. Future-dated off-window
  // annotations (annotation > endMs) aren't covered by any trailing
  // window, so a future-only off-window list returns no recommendation.
  // Tracking the oldest is sufficient for the common "you typed a 2008
  // date on a 1y chart" case.
  const oldestMs = Math.min(
    ...offWindow.map((a) => new Date(a.date).getTime()),
  );
  if (oldestMs > endMs) {
    // Every off-window annotation is in the future — no past-window
    // recommendation helps. Surface the count, omit the suggestion.
    return { count: offWindow.length, recommendedKey: null };
  }
  const ageDays = (nowMs - oldestMs) / 86_400_000;
  // Smallest-first walk: take the first window whose lookback covers
  // the oldest annotation. Falls through to null when none does.
  const sorted = [...windowDaysList].sort((a, b) => a.days - b.days);
  const rec = sorted.find((w) => w.days >= ageDays);
  return {
    count: offWindow.length,
    recommendedKey: rec ? rec.key : null,
  };
}

/**
 * "Annotations outside the chart's available data range" summary —
 * pure helper used by the cc-modal to warn the author at chart-
 * creation time. Unlike annotationsHiddenSummary (a per-window
 * filter on the rendered dialog), this catches annotations that
 * can't render at ANY window because the underlying source data
 * doesn't extend that far back or forward.
 *
 * `sourceRanges` is a list of `{firstObservation, lastObservation}`
 * for the chart's picked sources; either field may be undefined when
 * the source's data isn't loaded into library.json yet. The chart's
 * effective data span is the union [min(first), max(last)]; an
 * annotation that predates the union start or postdates the union
 * end is unreachable.
 *
 * Returns:
 *   - offBefore / offAfter: annotations on each side of the data span.
 *   - unionStart / unionEnd: the union span (null when no source
 *     observed-date data is available — in which case the function
 *     returns empty off-lists since we can't tell).
 */
export function annotationsOutOfRangeSummary(
  annotations: Annotation[] | undefined,
  sourceRanges: ReadonlyArray<{
    firstObservation?: string;
    lastObservation?: string;
  }>,
): {
  offBefore: Annotation[];
  offAfter: Annotation[];
  unionStart: string | null;
  unionEnd: string | null;
} {
  if (!annotations || annotations.length === 0 || sourceRanges.length === 0) {
    return {
      offBefore: [],
      offAfter: [],
      unionStart: null,
      unionEnd: null,
    };
  }
  let unionStart: string | null = null;
  let unionEnd: string | null = null;
  for (const s of sourceRanges) {
    if (s.firstObservation) {
      if (!unionStart || s.firstObservation < unionStart) {
        unionStart = s.firstObservation;
      }
    }
    if (s.lastObservation) {
      if (!unionEnd || s.lastObservation > unionEnd) {
        unionEnd = s.lastObservation;
      }
    }
  }
  if (!unionStart && !unionEnd) {
    return { offBefore: [], offAfter: [], unionStart: null, unionEnd: null };
  }
  // YYYY-MM-DD string compare is order-preserving — no Date() round-trip.
  const offBefore = annotations.filter(
    (a) => unionStart != null && a.date < unionStart,
  );
  const offAfter = annotations.filter(
    (a) => unionEnd != null && a.date > unionEnd,
  );
  return { offBefore, offAfter, unionStart, unionEnd };
}
