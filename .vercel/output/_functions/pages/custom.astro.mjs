import { e as createAstro, c as createComponent, r as renderComponent, b as renderTemplate, m as maybeRenderHead, d as addAttribute, F as Fragment, a as renderScript, u as unescapeHTML } from '../chunks/astro/server_DC5FRKA8.mjs';
import 'piccolore';
import { $ as $$BaseLayout } from '../chunks/BaseLayout_Co-Ii_Oo.mjs';
import { d as decodeComposedState, r as resolveSections, a as dashboardSupportedDeltas, b as resolveDashboardDefault, $ as $$Chart, e as effectiveChart, D as DELTA_LABELS_SHORT, c as $$ChartController } from '../chunks/composer-state_CNMwlujA.mjs';
/* empty css                                  */
export { renderers } from '../renderers.mjs';

var __freeze = Object.freeze;
var __defProp = Object.defineProperty;
var __template = (cooked, raw) => __freeze(__defProp(cooked, "raw", { value: __freeze(cooked.slice()) }));
var _a;
const $$Astro = createAstro("https://khs.github.io");
const prerender = false;
const $$Custom = createComponent(async ($$result, $$props, $$slots) => {
  const Astro2 = $$result.createAstro($$Astro, $$props, $$slots);
  Astro2.self = $$Custom;
  const dParam = Astro2.url.searchParams.get("d");
  const decoded = decodeComposedState(dParam);
  const baseUrl = "/dash";
  let title = "Composed dashboard";
  let description;
  let defaultDeltaRequested;
  let resolvedSections = [];
  let supported = [];
  let errorMessage = null;
  let forkUrl = null;
  let chartOverrides;
  if (!decoded.ok) {
    errorMessage = decoded.message;
  } else {
    const st = decoded.state;
    title = st.title ?? "Composed dashboard";
    description = st.description;
    chartOverrides = st.chartOverrides;
    resolvedSections = await resolveSections({
      sections: st.sections,
      charts: st.charts
    });
    supported = dashboardSupportedDeltas(resolvedSections);
    defaultDeltaRequested = resolveDashboardDefault(st.defaultDelta, supported);
    forkUrl = baseUrl + "/compose/?d=" + (dParam ?? "");
  }
  return renderTemplate`${renderComponent($$result, "BaseLayout", $$BaseLayout, { "title": `${title} — Legible Markets`, "description": description, "data-astro-cid-3tu5uloj": true }, { "default": async ($$result2) => renderTemplate` ${maybeRenderHead()}<div class="dashboard-root max-w-[1200px] mx-auto px-6 pt-8 pb-16"${addAttribute(defaultDeltaRequested ?? "1m", "data-dashboard-default-window")} data-astro-cid-3tu5uloj> <nav class="text-xs text-neutral-500 mb-3" data-astro-cid-3tu5uloj> <a${addAttribute(baseUrl, "href")} class="no-underline hover:text-neutral-900" data-astro-cid-3tu5uloj>All dashboards</a> <span class="mx-1" data-astro-cid-3tu5uloj>·</span> <a${addAttribute(`${baseUrl}/compose/`, "href")} class="no-underline hover:text-neutral-900" data-astro-cid-3tu5uloj>Composer</a> </nav> ${errorMessage ? renderTemplate`<div class="max-w-[640px] p-6 border hairline rounded bg-neutral-100 text-sm text-neutral-700 leading-relaxed" data-astro-cid-3tu5uloj> <p data-astro-cid-3tu5uloj><strong data-astro-cid-3tu5uloj>Couldn't render this composed dashboard.</strong></p> <p class="mt-2" data-astro-cid-3tu5uloj>${errorMessage}</p> <p class="mt-3" data-astro-cid-3tu5uloj> <a${addAttribute(`${baseUrl}/compose/`, "href")} class="underline" data-astro-cid-3tu5uloj>Start from scratch &rarr;</a> </p> </div>` : renderTemplate`${renderComponent($$result2, "Fragment", Fragment, { "data-astro-cid-3tu5uloj": true }, { "default": async ($$result3) => renderTemplate(_a || (_a = __template([' <header class="mb-4" data-astro-cid-3tu5uloj> <div class="flex items-baseline justify-between flex-wrap gap-3" data-astro-cid-3tu5uloj> <h1 class="text-2xl font-semibold" data-astro-cid-3tu5uloj>', '</h1> <div class="flex gap-2" data-astro-cid-3tu5uloj> <button type="button" class="text-xs text-neutral-600 hover:text-neutral-900 border hairline rounded-sm px-2 py-1 bg-white cursor-pointer" data-role="copy-link" data-astro-cid-3tu5uloj>\nCopy link\n</button> <button type="button" class="text-xs text-neutral-600 hover:text-neutral-900 border hairline rounded-sm px-2 py-1 bg-white cursor-pointer" data-role="save" data-astro-cid-3tu5uloj>\nSave to my account\n</button> ', ' </div> <script type="application/json" data-role="custom-state">', '</script> <script type="application/json" data-role="custom-base-url">', "</script> </div> ", " </header> ", " ", "", "", ""])), title, forkUrl && renderTemplate`<a${addAttribute(forkUrl, "href")} class="text-xs text-neutral-600 no-underline hover:text-neutral-900 border hairline rounded-sm px-2 py-1" data-astro-cid-3tu5uloj>
Open in composer &rarr;
</a>`, unescapeHTML(JSON.stringify(decoded.ok ? decoded.state : null)), unescapeHTML(JSON.stringify(baseUrl)), description && renderTemplate`<p class="mt-2 text-sm text-neutral-600 max-w-[640px]" data-astro-cid-3tu5uloj>${description}</p>`, renderScript($$result3, "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/pages/custom.astro?astro&type=script&index=0&lang.ts"), supported.length > 0 && renderTemplate`<div class="dashboard-window" role="group" aria-label="Default window" data-astro-cid-3tu5uloj> <span class="eyebrow" data-astro-cid-3tu5uloj>Window</span> <div class="pills" data-dashboard-window-control data-astro-cid-3tu5uloj> ${supported.map((w) => renderTemplate`<button type="button"${addAttribute(
    "pill" + (w === defaultDeltaRequested ? " pill-active" : ""),
    "class"
  )}${addAttribute(w, "data-dashboard-window")}${addAttribute(w === defaultDeltaRequested ? "true" : "false", "aria-pressed")} data-astro-cid-3tu5uloj> ${DELTA_LABELS_SHORT[w]} </button>`)} </div> </div>`, resolvedSections.map((section) => renderTemplate`<section class="dash-section" data-astro-cid-3tu5uloj> ${section.title && renderTemplate`<h2 class="section-heading" data-astro-cid-3tu5uloj>${section.title}</h2>`} ${section.description && renderTemplate`<p class="section-description" data-astro-cid-3tu5uloj>${section.description}</p>`} <div class="chart-grid" data-astro-cid-3tu5uloj> ${section.charts.map((c) => renderTemplate`${renderComponent($$result3, "Chart", $$Chart, { "chartId": c.chart.id, "chart": effectiveChart(c, chartOverrides?.[c.chart.id]), "sources": c.sources, "dashboardSlug": "custom", "dashboardWindow": defaultDeltaRequested, "data-astro-cid-3tu5uloj": true })}`)} </div> </section>`), resolvedSections.length === 0 && renderTemplate`<p class="mt-6 text-sm text-neutral-500" data-astro-cid-3tu5uloj>
This composition has no charts yet. <a${addAttribute(`${baseUrl}/compose/`, "href")} class="underline" data-astro-cid-3tu5uloj>Edit in composer</a>.
</p>`) })}`} </div> ${renderComponent($$result2, "ChartController", $$ChartController, { "data-astro-cid-3tu5uloj": true })} ` })} `;
}, "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/pages/custom.astro", void 0);
const $$file = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/pages/custom.astro";
const $$url = "/dash/custom";

const _page = /*#__PURE__*/Object.freeze(/*#__PURE__*/Object.defineProperty({
  __proto__: null,
  default: $$Custom,
  file: $$file,
  prerender,
  url: $$url
}, Symbol.toStringTag, { value: 'Module' }));

const page = () => _page;

export { page };
