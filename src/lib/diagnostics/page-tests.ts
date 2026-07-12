/**
 * Page-fetch diagnostic tests — BROWSER wrapper.
 *
 * The actual checks (routes, /library.json floor, og.png, sitemap, robots,
 * CSS-cache, 404, …) live in the framework-agnostic ./page-checks.mjs so this
 * in-app admin runner (/me/diagnostics, browser) and the post-deploy CI runner
 * (scripts/run-deploy-diagnostic.mjs, Node) share ONE definition and can't
 * drift. (They used to duplicate every check inline; the /library.json floor
 * drifted — the browser lowered it to 500 after the lean/geo split while the
 * Node runner kept the stale 1000 and warned on every healthy deploy.)
 *
 * This file only adapts each check into a typed DiagnosticTest and supplies a
 * browser fetch context: paths resolve against window.location.origin so the
 * suite always probes the deployment it's running on (preview, prod, localhost).
 */
import { pageChecks } from "./page-checks.mjs";
import type { PageCheckCtx } from "./page-checks.mjs";
import type { DiagnosticTest } from "../diagnostic-runner";

/**
 * Absolute-URL a same-origin path. Relative URLs from inside fetch() on a
 * nested SSR page can resolve oddly, so we anchor to the current origin.
 */
function url(pathOrUrl: string): string {
  if (/^https?:/i.test(pathOrUrl)) return pathOrUrl;
  return new URL(pathOrUrl, window.location.origin).toString();
}

/** Browser fetch context handed to every shared check. */
const browserCtx: PageCheckCtx = {
  async get(pathOrUrl) {
    const res = await fetch(url(pathOrUrl), {
      method: "GET",
      redirect: "follow",
      cache: "no-store",
    });
    const body = await res.text();
    return {
      status: res.status,
      contentType: res.headers.get("content-type"),
      cacheControl: res.headers.get("cache-control"),
      body,
    };
  },
  async getBuffer(pathOrUrl) {
    const res = await fetch(url(pathOrUrl), { cache: "no-store" });
    const buf = await res.arrayBuffer();
    return {
      status: res.status,
      contentType: res.headers.get("content-type"),
      bytes: buf.byteLength,
    };
  },
  nonce: Date.now(),
};

export const pageTests: DiagnosticTest[] = pageChecks.map((c) => ({
  id: c.id,
  label: c.label,
  category: c.category,
  timeoutMs: c.timeoutMs,
  run: () => c.run(browserCtx),
}));
