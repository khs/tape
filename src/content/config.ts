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
    // Display-time multiplier. Used when a series is stored in
    // billions (canonical FRED convention) but should render compact
    // as raw dollars — `scaleFactor: 1e9` turns a stored 1631 into
    // a displayed "$1.63T" under notation:compact.
    scaleFactor: z.number().positive().optional(),
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
    // Topic tags used by the composer's "Sources" filter chip strip and
    // the derived-source-modal's tag picker. Populated initially by
    // pipelines/backfill_source_tags.py from the tags of single-source
    // charts that reference each source (C1 approach); multi-source
    // charts get flagged for manual review by that script.
    tags: z.array(z.string()).default([]),
    // Coarse unit class — used by combineOpFormatting to pick the
    // output format of a derived source (divide/sum/diff). Distinct
    // from formatting.style because two sources can share a style
    // ("number") but differ semantically (US GDP in billions vs Case-
    // Shiller as an index). Populated by pipelines/backfill_unit_class.py
    // by inferring from formatting + unit text; can be overridden
    // per-source in YAML.
    //
    //   currency — denominated in $/€/etc. (raw, M, B, T)
    //   count    — discrete things (people, jobs, claims, units)
    //   rate     — percentage rate, basis points
    //   index    — unitless level (CPI, market index, etc.)
    //   ratio    — unitless ratio (the default for derived sources)
    unitClass: z
      .enum(["currency", "count", "rate", "index", "ratio"])
      .optional(),
    // When true, library.json drops the source from the composer's
    // browse + search surface. Existing dashboards that reference the
    // source by id still resolve normally (resolve-dashboard.ts looks
    // them up directly, not through library.json). Used to suppress
    // raw share-price sources for tickers where the marketcap series
    // is the canonical one we want users to discover — without
    // deleting the data files, breaking any saved dashboard, or
    // pruning git history. Set to true via YAML.
    hidden: z.boolean().optional(),
  }),
});

const charts = defineCollection({
  loader: glob({ pattern: "**/*.yaml", base: "./src/content/charts" }),
  schema: z
    .object({
    title: z.string(),
    // `sources` is required for everything except choropleth charts —
    // those bind to a (geo, indicator, vintage) tuple via the
    // dedicated fields below, not to a list of time-series source
    // IDs. Renderer dispatch is by `render`; the refine() at the
    // bottom enforces the right shape for each.
    sources: z.array(z.string()).optional(),
    render: z
      .enum([
        "line",
        "curve",
        "smallMultiples",
        "sparkDelta",
        "deltaGrid",
        "relativeReturns",
        "choropleth",
      ])
      .default("line"),
    defaultDelta: deltaWindow.default("1m"),
    blurb: z.string().optional(),
    emphasis: emphasis.optional(),
    // How to normalize multi-source plots. "rebase" indexes every series to 100
    // at the window start (good for comparing relative returns of dissimilar
    // scales). "raw" plots each at its natural scale.
    normalize: z.enum(["rebase", "raw", "dual-axis"]).optional(),
    // Y-axis scale type. "log" makes exponential growth (market caps, GDP,
    // stock prices over decades) read as straight lines. Compatible with raw
    // and rebase modes; explicitly NOT compatible with dual-axis — running
    // log on one axis and linear on the other is misleading.
    scale: z.enum(["linear", "log"]).optional(),
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
    // When a multi-source divide produces a percent-style output (e.g.
    // currency/currency, count/count), the renderer multiplies by 100 and
    // labels as "%". Override per chart:
    //   percent — "104%" (default)
    //   decimal — "1.04"  (e.g. WTI / Brent)
    //   ratio   — "1.04:1" (e.g. debt:equity, P:E framing)
    percentDisplay: z.enum(["percent", "decimal", "ratio"]).optional(),
    // Optional arithmetic combine between exactly two sources. When set,
    // the renderer collapses the chart into a single derived series
    // (a op b) — used for built-in spread/ratio charts whose meaning IS
    // the combination (e.g., 10Y − 2Y treasury spread, WTI ÷ Brent ratio)
    // rather than synthesizing a phantom source for it. Order matters
    // for divide/diff; sources[0] is A, sources[1] is B. Same machinery
    // as inline charts' combine op in composer-state.ts.
    op: z.enum(["divide", "sum", "diff"]).optional(),
    // Y-axis transformation applied at render time. The chart's
    // tile always renders at "level" — the transform only affects
    // the dialog's full plot. Readers can override per-session via
    // the pill row in the dialog without modifying the saved spec.
    //
    //   level       — raw stored values (default)
    //   yoy_pct     — 12-month % change at each date; drops the
    //                 first year of points (no prior to compare to)
    //   index_100   — visible window rebased so the first point is
    //                 100
    //
    // See src/lib/transforms.ts for the math.
    transform: z.enum(["level", "yoy_pct", "index_100"]).optional(),
    // Optional background shading layers. Each entry references a
    // preset in src/lib/shading-presets.ts and renders as semi-
    // transparent rectangles BEHIND the line(s) on the dialog plot —
    // recession bands, presidential-party tinting, Fed-Chair tenures,
    // etc. Multiple entries stack via alpha compositing so e.g.
    // ["recessions", "president_party"] paints recessions on top of
    // a party-tinted background. Tile sparklines stay un-shaded; the
    // bands are too small to read at thumbnail scale.
    // Editorial annotations: text labels pinned to specific dates on
    // the dialog plot. Each annotation renders as a thin vertical
    // dashed line + a label at the top of the plot — the FT/NYT
    // "Lehman collapse" / "COVID lockdown" / "Fed pivot 2022"
    // convention. Tile sparklines stay unannotated; the labels are
    // unreadable at thumbnail scale.
    annotations: z
      .array(
        z.object({
          date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
          label: z.string(),
          // Optional vertical placement of the label text. "above"
          // (default) sits at the top of the plot just below the
          // window pills; "below" sits at the bottom near the x-axis.
          // Useful when a chart has many annotations crowded into
          // the same era — alternating them stays legible.
          position: z.enum(["above", "below"]).optional(),
        }),
      )
      .optional(),
    shading: z
      .array(
        z.enum([
          "recessions",
          "president_party",
          "senate_majority",
          "house_majority",
          "bear_markets",
          "fed_chairs",
        ]),
      )
      .optional(),
    // ---- Choropleth-specific fields (render === "choropleth") ----
    // Geographic granularity. State + county data ship for the full
    // US. Tract + block-group data ship state-sharded; charts at
    // those levels must specify `state` (and may add `bbox` to clip
    // further). Renderer joins ACS values onto us-atlas TopoJSON via
    // GEOID — 2-digit state FIPS, 5-digit county FIPS, 11-digit
    // tract GEOID, 12-digit block-group GEOID.
    geo: z.enum(["state", "county", "tract", "block-group"]).optional(),
    // ACS indicator key (e.g., "poverty_rate", "median_hh_income",
    // "bachelors_plus_pct", "foreign_born_pct"). Must match the
    // out_id of one of pipelines/census_acs_choropleth.py's
    // INDICATORS entries. Resolves to public/data/acs_<geo>/
    // <indicator>_<vintage>.json (or the state-sharded variant for
    // tract / block-group).
    indicator: z.string().optional(),
    // ACS 5-year ending year, e.g. "2022".
    vintage: z.string().regex(/^\d{4}$/).optional(),
    // Required for tract / block-group when only one state's worth of
    // data is needed: 2-letter state code (e.g. "VA"). Selects the
    // state-sharded data file. Use `states` instead when a chart
    // spans multiple states (DMV-area tract maps span VA + MD + DC).
    state: z.string().length(2).optional(),
    states: z.array(z.string().length(2)).optional(),
    // For tract / block-group charts: path to a custom TopoJSON
    // boundary file (e.g. "/maps/dmv-tracts-topo.json"). State and
    // county charts reuse the bundled us-counties-10m.json so this
    // field is unused for those. The TopoJSON's top-level objects
    // map should contain a layer named "tracts" or "block_groups".
    boundaryFile: z.string().optional(),
    // Optional bounding box [west, south, east, north] in lng/lat,
    // for tract / block-group charts that want to clip to a region
    // smaller than the full state. Helps avoid death-by-polygons
    // when zoomed-out tract views aren't useful. Polygons whose
    // any vertex falls inside the bbox are kept; others are dropped
    // pre-render so Plot's projection auto-fits the clipped area.
    bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]).optional(),
    // Plot color scheme name (e.g., "blues", "ylorrd", "rdylgn").
    // Defaults to "blues" for sequential indicators. See
    // Observable Plot's scheme list.
    colorScheme: z.string().optional(),
    // Color-scale type. "linear" maps min→max linearly; "log" is
    // useful for indicators with a long tail (population, GDP) so
    // small regions don't all wash to the same dim color.
    colorScale: z.enum(["linear", "log"]).optional(),
  })
    .refine(
      (c) => {
        if (c.render === "choropleth") {
          if (!c.geo || !c.indicator || !c.vintage) return false;
          // tract + block-group require either `state` (single) or
          // `states` (multi-state span like DMV).
          if (c.geo === "tract" || c.geo === "block-group") {
            return !!c.state || (c.states && c.states.length > 0);
          }
          return true;
        }
        // Non-choropleth charts must have at least one source.
        return (c.sources?.length ?? 0) > 0;
      },
      {
        message:
          "Chart shape mismatch: choropleth needs geo/indicator/vintage " +
          "(and state for tract/block-group); other render types need sources.",
      },
    ),
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
    scale: z.enum(["linear", "log"]),
    seriesLabels: z.array(z.string()),
    percentDisplay: z.enum(["percent", "decimal"]),
    transform: z.enum(["level", "yoy_pct", "index_100"]),
    annotations: z.array(
      z.object({
        date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
        label: z.string(),
        position: z.enum(["above", "below"]).optional(),
      }),
    ),
    // Mirror of the chart-level `shading` field. Lets a dashboard
    // override the bands on a specific tile (e.g. all-charts use
    // recessions, but ONE chart wants party shading instead).
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
  })
  .partial();

const sectionSchema = z
  .object({
    title: z.string(),
    description: z.string().optional(),
    // Charts can be omitted (or empty) when the section is pure
    // markdown narrative — the renderer-side check requires either
    // charts.length > 0 OR a non-empty markdown body.
    charts: z.array(z.string()).default([]),
    // Section-as-markdown: a body of safe-subset markdown rendered
    // full-width between chart sections. See src/lib/markdown.ts
    // for the supported syntax. When set + charts is empty, the
    // section renders as a markdown-only narrative block; when set
    // alongside charts, it appears below the section description
    // and above the chart grid.
    markdown: z.string().optional(),
    // Section-level time window override. When set, charts in this
    // section render at this delta regardless of the dashboard-level
    // pill — useful for stacking the same chart-set across multiple
    // sections with different commentary per window (e.g., a "Last
    // decade" section + a "Last 30y" section showing the same series).
    // Per-tile pill clicks still work on top of this default.
    defaultDelta: deltaWindow.optional(),
    // Section-level fixed-date range. Pins every chart in the section
    // to a specific [start, end] window — overrides defaultDelta if
    // both are set. Lets one dashboard tell a "1990s vs 2000s vs 2010s"
    // story by repeating the same chart list under three sections, each
    // pinned to a different decade. ISO YYYY-MM-DD strings.
    fixedRange: z
      .object({
        start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
        end: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
      })
      .optional(),
  })
  .refine(
    // A section must have at least one chart OR a markdown body —
    // otherwise it's an empty heading with nothing under it.
    (s) => (s.charts && s.charts.length > 0) || (s.markdown && s.markdown.trim().length > 0),
    {
      message: "Section needs either a chart list or a markdown body.",
    },
  );

const dashboards = defineCollection({
  loader: glob({
    pattern: "**/*.{md,mdx}",
    base: "./src/content/dashboards",
  }),
  schema: z
    .object({
      title: z.string(),
      description: z.string().optional(),
      // Short topic blurb rendered in the "About this dashboard" section
      // at the bottom of the page, prepended to the editable-link prompt.
      // Distinct from `description` (which appears under the title and is
      // also used as the page meta description / OG sub-headline).
      aboutBlurb: z.string().optional(),
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
