import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const deltaWindow = z.enum([
  "1w",
  "1m",
  "ytd",
  "1y",
  "5y",
  "10y",
  "30y",
  "50y",
]);

const formatting = z
  .object({
    style: z
      .enum(["currency", "percent", "number", "index", "bps"])
      .default("number"),
    decimals: z.number().int().min(0).max(6).default(2),
    currency: z.string().optional(),
    prefix: z.string().optional(),
    suffix: z.string().optional(),
    // "compact" renders big numbers as "$3.41T", "$500M" etc. (uses Intl compact).
    notation: z.enum(["standard", "compact"]).optional(),
  })
  .default({});

const provenance = z.object({
  provider: z.string(),
  series: z.string().optional(),
  license: z.string().optional(),
  url: z.string().optional(),
  notes: z.string().optional(),
});

const emphasis = z.enum(["level", "change"]);

const sources = defineCollection({
  loader: glob({ pattern: "**/*.yaml", base: "./src/content/sources" }),
  schema: z.object({
    name: z.string(),
    shortName: z.string().optional(),
    description: z.string().optional(),
    kind: z.enum(["timeseries", "curve"]),
    pipeline: z.string(),
    dataFile: z.string(),
    supportedDeltas: z.array(deltaWindow).min(1),
    unit: z.string().optional(),
    formatting,
    provenance,
    emphasis: emphasis.default("level"),
  }),
});

const charts = defineCollection({
  loader: glob({ pattern: "**/*.yaml", base: "./src/content/charts" }),
  schema: z.object({
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
      .default("line"),
    defaultDelta: deltaWindow.default("1m"),
    blurb: z.string().optional(),
    emphasis: emphasis.optional(),
    // How to normalize multi-source plots. "rebase" indexes every series to 100
    // at the window start (good for comparing relative returns of dissimilar
    // scales). "raw" plots each at its natural scale.
    normalize: z.enum(["rebase", "raw", "dual-axis"]).optional(),
    // For dual-axis charts, source IDs that plot on the right axis. Anything
    // not listed plots on the left. Ignored unless normalize === "dual-axis".
    rightAxisSources: z.array(z.string()).optional(),
    // Per-chart short labels for series (overrides source.shortName for this chart).
    seriesLabels: z.array(z.string()).optional(),
    // Topic tags for the composer library filter. Multi-tag allowed; proposed
    // starter taxonomy (expand as needed): rates, equity-index, single-name,
    // macro, commodities, credit, world.
    tags: z.array(z.string()).default([]),
    // Chart-ID stability contract: deprecated charts with an aliasOf resolve
    // to the alias so composed/saved dashboards keep working across renames.
    deprecated: z.boolean().optional(),
    aliasOf: z.string().optional(),
  }),
});

const chartOverrideSchema = z
  .object({
    title: z.string(),
    render: z.enum([
      "line",
      "curve",
      "smallMultiples",
      "sparkDelta",
      "deltaGrid",
      "relativeReturns",
    ]),
    defaultDelta: deltaWindow,
    blurb: z.string(),
    sources: z.array(z.string()),
    emphasis,
    normalize: z.enum(["rebase", "raw", "dual-axis"]),
    seriesLabels: z.array(z.string()),
  })
  .partial();

const sectionSchema = z.object({
  title: z.string(),
  description: z.string().optional(),
  charts: z.array(z.string()).min(1),
});

const dashboards = defineCollection({
  loader: glob({
    pattern: "**/*.{md,mdx}",
    base: "./src/content/dashboards",
  }),
  schema: z
    .object({
      title: z.string(),
      description: z.string().optional(),
      charts: z.array(z.string()).optional(),
      sections: z.array(sectionSchema).optional(),
      chartOverrides: z.record(z.string(), chartOverrideSchema).optional(),
      defaultDelta: deltaWindow.optional(),
      fixedRange: z
        .object({
          start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
          end: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
        })
        .optional(),
      order: z.number().int().optional(),
    })
    .refine(
      (d) => (d.charts?.length ?? 0) > 0 || (d.sections?.length ?? 0) > 0,
      { message: "Dashboard must have at least one of `charts` or `sections`." },
    ),
});

export const collections = { sources, charts, dashboards };
