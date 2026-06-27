/**
 * Single source of truth for the chart-override field set.
 *
 * Historically the override shape was defined twice: the rich version in
 * `src/content/config.ts` (a dashboard's `chartOverrides`) and a 4-field
 * subset in `src/lib/composer-state.ts` (the `/compose/?d=` URL state). The
 * two drifted, and forking a preset that carried rich overrides silently
 * dropped everything but `title` / `defaultDelta` / `blurb` on the way into
 * the composer.
 *
 * Defining the shape ONCE here fixes that. It's a factory rather than a
 * plain exported schema because the two callers use different Zod
 * entrypoints — `config.ts` uses `astro:content`'s `z`, `composer-state.ts`
 * uses the `zod` package's `z` — and nesting a schema built by one instance
 * inside an object built by the other is a known footgun. The factory builds
 * every sub-schema with the caller's OWN `z`, so each side stays internally
 * consistent. `deltaWindowSchema` is passed in for the same reason: each
 * caller already has its own delta-window enum.
 *
 * Callers wrap the returned shape: `z.object(buildChartOverrideShape(z, dw)).partial()`.
 * Keep this in sync with the `charts` collection schema in
 * `src/content/config.ts` — every override field mirrors a chart field.
 */
import type * as Zod from "zod";

export function buildChartOverrideShape(
  z: typeof Zod.z,
  deltaWindowSchema: Zod.ZodTypeAny,
) {
  const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
  return {
    title: z.string(),
    render: z.enum([
      "line",
      "curve",
      "smallMultiples",
      "sparkDelta",
      "deltaGrid",
      "relativeReturns",
      "bar",
    ]),
    defaultDelta: deltaWindowSchema,
    blurb: z.string(),
    sources: z.array(z.string()),
    emphasis: z.enum(["level", "change"]),
    normalize: z.enum(["rebase", "raw", "dual-axis"]),
    scale: z.enum(["linear", "log"]),
    seriesLabels: z.array(z.string()),
    percentDisplay: z.enum(["percent", "decimal", "ratio"]),
    transform: z.enum(["level", "yoy_pct", "index_100"]),
    annotations: z.array(
      z.object({
        date: isoDate,
        label: z.string(),
        position: z.enum(["above", "below"]).optional(),
      }),
    ),
    // Background shading layers — mirror of the chart-level `shading` field.
    shading: z.array(
      z.enum([
        "recessions",
        "president_party",
        "senate_majority",
        "house_majority",
        "bear_markets",
        "fed_chairs",
      ]),
    ),
    // Bar-snapshot overrides (mirror the chart-level bar fields).
    barOrientation: z.enum(["vertical", "horizontal"]),
    barSort: z.enum(["desc", "asc", "source-order"]),
    barAsOf: isoDate,
  };
}
