# Tape — structural-refactor checklist

> Approved 2026-06-03. Eight structural improvements from a from-scratch
> review. This file is the durable source of truth across sessions — update
> the checkboxes as work lands. Companion: `docs/data-flow.md` (pipeline map).
>
> **Global gate for every change:** full `npm run build` locally before any
> push (astro check + vitest + pytest do NOT exercise library.json prerender
> invariants or SSR pages); `node scripts/audit-source-data.mjs`; for
> SSR-touching changes curl the affected pages on the deploy preview.
> **Explicit OK from Keller before every push to `main` (= prod).**

## Execution order

1. [ ] **Plan 8 — exposure scrub** (launch blocker, low risk)
2. [ ] **Plan 6 — cache consolidation** (pipelines, isolated)
3. [ ] **Plan 5 — chartOverride schema unification** (option A + parity tests)
4. [ ] **Plan 4 — dashboard renderer dedup**
5. [ ] **Plan 1 + 2 — compose.astro decompose + source-filters migration**
6. [ ] **Plan 3 — adopt SourcePicker.astro in composer**
7. [ ] **Plan 7 — inline-YAML standardization** (lowest urgency, splittable)

---

## Plan 8 — Remove public GitHub / internal-detail exposure  ⟶ EDITS DONE, BUILD-VERIFY PENDING
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
- [ ] **BLOCKED:** `npm run build` + curl `/source/fec/...` on preview —
      requires a working Node toolchain (absent on this laptop; see log).

## Plan 6 — Consolidate the two on-disk caches
- [ ] Make `pipelines/_cache.py` the single storage layer (readable bucket/key).
- [ ] Reimplement `common.cached_get` on top of it (same signature; bucket =
      caller, key = url+params, seconds→days). No ingest-pipeline changes.
- [ ] Migrate `_response_cache/` users transparently; delete old dir; tidy
      `.gitignore`.
- [ ] Verify: `pytest pipelines/test_common.py pipelines/test_cache.py`; run
      `cdc_health.py` twice → second run is a cache hit.

## Plan 5 — Unify chartOverride schema (option A) + parity tests
- [ ] Define the chart-field set once (in `src/content/config.ts` or a shared
      `src/lib/chart-schema.ts`); have `composer-state.ts` reuse it (Zod `.pick()`
      of the URL-safe subset) instead of its 4-field copy.
- [ ] Bump `COMPOSER_STATE_VERSION` 1→2; existing `wrong-version` decode banner
      handles old links.
- [ ] **BEFORE/AFTER PARITY TESTS (Keller's requirement):** snapshot what a
      forked preset-with-rich-overrides renders today, assert the post-change
      render is identical. Cover shading/transform/annotations/percentDisplay
      surviving the fork round-trip. *These tests are temporary — cull once live
      on Vercel and verified.*
- [ ] Verify: `composer-state` encode/decode round-trip tests; fork a rich
      preset, confirm fields survive; `npm run build`.

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
- [ ] **2a.** Move `<style is:global>` (9311–11007, ~1,700 lines) → `src/styles/
      compose.css`, import from page. (CSS-only, lowest risk.)
- [ ] **2b.** Extract leaf helpers + the filter swap → `src/lib/composer/
      geo-filter.ts`. Replace compose's inline `passesCdFilter`/`passesMetro
      Filter`/`passesCountryFilter`/`passesCountyFilter` (1745–1957) and the
      unlock memos with `src/lib/source-filters.ts` calls. Reconcile: lib's
      `passesCdFilter` has no `selectedTags` arg (CD_TAG toggle folds into
      `cdState`) → rewrite the Sources-tab empty-state copy (~2871); thread
      `library` into metro/country calls; move per-query memo to call-site
      WeakMap; preserve ds-modal's current skip of `passesCountyFilter` unless
      asked. Benchmark Sources-tab filter on full library before/after.
- [ ] **2c.** Introduce `src/lib/composer/state.ts` — one `ComposerStore` object
      replacing script-scope vars (1630–1679, 6876 ccModal, 8146 dsModal).
      Functions import the store instead of closing over locals.
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
  BLOCKER discovered: this laptop has no working dev toolchain — Node not
  installed, `node_modules` absent (`npm install` never run here), `python` is
  the Microsoft Store stub only. Cannot run `npm run build` / astro check /
  vitest / pytest, so NOTHING is build-verified and nothing can be pushed under
  the project's validation rule. Awaiting Keller's call on environment setup.
