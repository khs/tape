# Tape — structural-refactor checklist

> Approved 2026-06-03. Eight structural improvements from a from-scratch
> review. This file is the durable source of truth across sessions — update
> the checkboxes as work lands. Companion: `docs/data-flow.md` (pipeline map).
>
> **Global gate for every change (laptop rule, updated 2026-06-06):** local
> `astro check` + `vitest` (+ a parity test for behavior-preserving refactors).
> Do NOT run a full `npm run build` on the laptop — the Vercel function-bundle
> step (copies the ~290 MB `public/data` tree into the SSR bundle, ~4 GB heap)
> OOMs / crashes this 7.4 GB machine (it crashed it once, 2026-06-06). **CI is
> the authoritative build gate** (Linux — no fs/RAM limits): push at a logical
> checkpoint and verify CI + post-deploy smoke + diagnostic. Never leave
> `astro dev` running (its node proc leaks to multiple GB). `pytest` for pipeline
> changes is still fine locally (cheap).
> **Explicit OK from Keller before every push to `main` (= prod).**

---

## ⮕ RESUME HERE — updated 2026-06-08 (Plan 3a+3b DONE; 3c foundation done (richCards), adoption banked)

**Plan 1+2 — IN PROGRESS. 2a/2b/2c DONE + LIVE; 2d STARTED (foundation + share +
maps + generators + series + modal-tags + ds-modal + cc-modal + geo-chips + sources-tab + tiles verified).**
`compose.astro`: **11,007 → ~3,609 lines** and falling. `origin/main = 0251af492b (3a + 3b + 3c richCards foundation)` (compose ~3547 lines).
- **2a** (`f193eac42a`) — `<style is:global>` → `src/styles/compose.css`.
- **2b** (`e9bfb00370`) — geo/tag filters → `src/lib/composer/geo-filter.ts`
  (`createComposerGeoFilters` over `source-filters.ts`; per-query unlock memo +
  the CD "pick a state" gate preserved; 14-case parity test `geo-filter.test.ts`).
- **2c** (`f1983d0b68`) — `ComposerStore` → `src/lib/composer/state.ts`
  (`createComposerStore()`). compose **aliases** the never-reassigned slices
  (`const state = store.state`, `libGeo`, `ccModal`, `dsModal` — zero churn on
  ~700 refs); the 4 reassigned scalars (`sourcesSearchQuery` / `sourcesCdState` /
  `sourcesCdDistrict` / `activeSectionIdx`) are `store.x`; **`library` stays a
  local `let`** (its `LibraryPayload` type lives in compose; 2d folds it in).
  All three verified astro check 0/0/0 + vitest 720 + CI + post-deploy green.
- **✅ RUNTIME-VERIFIED LIVE (2026-06-07)** via a browser walkthrough on prod
  `/compose/`: source search + tag-facet recount, add-source→tile (the VIX line
  chart rendered client-side), share-URL serialize (`?d=` round-trips the store
  state), state persistence across filter changes, the **2b CD geo-filter** (the
  "pick a state" gate → `all (0)`, then picking California unlocks its statewide +
  congressional-district series + the district drill-down), and **both modals open
  fully wired** (cc-modal `ccModal`, ds-modal `dsModal`). **Zero console errors**
  throughout. NOT exercised (low residual risk): metro/country geo chips (the CD
  path — the trickiest — passed), the Maps tab, and "Save to my account"
  (server-persist — left alone deliberately). **2b/2c confirmed good on prod.**

**2d — IN PROGRESS. Splitting compose's `<script>` into `src/lib/composer/*`
feature modules, most-isolated first, ONE push + walkthrough per unit.** Pattern:
a `create<Feature>(ctx)` factory (like 2b's `createComposerGeoFilters`) closing
over a context, so compose destructures the functions it needs and the existing
call sites stay unchanged. 2d's risk is **DOM/event wiring, which `astro check`
does NOT catch** — only a live walkthrough does (so pure modules can skip it,
DOM-coupled ones can't). Done so far (compose 8,603 → 6,754):
- **ids.ts + library.ts** (`662eb69d44`, LIVE + CI/post-deploy green) — the PURE
  pieces: the `inline:/inlinemap:/derived:` prefixes + `isInlineId/isInlineMapId/
  isDerivedId`; the `LibraryPayload` type cluster + `loadLibrary(baseUrl)`. Pure →
  astro check fully validated it; no walkthrough needed.
- **share.ts** (`a0b53a0438`, LIVE + CI/post-deploy green + walkthrough-verified) — `createShareUrl(ctx)`
  owns `referencedInline{Charts,Maps,Sources}` + `referencedChartOverrides` +
  `singleChartPreviewUrl` + `writeUrl` (the `?d=` share URL, the Preview link, and
  single-tile preview). ctx = `{shell, baseUrl, state, getEditingSlug}`; edit-slug
  read via getter because `hydrateFromUrl` sets it after the factory is built.
  `hydrateFromUrl` STAYS in compose for now — it WRITES the mutable `editingSlug`/
  `copyMode` lets (shared with the save flow); fold those into the store later.
  Walkthrough-verified on prod (2026-06-08): `writeUrl` `?d=` round-trip +
  matching Preview href, `singleChartPreviewUrl` single-section collapse, the
  `/custom/?d=` URL renders, zero console errors.
- **maps.ts** (`2fdff1a0f2`, LIVE + walkthrough-verified) — `createMapsTab(ctx)`
  owns the Maps tab (indicator/vintage/geo/state pickers, the d3 bbox-brush
  preview, `addMapToDashboard`). `renderMapBuilder` is the only entry point. ctx
  adds `mapBboxTopoCache` (the topojson cache stays in compose — the tile-preview
  thumbnails share it) + escapeHtml + render/writeUrl/gate/clamp callbacks. No
  `library` coupling (static lookup tables). compose dropped its now Maps-only
  `d3-selection` / `d3-brush` imports.
- **generators.ts** (`e463c32f18`, LIVE + walkthrough-verified) —
  `createGeneratorsTab(ctx)` owns the mass-generate builder (template + entity
  pickers, indicator-vs-profile layouts, `generateMassDashboard` /
  `generateEntityProfile`). `renderGeneratorsBuilder` is the only entry. No
  `library` coupling (a separate `/generators-index.json` fetch). Same ctx shape
  (+ `baseUrl` for the index fetch).

  Both **walkthrough-verified on prod (2026-06-08)**: Maps built + added a county
  poverty choropleth (tile rendered, "20 regions no data" note shown); Generators
  "By indicator × Metro × Top-12" generated 12 metro charts into the section (all
  line charts rendered); `?d=` serialized both the inline map + the 12 charts;
  **zero console errors** throughout.
- **series.ts** (`bfb781bed3`, LIVE + walkthrough-verified) — shared
  source-series fetcher. `createSeriesFetcher(ctx)` owns `fetchSourceSeries`
  (fetch + cache + derived A-op-B resolution); `SeriesPoint` / `FetchedSeries` /
  `CC_COLORS` are static exports. Used by BOTH the tile-preview thumbnails AND the
  cc-preview (one shared cache). ctx = `{getLibrary, baseUrl, state}`; one
  captured-local `const lib = getLibrary()` (narrowing preserved — NOT a blanket
  rewrite). This is **step (1) of the cc-modal sequence below** — unblocks
  cc-modal+cc-preview. Clean (astro check 0/0/0 first try). Walkthrough-verified
  on prod (2026-06-08): VIX tile sparkline + the 10Y cc-modal preview both
  rendered (shared fetcher confirmed in both consumers).
- **modal-tags.ts** (`63480466c0`, LIVE + walkthrough-verified) -- the shared
  modal tag-chip strip. `createModalTagChips(ctx)` owns `renderModalTagChips`
  (+ its private `allPickableSourceTags`): the topical-tag pills rendered by
  BOTH the cc-modal AND ds-modal source pickers. ctx = `{shell, getLibrary,
  state}` + the tag consts. SCOUT FINDING: renderModalTagChips is the ONLY
  genuinely-shared modal fn -- the ds-only helpers (`pickableSourceOptions`,
  `sourceTagsFor`, `dsSourceLabel`, `inheritedTagsForDerived`) STAY in compose
  and move with ds-modal. This fully decouples cc-modal from the ds region.
  Walkthrough-verified on prod (2026-06-08): both modals render the identical
  36-chip topical strip ([data-role=cc-source-tags] / [data-role=ds-source-tags]);
  the `labor` chip toggles active in each (onToggle fires, `all` deactivates);
  zero app console errors (only the known Zotero-extension noise).
- **ds-modal.ts** (`9751163d82`, LIVE + walkthrough-verified) -- the
  derived-source modal. createDerivedSourceModal(ctx) owns the A/B operand
  pickers (renderDsPicker), the auto-name + rebuild-total / combine-hint
  suggestion chips, and the create flow (optional add-as-chart). ONE contiguous
  ~565-line block; the ds-only helpers (pickableSourceOptions, sourceTagsFor,
  dsSourceLabel, inheritedTagsForDerived) moved with it. The geo-chip <-> modal
  circular ref resolved via the factory: ds-modal EXPORTS renderDsPicker /
  renderDsModalTagChips, which compose geoSurfaceConfig calls for the "ds"
  surface; the per-surface geo-chip renderers + renderModalTagChips (modal-tags)
  + geo passes* (geo-filter) arrive via ctx. dsModal stays in compose for
  geoSurfaceConfig. library via getLibrary() per fn. Built from the real
  extracted text (PowerShell substring) + 5 library-const inserts -- no
  hand-transcription. astro check 0/0/0; vitest 720. Walkthrough-verified on
  prod (2026-06-08): modal renders A/B pickers (795 rows) + 36 tag chips + the
  CD geo chip (circular ref works); picked 10Y / 10Y real -> hint shows the
  equation + create enabled; created it (add-as-chart) -> the derived tile
  rendered a real divided line + ?d= serialized the chart; zero app errors.
- **cc-modal.ts** (`b8474940c0`, LIVE + walkthrough-verified) -- the
  custom-chart modal + live preview, the LARGEST 2d unit (~1,473 lines out).
  createCustomChartModal(ctx) owns the source picker (filteredModalSources /
  renderCustomChartSources), the mode/shading/annotation/op controls, the merge
  flow (openMergeModal + drag-two-tiles), and the live Plot preview
  (renderCustomChartPreview). TWO ranges (cc core + wireCustomChartModal,
  stranded after the old ds region) + the cc-only helpers fold in; the 5 fns
  compose / geoSurfaceConfig / ds-modal call are exported. Resolved the cc <->
  ds cross-dep: renderCustomChartSources now lives here + is passed into
  ds-modal via ctx, so the cc factory is built BEFORE ds. Shared deps via ctx:
  fetchSourceSeries (series), renderModalTagChips (modal-tags), passes* +
  per-surface geo chips, chartEffectiveSpec / baseTitleIsDefault /
  updateCcAnnotationsWarning / hover-tip (all stay in compose). library via
  getLibrary() per fn (7 inserts). Built from real extracted text; ctx
  converged via astro check. astro check 0/0/0; vitest 720. Walkthrough-
  verified on prod (2026-06-08): modal renders 752 source rows + 36 tag chips +
  3 cc geo chips (circular ref); picked 10Y real -> live Plot preview rendered
  (1 series, raw, legend); created the chart -> custom tile rendered a real
  line + ?d= serialized + modal closed; zero app console errors.

Remaining: the **Render core** (renderComposition + drag/drop + wire + load/save)
is the page core orchestrator -- see the ASSESSMENT below.

**STATUS 2026-06-08 (autonomous run -- 3 more modules extracted + verified live):**
- geo-chips.ts (`e98f2e5d52`), sources-tab.ts (`27208fb82d`), tiles.ts
  (`160d6354a9`) all EXTRACTED + astro 0/0/0 + vitest 720 + pushed + CI/post-
  deploy green + walkthrough-verified on prod. (modal-tags / ds-modal / cc-modal
  verified earlier this session.) origin/main = 160d6354a9. compose.astro ~3,675
  lines (was 11,007 -- 67% smaller). Tree clean.
  - geo-chips.ts: createGeoChips(ctx) -- metro/country/CD chips for lib/cc/ds;
    getSurfaceConfig=geoSurfaceConfig (STAYS in compose); cc/ds modules unchanged
    (now source the renderers from here). WT: lib geo strip renders + CD chip
    toggles the pick-a-state gate (the geoSurfaceConfig circular ref).
  - sources-tab.ts: createSourcesTab(ctx) -- Sources/Charts lib tab (tag filters,
    filtered lists, result renderers, hint chips, setActiveLibTab).
    chartsSelectedTags owned here; chartsSearchQuery via getter; sourcesSelectedTags
    stays in compose (geoSurfaceConfig reads it) via ctx. WT: 752 sources + 27 tag
    chips; agriculture filter 752->21; Charts tab 90 cards; click -> addSourceAsChart
    -> tile + ?d=.
  - tiles.ts: createTiles(ctx) -- renderTilePreview (sparklines + mini-map
    silhouettes). Pulled d3-geo / topojson / Plot out of compose. renderComposition
    (stays) calls renderTilePreview per tile.
    WT: source tile -> sparkline SVG; county map tile -> 3231-path choropleth
    silhouette; zero app console errors.

**ASSESSMENT -- Render core (renderComposition): RECOMMEND LEAVE IN COMPOSE.**
renderComposition (~615 lines) is the page core render method, deeply coupled to
the drag/drop + hover-merge system, wireGridDropTarget, the chart helpers
(chartEffectiveSpec / coverageWarningFor / baseTitleIsDefault / the hover-tip +
cc-annotations helpers), state, and renderTilePreview (tiles.ts, via ctx).
Extracting it would need a ~20-callback ctx (most of compose helpers) for ~615
fewer lines -- net negative (more plumbing than it removes) + highest-risk surgery
on the heart of the page. The remaining ~3,675-line compose is now a reasonable
CORE ORCHESTRATOR: imports + the create<Feature>(ctx) factory wiring + geoSurfaceConfig
+ appendCdDrillDown + the chart-add helpers + the drag/drop/hover-merge system +
renderComposition + the shared helpers (chartEffectiveSpec/escapeHtml/...) +
checkComposeAction/showSigninPrompt + wire() + the blurb modal + load/hydrate/save/
copy. The 2d feature-module split is DONE. Further core extraction is optional
polish, NOT recommended (it would force the shared helpers out of compose -> a
cc/ds/sources-tab ctx rewire for little gain).

**Re-grep section anchors before each extraction — line numbers shift as modules
leave.** Both gates per unit: **astro check 0/0/0 + vitest 720**.

**⚠️ cc-modal/cc-preview attempt (2026-06-08) — REVERTED (caught pre-push by
astro check, 35 errors). The remaining 4 are an ENTANGLED CLUSTER; here's the map
+ the plan:**
- **cc-preview's data layer is SHARED with tile-previews.** `fetchSourceSeries`,
  the `FetchedSeries` type, and `CC_COLORS` (in the cc-preview block) are also used
  by compose's `renderTileSparkline`. Moving cc-preview broke tile-previews. →
  extract these to a SHARED module FIRST (e.g. `src/lib/composer/series.ts`),
  imported by both. `fetchSourceSeries` itself needs library/baseUrl/
  `state.inlineSources` (resolves derived sources) → its own small ctx.
- cc-modal pulls ~10 compose-local helpers as ctx: the 2b geo-filter consts
  (`passesCdFilter`/`passesMetroFilter`/`passesCountryFilter`/`passesCountyFilter`),
  `updateCcAnnotationsWarning`, `chartEffectiveSpec`, `baseTitleIsDefault`,
  `dismissHoverMergeTip`, `isHoverMergeTipDismissed`; + imports `packSourceIds`,
  `COUNTRY_TAG`, `METRO_TAG`. Also: `renderModalTagChips` (shared w/ ds, depends on
  `allPickableSourceTags`) + `wireCustomChartModal` are stranded in the ds region.
- **LESSON: do NOT blanket `\blibrary\b`→`getLibrary()`** — it breaks
  guard-narrowing (`if(!library)return; library.sources`). Instead add
  `const library = getLibrary();` at each fn top, OR type `getLibrary():
  LibraryPayload` non-null + pass `() => library!` (cc fns run post-load → safe).
- **Recommended sequence (focused session):** (1) shared `series.ts`
  (`fetchSourceSeries`/`FetchedSeries`/`CC_COLORS`), verify tiles render; (2)
  cc-modal+cc-preview; (3) ds-modal; (4) geo-chips (interleaved w/ sources-tab:
  move 1695–2103 + `appendCdDrillDown` ~2212; keep `geoSurfaceConfig` in compose);
  (5) sources-tab; (6) Render core last. geo-chip ↔ modal refs are circular but
  resolve via the factory pattern (modals take geo-chip fns via ctx;
  `geoSurfaceConfig` uses the modal factories' returned render fns).

**Dev server — STILL UNUSABLE (don't re-burn time on the easy fix):** `astro dev`
has TWO blockers. (1) **Content-sync timeout** — globbing the ~35k-file `sources`
collection (acs_cd ~20k, acs_metro ~6k) exceeds Vite's 60s transport limit.
FIXED-IN-TESTING by a DEV-only subset glob in `src/content/config.ts`
(`pattern: import.meta.env.DEV ? ["{fred,yahoo_marketcap,worldbank_extended,
acs_labor,acs_state,bea,oecd,eia_prices,fbi_crime,naep,cdc_health}/**/*.yaml"] :
"**/*.yaml"`) → sync dropped to ~8s. (2) **BUT `/compose/` rendering still hangs**
— Vite-8 dev SSR module-runner transport chokes on the 8,895-line compose.astro
graph (boot ~59s, page never responds). #2 is the real unsolved blocker; the
subset alone does NOT make dev usable, so it was **reverted**. Possible angle:
2d's split might shrink compose.astro enough to fix #2 (chicken/egg — worth
probing once a few modules are out).

**⚠️ MACHINE — 7.4GB RAM. The laptop CRASHED once (2026-06-06):** a leaked
`astro dev` node grew to 2.5GB and a build OOM'd the rest. RULES: never run a full
`npm run build` on the laptop (CI is the build gate); never run `astro dev` and a
build together; `TaskStop` does NOT kill the dev's child node — kill explicitly
via `Get-NetTCPConnection -LocalPort 4321` → `Stop-Process -Id <owner> -Force`,
then verify no `node.exe` remains. `npm`/`node` aren't always on the terminal
PATH: `$env:Path = "$env:LOCALAPPDATA\nodejs;$env:Path"` first.

---

### Earlier this session (all LIVE on prod) — detail below

**Live on prod (pushed, CI-green):** Plans **8, 6, 5, 4** + the **va-08**
dangling-ref fix + the **welcome-popout sizing fix** (`f72853e2f4`: expanded
map + line-chart dialog now fill the popout). Choropleth-map fill confirmed
locally (built code in a popout-sized iframe) and post-deploy smoke + diagnostic
green. The popout bug is **resolved**; `docs/popout-sizing-bug.md` is now
historical. `origin/main..HEAD` was empty after that push.

**Live on prod — choropleth→map rename (`c6ca51b3fd`, CI + post-deploy green):**
Renamed "choropleth"→"map" across everything user-facing + app internals: the
`render` enum value (`config.ts` + all **321** chart YAMLs + every dispatch site
+ tests), the component (`ChartChoropleth.astro` → **`ChartMap.astro`**), the
`.choro-*` CSS / `data-choro` attr → `.map-*` / `data-map`, the
welcome/about/compose/custom/source/user pages + MDX dashboards, `source-hints`,
`methodology`, diagnostics, and docs. **Typecheck 0/0/0, vitest 706 pass, pytest
192 pass; full astro build Complete!** Committed + pushed; CI + post-deploy
smoke + diagnostic all green. **LIVE on prod.**

**Live on prod (`a50849168c` / `fab4deefb7` / `8c44b2a4ca`; CI + post-deploy
smoke + diagnostic green):**
- **Popout single-frame fix** (`src/pages/chart/[...id].astro`) — in the welcome
  popout the map auto-enters its `.map-dialog-wide` fullscreen layout, and a
  popout rule forces that dialog to `position:fixed; inset:0` (fills the iframe
  exactly — beats ChartMap's `width:100vw` by source order) with html/body/dialog
  `overflow:hidden` (no doubled scrollbars). Non-wide `.chart-dialog` /
  `.map-dialog:not(.map-dialog-wide)` still widen to `min(96vw,1700px)`; the
  auto-expand inline script clicks the map's Full-screen control 150ms after open.
  Verified clean-room in Incognito: dialog fills the iframe (1472×631 at the test
  viewport), 0 visible scrollbars.
- **Build auto-clean** (`scripts/clean-build-output.mjs` + `package.json`
  `prebuild`) — robust `rmSync` of `dist/` + `.vercel/output` before each build so
  a sleep/lid-killed build never poisons the next (the Vite
  `prepareOutDir`/`statSync` crash). Self-healed build #4's leftover in practice
  (`[clean] cleared dist`). No-op on fresh CI/Vercel checkouts.
- **Welcome copy** (`src/pages/welcome.astro`) — Compose use-case blurb rewritten
  to "Build your dashboard." (source breadth macro→weather + the US-vs-China GDP
  derived-series hook + annotations + sharing).
- **Search-in-composer inconsistency** (ds-modal "New derived source" uses its own
  inline operand search vs the shared `SourcePicker.astro`) — Keller deferred the
  fix to **Plan 3** (3a), since there are no users yet. Symptom: typing
  "United States GDP" in an operand finds nothing.

**"choropleth" deliberately KEPT (14 files) — the Python data-engineering layer:**
`census_acs_choropleth.py` + `census_acs_choropleth_derive_state.py` (filenames
wired into `refresh-demographics.yml` + `run-data-refresh-local.sh`), `bea.py`
(`county_choropleth` fn + `choropleth` CLI keyword), `census_acs_cd.py`,
`build_state_tract_topo.py`, `_generate_acs_sources.py`,
`test_welcome_page_coverage.py`, plus filename refs inside
`config.ts`/`composer-state.ts`/`compose.astro`/`README.md`/`data-flow.md`.
Reason: CI-coupled, precise cartographic term, zero user surface, the refresh
can't be end-to-end tested here, and app code never references the render value
by this name. (Revisit if Keller wants the pipelines renamed too.)

**Stale branches — SUPERSEDED, safe to delete:** `refactor/structural-cleanup`
and `fix/va08-bg-map-refs` are fully merged into `main` (and live on prod). Work
on `main`.

**Remaining refactor plans (this file):** Plan **1+2** — 2a/2b/2c DONE+LIVE;
**only 2d remains** (the 7-module feature split — see "RESUME HERE" above for the
plan + the blind-execution caveat). Plan **3** (SourcePicker adoption — also fixes
the deferred ds-modal search bug), Plan **7** (inline-YAML standardization).

**Env / tooling (laptop):** Node 22 + Python 3.13 installed; `npm install` done;
**`NODE_OPTIONS=--max-old-space-size=4096`** user env var (build OOMs without it;
builds take ~14 min). `npm run dev` BOOTS but content pages 500 (Vite-8 content
transport timeout under the 35k-file collection — own effort). Autonomous
**sleep-guard** keeps the machine awake during builds while on AC —
`C:\Users\kelle\.tape-tools\SLEEPGUARD.md`.

## Laptop dev environment (set up 2026-06-03)
- Node **22.22.3** (portable, `%LOCALAPPDATA%\nodejs`, on user PATH) + npm 10.9.8.
  Matches `package.json` engines `22.x`. winget no longer carries 22.x.
- Python **3.13.13** (winget user scope, on user PATH) + `pytest pyyaml
  python-dotenv requests` (pip --user). Run pipeline tests via `python -m pytest`.
- `npm install --legacy-peer-deps` done (704 pkgs).
- ⚠️ **Low RAM (7.4 GB):** the `@astrojs/vercel` build:done function-tracer OOMs
  at Node's ~2 GB default heap. Fixed with user env var
  `NODE_OPTIONS=--max-old-space-size=4096` (laptop-only; does NOT affect CI/Vercel).
  Full `npm run build` takes ~14 min on this machine.
- `.env` present with all 9 keys (7 provider + both PUBLIC_SUPABASE_*).
- Pre-existing issue spawned as a side task: /va-08/ references two missing
  block-group map charts (poverty_rate, foreign_born_pct) — dangling refs,
  non-fatal build warnings.

## Execution order

1. [x] **Plan 8 — exposure scrub** (launch blocker, low risk) — DONE + build-verified
2. [x] **Plan 6 — cache consolidation** (pipelines, isolated) — DONE + VERIFIED
3. [x] **Plan 5 — chartOverride schema unification** (option A + parity tests) — DONE + VERIFIED
4. [x] **Plan 4 — dashboard renderer dedup** — DONE + VERIFIED + LIVE
5. [ ] **Plan 1 + 2 — compose.astro decompose + source-filters migration** ← NEXT
6. [ ] **Plan 3 — adopt SourcePicker.astro in composer**
7. [ ] **Plan 7 — inline-YAML standardization** (lowest urgency, splittable)

---

## Plan 8 — Remove public GitHub / internal-detail exposure  ⟶ DONE + BUILD-VERIFIED
**Decision (Keller):** KEEP the methodology cards; cull only repo links, run
commands, and internal paths.
- [x] `src/lib/methodology.ts`: removed `REPO_BLOB_BASE` + `repoFileUrl`; dropped
      `pipelineFile` + `runCommand` from the `ProviderMethodology` type and all
      6 entries (fec, bea, fred_series, noaa_climate, fbi_crime, acs_cd).
- [x] `methodology.ts` `bea` caveat: reworded to drop the `public/data/acs_county/…`
      internal path.
- [x] `src/components/SourceMethodology.astro`: removed the "Source code →" and
      "Run it" `<dl>` rows + import + `codeUrl`; reworded footer; kept upstream /
      access / this-series / steps / caveats / stored-as.
- [x] `src/pages/about.astro`: removed the visible `github.com/khs/tape` link.
- [x] `src/lib/methodology.test.ts`: dropped `REPO_BLOB_BASE`/file-URL asserts +
      on-disk test; ADDED a guard test that no entry leaks `pipelines/*.py` or
      `python pipelines` (this guard is permanent, not a temp parity test).
- [x] `compose.astro`: converted a `<!-- … pipelines/_generate_generators_index.py -->`
      HTML comment to a stripped `{/* */}` comment; genericized the
      generators-load error string (was "Run `python pipelines/…`").
- [x] KEEP confirmed: OWID provenance `url: github.com/owid/co2-data` (upstream's
      own repo, legit citation); developer comments in server-side frontmatter
      and minified-away client script are not public exposure.
- [ ] FLAG ONLY (no change unless Keller says): `src/pages/api/diagnostic.ts`
      files issues to `api.github.com/repos/khs/tape` via an env-gated token —
      internal ops endpoint, not a visible link. Confirm it's not abusable.
- [x] Verify grep: only developer comments + OWID provenance remain in `src/`.
- [x] `npm run build` → clean `Complete!` (exit 0) after the env was set up.
      Static render phase (incl. library.json prerender-invariant guards) and
      the methodology test (3/3, with the new leak guard) both pass.
      (SSR `/source/` render not exercised by build — verify by curl post-deploy.)

## Plan 6 — Consolidate the two on-disk caches  ⟶ DONE + VERIFIED
- [x] `_cache.py` is the single storage layer; both its artifact caching and
      `cached_get`'s HTTP responses (under bucket `"http"`) live in
      `pipelines/_cache/`. The `_response_cache/` store is retired.
- [x] Reimplemented `common.cached_get` on top of `_cache.cache_get`/`cache_put`
      (same signature; sha256 key under `http` bucket; `ttl_seconds/86400` →
      `max_age_days`; mtime-based freshness). No ingest-pipeline changes — the
      8 `cached_get` callers are untouched.
- [x] Removed `common.CACHE_ROOT`; tidied `.gitignore` (dropped the
      `_response_cache/` rule, noted `_cache/` is now the single cache).
- [x] Verify: rewrote `CachedGetTests` for the new store; `pytest
      pipelines/test_common.py pipelines/test_cache.py` → 40 passed; full
      `pytest pipelines/` → 192 passed; live integration check (mock session,
      real `_cache/http/`) confirmed fetch-once + cache-hit, artifact cleaned up.

## Plan 5 — Unify chartOverride schema (option A) + parity tests  ⟶ DONE + VERIFIED
- [x] Defined the field set ONCE in `src/lib/chart-schema.ts` as a factory
      `buildChartOverrideShape(z, deltaWindowSchema)` — a factory (not a shared
      schema object) so `config.ts` (astro:content `z`) and `composer-state.ts`
      (zod `z`) each build with their OWN `z`, dodging the cross-instance
      nesting footgun. Both now derive `chartOverrideSchema` from it (16 fields).
- [x] **Did NOT bump `COMPOSER_STATE_VERSION`** (deviation from plan, flagged to
      Keller): the change is additive (all new fields optional), so every
      existing v1 link/saved dashboard still validates. A bump would force a
      re-fork of all existing links for no benefit. Added a test pinning v=1.
- [x] `[...slug].astro` fork now passes the full override through instead of
      stripping to title/defaultDelta/blurb.
- [x] **PARITY TESTS (TEMPORARY — cull post-Vercel):** added to
      `composer-state.test.ts` — full 16-field override survives encode→decode
      deep-equal (regression guard for the old lossy fork); old 3-field shape
      still round-trips; version pinned at 1.
- [x] Verify: `vitest composer-state.test.ts` → 13 passed; `astro check` → 0
      errors (content sync executed config.ts schema); full `npm run build` →
      Complete! (preset pages render via effectiveChart unchanged).

## Plan 4 — Collapse the three dashboard renderers
- [ ] Extract shared computation → `src/lib/resolve-dashboard-for-render.ts`
      (`{sections, supportedDeltas, defaultDelta, barSnapshots, viewedSourceIds,
      viewedChartCount, forkUrl}`).
- [ ] Extract shared markup → `<DashboardGrid>` component.
- [ ] Rewrite `[...slug].astro`, `custom.astro`, `index.astro` to use both; only
      input acquisition stays unique.
- [ ] Verify: `npm run build` (catches prerendered `[...slug]`); curl a preset,
      a `/custom/?d=…`, and home featured dashboard on preview; fork URLs
      byte-identical before/after.

## Plan 1 + 2 — Decompose compose.astro + finish source-filters migration
Incremental, each step its own commit + build:
- [x] **2a.** (DONE + LIVE `f193eac42a`) Move `<style is:global>` (9311–11007, ~1,700 lines) → `src/styles/
      compose.css`, import from page. (CSS-only, lowest risk.)
- [x] **2b.** (DONE + LIVE `e9bfb00370`; geo-filter.ts + parity test, compose.astro 11,007 → ~9,100 lines) Extract leaf helpers + the filter swap → `src/lib/composer/
      geo-filter.ts`. Replace compose's inline `passesCdFilter`/`passesMetro
      Filter`/`passesCountryFilter`/`passesCountyFilter` (1745–1957) and the
      unlock memos with `src/lib/source-filters.ts` calls. Reconcile: lib's
      `passesCdFilter` has no `selectedTags` arg (CD_TAG toggle folds into
      `cdState`) → rewrite the Sources-tab empty-state copy (~2871); thread
      `library` into metro/country calls; move per-query memo to call-site
      WeakMap; preserve ds-modal's current skip of `passesCountyFilter` unless
      asked. Benchmark Sources-tab filter on full library before/after.
- [x] **2c.** (DONE + LIVE `f1983d0b68`) Introduce `src/lib/composer/state.ts` — one `ComposerStore` object
      replacing script-scope vars (1630–1679, 6876 ccModal, 8146 dsModal).
      Functions import the store instead of closing over locals.
      **SCOPED 2026-06-06, ready to execute (← NEXT):**
      (1) MOVE type defs → `state.ts` + import back: `ChartOverride`/`UISection`/
      `UIState` (~1267), `GeoState`+`newGeoState` (~1647), `CustomChartMode`/
      `ChartCombineOp` (~6573), `CustomChartModalState` (~6575), `DerivedModalState`
      (~7908). Deps: InlineChart/Map/Source (composer-state), DeltaWindow (deltas).
      (2) WIRE via the ALIAS trick (ref-analysis verified): `state` (394 refs),
      `libGeo` (12), `ccModal` (205), `dsModal` (86) are NEVER reassigned →
      `const state = store.state` etc. = ZERO churn. `library` (122) is reassigned
      once on load (~9079) → keep the local `let library` + set `store.library =
      lib` on load (zero churn). Only the reassigned scalars become `store.x`:
      `sourcesSearchQuery` (7), `sourcesCdState` (7), `sourcesCdDistrict` (6),
      `activeSectionIdx` (28) ≈ 48 ref updates total.
      (3) GUARD: `astro check` (catches every missed/wrong ref) + `vitest`; then
      push → CI build + post-deploy diagnostic + a live-composer walkthrough
      (add source → chart → derived → map → share). No local full build.
- [ ] **2d.** Extract by feature → `src/lib/composer/`: `library-load.ts`,
      `sources-tab.ts`, `cc-modal.ts`, `ds-modal.ts`, `maps.ts`, `generators.ts`,
      `share.ts`. Page `<script>` becomes a thin bootstrap.
- [ ] Verify after EACH step: `npm run build`; manual composer walkthrough
      (add source → build chart → derived source → map → share round-trip) via
      preview browser tools.

## Plan 3 — Adopt SourcePicker.astro in composer
- [ ] **3a.** ds-modal → SourcePicker (direct analog of alerts' A/B builder).
      Add optional `disabledIds` inbound event for cross-side disable.
- [ ] **3b.** cc-modal → SourcePicker (`markedIds` + pick-as-toggle; derived
      sources via `extraSources`/`set-extra-sources`; host keeps `selectedOrder`).
- [ ] **3c.** Reassess Sources tab — may stay bespoke (hint `maps-tab` chip
      coupling + tag-count precompute-vs-live-walk divergence). Decide after
      3a/3b land.
- [ ] Verify: per-modal parity vs current; alerts flow as reference.

## Plan 3a EXECUTION (started 2026-06-08)
- DONE: SourcePicker.astro gained `disabledIds` (optional prop +
  source-picker:set-disabled-ids inbound event + greyed disabled-card render).
  astro 0/0/0. Committed locally, UNUSED until the ds-modal adopts it (push
  it together WITH the ds-modal change).
- NEXT (the ds-modal rewire): only HOW dsModal.a/b get SET changes -- the op /
  quick-divisor / suggestions (rebuild/pxq) / auto-name (syncDerivedHint) /
  create logic all read dsModal.a/b and STAY.
  - compose.astro frontmatter: import SourcePicker from ../components/SourcePicker.astro
  - compose.astro template (~767-840): replace the ds geo-chip strip + ds-source-tags
    + ds-a-search/ds-a-list + ds-b-search/ds-b-list with TWO <SourcePicker
    instanceId=ds-a / ds-b> mounts (mirror alerts.astro @196-234). KEEP the A/B name
    labels (ds-a-current/ds-b-current), quick-divisors, name, op, ds-rebuild/ds-pxq,
    ds-hint, add-as-chart, footer.
  - ds-modal.ts: DELETE renderDsPicker, pickableSourceOptions, sourceTagsFor,
    renderDsModalTagChips. openDerivedSourceModal: drop the geo/tag/picker calls; ADD
    dispatch set-extra-sources (derived sources from state.inlineSources) +
    set-disabled-ids (clear) to both picker roots; reset the A/B labels.
    wireDerivedSourceModal: drop ds-a-search/ds-b-search wiring; replace the ~5
    renderDsPicker("a");renderDsPicker("b") sites with an updateDsOperandUI() helper
    (sets A/B name labels + dispatches cross-side set-disabled-ids) + syncDerivedHint();
    ADD source-picker:pick listeners on the ds-a/ds-b roots (set dsModal.a/b ->
    updateDsOperandUI + syncDerivedHint). ctx: DROP passesCdFilter/Metro/Country,
    renderMetroChip/Cd/Country, wireGeoChips, renderModalTagChips; KEEP shell/store/
    state/getLibrary/checkComposeAction/showSigninPrompt/clampActiveSection/writeUrl/
    renderComposition/renderCustomChartSources. return: drop renderDsPicker +
    renderDsModalTagChips (export openDerivedSourceModal + wireDerivedSourceModal only).
  - compose.astro: remove the geoSurfaceConfig "ds" branch + update the ds factory
    ctx/destructure. Confirm the geo-chips / modal-tags "ds" usages are fully gone.
  - Derived operands: pass state.inlineSources as SourcePicker extraSources
    (id/name/tags) so derived sources are pickable + recursive derivation works.
  - VERIFY (walkthrough): search "United States GDP" in an operand now resolves
    (THE bug); A/B pick via SourcePicker; cross-disable; derived operand;
    quick-divisor + rebuild/pxq still set B/A; create. Then 3b (cc-modal).


### 3a RESULT (2026-06-08) -- DONE + PROD-VERIFIED (e26274ab7a + focus fix)
- Shipped: SourcePicker.disabledIds (babd0c3c22) + ds-modal adoption (e26274ab7a,
  +141/-304). astro 0/0/0, vitest 720. CI + post-deploy smoke/diagnostic green.
- PROD WALKTHROUGH (Chrome MCP, /compose; ZERO app console errors -- only Zotero
  extension noise):
  - Both ds-a/ds-b SourcePickers render (752 cards each + own geo + tag chips +
    search). Old ds-a-list/ds-b-list + the ds geo/tag strips are gone.
  - Search is token-AND on searchText now: "us gdp"->1, "real gdp"->16, "us real
    gdp"->3 (the old list searched the display LABEL only -> these failed before).
  - Pick A -> "Picked: US real GDP" label; that source then renders DISABLED +
    non-pickable in B (disabledIds cross-disable). Pick B -> reverse disable +
    Create enables. Op change -> auto-name hint updates. Quick-divisor (US
    population) -> op=divide + B set + active chip + hint. Create -> modal closes,
    auto-chart created, TILE RENDERS (2 svgs). Reopen -> clean reset.
  - derived-operand wiring verified: dispatching set-extra-sources renders
    .source-picker-card-extra cards that are pickable (sets the operand).
- TWO NOTES (neither a regression introduced by 3a):
  1. "United States GDP" -> 0 results. Pre-existing GLOBAL data-vocabulary gap:
     US-specific FRED sources carry "US"/"U.S." in searchText, not "united
     states", so this query fails in EVERY picker (Sources tab, cc-modal, alerts
     too). Fix = add "united states" synonyms to those sources searchText in the
     data pipeline -- separate task, app-wide, out of 3a scope.
  2. focusPickerSearch had a wrong selector ([data-spicker-search] vs the real
     [data-spicker-role=search]) -> the post-quick-divisor auto-focus silently
     no-opped. FIXED (one line); pushed as a follow-up.
- Created derived sources are pruned from the ?d= URL when only "add as chart" is
  used (the auto-chart cites the two PARENT ids [a,b] + op, not the derived id, so
  the derived source is unreferenced). Pre-existing create/state behavior,
  UNCHANGED by 3a; the extras wiring is correct regardless.

### 3b (cc-modal -> SourcePicker) SCOUTED -- MATERIALLY HEAVIER than 3a:
- cc-modal is MULTI-select with ORDER (ccModal.selected Set + selectedOrder) and
  renders PER-SOURCE inline L|R axis pills (dual-axis mode) INSIDE each source row
  -- a control SourcePicker cards cannot host. cc-modal.ts renderCustomChartSources
  (~770) builds checkbox rows + axis pills + drives mode/op/preview on every
  toggle. A faithful 3b therefore needs SourcePicker for BROWSING (pick -> toggle
  selected + set-marked-ids for the check) PLUS a SEPARATE "selected sources"
  panel hosting the order/axis/remove controls. That is a 2-component redesign,
  not a swap. DECIDE WITH KELLER before executing (full redesign vs partial
  browse-only adoption vs leave cc-modal bespoke given the axis-pill coupling).


### 3b EXECUTION PLAN (cc-modal -> SourcePicker) -- turn-key, scouted 2026-06-08
Safety: tree clean at d1fb160e7c first (git checkout = undo). Only push when
astro 0/0/0 + vitest 720. MONOLITHIC: HTML + cc-modal.ts + compose land together.

HTML (compose.astro, the Sources cc-field ~@836-872):
- KEEP the header (Sources eyebrow + cc-count "0 selected").
- REMOVE cc-source-search, cc-geo-chips (metro/cd/country), cc-source-tags,
  cc-source-list.
- ADD in order: <div class="cc-selected-list" data-role="cc-selected-list"></div>
  then <SourcePicker instanceId="cc" rootClass="cc-source-picker"
  searchPlaceholder="Search sources by name, ticker, or tag..." />.

cc-modal.ts:
- ctx: DROP passesCdFilter/Metro/Country/County, renderModalTagChips,
  renderMetroChip/Cd/Country, wireGeoChips. KEEP all else.
- DELETE filteredModalSources (~@687-757) + renderCcModalTagChips (~@352-375).
- renderCustomChartSources (~@770-877) -> REWRITE as renderSelectedSources():
  render ccModal.selectedOrder into [data-role=cc-selected-list]; each row = name
  (ccSourceLookup) + (dual-axis mode) the L|R axis pills (EXACT @840-873 logic) +
  a remove (x) button -> ccPickToggle(id). Empty -> "No sources selected yet."
- ADD ccPickToggle(id): the @787-830 checkbox-change body parameterized by id
  (add if !selected else remove; keep selectedOrder; mode/op/rightAxis cascade;
  syncModeRadioFromState/syncLogUI/syncOpUI; updateCustomChartCreateState;
  renderSelectedSources; renderCustomChartPreview; updateCcAnnotationsWarning;
  maybeRefreshCcAutoTitle; update cc-count; then ccSyncMarked()).
- ADD ccDispatch(type,detail) ([data-spicker-instance=cc].dispatchEvent),
  ccSyncMarked() (set-marked-ids {ids:[...ccModal.selected]}), ccExtraSources()
  (derived from state.inlineSources -> {id,name:name+" (derived)",tags}).
- openCustomChartModal (~@196-350): REMOVE the browse render + renderMetroChip
  ("cc")/Cd/Country + wireGeoChips("cc") + renderCcModalTagChips. ADD ccDispatch
  set-extra-sources(ccExtraSources()) + ccSyncMarked() + renderSelectedSources().
  KEEP title/mode/op + the editing-existing-chart path (sets ccModal.selected
  from the chart -> ccSyncMarked reflects the check marks).
- wireCustomChartModal (~@1253+): REMOVE cc-source-search + geo + tag wiring. ADD
  a source-picker:pick listener on [data-spicker-instance=cc] -> ccPickToggle
  (detail.sourceId). KEEP mode/op/log/blurb/percent/create wiring.
- return: drop renderCustomChartSources + renderCcModalTagChips (picker internal).

compose.astro:
- import SourcePicker already present (3a). Mount the cc SourcePicker (HTML above).
- geoSurfaceConfig: REMOVE the "cc" fallback -> "lib" is the ONLY surface now (ds
  + cc both retired). Return the lib config; createGeoChips serves only the
  Sources tab.
- cc factory ctx/destructure: drop passesCdFilter/Metro/Country/County,
  renderModalTagChips, renderMetroChip/Cd/Country, wireGeoChips + the
  renderCustomChartSources/renderCcModalTagChips exports.
- CROSS-DEP: ds-modal.ts ctx has renderCustomChartSources (post-derived-create
  refresh of an open cc picker). After 3b that fn is gone -> drop it from the ds
  ctx + its post-create call (the cc-modal re-dispatches extras on its next open;
  the two modals are never open at once).

compose.css: .cc-selected-list (rows + remove x), .cc-source-picker
.source-picker-results { max-height ~40vh } (shares the modal w/ selected + preview).

VERIFY (prod walkthrough): open cc-modal -> SourcePicker browse (search/geo/tag);
pick 2+ -> each enters cc-selected-list + gets a check in the picker + cc-count
updates + live preview renders; remove from the panel -> check clears + preview
updates; dual-axis -> L|R pills in the panel -> preview splits axes; raw/rebase
auto-mode; op (2 same-class) + percent-display; log; derived source as an extra
(create one first); EDIT an existing custom chart (selection + marks restored);
Create -> tile. Zero app console errors.


### 3b RESULT (2026-06-08) -- DONE + PROD-VERIFIED (b7439768e9 + modal-tags cleanup)
- Shipped: cc-modal adoption (b7439768e9, +202/-336). astro 0/0/0, vitest 720.
  CI + post-deploy smoke green. Then modal-tags.ts DELETED (orphaned -- no modal
  uses the bespoke tag strip after 3a+3b; astro 0/0/0, now 144 files).
- PROD WALKTHROUGH (Chrome MCP, /compose; ZERO app console errors -- Zotero only):
  - cc-modal opens: <SourcePicker instanceId=cc> browse (752 cards + own search +
    geo chips) + the new cc-selected-list panel (empty) + "0 selected" + preview
    prompt. Old cc-source-search/cc-geo-chips/cc-source-tags/cc-source-list gone.
  - Multi-select: pick -> selected-panel row (correct label) + a check in the
    picker (set-marked-ids) + count + auto-mode (rebase for mixed scales) + live
    preview (1 svg). 2nd pick -> 2 rows + 2 checks + "2 selected".
  - Dual-axis: L|R pills render in the selected rows w/ the correct default split;
    preview -> "2 series dual-axis".
  - Remove via the panel x: drops the source + clears its check + decrements count
    + the mode cascade flips dual->raw when under 2 sources.
  - Create: 2-source chart created (both sources, raw) + modal closes + TILE
    renders (2 svgs).
  - Edit existing chart (pencil): "Edit chart" + "Save changes" + title +
    selection restored in the panel; marks correct in state (only filtered from
    the BROWSE view by a stale persistent search -- clearing it shows both checks).
- NOTE (minor, shared with ds-modal): SourcePicker keeps its search across modal
  opens, so an edit can open with a stale browse filter. The always-visible
  selected panel mitigates. A SourcePicker "reset search on open" event would
  polish both modals -- out of 3b scope.
- Plan 3 SourcePicker adoption is COMPLETE for both modals. Remaining: 3c
  (reassess the Sources tab -- the last bespoke source browser; likely a clean
  target: single-click add, no axis pills -- OR already fine as-is).


### 3c PLAN (Sources tab -> SourcePicker) -- foundation DONE; adoption banked
DECISION (Keller): enrich SourcePicker, then adopt (no regression to the rich
browser). KEY FINDING: the Sources tab cards are RICHER than the modal pickers --
CD/state geo badges ("TX-12" / "TX statewide"), tags line, shortName. The geo
badge is ESSENTIAL: ~435 congressional-district sources share the same name, only
the badge distinguishes them. SourcePicker already had parseCdSourceId +
formatCdShortLabel + hint-card handling + the same empty-state copy.

DONE (0251af492b): SourcePicker gained an opt-in `richCards` prop -> geo badges +
tags line + shortName (richCardExtras). Default off; the ds/cc pickers keep the
simple card. astro 0/0/0. Unused until the Sources tab adopts it.

NEXT (the adoption -- a fresh focused pass; big + retires shared code):
- PRE-SCOUT: read the Sources-tab HTML in compose (lib-tab switcher + the Sources
  sub-tab: lib-sources-search / lib-geo-chips / lib-source-tags / lib-results-
  sources + the Charts sub-tab); sources-tab.ts ctx + filteredSources +
  engageHintChip + setActiveLibTab; and GREP geo-filter.ts consumers (the Maps
  tab / map-builder may use passesCountyFilter -> do NOT delete geo-filter.ts if so).
- HTML: replace the Sources sub-tab [search + lib-geo-chips + lib-source-tags +
  lib-results-sources] with <SourcePicker instanceId="lib" richCards
  rootClass="lib-source-picker" />. KEEP the lib-tab switcher + the Charts sub-tab.
- sources-tab.ts: DELETE filteredSources, renderSourcesList, renderTagFiltersSources,
  engageHintChip, allSourceTags. KEEP the Charts sub-tab (filteredCharts,
  renderChartsList, renderTagFiltersCharts, allChartTags, setActiveLibTab). ctx:
  drop the geo/tag/passes* fields. Wire the lib SourcePicker source-picker:pick ->
  addSourceAsChart(detail.sourceId). VERIFY SourcePicker hint-card handling covers
  the Sources-tab hints (geo-chip engage + the "maps-tab" tab-switch hints).
- compose: mount the lib SourcePicker; RETIRE geoSurfaceConfig (now empty -> delete)
  + createGeoChips destructure + the renderMetroChip/Cd/Country/wireGeoChips("lib")
  calls + appendCdDrillDown + the lib-geo-chips HTML.
- RETIREMENT CASCADE (astro flags unused): DELETE geo-chips.ts (no surfaces left).
  geo-filter.ts (createComposerGeoFilters): DELETE only if truly orphaned -- the
  modals use source-filters.ts not this, but CHECK the Maps tab/map-builder first.
  Remove now-unused compose geo imports (CD_TAG/METRO_TAG/COUNTRY_TAG/parse*/GeoSurface).
- VERIFY: astro 0/0/0 + vitest 720; prod walkthrough -- Sources tab rich cards
  (GEO BADGES render so districts are distinguishable!) + click->addSourceAsChart
  ->tile + CD gate + hints; Charts sub-tab; confirm the ds/cc modals still pick
  (unaffected by the geo retirement). Zero app console errors.
RISKS: geo-filter.ts may back the Maps tab (county choropleth) -- verify before
deleting; the maps-tab hint switch; any Charts-sub-tab shared helper.


## Deferred TODOs (product)
- **Composite / derived-source alerts** REMOVED 2026-06-08 to prioritize
  single-source reliability + because the feature needed migration 0007 (the
  derived_spec column), which was never applied to prod (root cause of composite
  rule saves 400ing). Keller wants it back PROPERLY later. Re-add = apply
  supabase/migrations/0007_alert_derived_spec.sql + re-add the A/B builder UI
  (ideally matching the ds-modal 2-picker + cross-disable) + the derived_spec
  save path. The rule type field, the "derived:adhoc" guards, and the
  check_alerts.py evaluator all remain. See the REMOVED-marker comment in
  src/pages/alerts.astro.


## Plan 3 (note) — depends on Plan 1's state store existing first.

## Plan 7 — Standardize source-YAML on the inline pattern
- [ ] Document the convention in `docs/new-data-source-checklist.md` (new
      providers write YAML inline at ingest; `_generate_*`/`_scaffold_*` legacy).
- [ ] Fold simple `_scaffold_*` emitters into their pipelines, ONE provider at a
      time (eia_state_energy, naep, edu_spending, census_govfin, acs_labor). Leave
      derived ACS-CD/national generators if risky.
- [ ] After each provider goes inline, drop it from the refresh workflows'
      hardcoded YAML-dir list (the `acs_cd acs_state … worldbank_extended` lists
      in both `refresh-*.yml` commit steps). ⚠️ This is the June-2026 data-loss
      area — one provider at a time, `git diff --stat` before commit.
- [ ] Verify per provider: run pipeline locally, YAML+data both land, idempotent
      on re-run, `audit_all_sources.py --strict` passes.

---

## Progress log
- 2026-06-03: checklist created; all 8 approved; starting Plan 8.
- 2026-06-03: Plan 8 code edits complete on branch `refactor/structural-cleanup`.
  BLOCKER discovered: this laptop had no working dev toolchain.
- 2026-06-03: Toolchain set up on the laptop (Node 22.22.3 + Python 3.13.13 +
  npm install + NODE_OPTIONS heap fix — see "Laptop dev environment" above).
  Plan 8 now BUILD-VERIFIED (`npm run build` → Complete!, methodology test 3/3).
  Starting Plan 6 (cache consolidation).
- 2026-06-03: Plan 6 DONE + VERIFIED — `cached_get` re-backed on `_cache.py`;
  single `pipelines/_cache/` store; `_response_cache/` retired. Full pipeline
  pytest 192 passed. Next: Plan 5.
- 2026-06-03: Plan 5 DONE + VERIFIED — shared `chart-schema.ts` factory; both
  schemas unified (16 fields); fork no longer lossy; NO version bump (additive);
  temporary parity tests added (13 passed); `npm run build` → Complete!.
  Next: Plan 4.
- 2026-06-03: Side task DONE — va-08 dangling bg-map refs fixed on branch
  `fix/va08-bg-map-refs` (off main, commit 38069b7d26). Root cause: Census
  suppresses poverty + place-of-birth at block-group level, so 2 of the 4 BG
  charts can't exist; removed the dangling refs + corrected dashboard copy.
  Verified: audit 0 warnings, build Complete!, warnings gone. Branch is
  local-only, separate from the refactor branch.
- 2026-06-04: NOTE — abandoned the local feature-branch approach; per Keller,
  shipping each verified plan straight to `main` (= prod). Plans 8/6/5 + va-08
  were merged to main + pushed earlier (CI green, curl-verified).
- 2026-06-04: Plan 4 DONE + VERIFIED + LIVE — `resolveDashboardForRender` lib
  fn + `<DashboardGrid>` component; [...slug]/custom/index all migrated (3
  increments). index now renders bar/map on featured dashboards (was
  using <Chart> directly). Pushed to main (3461eeb6ea); CI + post-deploy smoke
  + diagnostic all green; curled /, /us-macro/, /custom/ — DashboardGrid
  renders on SSR home + prerendered presets. Next: Plan 1+2 (compose.astro).
  NOTE for next session: the laptop build needs NODE_OPTIONS=--max-old-space
  -size=4096 (set as user env var); builds ~14 min; sleep-guard auto-keeps the
  machine awake while plugged in (see C:\Users\kelle\.tape-tools\SLEEPGUARD.md).
