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
