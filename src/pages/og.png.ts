/**
 * Server-rendered Open Graph image endpoint. One URL,
 *   /og.png?<one of: dash | chart | d | title>
 * resolves into a 1200×630 PNG suitable for og:image / twitter:image meta
 * tags. The product is shareable URLs — without a real chart in the unfurl
 * preview, the natural Twitter/Substack/Slack/Discord distribution loop is
 * leaking conversions. This is the cheap, high-leverage fix.
 *
 * Query parameter precedence (first match wins):
 *   ?dash=<preset-slug>     — preset dashboard (oil-energy, us-macro, …)
 *   ?chart=<chart-id>       — individual library chart (e.g. "oil/wti")
 *   ?source=<source-id>     — single data series (per-source citation page)
 *   ?d=<encoded-state>      — URL-state composed dashboard from /custom/
 *   ?title=<text>           — fallback bare card for the homepage / about
 *
 * Saved /u/<slug>/ dashboards aren't fetchable server-side here without the
 * service-role Supabase key (RLS would reject anon reads). Those pages
 * therefore fall back to the bare /og.png?title=… card; a follow-up can
 * generate them via a Supabase Edge Function once we want it.
 */
import type { APIRoute } from "astro";
import { ImageResponse } from "@vercel/og";
import { getEntry } from "astro:content";
import fs from "node:fs";
import path from "node:path";
import { loadSourceData } from "../lib/load-data";
import { resolveSections } from "../lib/resolve-dashboard";
import { decodeComposedState } from "../lib/composer-state";
import {
  OG_COLORS,
  buildSvgPaths,
  rebaseTo100,
  windowPoints,
  type OgSeries,
} from "../lib/og-render";
import { SITE_BRAND_URL, SITE_BRAND_NAME } from "../lib/brand";

export const prerender = false;

const WIDTH = 1200;
const HEIGHT = 630;
const CHART_W = 1040;
const CHART_H = 280;
const FOOT_NOTE = SITE_BRAND_URL;

// Trailing window for the OG thumbnail — picked separately from the chart's
// saved defaultDelta because the goal is "evocative thumbnail", not "literal
// current view". ~5 years gives a recognizable shape for most series and
// gracefully falls back to "everything we have" for shorter histories.
const OG_TRAILING_DAYS = 365 * 5;

let cachedFonts: { name: string; data: ArrayBuffer; weight: 400 | 600; style: "normal" }[] | null = null;
function loadFonts() {
  if (cachedFonts) return cachedFonts;
  const root = process.cwd();
  const regular = fs.readFileSync(
    path.join(root, "node_modules/@fontsource/inter/files/inter-latin-400-normal.woff"),
  );
  const semibold = fs.readFileSync(
    path.join(root, "node_modules/@fontsource/inter/files/inter-latin-600-normal.woff"),
  );
  cachedFonts = [
    { name: "Inter", data: regular.buffer.slice(regular.byteOffset, regular.byteOffset + regular.byteLength), weight: 400, style: "normal" },
    { name: "Inter", data: semibold.buffer.slice(semibold.byteOffset, semibold.byteOffset + semibold.byteLength), weight: 600, style: "normal" },
  ];
  return cachedFonts;
}

type Resolved = {
  title: string;
  subtitle?: string;
  series: OgSeries[];
  /** Forces a single-series layout (no legend strip when only one) */
  isSingle: boolean;
};

/**
 * Threaded through the resolvers so an error/degraded render can be flagged
 * without a module-scoped flag (which would leak across concurrent requests in
 * a warm serverless isolate). `degraded` starts false; any error catch path
 * that falls through to a chartless/fallback card flips it true, and the final
 * ImageResponse then downgrades the edge cache so a transient failure isn't
 * pinned for ~25h.
 */
type RenderCtx = { degraded: boolean };

/**
 * Resolve a single chart's series (up to 4, to keep the OG legend compact)
 * into rebased points. We always rebase for the OG image: it makes the chart
 * legible even when source scales differ wildly, and ratios/levels both look
 * fine indexed to 100.
 */
function resolveChartSeries(
  chartData: { sources?: string[]; seriesLabels?: string[]; normalize?: string },
  sourceData: { id: string; name: string; shortName?: string; points: { t: string; v: number }[] }[],
): OgSeries[] {
  const out: OgSeries[] = [];
  const limit = Math.min(4, sourceData.length);
  for (let i = 0; i < limit; i++) {
    const sd = sourceData[i];
    const pointsTrim = windowPoints(sd.points, OG_TRAILING_DAYS);
    // Rebase when multi-series, or when chart explicitly opted into rebase.
    const points =
      limit > 1 || chartData.normalize === "rebase"
        ? rebaseTo100(pointsTrim)
        : pointsTrim;
    if (points.length < 2) continue;
    const label =
      chartData.seriesLabels?.[i] ??
      sd.shortName ??
      sd.name;
    out.push({ name: label, color: OG_COLORS[i % OG_COLORS.length], points });
  }
  return out;
}

async function resolveDashSlug(slug: string, ctx: RenderCtx): Promise<Resolved | null> {
  const dash = await getEntry("dashboards", slug);
  if (!dash) return null;
  // Find the first chart in the dashboard (sections preferred, then flat charts).
  const firstChartId =
    dash.data.sections?.[0]?.charts?.[0] ?? dash.data.charts?.[0];
  if (!firstChartId)
    return { title: dash.data.title, subtitle: dash.data.description, series: [], isSingle: false };
  const chart = await getEntry("charts", firstChartId);
  if (!chart)
    return { title: dash.data.title, subtitle: dash.data.description, series: [], isSingle: false };
  const sources: { id: string; name: string; shortName?: string; points: { t: string; v: number }[] }[] = [];
  for (const sid of chart.data.sources ?? []) {
    const src = await getEntry("sources", sid);
    if (!src) continue;
    try {
      const data = await loadSourceData(src.data.dataFile);
      if (data.kind !== "timeseries") continue;
      sources.push({
        id: src.id,
        name: src.data.name,
        shortName: src.data.shortName,
        points: data.points,
      });
    } catch {
      // missing data file — fall through with an empty card
      ctx.degraded = true;
    }
  }
  const series = resolveChartSeries(chart.data, sources);
  return {
    title: dash.data.title,
    subtitle: chart.data.title,
    series,
    isSingle: series.length === 1,
  };
}

async function resolveChartId(chartId: string, ctx: RenderCtx): Promise<Resolved | null> {
  const chart = await getEntry("charts", chartId);
  if (!chart) return null;
  const sources: { id: string; name: string; shortName?: string; points: { t: string; v: number }[] }[] = [];
  for (const sid of chart.data.sources ?? []) {
    const src = await getEntry("sources", sid);
    if (!src) continue;
    try {
      const data = await loadSourceData(src.data.dataFile);
      if (data.kind !== "timeseries") continue;
      sources.push({
        id: src.id,
        name: src.data.name,
        shortName: src.data.shortName,
        points: data.points,
      });
    } catch {
      // skip
      ctx.degraded = true;
    }
  }
  const series = resolveChartSeries(chart.data, sources);
  return {
    title: chart.data.title,
    subtitle: chart.data.blurb,
    series,
    isSingle: series.length === 1,
  };
}

async function resolveSource(sourceId: string, ctx: RenderCtx): Promise<Resolved | null> {
  const src = await getEntry("sources", sourceId);
  if (!src) return null;
  const sources: { id: string; name: string; shortName?: string; points: { t: string; v: number }[] }[] = [];
  try {
    const data = await loadSourceData(src.data.dataFile);
    if (data.kind === "timeseries") {
      sources.push({
        id: src.id,
        name: src.data.name,
        shortName: src.data.shortName,
        points: data.points,
      });
    }
  } catch {
    // missing data file — fall through with a titled, chartless card
    ctx.degraded = true;
  }
  // Single-series card: resolveChartSeries leaves a lone source un-rebased,
  // so the OG thumbnail shows the series' real (windowed) level shape.
  const series = resolveChartSeries({ sources: [src.id] }, sources);
  return {
    title: src.data.name,
    subtitle: src.data.description,
    series,
    isSingle: series.length === 1,
  };
}

async function resolveComposed(d: string, ctx: RenderCtx): Promise<Resolved | null> {
  const decoded = decodeComposedState(d);
  if (!decoded.ok) return null;
  const st = decoded.state;
  const sections = await resolveSections({
    sections: st.sections,
    charts: st.charts,
    inlineCharts: st.inlineCharts,
    inlineSources: st.inlineSources,
  });
  const firstChart = sections[0]?.charts?.[0];
  if (!firstChart)
    return { title: st.title ?? "Composed dashboard", subtitle: st.description, series: [], isSingle: false };
  // Build series from the resolved chart's sources, preferring preloaded data
  // (which is how derived sources surface their computed points).
  const sources: { id: string; name: string; shortName?: string; points: { t: string; v: number }[] }[] = [];
  for (const s of firstChart.sources) {
    const preloaded = firstChart.preloaded?.[s.id];
    let pts: { t: string; v: number }[] | null = null;
    if (preloaded && preloaded.kind === "timeseries") {
      pts = preloaded.points;
    } else {
      try {
        const data = await loadSourceData(s.data.dataFile);
        if (data.kind === "timeseries") pts = data.points;
      } catch {
        /* skip */
        ctx.degraded = true;
      }
    }
    if (!pts) continue;
    sources.push({
      id: s.id,
      name: s.data.name,
      shortName: s.data.shortName,
      points: pts,
    });
  }
  const series = resolveChartSeries(firstChart.chart.data, sources);
  return {
    title: st.title ?? "Composed dashboard",
    subtitle: firstChart.chart.data.title,
    series,
    isSingle: series.length === 1,
  };
}

export const GET: APIRoute = async ({ url }) => {
  const params = url.searchParams;

  // Per-request flag: any error catch path flips this so the final response
  // downgrades the edge cache. Kept request-local (not module-scoped) so it
  // can't leak between concurrent requests in a warm serverless isolate.
  const ctx: RenderCtx = { degraded: false };

  // Did the caller ask for a specific entity? If so, a null resolution means
  // "not found" (a genuine miss), which is degraded and must NOT be pinned at
  // the edge. A bare ?title= (or no params) is the deliberate homepage/about
  // fallback card and stays a clean, long-cached success.
  const askedForEntity =
    params.has("dash") ||
    params.has("chart") ||
    params.has("source") ||
    params.has("d");

  let resolved: Resolved | null = null;
  if (params.has("dash")) resolved = await resolveDashSlug(params.get("dash")!, ctx);
  else if (params.has("chart")) resolved = await resolveChartId(params.get("chart")!, ctx);
  else if (params.has("source")) resolved = await resolveSource(params.get("source")!, ctx);
  else if (params.has("d")) resolved = await resolveComposed(params.get("d")!, ctx);

  // Fallback / explicit title-only card.
  if (!resolved) {
    // A not-found on a requested entity is degraded (short cache); the bare
    // title-only card is a legitimate success (long cache).
    if (askedForEntity) ctx.degraded = true;
    resolved = {
      title: params.get("title") ?? SITE_BRAND_NAME,
      subtitle:
        params.get("subtitle") ??
        "Shareable, citation-ready financial dashboards for analysts, journalists, and staffers.",
      series: [],
      isSingle: false,
    };
  }

  const { paths } = buildSvgPaths(resolved.series, CHART_W, CHART_H);

  // Pre-truncate title — satori will overflow / wrap awkwardly with very long
  // strings; cut at a generous limit and ellipsize.
  const title =
    resolved.title.length > 80 ? resolved.title.slice(0, 78) + "…" : resolved.title;
  const subtitle = resolved.subtitle
    ? resolved.subtitle.length > 120
      ? resolved.subtitle.slice(0, 118) + "…"
      : resolved.subtitle
    : undefined;

  const tree = {
    type: "div",
    props: {
      style: {
        width: WIDTH,
        height: HEIGHT,
        display: "flex",
        flexDirection: "column",
        padding: "56px 72px",
        background: "linear-gradient(180deg, #fdfcfb 0%, #f5f3ef 100%)",
        fontFamily: "Inter",
        color: "#111",
      },
      children: [
        // Brand wordmark
        {
          type: "div",
          props: {
            style: {
              fontSize: 18,
              color: "#0d7a6a",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontWeight: 600,
              marginBottom: 14,
            },
            children: SITE_BRAND_NAME,
          },
        },
        // Title
        {
          type: "div",
          props: {
            style: {
              fontSize: 62,
              fontWeight: 600,
              lineHeight: 1.05,
              marginBottom: 12,
              display: "flex",
            },
            children: title,
          },
        },
        // Subtitle (chart title or dashboard description)
        subtitle
          ? {
              type: "div",
              props: {
                style: {
                  fontSize: 26,
                  color: "#555",
                  lineHeight: 1.3,
                  marginBottom: 24,
                  maxWidth: 980,
                  display: "flex",
                },
                children: subtitle,
              },
            }
          : null,
        // Chart canvas (only when we have data)
        paths.length > 0
          ? {
              type: "div",
              props: {
                style: {
                  flex: 1,
                  display: "flex",
                  alignItems: "stretch",
                  marginTop: 8,
                },
                children: {
                  type: "svg",
                  props: {
                    width: CHART_W,
                    height: CHART_H,
                    viewBox: `0 0 ${CHART_W} ${CHART_H}`,
                    children: paths.map((p) => ({
                      type: "path",
                      props: {
                        d: p.d,
                        stroke: p.color,
                        strokeWidth: 3,
                        fill: "none",
                        strokeLinecap: "round",
                        strokeLinejoin: "round",
                      },
                    })),
                  },
                },
              },
            }
          : {
              type: "div",
              props: { style: { flex: 1, display: "flex" }, children: "" },
            },
        // Footer: legend + url
        {
          type: "div",
          props: {
            style: {
              fontSize: 20,
              color: "#666",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginTop: 18,
            },
            children: [
              {
                type: "div",
                props: {
                  style: { display: "flex", gap: 28, flexWrap: "wrap" },
                  children:
                    resolved.series.length === 0
                      ? "Build your own financial dashboard."
                      : resolved.series.map((s) => ({
                          type: "div",
                          props: {
                            style: {
                              display: "flex",
                              alignItems: "center",
                              gap: 10,
                            },
                            children: [
                              {
                                type: "div",
                                props: {
                                  style: {
                                    width: 14,
                                    height: 14,
                                    background: s.color,
                                    borderRadius: 3,
                                  },
                                },
                              },
                              s.name,
                            ],
                          },
                        })),
                },
              },
              {
                type: "div",
                props: {
                  style: { color: "#888", fontSize: 18 },
                  children: FOOT_NOTE,
                },
              },
            ],
          },
        },
      ].filter(Boolean),
    },
  };

  // A clean render is a pure function of the request URL, so it's safely
  // cacheable: 1 hour edge cache, 24h stale-while-revalidate. A degraded/error
  // render (missing data file, not-found entity, etc.) must NOT be pinned at
  // the edge for ~25h — a transient upstream failure would otherwise freeze a
  // broken card. Give those a short, always-revalidated cache instead.
  const cacheControl = ctx.degraded
    ? "public, max-age=60, must-revalidate"
    : "public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400";
  return new ImageResponse(tree as never, {
    width: WIDTH,
    height: HEIGHT,
    fonts: loadFonts(),
    headers: {
      "Cache-Control": cacheControl,
    },
  });
};
