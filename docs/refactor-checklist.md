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
4. [ ] **Plan 4 — dashboard renderer dedup** ← NEXT
5. [ ] **Plan 1 + 2 — compose.astro decompose + source-filters migration**
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
  Next: Plan 4. (Side task: va-08 dangling bg-map refs — fixing on its own
  branch off main next.)
