# Welcome-popout chart sizing bug (resumable)

Status 2026-06-04: **partially fixed, NOT yet verified against the real
expanded view. Not deployed.** The browser is connected (Claude-in-Chrome) for
faithful reproduction next time.

## Symptom (from Keller's prod screenshots, legible-markets.vercel.app/welcome/)
On the welcome page, clicking a coverage chip opens a full-screen popout. The
chart inside doesn't fill it:
- **Map** (county bachelor's-degree map): map sat left-aligned at a
  fixed width with a wide blank gap on the right. Screenshot showed the
  **expanded** controls (Color picker, ± zoom, Reset zoom, Full screen, "Why no
  rainbow?", legend) — i.e. the EXPANDED view, not the tile.
- **Line chart** (CPI): a ~1020px dialog card centered in the ~1800px popout
  with big grey margins — the expanded **dialog** not filling the popout.

## Architecture (how the popout works)
- `src/pages/welcome.astro`: `.welcome-popout-overlay` (fixed, flex-centered,
  z-1000) contains `.welcome-popout-iframe` (`width:100%; max-width:1800px`).
  The iframe loads `chartHref` = `/chart/<id>/?expanded=1`.
- `src/pages/chart/[...id].astro`: when framed (`window.parent !== window`) an
  inline script adds `chart-detail-host-popout` to `<html>`; CSS removes the
  `.chart-detail` 880px cap (`max-width:none !important`). **This works** —
  verified live: `.chart-detail` is full-width (1442px in a 1457px iframe).
  A second inline script auto-opens the chart's dialog when `?expanded=1`.

## Root cause(s) — the chart/map renders at a FIXED width, not container-derived
The container is correctly full-width; the inner SVG isn't.
- **Map** (`src/components/ChartMap.astro` ~line 892): width is
  chosen by mode — `fullscreen: min(vw-40,2400)`, `expanded: 1000`,
  `tile: 620`. All FIXED. `svg { max-width:100% }` scales DOWN for small grid
  tiles but never UP, so any wider container leaves a gap.
  - **DONE (committed 433d43a38e, NOT verified, NOT pushed):** tile mode now
    `Math.max(620, canvas.clientWidth)` + height scaled to keep aspect. Verified
    live that the popout TILE map was svg=620 in a 1352 canvas, so this
    fixes the *tile* case.
  - **REMAINING:** Keller's screenshot shows the **expanded** map (1000px
    fixed), which my programmatic repro never triggered (it stayed on the tile).
    Expanded mode (1000) also won't fill an 1800px popout → same gap. Likely fix:
    make `expanded` width container-derived too (e.g. `Math.max(1000, canvasW)`),
    or detect the popout host. MUST reproduce + measure first.
- **Line chart** (`src/components/ChartController.astro`): derives plot width from
  `container.clientWidth` (lines ~1255/1341/1545) and re-renders on
  `window.resize` (~line 3205). In the popout the auto-opened **dialog** likely
  has its own max-width (~1000-1020) so the dialog's plot fills only the dialog,
  not the popout → grey margins. NOT yet inspected. Need to measure the open
  `<dialog>` width + its plot in the popout and decide whether to widen the
  dialog in `chart-detail-host-popout` context.

## What's committed locally (unpushed — prod untouched)
- `a237fb639f` fix(dev): remove literal `<script>` from 2 comments (real,
  unrelated win — see below).
- `433d43a38e` fix(map): tile-mode fill (PARTIAL — tile only).
- `f9ec7e76e0` docs(checklist): Plan 4 status.

## To resume (faithful repro — don't guess)
1. Connected browser → new MCP tab → navigate `…/welcome/`.
2. **Natural flow**: click a coverage chip (don't just set iframe `src` — that
   didn't trigger the map expand). Let the popout open expanded.
3. Inspect the iframe's `document`: find `dialog[open]` (line chart) and the
   expanded map canvas; measure widths + the cap chain (the technique
   that found the 620). Confirm which fixed width is leaving the gap.
4. Fix the **expanded** map width + the **line dialog** width to fill the
   popout (container-derived), keeping standalone/grid behavior unchanged.
5. Verify in-browser at the popout, then build + push + curl/eyeball.

## Dev-server caveat (blocks local visual verification of CONTENT pages)
`astro dev` now BOOTS (scanner crash fixed) but Vite 8's module-runner
**transport times out loading `src/content/config.ts` (60s)** under the 35k-file
`sources` collection on Windows → content pages (dashboards, `/chart/`, welcome)
500 in dev. So local visual verification isn't available yet; use the connected
browser against **prod**, or `astro build` + a static server over
`.vercel/output/static` (prerendered pages only). Solving the transport timeout
is its own effort (Vite-version test / content-layer mitigation).
