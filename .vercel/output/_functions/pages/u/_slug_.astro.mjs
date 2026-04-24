import { c as createComponent, r as renderComponent, b as renderTemplate, e as createAstro, m as maybeRenderHead, d as addAttribute, F as Fragment, a as renderScript } from '../../chunks/astro/server_DWURT7C5.mjs';
import 'piccolore';
import { $ as $$BaseLayout } from '../../chunks/BaseLayout_3yRXHE75.mjs';
import { f as composedStateSchema, r as resolveSections, a as dashboardSupportedDeltas, b as resolveDashboardDefault, g as encodeComposedState, D as DELTA_LABELS_SHORT, $ as $$Chart, e as effectiveChart, c as $$ChartController } from '../../chunks/composer-state_CLR-Mpem.mjs';
import { createClient } from '@supabase/supabase-js';
/* empty css                                     */
export { renderers } from '../../renderers.mjs';

const SUPABASE_URL = "https://abelpkfwighqtueglbnf.supabase.co";
const SUPABASE_ANON_KEY = "sb_publishable_NHrJ0VI1hHYn-j3Yjt_ojA_m5_CzO8l";
function createSupabase() {
  if (typeof window !== "undefined") {
    if (window.__legibleMarketsSupabase) {
      return window.__legibleMarketsSupabase;
    }
    const client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        // Bypass the NavigatorLock entirely. Stuck locks from prior versions
        // of this page (where multiple clients contended) caused getSession()
        // to hang indefinitely. Single-tab usage doesn't need cross-tab
        // serialization; worst case on multi-tab is one tab retries a refresh.
        lock: async (_name, _acquireTimeout, fn) => fn()
      }
    });
    window.__legibleMarketsSupabase = client;
    return client;
  }
  return createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false
    }
  });
}
const isSupabaseConfigured = Boolean(SUPABASE_ANON_KEY);

const $$Astro = createAstro();
const prerender = false;
const $$slug = createComponent(async ($$result, $$props, $$slots) => {
  const Astro2 = $$result.createAstro($$Astro, $$props, $$slots);
  Astro2.self = $$slug;
  const baseUrl = "/";
  const slug = Astro2.params.slug;
  let notFound = false;
  let errorMessage = null;
  let state = null;
  let ownerBadge = null;
  if (!isSupabaseConfigured) {
    errorMessage = "Supabase is not configured on this build.";
  } else {
    const sb = createSupabase();
    const { data, error } = await sb.from("saved_dashboards").select("title, state_json, visibility").eq("slug", slug).maybeSingle();
    if (error) {
      errorMessage = "Couldn't load this dashboard.";
    } else if (!data) {
      notFound = true;
    } else {
      const parsed = composedStateSchema.safeParse(data.state_json);
      if (!parsed.success) {
        errorMessage = "This saved dashboard's state is malformed.";
      } else {
        state = parsed.data;
        if (data.title && !state.title) state.title = data.title;
        ownerBadge = data.visibility === "private" ? "private" : null;
      }
    }
  }
  let resolvedSections = [];
  let supported = [];
  let defaultDelta;
  if (state) {
    resolvedSections = await resolveSections({
      sections: state.sections,
      charts: state.charts
    });
    supported = dashboardSupportedDeltas(resolvedSections);
    defaultDelta = resolveDashboardDefault(state.defaultDelta, supported);
  }
  return renderTemplate`${renderComponent($$result, "BaseLayout", $$BaseLayout, { "title": `${state?.title ?? "Saved dashboard"} — Legible Markets`, "data-astro-cid-xpoxhcjc": true }, { "default": async ($$result2) => renderTemplate` ${maybeRenderHead()}<div class="dashboard-root max-w-[1200px] mx-auto px-6 pt-8 pb-16"${addAttribute(defaultDelta ?? "1m", "data-dashboard-default-window")} data-astro-cid-xpoxhcjc> <nav class="text-xs text-neutral-500 mb-3" data-astro-cid-xpoxhcjc> <a${addAttribute(baseUrl, "href")} class="no-underline hover:text-neutral-900" data-astro-cid-xpoxhcjc>All dashboards</a> <span class="mx-1" data-astro-cid-xpoxhcjc>·</span> <a${addAttribute(`${baseUrl}/compose/`, "href")} class="no-underline hover:text-neutral-900" data-astro-cid-xpoxhcjc>Composer</a> </nav> ${notFound ? renderTemplate`<div class="max-w-[640px] p-6 border hairline rounded bg-neutral-100 text-sm text-neutral-700 leading-relaxed" data-astro-cid-xpoxhcjc> <p data-astro-cid-xpoxhcjc><strong data-astro-cid-xpoxhcjc>Dashboard not found.</strong></p> <p class="mt-2" data-astro-cid-xpoxhcjc>
The dashboard at <code data-astro-cid-xpoxhcjc>/u/${slug}/</code> doesn't exist, or it was set to private by its owner.
</p> </div>` : errorMessage ? renderTemplate`<div class="max-w-[640px] p-6 border hairline rounded bg-neutral-100 text-sm text-neutral-700 leading-relaxed" data-astro-cid-xpoxhcjc> <p data-astro-cid-xpoxhcjc><strong data-astro-cid-xpoxhcjc>${errorMessage}</strong></p> </div>` : state ? renderTemplate`${renderComponent($$result2, "Fragment", Fragment, { "data-astro-cid-xpoxhcjc": true }, { "default": async ($$result3) => renderTemplate` <header class="mb-4" data-astro-cid-xpoxhcjc> <div class="flex items-baseline justify-between flex-wrap gap-3" data-astro-cid-xpoxhcjc> <h1 class="text-2xl font-semibold" data-astro-cid-xpoxhcjc>${state.title}</h1> <div class="flex gap-2 items-center" data-astro-cid-xpoxhcjc> ${ownerBadge && renderTemplate`<span class="text-xs px-2 py-0.5 rounded-sm bg-neutral-100 text-neutral-500 uppercase tracking-wider" data-astro-cid-xpoxhcjc>private</span>`} <button type="button" class="text-xs text-neutral-600 hover:text-neutral-900 border hairline rounded-sm px-2 py-1 bg-white cursor-pointer" data-role="copy-link" data-astro-cid-xpoxhcjc>
Copy link
</button> <a${addAttribute(`${baseUrl}/compose/?d=${encodeComposedState({
    title: state.title,
    description: state.description,
    defaultDelta: state.defaultDelta,
    sections: state.sections,
    charts: state.charts,
    chartOverrides: state.chartOverrides
  })}`, "href")} class="text-xs text-neutral-600 no-underline hover:text-neutral-900 border hairline rounded-sm px-2 py-1" data-astro-cid-xpoxhcjc>
Fork this &rarr;
</a> </div> </div> ${state.description && renderTemplate`<p class="mt-2 text-sm text-neutral-600 max-w-[640px]" data-astro-cid-xpoxhcjc>${state.description}</p>`} </header> ${supported.length > 0 && renderTemplate`<div class="dashboard-window" role="group" aria-label="Default window" data-astro-cid-xpoxhcjc> <span class="eyebrow" data-astro-cid-xpoxhcjc>Window</span> <div class="pills" data-dashboard-window-control data-astro-cid-xpoxhcjc> ${supported.map((w) => renderTemplate`<button type="button"${addAttribute("pill" + (w === defaultDelta ? " pill-active" : ""), "class")}${addAttribute(w, "data-dashboard-window")}${addAttribute(w === defaultDelta ? "true" : "false", "aria-pressed")} data-astro-cid-xpoxhcjc> ${DELTA_LABELS_SHORT[w]} </button>`)} </div> </div>`}${resolvedSections.map((section) => renderTemplate`<section class="dash-section" data-astro-cid-xpoxhcjc> ${section.title && renderTemplate`<h2 class="section-heading" data-astro-cid-xpoxhcjc>${section.title}</h2>`} ${section.description && renderTemplate`<p class="section-description" data-astro-cid-xpoxhcjc>${section.description}</p>`} <div class="chart-grid" data-astro-cid-xpoxhcjc> ${section.charts.map((c) => renderTemplate`${renderComponent($$result3, "Chart", $$Chart, { "chartId": c.chart.id, "chart": effectiveChart(
    c,
    state?.chartOverrides?.[c.chart.id]
  ), "sources": c.sources, "dashboardSlug": `u-${slug}`, "dashboardWindow": defaultDelta, "data-astro-cid-xpoxhcjc": true })}`)} </div> </section>`)}${resolvedSections.length === 0 && renderTemplate`<p class="mt-6 text-sm text-neutral-500" data-astro-cid-xpoxhcjc>
This dashboard has no charts. <a class="underline"${addAttribute(`${baseUrl}/compose/`, "href")} data-astro-cid-xpoxhcjc>Compose one</a>.
</p>`}${renderScript($$result3, "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/pages/u/[slug].astro?astro&type=script&index=0&lang.ts")} ` })}` : null} </div> ${renderComponent($$result2, "ChartController", $$ChartController, { "data-astro-cid-xpoxhcjc": true })} ` })} `;
}, "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/pages/u/[slug].astro", void 0);
const $$file = "C:/Users/Nemo/Documents/Coding/FinanceForDC/src/pages/u/[slug].astro";
const $$url = "/u/[slug]";

const _page = /*#__PURE__*/Object.freeze(/*#__PURE__*/Object.defineProperty({
  __proto__: null,
  default: $$slug,
  file: $$file,
  prerender,
  url: $$url
}, Symbol.toStringTag, { value: 'Module' }));

const page = () => _page;

export { page };
