import { c as createComponent, m as maybeRenderHead, d as addAttribute, b as renderTemplate, r as renderComponent, F as Fragment, u as unescapeHTML, e as createAstro, a as renderScript } from './astro/server_DWURT7C5.mjs';
import 'piccolore';
import fs from 'node:fs';
import nodePath from 'node:path';
/* empty css                          */
import 'clsx';
import { a as getEntry } from './_astro_content_B57TNz3M.mjs';
import { z } from 'zod';

const DELTA_WINDOWS = ["1w", "1m", "1y", "5y", "10y"];
const DELTA_LABELS_PAST = {
  "1w": "past week",
  "1m": "past month",
  "1y": "past year",
  "5y": "past five years",
  "10y": "past ten years"
};
const DELTA_LABELS_SHORT = {
  "1w": "1W",
  "1m": "1M",
  "1y": "1Y",
  "5y": "5Y",
  "10y": "10Y"
};
const DELTA_DAYS = {
  "1w": 7,
  "1m": 30,
  "1y": 365,
  "5y": 365 * 5,
  "10y": 365 * 10
};
function closestSupported(want, supported) {
  if (supported.length === 0) return want;
  if (supported.includes(want)) return want;
  const wantLog = Math.log(DELTA_DAYS[want]);
  let best = supported[0];
  let bestDist = Math.abs(Math.log(DELTA_DAYS[best]) - wantLog);
  for (const s of supported) {
    const d = Math.abs(Math.log(DELTA_DAYS[s]) - wantLog);
    if (d < bestDist) {
      best = s;
      bestDist = d;
    }
  }
  return best;
}

function loadSourceData(dataFile) {
  const fullPath = nodePath.join(process.cwd(), "public", dataFile);
  const raw = fs.readFileSync(fullPath, "utf-8");
  return JSON.parse(raw);
}
function findPriorPoint(data, window) {
  if (data.points.length === 0) return null;
  const last = data.points[data.points.length - 1];
  const targetMs = new Date(last.t).getTime() - DELTA_DAYS[window] * 24 * 60 * 60 * 1e3;
  if (new Date(data.points[0].t).getTime() > targetMs) return null;
  let best = data.points[0];
  for (const p of data.points) {
    if (new Date(p.t).getTime() <= targetMs) {
      best = p;
    } else {
      break;
    }
  }
  return best;
}
function currentPoint(data) {
  if (data.points.length === 0) return null;
  return data.points[data.points.length - 1];
}

function formatValue(v, fmt) {
  const opts = {
    minimumFractionDigits: fmt.decimals,
    maximumFractionDigits: fmt.decimals
  };
  if (fmt.notation === "compact") {
    opts.notation = "compact";
    opts.compactDisplay = "short";
  }
  let formatted;
  switch (fmt.style) {
    case "currency":
      formatted = new Intl.NumberFormat("en-US", {
        ...opts,
        style: "currency",
        currency: fmt.currency ?? "USD"
      }).format(v);
      break;
    case "percent":
      formatted = new Intl.NumberFormat("en-US", opts).format(v) + "%";
      break;
    case "bps":
      formatted = `${new Intl.NumberFormat("en-US", opts).format(v)} bps`;
      break;
    case "index":
    case "number":
    default:
      formatted = new Intl.NumberFormat("en-US", opts).format(v);
  }
  if (fmt.prefix) formatted = fmt.prefix + formatted;
  if (fmt.suffix) formatted = formatted + fmt.suffix;
  return formatted;
}
function formatDeltaDisplay(current, prior, fmt) {
  const d = formatDelta(current, prior, fmt);
  const text = fmt.style === "percent" ? `${d.pct} (${d.abs})` : d.pct;
  return { text, pct: d.pct, abs: d.abs, direction: d.direction };
}
function formatDelta(current, prior, fmt) {
  const diff = current - prior;
  const pct = prior !== 0 ? diff / Math.abs(prior) * 100 : 0;
  const direction = Math.abs(diff) < 1e-9 ? "flat" : diff > 0 ? "up" : "down";
  const absFmt = { ...fmt, decimals: fmt.decimals };
  const abs = formatValue(diff, absFmt);
  const pctFmt = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
    signDisplay: "exceptZero"
  });
  return {
    abs: diff >= 0 ? `+${abs}` : abs,
    pct: `${pctFmt.format(pct)}%`,
    direction
  };
}
function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric"
  });
}

const SERIES_COLORS = [
  "#0F766E",
  // teal (matches site accent)
  "#B45309",
  // ochre
  "#7C3AED",
  // violet
  "#0284C7",
  // blue
  "#DB2777",
  // magenta
  "#65A30D"
  // olive
];
function seriesColor(i) {
  return SERIES_COLORS[i % SERIES_COLORS.length];
}

var __freeze = Object.freeze;
var __defProp = Object.defineProperty;
var __template = (cooked, raw) => __freeze(__defProp(cooked, "raw", { value: __freeze(cooked.slice()) }));
var _a;
const $$Astro = createAstro();
const $$Chart = createComponent(($$result, $$props, $$slots) => {
  const Astro2 = $$result.createAstro($$Astro, $$props, $$slots);
  Astro2.self = $$Chart;
  const { chartId, chart, sources, dashboardSlug, dashboardWindow } = Astro2.props;
  const isMulti = sources.length > 1;
  const normalize = chart.normalize ?? (isMulti ? "rebase" : "raw");
  const allSupported = DELTA_WINDOWS.filter(
    (w) => sources.every((s) => s.data.supportedDeltas.includes(w))
  );
  const effectiveSupported = allSupported.length > 0 ? allSupported : sources[0].data.supportedDeltas;
  const defaultDelta = dashboardWindow ? closestSupported(dashboardWindow, effectiveSupported) : closestSupported(chart.defaultDelta, effectiveSupported);
  function trimPoints(ts, supported) {
    if (ts.points.length === 0) return ts;
    const maxDays = Math.max(...supported.map((w) => DELTA_DAYS[w]));
    const lastMs = new Date(ts.points[ts.points.length - 1].t).getTime();
    const cutoffMs = lastMs - (maxDays + 365) * 864e5;
    const trimmed = ts.points.filter((p) => new Date(p.t).getTime() >= cutoffMs);
    return { ...ts, points: trimmed };
  }
  const perSource = sources.map((s, i) => {
    const label = chart.seriesLabels?.[i] ?? s.data.shortName ?? s.data.name;
    let data = null;
    let loadError = null;
    try {
      const raw = loadSourceData(s.data.dataFile);
      if (raw.kind === "timeseries") data = raw;
    } catch (e) {
      loadError = `Data unavailable: ${s.data.dataFile}`;
    }
    const trimmed = data ? trimPoints(data, s.data.supportedDeltas) : null;
    const effectiveDeltaForSource = closestSupported(
      defaultDelta,
      s.data.supportedDeltas
    );
    const current = trimmed ? currentPoint(trimmed) : null;
    const prior = trimmed ? findPriorPoint(trimmed, effectiveDeltaForSource) : null;
    const currentStr = current ? formatValue(current.v, s.data.formatting) : "\u2014";
    const priorStr = prior ? formatValue(prior.v, s.data.formatting) : null;
    const delta = current && prior ? formatDeltaDisplay(current.v, prior.v, s.data.formatting) : null;
    return {
      id: s.id,
      source: s,
      label,
      color: seriesColor(i),
      data: trimmed,
      current,
      prior,
      currentStr,
      priorStr,
      delta,
      loadError
    };
  });
  const primary = perSource[0];
  const primarySource = primary.source;
  const effectiveEmphasis = chart.emphasis ?? primarySource.data.emphasis ?? "level";
  const directionWord = primary.delta?.direction === "up" ? "up" : primary.delta?.direction === "down" ? "down" : "roughly unchanged";
  const singleDescriptor = primary.current && primary.prior && primary.priorStr && primary.delta ? primary.delta.direction === "flat" ? `${primarySource.data.name} is at ${primary.currentStr}, roughly unchanged over the ${DELTA_LABELS_PAST[defaultDelta]}.` : `${primarySource.data.name} is at ${primary.currentStr}, ${directionWord} from ${primary.priorStr} over the ${DELTA_LABELS_PAST[defaultDelta]} (${primary.delta.text}).` : primary.current ? `${primarySource.data.name} is at ${primary.currentStr}.` : "Data unavailable.";
  const uniqueId = `dialog-${dashboardSlug}-${chartId.replace(/[^a-z0-9-]/gi, "-")}`;
  const payload = {
    isMulti,
    normalize,
    supportedDeltas: effectiveSupported,
    defaultDelta,
    sources: perSource.filter((p) => p.data !== null).map((p) => ({
      id: p.id,
      name: p.source.data.name,
      shortName: p.label,
      color: p.color,
      formatting: p.source.data.formatting,
      supportedDeltas: p.source.data.supportedDeltas,
      emphasis: p.source.data.emphasis,
      points: p.data.points,
      lastUpdated: p.data.lastUpdated
    }))
  };
  const anyLoadError = perSource.find((p) => p.loadError);
  const blurb = chart.blurb;
  const mostRecentUpdate = payload.sources.map((s) => s.lastUpdated).sort().at(-1);
  return renderTemplate`${maybeRenderHead()}<button type="button"${addAttribute("chart-tile" + (isMulti ? " chart-tile-multi" : ""), "class")}${addAttribute(uniqueId, "data-chart-ref")}${addAttribute(effectiveEmphasis, "data-emphasis")}${addAttribute(isMulti ? "true" : "false", "data-multi")} aria-haspopup="dialog"${addAttribute(`${chart.title} details`, "aria-label")} data-astro-cid-jpiiosee> <div class="tile-title" data-astro-cid-jpiiosee>${chart.title}</div> ${isMulti ? renderTemplate`<ul class="tile-series-list tabular" data-role="tile-series-list" data-astro-cid-jpiiosee> ${perSource.map((p) => renderTemplate`<li class="tile-series-row" data-astro-cid-jpiiosee> <span class="series-dot"${addAttribute(`background: ${p.color}`, "style")} data-astro-cid-jpiiosee></span> <span class="series-label" data-astro-cid-jpiiosee>${p.label}</span> <span class="series-delta" data-role="series-delta"${addAttribute(p.id, "data-source-id")}${addAttribute(p.delta?.direction ?? "flat", "data-direction")} data-astro-cid-jpiiosee> ${p.delta ? p.delta.text : "\u2014"} </span> </li>`)} </ul>` : renderTemplate`<div class="tile-reading tabular" data-astro-cid-jpiiosee> <span class="tile-value" data-role="tile-value" data-astro-cid-jpiiosee> ${primary.currentStr} </span> ${primary.delta && renderTemplate`<span class="tile-delta" data-role="tile-delta"${addAttribute(primary.delta.direction, "data-direction")} data-astro-cid-jpiiosee> ${primary.delta.text} </span>`} </div>`} <div class="tile-spark" data-role="tile-spark" data-astro-cid-jpiiosee></div> <div class="tile-window muted" data-astro-cid-jpiiosee>
over the ${DELTA_LABELS_PAST[defaultDelta]} </div> </button> <dialog${addAttribute(uniqueId, "id")} class="chart-dialog"${addAttribute(uniqueId, "data-chart-ref")}${addAttribute(effectiveEmphasis, "data-emphasis")}${addAttribute(isMulti ? "true" : "false", "data-multi")}${addAttribute(`${uniqueId}-title`, "aria-labelledby")} data-astro-cid-jpiiosee> <div class="dialog-close-bar" data-astro-cid-jpiiosee> <button type="button" class="dialog-close" aria-label="Close" data-astro-cid-jpiiosee>
&times;
</button> </div> <div class="dialog-body" data-astro-cid-jpiiosee> <header class="dialog-header" data-astro-cid-jpiiosee> <h2${addAttribute(`${uniqueId}-title`, "id")} data-astro-cid-jpiiosee>${chart.title}</h2> ${!isMulti && primarySource.data.description && renderTemplate`<p class="dialog-subtitle" data-astro-cid-jpiiosee>${primarySource.data.description}</p>`} </header> ${anyLoadError ? renderTemplate`<p class="dialog-error" data-astro-cid-jpiiosee>${anyLoadError.loadError}</p>` : isMulti ? renderTemplate`<div class="dialog-multi-readouts" data-role="multi-readouts" data-astro-cid-jpiiosee> ${perSource.map((p) => renderTemplate`<div class="multi-readout-row tabular"${addAttribute(p.id, "data-source-id")} data-astro-cid-jpiiosee> <span class="series-dot"${addAttribute(`background: ${p.color}`, "style")} data-astro-cid-jpiiosee></span> <span class="readout-label" data-astro-cid-jpiiosee>${p.label}</span> <span class="readout-level" data-role="readout-level" data-astro-cid-jpiiosee> ${p.currentStr} </span> ${p.delta && renderTemplate`<span class="readout-delta-multi" data-role="readout-delta"${addAttribute(p.delta.direction, "data-direction")} data-astro-cid-jpiiosee> ${p.delta.text} </span>`} </div>`)} <p class="multi-caption muted" data-role="descriptor" data-astro-cid-jpiiosee>
Over the ${DELTA_LABELS_PAST[defaultDelta]}.
</p> </div>` : renderTemplate`${renderComponent($$result, "Fragment", Fragment, { "data-astro-cid-jpiiosee": true }, { "default": ($$result2) => renderTemplate` <div class="readout-row tabular" data-astro-cid-jpiiosee> <span class="readout-value" data-role="value" data-astro-cid-jpiiosee> ${primary.currentStr} </span> ${primary.delta && renderTemplate`<span class="readout-delta" data-role="delta-pct"${addAttribute(primary.delta.direction, "data-direction")} data-astro-cid-jpiiosee> ${primary.delta.text} </span>`} </div> <p class="descriptor" data-role="descriptor" data-astro-cid-jpiiosee> ${singleDescriptor} </p> ` })}`} ${!anyLoadError && renderTemplate`${renderComponent($$result, "Fragment", Fragment, { "data-astro-cid-jpiiosee": true }, { "default": ($$result2) => renderTemplate` <div class="pills" role="group" aria-label="Delta window" data-astro-cid-jpiiosee> ${effectiveSupported.map((w) => renderTemplate`<button type="button"${addAttribute("pill" + (w === defaultDelta ? " pill-active" : ""), "class")}${addAttribute(w, "data-window")}${addAttribute(w === defaultDelta ? "true" : "false", "aria-pressed")} data-astro-cid-jpiiosee> ${DELTA_LABELS_SHORT[w]} </button>`)} </div> ${isMulti && normalize === "rebase" && renderTemplate`<p class="dialog-plot-caption muted" data-astro-cid-jpiiosee>
Values rebased to 100 at window start.
</p>`}<div class="dialog-plot" data-role="plot" data-astro-cid-jpiiosee></div> ` })}`} <div class="dialog-blurb" data-astro-cid-jpiiosee> ${blurb && blurb !== "KELLER WRITE THIS" ? renderTemplate`${renderComponent($$result, "Fragment", Fragment, {}, { "default": ($$result2) => renderTemplate`${unescapeHTML(blurb)}` })}` : renderTemplate`<mark class="todo" data-astro-cid-jpiiosee>KELLER WRITE THIS</mark>`} </div> <footer class="dialog-footer muted" data-astro-cid-jpiiosee> ${isMulti ? renderTemplate`<span data-astro-cid-jpiiosee>
Sources:${" "} ${perSource.map((p, i) => renderTemplate`${renderComponent($$result, "Fragment", Fragment, { "data-astro-cid-jpiiosee": true }, { "default": ($$result2) => renderTemplate`${i > 0 && ", "}${p.source.data.provenance.url ? renderTemplate`<a${addAttribute(p.source.data.provenance.url, "href")} target="_blank" rel="noopener noreferrer" data-astro-cid-jpiiosee> ${p.label} </a>` : renderTemplate`<span data-astro-cid-jpiiosee>${p.label}</span>`}` })}`)} </span>` : renderTemplate`<span data-astro-cid-jpiiosee>
Source: ${primarySource.data.provenance.provider} ${primarySource.data.provenance.series && ` \u2014 ${primarySource.data.provenance.series}`} ${primarySource.data.provenance.url && renderTemplate`${renderComponent($$result, "Fragment", Fragment, { "data-astro-cid-jpiiosee": true }, { "default": ($$result2) => renderTemplate`${" "}
(<a${addAttribute(primarySource.data.provenance.url, "href")} target="_blank" rel="noopener noreferrer" data-astro-cid-jpiiosee>
link
</a>)
` })}`} </span>`} ${mostRecentUpdate && renderTemplate`<span data-astro-cid-jpiiosee>Updated ${formatDate(mostRecentUpdate)}</span>`} </footer> </div> ${!anyLoadError && renderTemplate(_a || (_a = __template(['<script type="application/json" data-chart-payload>', "<\/script>"])), unescapeHTML(JSON.stringify(payload)))} </dialog> `;
}, "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/components/Chart.astro", void 0);

const $$ChartController = createComponent(($$result, $$props, $$slots) => {
  return renderTemplate`${renderScript($$result, "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/components/ChartController.astro?astro&type=script&index=0&lang.ts")}`;
}, "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/components/ChartController.astro", void 0);

async function resolveChart(id) {
  let chart = await getEntry("charts", id);
  if (!chart) return null;
  if (chart.data.aliasOf) {
    const target = await getEntry("charts", chart.data.aliasOf);
    if (target) chart = target;
  }
  const sources = await Promise.all(
    chart.data.sources.map((sid) => getEntry("sources", sid))
  );
  const validSources = sources.filter(
    (s) => s !== void 0
  );
  if (validSources.length === 0) return null;
  return { chart, sources: validSources };
}
async function resolveSections(dashboard) {
  const sectionsRaw = dashboard.sections ?? [
    { title: null, charts: dashboard.charts ?? [] }
  ];
  const out = [];
  for (const s of sectionsRaw) {
    const resolved = await Promise.all(s.charts.map(resolveChart));
    const valid = resolved.filter((r) => r !== null);
    if (valid.length > 0) {
      out.push({
        title: s.title ?? null,
        description: s.description,
        charts: valid
      });
    }
  }
  return out;
}
function perChartSupportedDeltas(sections) {
  return sections.flatMap(
    (sec) => sec.charts.map(
      (c) => DELTA_WINDOWS.filter(
        (w) => c.sources.every((s) => s.data.supportedDeltas.includes(w))
      )
    )
  );
}
function dashboardSupportedDeltas(sections) {
  const perChart = perChartSupportedDeltas(sections);
  const supported = DELTA_WINDOWS.filter(
    (w) => perChart.some((sup) => sup.includes(w))
  );
  return supported.length > 0 ? supported : [...DELTA_WINDOWS];
}
function resolveDashboardDefault(requested, supported) {
  const want = requested ?? "1m";
  if (supported.includes(want)) return want;
  return closestSupported(want, supported);
}
function effectiveChart(resolved, override) {
  return { ...resolved.chart.data, ...override ?? {} };
}

const COMPOSER_STATE_VERSION = 1;
const deltaWindowSchema = z.enum(DELTA_WINDOWS);
const chartOverrideSchema = z.object({
  title: z.string(),
  defaultDelta: deltaWindowSchema,
  blurb: z.string()
}).partial();
const sectionSchema = z.object({
  title: z.string(),
  description: z.string().optional(),
  charts: z.array(z.string()).min(1)
});
const composedStateSchema = z.object({
  v: z.literal(COMPOSER_STATE_VERSION),
  title: z.string().optional(),
  description: z.string().optional(),
  defaultDelta: deltaWindowSchema.optional(),
  charts: z.array(z.string()).optional(),
  sections: z.array(sectionSchema).optional(),
  chartOverrides: z.record(z.string(), chartOverrideSchema).optional()
});
function base64urlEncode(input) {
  const bytes = new TextEncoder().encode(input);
  let b64;
  if (typeof btoa !== "undefined") {
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    b64 = btoa(bin);
  } else {
    b64 = Buffer.from(bytes).toString("base64");
  }
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function base64urlDecode(input) {
  const pad = input.length % 4 === 0 ? "" : "=".repeat(4 - input.length % 4);
  const b64 = input.replace(/-/g, "+").replace(/_/g, "/") + pad;
  if (typeof atob !== "undefined") {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }
  return Buffer.from(b64, "base64").toString("utf-8");
}
function encodeComposedState(partial) {
  const full = { v: COMPOSER_STATE_VERSION, ...partial };
  const clean = JSON.parse(JSON.stringify(full));
  return base64urlEncode(JSON.stringify(clean));
}
function decodeComposedState(raw) {
  if (!raw) return { ok: false, reason: "empty", message: "No composition provided." };
  let json;
  try {
    json = base64urlDecode(raw);
  } catch (e) {
    return { ok: false, reason: "invalid-encoding", message: "Composition link is malformed." };
  }
  let parsed;
  try {
    parsed = JSON.parse(json);
  } catch {
    return { ok: false, reason: "invalid-encoding", message: "Composition JSON is corrupted." };
  }
  const maybe = composedStateSchema.safeParse(parsed);
  if (!maybe.success) {
    const obj = parsed;
    if (typeof obj?.v === "number" && obj.v !== COMPOSER_STATE_VERSION) {
      return {
        ok: false,
        reason: "wrong-version",
        message: `This composition was created with a different version (v${obj.v}). Please re-fork or re-compose.`
      };
    }
    return { ok: false, reason: "invalid-shape", message: "Composition doesn't match the expected shape." };
  }
  return { ok: true, state: maybe.data };
}

export { $$Chart as $, DELTA_LABELS_SHORT as D, dashboardSupportedDeltas as a, resolveDashboardDefault as b, $$ChartController as c, decodeComposedState as d, effectiveChart as e, composedStateSchema as f, encodeComposedState as g, resolveSections as r };
