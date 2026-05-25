/**
 * Browser-environment diagnostic tests.
 *
 * These verify that the APIs Tape's client code expects to be
 * available actually are. Most are no-cost feature-detection probes;
 * the goal is to catch "this browser/extension/network shape silently
 * breaks the site" cases before the admin has to triage them by hand.
 *
 * Specific motivations:
 *   - Safari + content blockers sometimes break IntersectionObserver
 *     for cross-origin images, which breaks the chart-tile lazy load.
 *   - localStorage is gated by Safari ITP in some Private contexts;
 *     auth state silently falls back to "signed out" if it's not
 *     writable.
 *   - prefers-reduced-motion affects which chart-animation paths run.
 *     Worth surfacing.
 */
import {
  fail,
  pass,
  warn,
  type DiagnosticTest,
} from "../diagnostic-runner";

export const browserTests: DiagnosticTest[] = [
  {
    id: "browser/localStorage-writable",
    category: "browser",
    label: "localStorage is writable",
    run: () => {
      try {
        const key = "__tape_diag_probe__";
        localStorage.setItem(key, "1");
        const read = localStorage.getItem(key);
        localStorage.removeItem(key);
        if (read !== "1") {
          return fail("localStorage round-trip returned wrong value");
        }
        return pass();
      } catch (e) {
        return fail(
          `localStorage threw on write — likely Safari Private mode or storage quota exceeded: ${(e as Error).message}`,
        );
      }
    },
  },
  {
    id: "browser/sessionStorage-writable",
    category: "browser",
    label: "sessionStorage is writable",
    run: () => {
      try {
        const key = "__tape_diag_probe__";
        sessionStorage.setItem(key, "1");
        sessionStorage.removeItem(key);
        return pass();
      } catch (e) {
        return fail(
          `sessionStorage threw: ${(e as Error).message}`,
        );
      }
    },
  },
  {
    id: "browser/cookies-enabled",
    category: "browser",
    label: "cookies enabled (navigator.cookieEnabled)",
    run: () => {
      if (typeof navigator === "undefined") {
        return fail("no navigator object");
      }
      if (!navigator.cookieEnabled) {
        // Supabase auth uses cookies for some flows; without them
        // sign-in may not persist.
        return warn(
          "cookies disabled — Supabase auth flows may not persist sessions",
        );
      }
      return pass();
    },
  },
  {
    id: "browser/fetch-api-present",
    category: "browser",
    label: "fetch API present",
    run: () => {
      if (typeof fetch !== "function") {
        return fail("global fetch missing — ancient browser?");
      }
      return pass();
    },
  },
  {
    id: "browser/intersection-observer-present",
    category: "browser",
    label: "IntersectionObserver present (chart-tile lazy load)",
    run: () => {
      if (typeof IntersectionObserver === "undefined") {
        return fail(
          "IntersectionObserver missing — chart tiles won't lazy-load",
        );
      }
      return pass();
    },
  },
  {
    id: "browser/resize-observer-present",
    category: "browser",
    label: "ResizeObserver present (chart-plot re-layout)",
    run: () => {
      if (typeof ResizeObserver === "undefined") {
        return warn(
          "ResizeObserver missing — chart plots may not relayout on resize",
        );
      }
      return pass();
    },
  },
  {
    id: "browser/abort-controller-present",
    category: "browser",
    label: "AbortController present (fetch cancellation in dialog flow)",
    run: () => {
      if (typeof AbortController === "undefined") {
        return fail("AbortController missing");
      }
      return pass();
    },
  },
  {
    id: "browser/dialog-element-supported",
    category: "browser",
    label: "<dialog> element supported (chart fullscreen)",
    run: () => {
      const el = document.createElement("dialog");
      if (typeof (el as HTMLDialogElement).showModal !== "function") {
        return fail(
          "<dialog>.showModal not a function — chart popout won't open",
        );
      }
      return pass();
    },
  },
  {
    id: "browser/viewport-info",
    category: "browser",
    label: "viewport + DPR info",
    run: () => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      const dpr = window.devicePixelRatio || 1;
      if (w < 320) {
        return warn(`viewport unusually small: ${w}x${h}`, {
          width: w,
          height: h,
          dpr,
        });
      }
      return pass(`${w}x${h} @ ${dpr}x DPR`, {
        width: w,
        height: h,
        dpr,
        ua: navigator.userAgent,
        language: navigator.language,
        platform: navigator.platform,
        languages: navigator.languages,
      });
    },
  },
  {
    id: "browser/network-online",
    category: "browser",
    label: "navigator.onLine is true",
    run: () => {
      if (!navigator.onLine) {
        return warn(
          "navigator.onLine is false — subsequent network tests will fail",
        );
      }
      return pass();
    },
  },
  {
    id: "browser/timezone-info",
    category: "browser",
    label: "Intl + timezone present",
    run: () => {
      if (typeof Intl === "undefined") return fail("Intl missing");
      const tz =
        Intl.DateTimeFormat().resolvedOptions().timeZone ?? "unknown";
      return pass(`tz=${tz}`, { timeZone: tz });
    },
  },
  {
    id: "browser/observable-plot-loaded",
    category: "browser",
    label: "Observable Plot bundle is loadable",
    timeoutMs: 10000,
    run: async () => {
      // Plot is bundled per-tile via dynamic import. Probe the bundle
      // by importing it here — if the chunk's missing or the import
      // fails, every chart that opens its dialog will fail too.
      try {
        const mod = await import("@observablehq/plot");
        if (typeof (mod as { plot?: unknown }).plot !== "function") {
          return fail("Plot module loaded but `plot` export is missing");
        }
        return pass();
      } catch (e) {
        return fail(`Failed to import @observablehq/plot: ${(e as Error).message}`);
      }
    },
  },
  {
    id: "browser/d3-loaded",
    category: "browser",
    label: "d3 bundle is loadable",
    timeoutMs: 10000,
    run: async () => {
      // d3 used by choropleth zoom + selection. Same probe pattern.
      try {
        const mod = await import("d3");
        if (typeof (mod as { select?: unknown }).select !== "function") {
          return fail("d3 loaded but `select` is missing");
        }
        return pass();
      } catch (e) {
        return fail(`Failed to import d3: ${(e as Error).message}`);
      }
    },
  },
  {
    id: "browser/preferences-info",
    category: "browser",
    label: "user-preference media queries (informational)",
    run: () => {
      const reducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      const colorScheme = window.matchMedia("(prefers-color-scheme: dark)")
        .matches
        ? "dark"
        : "light";
      const contrast = window.matchMedia("(prefers-contrast: more)").matches
        ? "more"
        : "no-preference";
      return pass(
        `motion=${reducedMotion ? "reduce" : "no-pref"} color=${colorScheme} contrast=${contrast}`,
        { reducedMotion, colorScheme, contrast },
      );
    },
  },
  {
    id: "browser/console-errors-during-this-page-load",
    category: "browser",
    label: "no console.error since page open",
    run: () => {
      // The diagnostics page installs a ring buffer at top of <script>
      // (see /me/diagnostics.astro). If anything errored during this
      // page's own load, surface it — it'd be the most relevant
      // signal of "something is wrong here".
      const buf =
        (window as unknown as { __tapeDiagErrors?: string[] })
          .__tapeDiagErrors ?? [];
      if (buf.length === 0) return pass();
      return warn(`${buf.length} console.error events since page load`, {
        firstFew: buf.slice(0, 5),
      });
    },
  },
];
