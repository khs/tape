import { z } from "zod";
import { DELTA_WINDOWS, type DeltaWindow } from "./deltas";
import { buildChartOverrideShape } from "./chart-schema";

/**
 * Schema version for composed-dashboard URL state. Bump this whenever the
 * shape changes incompatibly; the /custom/ renderer shows an error banner when
 * the incoming `v` doesn't match and asks the user to re-fork.
 */
export const COMPOSER_STATE_VERSION = 1 as const;

// Upper bounds so a hostile ?d= / saved-dashboard row can't fan resolveSections
// out into a compute/egress DoS (security audit 2026-06). Generous — far above
// any real dashboard; they bound abuse, not legitimate composition.
const MAX_SECTIONS = 100;
const MAX_CHARTS = 300; // per-section and top-level chart lists
const MAX_INLINE_ENTRIES = 300; // inlineCharts / inlineSources / inlineMaps / chartOverrides
const MAX_SOURCES_PER_CHART = 50;
const boundedRecord = <T extends z.ZodTypeAny>(value: T, max = MAX_INLINE_ENTRIES) =>
  z
    .record(z.string(), value)
    .refine((o) => Object.keys(o).length <= max, { message: `too many entries (max ${max})` });

const deltaWindowSchema = z.enum(DELTA_WINDOWS as unknown as [DeltaWindow, ...DeltaWindow[]]);

const shadingSchema = z.array(
  z.enum([
    "recessions",
    "president_party",
    "senate_majority",
    "house_majority",
    "bear_markets",
    "fed_chairs",
  ]),
);

// Field set shared with the dashboard content schema via the factory in
// chart-schema.ts. Previously this carried only title/defaultDelta/blurb/
// shading, so forking a preset with richer overrides (emphasis, normalize,
// scale, transform, annotations, bar settings, …) dropped them. The factory
// is the single source of truth; this is the full set, all optional. The
// change is additive — every existing v1 state still validates — so
// COMPOSER_STATE_VERSION stays 1 (no forced re-fork of saved/shared links).
const chartOverrideSchema = z
  .object(buildChartOverrideShape(z, deltaWindowSchema))
  .partial();

// Sections can carry their own time-window settings, overriding the
// dashboard-level one for the charts inside. Two ways:
//   - defaultDelta: pick a relative window (1y, 10y, 30y, …)
//   - fixedRange: pin to specific dates
// When both are present, fixedRange wins (matches the dashboard-level
// precedence). Per-tile pill clicks still work on top of either.
const sectionFixedRangeSchema = z.object({
  start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  end: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
});

const sectionSchema = z
  .object({
    title: z.string(),
    description: z.string().optional(),
    // Charts can be empty when the section is markdown-only. The
    // .refine below requires either a non-empty chart list OR a
    // markdown body so a section can't be both empty.
    charts: z.array(z.string()).max(MAX_CHARTS).default([]),
    // Section-as-markdown body. Safe-subset markdown (see
    // src/lib/markdown.ts). Renders full-width when the section has
    // no charts; renders above the chart grid when charts is set.
    markdown: z.string().optional(),
    defaultDelta: deltaWindowSchema.optional(),
    fixedRange: sectionFixedRangeSchema.optional(),
  })
  .refine(
    (s) =>
      (s.charts && s.charts.length > 0) ||
      (s.markdown && s.markdown.trim().length > 0),
    { message: "Section needs either a chart list or a markdown body." },
  );

/**
 * An ad-hoc chart assembled in the composer from 1+ source IDs. Stored in the
 * composed state's `inlineCharts` map; section chart lists reference these by
 * an `inline:<id>` key. Keeping them as a map (rather than inlined into the
 * chart list) lets a chart be referenced multiple times within one dashboard
 * and keeps the renderer's chart-ID abstraction uniform.
 */
const inlineChartSchema = z.object({
  title: z.string(),
  sources: z.array(z.string()).min(1).max(MAX_SOURCES_PER_CHART),
  render: z
    .enum([
      "line",
      "curve",
      "smallMultiples",
      "sparkDelta",
      "deltaGrid",
      "relativeReturns",
      "bar",
    ])
    .optional(),
  // Bar-snapshot fields (only honored when render === "bar"). Mirror
  // the chart-spec schema so a composer-built inline bar chart
  // round-trips identically to a curated library bar chart.
  barOrientation: z.enum(["vertical", "horizontal"]).optional(),
  barSort: z.enum(["desc", "asc", "source-order"]).optional(),
  barAsOf: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
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
  // Order matters for divide / diff (sources[0] op sources[1]); sum and
  // multiply are commutative. Currently restricted to 2 sources.
  op: z.enum(["divide", "sum", "diff", "multiply"]).optional(),
  // For divide-results that would auto-render as percent (same-style
  // numerator + denominator), choose between "percent" (default,
  // multiplies by 100 and labels with %) and "decimal" (skips the
  // multiplier, displays raw ratio with 4 decimals). "decimal" reads
  // better for cross-commodity ratios like WTI/Brent where "104%"
  // implies a share-of relationship that doesn't really apply.
  percentDisplay: z.enum(["percent", "decimal", "ratio"]).optional(),
  // Background shading layers — see src/lib/shading-presets.ts. Each
  // preset paints semi-transparent rectangles BEHIND the line on the
  // dialog plot. Multiple stack via alpha compositing. Optional —
  // omitted means no shading; an empty array also means no shading.
  shading: shadingSchema.optional(),
  // Default y-axis transformation (level / yoy_pct / index_100).
  // Per-session pill clicks in the dialog override this without
  // mutating the saved chart. See src/lib/transforms.ts.
  transform: z.enum(["level", "yoy_pct", "index_100"]).optional(),
  // Editorial annotations on the dialog plot — text labels pinned
  // to specific dates with a thin vertical guide. See chart schema
  // in src/content/config.ts for the field's full rationale.
  annotations: z
    .array(
      z.object({
        date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
        label: z.string(),
        position: z.enum(["above", "below"]).optional(),
      }),
    )
    .optional(),
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
  op: z.enum(["divide", "sum", "diff", "multiply"]),
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

/**
 * An ad-hoc map built in the composer's Maps tab.
 *
 * Map charts don't fit the standard `inlineChartSchema` (which
 * requires a `sources` list and uses `render` to dispatch a renderer).
 * Maps are dispatched by `render === "map"` at the existing
 * Chart.astro / ChartMap.astro boundary; we encode them as
 * their own schema here so the composer + renderer share the same
 * field set without overloading the time-series shape.
 *
 * Referenced from section chart lists by `inlinemap:<id>`. Lives in
 * `composedState.inlineMaps`, mirroring how `inlineCharts` works.
 *
 * Field semantics match `src/content/config.ts`'s map-chart
 * shape exactly — see that file for the canonical reference. Briefly:
 *   geo            tract | block-group | county | state
 *   indicator      out_id from census_acs_choropleth.py's INDICATORS
 *   vintage        "YYYY" of ACS 5-year vintage
 *   state          2-letter code (required when geo is tract / BG)
 *   bbox           [west, south, east, north] in lng/lat; clips view
 *   boundaryFile   path under public/ to a TopoJSON with the polygons
 *   colorScheme    Plot color-scheme name, e.g. "reds"
 *   colorScale     "linear" or "log"
 */
const inlineMapSchema = z.object({
  title: z.string(),
  geo: z.enum(["state", "county", "tract", "block-group"]),
  indicator: z.string(),
  vintage: z.string().regex(/^\d{4}$/),
  state: z.string().length(2).optional(),
  states: z.array(z.string().length(2)).optional(),
  bbox: z
    .tuple([z.number(), z.number(), z.number(), z.number()])
    .optional(),
  boundaryFile: z.string().optional(),
  colorScheme: z.string().optional(),
  colorScale: z.enum(["linear", "log"]).optional(),
  blurb: z.string().optional(),
});

export type InlineMap = z.infer<typeof inlineMapSchema>;

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
  charts: z.array(z.string()).max(MAX_CHARTS).optional(),
  sections: z.array(sectionSchema).max(MAX_SECTIONS).optional(),
  chartOverrides: boundedRecord(chartOverrideSchema).optional(),
  inlineCharts: boundedRecord(inlineChartSchema).optional(),
  inlineSources: boundedRecord(inlineSourceSchema).optional(),
  inlineMaps: boundedRecord(inlineMapSchema).optional(),
  /**
   * Thin reference to a preset dashboard. When set, the renderer
   * IGNORES sections/charts/inlineCharts on this row and renders the
   * named preset's content instead (so updates to the preset YAML
   * automatically flow to every user with a presetRef row, no
   * snapshot drift).
   *
   * Used by the walkthrough seed: every signed-in user gets exactly
   * one row with `presetRef: "walkthrough"`, which renders as a live
   * mirror of /walkthrough/.
   *
   * Value must match a real preset dashboard collection ID; unknown
   * preset refs fall back to whatever sections/charts the row also
   * carries (in practice empty, so the user sees "this dashboard
   * has no charts").
   */
  presetRef: z.string().optional(),
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
