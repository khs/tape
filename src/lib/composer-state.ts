import { z } from "zod";
import { DELTA_WINDOWS, type DeltaWindow } from "./deltas";

/**
 * Schema version for composed-dashboard URL state. Bump this whenever the
 * shape changes incompatibly; the /custom/ renderer shows an error banner when
 * the incoming `v` doesn't match and asks the user to re-fork.
 */
export const COMPOSER_STATE_VERSION = 1 as const;

const deltaWindowSchema = z.enum(DELTA_WINDOWS as unknown as [DeltaWindow, ...DeltaWindow[]]);

const chartOverrideSchema = z
  .object({
    title: z.string(),
    defaultDelta: deltaWindowSchema,
    blurb: z.string(),
  })
  .partial();

const sectionSchema = z.object({
  title: z.string(),
  description: z.string().optional(),
  charts: z.array(z.string()).min(1),
});

/**
 * An ad-hoc chart assembled in the composer from 1+ source IDs. Stored in the
 * composed state's `inlineCharts` map; section chart lists reference these by
 * an `inline:<id>` key. Keeping them as a map (rather than inlined into the
 * chart list) lets a chart be referenced multiple times within one dashboard
 * and keeps the renderer's chart-ID abstraction uniform.
 */
const inlineChartSchema = z.object({
  title: z.string(),
  sources: z.array(z.string()).min(1),
  render: z
    .enum([
      "line",
      "curve",
      "smallMultiples",
      "sparkDelta",
      "deltaGrid",
      "relativeReturns",
    ])
    .optional(),
  normalize: z.enum(["rebase", "raw", "dual-axis"]).optional(),
  // Y-axis scale. Default linear; "log" makes exponential growth read as
  // a straight line. Incompatible with dual-axis (mixing log + linear axes
  // is misleading) — the composer enforces this in its UI, but the schema
  // doesn't constrain it because a user could hand-craft a state with both
  // and we'd rather render something than reject the URL state outright.
  scale: z.enum(["linear", "log"]).optional(),
  // For dual-axis charts, source IDs that should plot on the right axis.
  // Anything not listed plots on the left. Ignored unless normalize === "dual-axis".
  rightAxisSources: z.array(z.string()).optional(),
  defaultDelta: deltaWindowSchema.optional(),
  blurb: z.string().optional(),
  // Optional arithmetic operation between sources. When set, the chart
  // plots a single derived series instead of the individual sources.
  // Order matters for divide / diff (sources[0] op sources[1]); sum is
  // commutative. Currently restricted to 2 sources.
  op: z.enum(["divide", "sum", "diff"]).optional(),
  // For divide-results that would auto-render as percent (same-style
  // numerator + denominator), choose between "percent" (default,
  // multiplies by 100 and labels with %) and "decimal" (skips the
  // multiplier, displays raw ratio with 4 decimals). "decimal" reads
  // better for cross-commodity ratios like WTI/Brent where "104%"
  // implies a share-of relationship that doesn't really apply.
  percentDisplay: z.enum(["percent", "decimal", "ratio"]).optional(),
});

export type InlineChart = z.infer<typeof inlineChartSchema>;

/**
 * A user-defined derived source: A op B, where A and B can each be a real
 * source ID OR another inline-source ID. The result is a first-class
 * source: it can be added to charts, combined further, given to the
 * dual-axis picker, etc. Stored in the composed state's `inlineSources`
 * map and referenced via the `derived:<id>` ID prefix.
 */
const inlineSourceSchema = z.object({
  op: z.enum(["divide", "sum", "diff"]),
  a: z.string(),
  b: z.string(),
  name: z.string(),
  // Topic tags inherited from parents at creation time (union of A.tags
  // and B.tags) plus a "custom" tag so the composer's source picker
  // can offer a "show only my custom sources" filter. Optional for
  // back-compat with older saved states; treated as empty when absent.
  tags: z.array(z.string()).optional(),
});

export type InlineSource = z.infer<typeof inlineSourceSchema>;

// Fixed-date range that pins both the visible window and the delta-prior
// anchor to a specific [start, end] pair. When set, overrides defaultDelta
// and the per-viewer window pills entirely so the dashboard reads the same
// regardless of when it's loaded — useful for "snapshot" or presentation
// dashboards. Both bounds are ISO YYYY-MM-DD strings.
const fixedRangeSchema = z.object({
  start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  end: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
});

export const composedStateSchema = z.object({
  v: z.literal(COMPOSER_STATE_VERSION),
  title: z.string().optional(),
  description: z.string().optional(),
  defaultDelta: deltaWindowSchema.optional(),
  fixedRange: fixedRangeSchema.optional(),
  charts: z.array(z.string()).optional(),
  sections: z.array(sectionSchema).optional(),
  chartOverrides: z.record(z.string(), chartOverrideSchema).optional(),
  inlineCharts: z.record(z.string(), inlineChartSchema).optional(),
  inlineSources: z.record(z.string(), inlineSourceSchema).optional(),
});

export type ComposedState = z.infer<typeof composedStateSchema>;

/** Base64url encode without padding (URL-safe). */
function base64urlEncode(input: string): string {
  // TextEncoder -> bytes -> base64 -> base64url (replace / + and strip =)
  const bytes = new TextEncoder().encode(input);
  let b64: string;
  // Browser-compatible path when available.
  if (typeof btoa !== "undefined") {
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    b64 = btoa(bin);
  } else {
    // Node fallback.
    b64 = Buffer.from(bytes).toString("base64");
  }
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64urlDecode(input: string): string {
  const pad = input.length % 4 === 0 ? "" : "=".repeat(4 - (input.length % 4));
  const b64 = input.replace(/-/g, "+").replace(/_/g, "/") + pad;
  if (typeof atob !== "undefined") {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }
  return Buffer.from(b64, "base64").toString("utf-8");
}

/**
 * Encode a composed dashboard's state into the `?d=...` URL param.
 * Accepts a partial input; stamps the current version automatically.
 */
export function encodeComposedState(
  partial: Omit<ComposedState, "v"> & Partial<Pick<ComposedState, "v">>,
): string {
  const full: ComposedState = { v: COMPOSER_STATE_VERSION, ...partial };
  // Strip undefined values so the JSON stays compact.
  const clean = JSON.parse(JSON.stringify(full));
  return base64urlEncode(JSON.stringify(clean));
}

export type DecodeResult =
  | { ok: true; state: ComposedState }
  | { ok: false; reason: "empty" | "invalid-encoding" | "invalid-shape" | "wrong-version"; message: string };

/**
 * Decode + Zod-validate a `?d=...` value. Callers should pattern-match on
 * `ok` and render an error panel when decode fails.
 */
export function decodeComposedState(raw: string | null | undefined): DecodeResult {
  if (!raw) return { ok: false, reason: "empty", message: "No composition provided." };
  let json: string;
  try {
    json = base64urlDecode(raw);
  } catch (e) {
    return { ok: false, reason: "invalid-encoding", message: "Composition link is malformed." };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return { ok: false, reason: "invalid-encoding", message: "Composition JSON is corrupted." };
  }
  const maybe = composedStateSchema.safeParse(parsed);
  if (!maybe.success) {
    const obj = parsed as { v?: unknown };
    if (typeof obj?.v === "number" && obj.v !== COMPOSER_STATE_VERSION) {
      return {
        ok: false,
        reason: "wrong-version",
        message: `This composition was created with a different version (v${obj.v}). Please re-fork or re-compose.`,
      };
    }
    return { ok: false, reason: "invalid-shape", message: "Composition doesn't match the expected shape." };
  }
  return { ok: true, state: maybe.data };
}
