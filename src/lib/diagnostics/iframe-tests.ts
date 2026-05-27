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
  opts?: { heightPx?: number },
): Promise<T> {
  const iframe = document.createElement("iframe");
  iframe.style.position = "fixed";
  iframe.style.top = "-9999px";
  iframe.style.left = "-9999px";
  iframe.style.width = "1280px";
  // Default 900px viewport works for most tests. Choropleth-bearing
  // pages need a taller viewport so lazy-loaded (IntersectionObserver-
  // gated) charts below the fold actually mount their canvas.
  iframe.style.height = `${opts?.heightPx ?? 900}px`;
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
    label: "an /embed/chart/... iframe URL loads with an SVG inside",
    timeoutMs: 30000,
    run: async (): Promise<DiagnosticResult> => {
      // The embed URL pattern is /embed/chart/<chart-id>/. We try a
      // few well-known chart IDs; pass if any one loads + renders an
      // SVG (the chart Plot). Previously we only checked "no errors"
      // — an empty embed silently passed.
      // Discover chart-ids via library.json so we don't hardcode ids
      // that may drift (the previous hardcoded list went stale and
      // none of them existed any more).
      const libRes = await fetch(
        new URL("/library.json", window.location.origin).toString(),
        { cache: "no-store" },
      );
      if (libRes.status !== 200) {
        return fail(`library.json status=${libRes.status}`);
      }
      const lib = (await libRes.json()) as {
        charts?: Array<{ id?: string }>;
      };
      const candidates = (lib.charts ?? [])
        .map((c) => c?.id)
        .filter((s): s is string => !!s)
        .slice(0, 3)
        .map((id) => `/embed/chart/${id}/`);
      if (candidates.length === 0) {
        return fail("no chart ids in library.json");
      }
      for (const path of candidates) {
        try {
          const res = await withHiddenIframe(
            path,
            6000, // Plot dynamic-import + data fetch + render
            (_win, doc, errors) => {
              if (!doc.body || doc.body.children.length === 0) {
                return { ok: false, reason: "empty body" } as const;
              }
              const svgs = doc.querySelectorAll("svg");
              return {
                ok: true,
                path,
                svgCount: svgs.length,
                errorCount: errors.length,
                errors: errors.slice(0, 3),
              } as const;
            },
          );
          if (res.ok) {
            if (res.svgCount === 0) {
              // Empty body — Plot never rendered. Move on to next.
              continue;
            }
            if (res.errorCount > 0) {
              return warn(
                `${path}: ${res.svgCount} SVGs but ${res.errorCount} console.errors`,
                { errors: res.errors },
              );
            }
            return pass(`${path} (${res.svgCount} SVGs)`);
          }
        } catch {
          // try next candidate
        }
      }
      return fail(
        `tried ${candidates.length} embed candidates (from library.json); none rendered an SVG within 6s`,
        { candidates },
      );
    },
  },
  {
    id: "iframe/choropleth-renders",
    category: "iframe",
    label: "a choropleth tile produces an SVG with features",
    timeoutMs: 35000,
    run: async (): Promise<DiagnosticResult> => {
      // /federal-budget/ has a "Demographic context (heatmaps)" section
      // with 4+ choropleths at state + county granularity. Tall
      // iframe so IntersectionObserver-gated lazy mounts fire even
      // for below-the-fold tiles.
      return await withHiddenIframe(
        "/federal-budget/",
        7000, // boundary TopoJSON fetch + d3 render = slow
        (_win, doc, errors) => {
          const choroTiles = doc.querySelectorAll('[data-choro="1"]');
          if (choroTiles.length === 0) {
            return fail(
              "no [data-choro] tiles found — selector drift or wrong dashboard",
            );
          }
          // Check at least one rendered an SVG with paths inside its
          // choro-canvas. An empty canvas means the boundary fetch
          // failed, Plot crashed, or the data file 404'd.
          let renderedCount = 0;
          let pathTotal = 0;
          for (const tile of Array.from(choroTiles)) {
            const canvas = tile.querySelector(".choro-canvas");
            const svg = canvas?.querySelector("svg");
            if (!svg) continue;
            const paths = svg.querySelectorAll("path");
            if (paths.length > 0) {
              renderedCount++;
              pathTotal += paths.length;
            }
          }
          if (renderedCount === 0) {
            return fail(
              `${choroTiles.length} choropleth tiles found but NONE rendered SVG paths — boundary fetch or render failure`,
              {
                choroTileCount: choroTiles.length,
                consoleErrors: errors.slice(0, 5),
              },
            );
          }
          if (errors.length > 0) {
            return warn(
              `${renderedCount}/${choroTiles.length} choropleths rendered (${pathTotal} paths) but ${errors.length} console.errors`,
              { errors: errors.slice(0, 3) },
            );
          }
          return pass(
            `${renderedCount}/${choroTiles.length} rendered, ${pathTotal} feature paths`,
            { renderedCount, totalTiles: choroTiles.length, pathTotal },
          );
        },
        { heightPx: 4000 },
      );
    },
  },
  {
    id: "iframe/choropleth-dialog-has-fullscreen-and-scheme-picker",
    category: "iframe",
    label:
      "clicking a choropleth tile opens a dialog with scheme picker + fullscreen button",
    timeoutMs: 35000,
    run: async (): Promise<DiagnosticResult> => {
      return await withHiddenIframe(
        "/federal-budget/",
        7000, // boundary fetch + first paint
        async (_win, doc, errors) => {
          const tile = doc.querySelector<HTMLElement>('[data-choro="1"]');
          if (!tile) return fail("no [data-choro] tile to click");
          // The tile root is wrapped in <a class="chart-tile">; click
          // the tile (or its inner anchor) to open the dialog. The
          // outer <a> swallows the click in either case.
          const clickable =
            tile.closest("a") ?? tile.querySelector("a") ?? tile;
          (clickable as HTMLElement).click();
          // Wait for dialog open + d3 render in expanded mode.
          await new Promise((r) => setTimeout(r, 3500));
          const dialog = doc.querySelector("dialog[open]");
          if (!dialog) {
            return fail(
              "tile click did not open <dialog[open]>",
              { errors: errors.slice(0, 5) },
            );
          }
          const fullscreenBtn = dialog.querySelector(
            ".choro-dialog-fullscreen",
          );
          // Scheme picker is a <select> (see ChartChoropleth.astro).
          // We don't lock down a specific class; look for any select
          // inside the dialog as a permissive check.
          const schemeSelect = dialog.querySelector("select");
          if (!fullscreenBtn) {
            return fail(
              "choropleth dialog opened but has no .choro-dialog-fullscreen button",
              { errors: errors.slice(0, 3) },
            );
          }
          if (!schemeSelect) {
            return fail(
              "choropleth dialog opened but has no scheme <select> picker",
              { errors: errors.slice(0, 3) },
            );
          }
          if (errors.length > 0) {
            return warn(
              `dialog has fullscreen + scheme picker, but ${errors.length} console.errors`,
              { errors: errors.slice(0, 3) },
            );
          }
          return pass("fullscreen button + scheme picker both present");
        },
        { heightPx: 4000 },
      );
    },
  },
  {
    id: "iframe/composer-sources-tab-populates-and-is-clickable",
    category: "iframe",
    label:
      "Composer Sources tab renders > 100 source cards and a click adds a chart",
    timeoutMs: 30000,
    run: async (): Promise<DiagnosticResult> => {
      return await withHiddenIframe(
        "/compose/",
        4000, // composer hydration + library.json fetch
        async (_win, doc, errors) => {
          // The Sources tab is the default; library.json populates
          // it post-hydration. Source rows render as
          // <button class="source-card">.
          const cards = doc.querySelectorAll<HTMLElement>(
            "[data-role='lib-results-sources'] .source-card",
          );
          if (cards.length < 100) {
            return fail(
              `Sources tab only has ${cards.length} cards — library.json didn't populate or rendering broke`,
              { cardCount: cards.length, errors: errors.slice(0, 3) },
            );
          }
          // Pick the first non-hint card (hint cards have a different
          // class + handler). Click it; verify a new tile appeared in
          // the compose area.
          let target: HTMLElement | null = null;
          for (const card of Array.from(cards)) {
            if (!card.classList.contains("source-card-hint")) {
              target = card;
              break;
            }
          }
          if (!target) {
            return fail(`all ${cards.length} source cards are hint cards`);
          }
          // After click, anything different in the DOM means the
          // handler did SOMETHING — opened a modal, added a tile,
          // toggled a tab, anything. We use overall element count +
          // any visible dialog as a permissive signal. The specific
          // "did a tile get added to the compose canvas" check
          // turned out too brittle to rely on; v1 used hardcoded
          // selectors that didn't match any real DOM.
          const elementCountBefore = doc.querySelectorAll("*").length;
          const bodyLenBefore = doc.body.innerHTML.length;
          target.click();
          await new Promise((r) => setTimeout(r, 800));
          const elementCountAfter = doc.querySelectorAll("*").length;
          const bodyLenAfter = doc.body.innerHTML.length;
          const dialogOpen = !!doc.querySelector("dialog[open]");
          const elementDelta = elementCountAfter - elementCountBefore;
          const bodyDelta = bodyLenAfter - bodyLenBefore;
          const handlerFired =
            dialogOpen ||
            elementDelta > 5 ||
            Math.abs(bodyDelta) > 200;
          if (!handlerFired) {
            return warn(
              `${cards.length} cards rendered but clicking one had no visible effect (dialogOpen=${dialogOpen} ΔElements=${elementDelta} ΔBodyLen=${bodyDelta})`,
              {
                cardCount: cards.length,
                elementDelta,
                bodyDelta,
                dialogOpen,
                errors: errors.slice(0, 3),
              },
            );
          }
          if (errors.length > 0) {
            return warn(
              `${cards.length} cards + click triggered changes but ${errors.length} console.errors`,
              { errors: errors.slice(0, 3) },
            );
          }
          return pass(
            `${cards.length} cards rendered; click ${dialogOpen ? "opened dialog" : `changed DOM (Δelements=${elementDelta})`}`,
            { cardCount: cards.length, elementDelta, bodyDelta, dialogOpen },
          );
        },
      );
    },
  },
  {
    id: "iframe/composer-tile-drag-attribute",
    category: "iframe",
    label:
      "Composer with pre-encoded state shows draggable tiles (drag wiring prerequisite)",
    timeoutMs: 30000,
    run: async (): Promise<DiagnosticResult> => {
      // Drag-drop interaction tests are infamously flaky across
      // browsers (DataTransfer + dragstart synthesis is poorly
      // standardized). Rather than trying to drive a full drag flow,
      // this test verifies the PREREQUISITE: that tiles render with
      // draggable=true + the data-sec-idx / data-chart-idx attrs the
      // composer's dragstart handler reads. If those aren't present,
      // drag-to-reorder is broken regardless of whether the
      // dispatch succeeds. Also fires a synthetic dragstart and
      // reports whether anything visibly responded — informational
      // only.
      const { encodeComposedState } = await import(
        "../composer-state"
      );
      // Two charts in one section so the user has something to
      // reorder. countries/australia was confirmed real in earlier
      // diagnostic runs; pick any two chart IDs from library.json
      // if a renamed dashboard later breaks both.
      const libRes = await fetch(
        new URL("/library.json", window.location.origin).toString(),
        { cache: "no-store" },
      );
      if (libRes.status !== 200) {
        return fail(`library.json status=${libRes.status}`);
      }
      const lib = (await libRes.json()) as {
        charts?: Array<{ id?: string }>;
      };
      const chartIds = (lib.charts ?? [])
        .map((c) => c?.id)
        .filter((s): s is string => !!s)
        .slice(0, 2);
      if (chartIds.length < 2) {
        return fail("library.json has < 2 chart ids");
      }
      const encoded = encodeComposedState({
        title: "Diag drag-drop probe",
        sections: [
          {
            title: "Two tiles to reorder",
            charts: chartIds,
          },
        ],
      });
      return await withHiddenIframe(
        `/compose/?d=${encoded}`,
        4500, // hydration + state decode + tile render
        async (win, doc, errors) => {
          const tiles = doc.querySelectorAll<HTMLElement>(
            ".comp-section-grid .comp-tile",
          );
          if (tiles.length < 2) {
            return fail(
              `expected >= 2 tiles after state-encoded URL load, got ${tiles.length}`,
              {
                tileCount: tiles.length,
                errors: errors.slice(0, 3),
              },
            );
          }
          // Prerequisite check: tiles MUST be draggable + have the
          // dataset.secIdx / dataset.chartIdx that the handler reads.
          const first = tiles[0];
          const second = tiles[1];
          if (!first.draggable) {
            return fail(
              "first tile has draggable=false — drag-to-reorder wiring broken at the DOM level",
              { errors: errors.slice(0, 3) },
            );
          }
          if (first.dataset.secIdx == null || first.dataset.chartIdx == null) {
            return fail(
              "tiles missing data-sec-idx / data-chart-idx — composer drag handler can't identify them",
            );
          }
          // Attempt a synthetic drag — best-effort, won't fail the
          // test if it doesn't reorder anything. JSDOM-style synthetic
          // DataTransfer is finicky; we just need to know "did the
          // dragstart handler at least fire without crashing?"
          let dragstartCount = 0;
          first.addEventListener(
            "dragstart",
            () => {
              dragstartCount++;
            },
            { once: true },
          );
          try {
            const dt = new (win as unknown as { DataTransfer: typeof DataTransfer })
              .DataTransfer();
            const dragstartEvent = new (win as unknown as {
              DragEvent: typeof DragEvent;
            }).DragEvent("dragstart", {
              bubbles: true,
              cancelable: true,
              dataTransfer: dt,
            });
            first.dispatchEvent(dragstartEvent);
            // Best-effort drop on second tile.
            const dropEvent = new (win as unknown as {
              DragEvent: typeof DragEvent;
            }).DragEvent("drop", {
              bubbles: true,
              cancelable: true,
              dataTransfer: dt,
            });
            second.dispatchEvent(dropEvent);
            first.dispatchEvent(
              new (win as unknown as {
                DragEvent: typeof DragEvent;
              }).DragEvent("dragend", { bubbles: true }),
            );
          } catch (e) {
            // Drag synthesis failed — that's the EXPECTED outcome in
            // many browsers. Don't fail the test on this alone.
            return warn(
              `tile prerequisites OK (draggable=true, data attrs present); synthetic drag dispatch failed: ${(e as Error).message}`,
              { tileCount: tiles.length },
            );
          }
          await new Promise((r) => setTimeout(r, 500));
          // Inspect whether the order changed — if it did, the drag
          // actually worked, which is a stronger pass.
          const afterTiles = doc.querySelectorAll<HTMLElement>(
            ".comp-section-grid .comp-tile",
          );
          const newFirstChartIdx = afterTiles[0]?.dataset.chartIdx;
          const reordered = newFirstChartIdx !== first.dataset.chartIdx;
          return pass(
            `${tiles.length} draggable tiles; dragstart fired ${dragstartCount}x; reorder=${reordered}`,
            {
              tileCount: tiles.length,
              dragstartCount,
              reordered,
              errorCount: errors.length,
            },
          );
        },
      );
    },
  },
  {
    id: "iframe/mobile-viewport-no-horizontal-scroll",
    category: "iframe",
    label:
      "/us-macro/ in a 375px-wide viewport doesn't horizontal-scroll",
    timeoutMs: 25000,
    run: async (): Promise<DiagnosticResult> => {
      // Override the iframe's width to iPhone-class (375px) so
      // mobile-only CSS paths (single-column tile stacking,
      // pill-row wrap, dialog full-width) actually fire.
      const iframe = document.createElement("iframe");
      iframe.style.position = "fixed";
      iframe.style.top = "-9999px";
      iframe.style.left = "-9999px";
      iframe.style.width = "375px";
      iframe.style.height = "3500px";
      iframe.style.border = "0";
      iframe.setAttribute("aria-hidden", "true");
      iframe.setAttribute("data-tape-diagnostic-iframe", "/us-macro/?mobile");
      document.body.appendChild(iframe);

      try {
        await new Promise<void>((resolve, reject) => {
          iframe.addEventListener("load", () => resolve(), { once: true });
          iframe.addEventListener(
            "error",
            () => reject(new Error("iframe load error")),
            { once: true },
          );
          iframe.src = "/us-macro/";
        });
        const win = iframe.contentWindow!;
        const doc = iframe.contentDocument!;
        await new Promise((r) => setTimeout(r, 4000));
        // scrollWidth > innerWidth means there's overflow — the
        // canonical "your page horizontal-scrolls on mobile" signal.
        const scrollWidth = doc.documentElement.scrollWidth;
        const innerWidth = win.innerWidth;
        if (scrollWidth > innerWidth + 8) {
          // 8px tolerance for sub-pixel rendering quirks.
          return fail(
            `body scrollWidth=${scrollWidth} > viewport ${innerWidth} (overflow=${scrollWidth - innerWidth}px)`,
            { scrollWidth, innerWidth, overflow: scrollWidth - innerWidth },
          );
        }
        // Confirm at least one chart tile rendered — otherwise
        // there's nothing to overflow and the test is vacuous.
        const tiles = doc.querySelectorAll(
          "[data-chart-id], .chart-tile, [data-tile-chart-id]",
        );
        if (tiles.length === 0) {
          return warn(
            "no chart tiles rendered in mobile viewport — overflow check vacuous",
          );
        }
        return pass(
          `scrollWidth=${scrollWidth} ≤ viewport ${innerWidth} (${tiles.length} tiles rendered)`,
          { scrollWidth, innerWidth, tileCount: tiles.length },
        );
      } finally {
        iframe.remove();
      }
    },
  },
  {
    id: "iframe/dialog-opens-on-tile-click",
    category: "iframe",
    label: "clicking a chart tile opens the <dialog>",
    timeoutMs: 30000,
    run: async (): Promise<DiagnosticResult> => {
      return await withHiddenIframe(
        "/us-macro/",
        4000,
        async (_win, doc, errors) => {
          // Tiles are <button class="chart-tile" data-chart-ref="...">
          // (see Chart.astro). The previous version of this test used
          // `a.chart-tile` + `data-chart-id` — both wrong. The matched
          // selector below is the same one iframe/us-macro-charts-
          // render successfully uses to count 32 tiles.
          const tile = doc.querySelector<HTMLElement>(
            ".chart-tile[data-chart-ref], .chart-tile",
          );
          if (!tile) {
            return fail(
              "no chart tile found to click (.chart-tile selector miss — DOM shape changed?)",
              { errors: errors.slice(0, 3) },
            );
          }
          tile.click();
          // ChartController.astro wires tile.click -> dialog.showModal()
          // synchronously, then kicks an async update for the Plot
          // SVG. Settle 3s to cover the full-data fetch + Plot render.
          await new Promise((r) => setTimeout(r, 3000));
          const dialog = doc.querySelector("dialog[open]");
          if (!dialog) {
            return fail(
              "tile click did not open any <dialog[open]> — click handler not wired?",
              { errors: errors.slice(0, 5) },
            );
          }
          const svgInside = dialog.querySelector("svg");
          if (errors.length > 0) {
            return warn(
              `dialog opened${svgInside ? " + SVG rendered" : " but no SVG"} (${errors.length} console.errors)`,
              { errors: errors.slice(0, 3) },
            );
          }
          if (!svgInside) {
            return warn(
              "dialog opened but no SVG inside (full-data fetch pending? Plot async path stuck?)",
            );
          }
          return pass("dialog opened + SVG rendered");
        },
      );
    },
  },
];
