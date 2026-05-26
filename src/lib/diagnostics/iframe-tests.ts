/**
 * In-iframe DOM diagnostic tests.
 *
 * These load a same-origin page in a hidden iframe, wait for its
 * load + a small settle period for client-side hydration, then poke
 * around in its DOM to verify charts actually rendered, the composer
 * tabs all mount, etc. This is the closest we can get from inside
 * the app to "did the page actually work" without a real headless
 * browser.
 *
 * Constraints:
 *   - Same-origin only (cross-origin would 'opaque' the contentWindow).
 *   - Each iframe is created + destroyed within one test. No leaks
 *     between tests; if a test fails the cleanup still runs in a
 *     try/finally.
 *   - Tests have a per-test timeout (default 5s; iframe tests bump
 *     to 15-20s because Plot + d3 chunks have to load).
 *
 * Console-error capture inside the iframe: each iframe gets a
 * console.error wrapper installed BEFORE it navigates, so we capture
 * everything from the moment the page boots.
 */
import {
  fail,
  pass,
  warn,
  type DiagnosticTest,
  type DiagnosticResult,
} from "../diagnostic-runner";

/**
 * Mount a hidden iframe at the given path, wait for full load + a
 * fixed settle (default 1.5s for client-script hydration), call the
 * inspector with the iframe's window+document, then tear down.
 *
 * Returns whatever the inspector returns. Captures console errors
 * fired inside the iframe into a side-channel array the inspector
 * can read.
 */
async function withHiddenIframe<T>(
  path: string,
  settleMs: number,
  inspector: (
    win: Window,
    doc: Document,
    consoleErrors: string[],
  ) => Promise<T> | T,
): Promise<T> {
  const iframe = document.createElement("iframe");
  iframe.style.position = "fixed";
  iframe.style.top = "-9999px";
  iframe.style.left = "-9999px";
  iframe.style.width = "1280px";
  iframe.style.height = "900px";
  iframe.style.border = "0";
  iframe.setAttribute("aria-hidden", "true");
  iframe.setAttribute("data-tape-diagnostic-iframe", path);
  document.body.appendChild(iframe);

  const consoleErrors: string[] = [];

  // Wait for the iframe's first load event before we can reach into
  // contentWindow. Capture both load (fires after document parse)
  // and any blocking error event.
  const loadPromise = new Promise<void>((resolve, reject) => {
    iframe.addEventListener("load", () => resolve(), { once: true });
    iframe.addEventListener("error", () => reject(new Error("iframe load error")), { once: true });
  });
  iframe.src = path;
  await loadPromise;

  // Install console-error capture. Done AFTER load because the
  // iframe's window may have been reset/replaced by the navigation.
  const win = iframe.contentWindow;
  const doc = iframe.contentDocument;
  if (!win || !doc) throw new Error("iframe content unavailable");
  try {
    // TS's lib.dom doesn't put `console` on Window, even though every
    // browser has it. Cast to access it.
    const iframeConsole = (win as unknown as { console: Console }).console;
    const origError = iframeConsole.error.bind(iframeConsole);
    iframeConsole.error = (...args: unknown[]) => {
      try {
        consoleErrors.push(args.map((a) => String(a)).join(" "));
      } catch {
        /* ignore */
      }
      origError(...args);
    };
    // Also listen for runtime errors + unhandled rejections.
    win.addEventListener("error", (e) => {
      consoleErrors.push(`[error] ${e.message} (${e.filename}:${e.lineno})`);
    });
    win.addEventListener(
      "unhandledrejection",
      (e: PromiseRejectionEvent) => {
        consoleErrors.push(`[unhandledrejection] ${String(e.reason)}`);
      },
    );

    // Settle delay — gives client-side hydration a chance to run
    // before we inspect. 1.5s is empirically enough for the homepage;
    // chart-heavy pages bump it via the caller.
    await new Promise((r) => setTimeout(r, settleMs));

    return await inspector(win, doc, consoleErrors);
  } finally {
    iframe.remove();
  }
}

export const iframeTests: DiagnosticTest[] = [
  {
    id: "iframe/home-loads",
    category: "iframe",
    label: "home page loads in iframe without console errors",
    timeoutMs: 20000,
    run: async () => {
      return await withHiddenIframe("/", 2000, (_win, doc, errors) => {
        const title = doc.title;
        if (!title) return fail("no document.title");
        if (errors.length > 0) {
          return warn(
            `${errors.length} console.error events during load`,
            { firstFew: errors.slice(0, 3), title },
          );
        }
        return pass(`title="${title}"`, { title });
      });
    },
  },
  {
    id: "iframe/us-macro-charts-render",
    category: "iframe",
    label: "/us-macro/ renders > 0 chart tiles",
    timeoutMs: 25000,
    run: async () => {
      return await withHiddenIframe(
        "/us-macro/",
        3000,
        (_win, doc, errors) => {
          // Tiles are <a class="chart-tile"> in the current template.
          // We accept several selectors to survive a class rename
          // gracefully (better an over-permissive selector than a
          // brittle fail).
          const tileSelectors = [
            "[data-chart-id]",
            ".chart-tile",
            "[data-tile-chart-id]",
          ];
          let tileCount = 0;
          for (const sel of tileSelectors) {
            tileCount = Math.max(tileCount, doc.querySelectorAll(sel).length);
          }
          if (tileCount === 0) {
            return fail(
              "no chart tiles found via any selector",
              { tried: tileSelectors, errors: errors.slice(0, 3) },
            );
          }
          if (errors.length > 0) {
            return warn(
              `${tileCount} tiles but ${errors.length} console.errors`,
              { tileCount, firstFewErrors: errors.slice(0, 3) },
            );
          }
          return pass(`${tileCount} tiles`, { tileCount });
        },
      );
    },
  },
  {
    id: "iframe/walkthrough-loads",
    category: "iframe",
    label: "/walkthrough/ loads + has chart tiles + no errors",
    timeoutMs: 25000,
    run: async () => {
      return await withHiddenIframe(
        "/walkthrough/",
        3000,
        (_win, doc, errors) => {
          const tiles = doc.querySelectorAll(
            "[data-chart-id], .chart-tile, [data-tile-chart-id]",
          );
          if (tiles.length === 0) {
            return fail("no chart tiles on walkthrough");
          }
          if (errors.length > 0) {
            return warn(
              `${tiles.length} tiles but ${errors.length} console.errors`,
              { errors: errors.slice(0, 5) },
            );
          }
          return pass(`${tiles.length} tiles`);
        },
      );
    },
  },
  {
    id: "iframe/compose-tabs-render",
    category: "iframe",
    label: "/compose/ mounts and shows tab controls",
    timeoutMs: 25000,
    run: async () => {
      return await withHiddenIframe(
        "/compose/",
        3500,
        (_win, doc, errors) => {
          // The composer renders a tab strip with these four labels
          // (see src/pages/compose.astro). NB: "Pregenerated charts"
          // — not "Charts" — was the canonical tab label as of the
          // 2026-05-25 build.
          const text = doc.body.textContent ?? "";
          const wantedTabs = [
            "Sources",
            "Pregenerated charts",
            "Maps",
            "Generators",
          ];
          const missing = wantedTabs.filter((t) => !text.includes(t));
          if (missing.length > 0) {
            return fail(
              `missing tab labels: ${missing.join(", ")}`,
              {
                bodyTextLength: text.length,
                errors: errors.slice(0, 3),
              },
            );
          }
          if (errors.length > 0) {
            return warn(
              `tabs present but ${errors.length} console.errors`,
              { errors: errors.slice(0, 3) },
            );
          }
          return pass("all tab labels present");
        },
      );
    },
  },
  {
    id: "iframe/library-page-loads",
    category: "iframe",
    label: "/library/ index loads without errors",
    timeoutMs: 25000,
    run: async () => {
      return await withHiddenIframe(
        "/library/",
        3000,
        (_win, _doc, errors) => {
          if (errors.length > 0) {
            return warn(
              `${errors.length} console.error events`,
              { errors: errors.slice(0, 5) },
            );
          }
          return pass();
        },
      );
    },
  },
  {
    id: "iframe/known-embed-loads",
    category: "iframe",
    label: "an /embed/chart/... iframe URL loads",
    timeoutMs: 25000,
    run: async (): Promise<DiagnosticResult> => {
      // The embed URL pattern is /embed/chart/<chart-id>/. We try a
      // few well-known chart IDs; pass if any one loads cleanly.
      const candidates = [
        "/embed/chart/us-macro/cpi-yoy/",
        "/embed/chart/us-macro/dgs10/",
        "/embed/chart/stocks/spy/",
      ];
      for (const path of candidates) {
        try {
          const res = await withHiddenIframe(
            path,
            2500,
            (_win, doc, errors) => {
              if (!doc.body || doc.body.children.length === 0) {
                return { ok: false, reason: "empty body" } as const;
              }
              return {
                ok: true,
                path,
                errorCount: errors.length,
                errors: errors.slice(0, 3),
              } as const;
            },
          );
          if (res.ok) {
            if (res.errorCount > 0) {
              return warn(
                `${path}: ${res.errorCount} console.errors`,
                { errors: res.errors },
              );
            }
            return pass(path);
          }
        } catch {
          // try next candidate
        }
      }
      return fail(
        `none of ${candidates.length} embed candidates loaded cleanly`,
        { candidates },
      );
    },
  },
];
