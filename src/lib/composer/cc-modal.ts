/**
 * Custom-chart modal + live preview (Plan 2d) -- the "+ Custom chart" builder.
 *
 * Owns the modal that combines several sources onto one chart: the source
 * picker (filteredModalSources / renderCustomChartSources), the A/B operand +
 * op controls, the mode toggles (raw / rebase / dual-axis / log), background
 * shading, annotations, the merge flow (openMergeModal, drag-two-tiles), and
 * the live Plot preview (renderCustomChartPreview). renderCustomChartSources is
 * also consumed by ds-modal (after a derived-source create) + by geoSurfaceConfig
 * for the "cc" surface -- so it is EXPORTED and compose passes it into ds-modal.
 *
 * Extracted from compose.astro via the create<Feature>(ctx) factory. The shared
 * tag-chip strip (renderModalTagChips, modal-tags), the source-series fetcher
 * (fetchSourceSeries, series.ts), the geo filter predicates (passes*, geo-filter)
 * and per-surface geo-chip renderers (render*Chip / wireGeoChips for "cc", which
 * stay in compose with geoSurfaceConfig) all come in via ctx. The cc-only
 * helpers that live elsewhere in compose (chartEffectiveSpec, baseTitleIsDefault,
 * updateCcAnnotationsWarning, dismissHoverMergeTip, isHoverMergeTipDismissed)
 * arrive via ctx too. library is read via getLibrary() per fn (narrowing kept).
 */
import { nanoid } from "nanoid";
import { track } from "../track";
import * as Plot from "@observablehq/plot";
import { packSourceIds } from "../analytics-helpers";
import { parseAnnotationLines, formatAnnotationLines, type Annotation } from "../annotations";
import {
  CD_TAG,
  STATEWIDE_DISTRICT_CODE,
  parseCdSourceId,
  parseStateSourceId,
} from "../congressional-districts";
import { COUNTRY_TAG } from "../countries";
import { METRO_TAG } from "../geographic-regions";
import { deriveAutoTitle, isTitleAuto } from "../chart-title";
import { bandsFor, SHADING_FILL_OPACITY, type ShadingKey } from "../shading-presets";
import { INLINE_PREFIX, isInlineId, isDerivedId } from "./ids";
import { newGeoState } from "./state";
import { CC_COLORS, type FetchedSeries } from "./series";
import type { DeltaWindow } from "../deltas";
import type {
  UIState,
  ComposerStore,
  CustomChartMode,
  ChartCombineOp,
} from "./state";
import type { LibraryPayload, LibrarySource } from "./library";
import type { ComposerGeoFilters } from "./geo-filter";
import type { InlineChart } from "../composer-state";

type GeoSurface = "lib" | "cc" | "ds";

export interface CustomChartModalContext {
  shell: HTMLElement;
  store: ComposerStore;
  state: UIState;
  getLibrary: () => LibraryPayload | null;
  fetchSourceSeries: (sourceId: string) => Promise<FetchedSeries | null>;
  escapeHtml: (s: string) => string;
  renderComposition: () => void;
  writeUrl: () => void;
  clampActiveSection: () => void;
  passesCdFilter: ComposerGeoFilters["passesCdFilter"];
  passesMetroFilter: ComposerGeoFilters["passesMetroFilter"];
  passesCountryFilter: ComposerGeoFilters["passesCountryFilter"];
  passesCountyFilter: ComposerGeoFilters["passesCountyFilter"];
  renderModalTagChips: (
    hostSelector: string,
    selected: Set<string>,
    onToggle: () => void,
    cdGetters: {
      getState: () => string | null;
      setState: (v: string | null) => void;
      getDistrict: () => string | null;
      setDistrict: (v: string | null) => void;
    },
  ) => void;
  renderMetroChip: (surface: GeoSurface) => void;
  renderCdChip: (surface: GeoSurface) => void;
  renderCountryChip: (surface: GeoSurface) => void;
  wireGeoChips: (surface: GeoSurface) => void;
  chartEffectiveSpec: (chartId: string) => {
    title: string;
    blurb?: string;
    defaultDelta?: DeltaWindow;
    sources: string[];
  };
  baseTitleIsDefault: (chartId: string) => boolean;
  updateCcAnnotationsWarning: () => void;
  dismissHoverMergeTip: () => void;
  isHoverMergeTipDismissed: () => boolean;
}

export function createCustomChartModal(ctx: CustomChartModalContext) {
  const {
    shell,
    store,
    state,
    getLibrary,
    fetchSourceSeries,
    escapeHtml,
    renderComposition,
    writeUrl,
    clampActiveSection,
    passesCdFilter,
    passesMetroFilter,
    passesCountryFilter,
    passesCountyFilter,
    renderModalTagChips,
    renderMetroChip,
    renderCdChip,
    renderCountryChip,
    wireGeoChips,
    chartEffectiveSpec,
    baseTitleIsDefault,
    updateCcAnnotationsWarning,
    dismissHoverMergeTip,
    isHoverMergeTipDismissed,
  } = ctx;
  const ccModal = store.ccModal;
  // True when every selected source shares the same formatting style + unit
  // (e.g. all percent / all USD-per-barrel) — they can be plotted on one axis
  // legibly without rebasing.
  function ccSelectedSharesScale(): boolean {
    const library = getLibrary();
    if (!library) return false;
    const ids = [...ccModal.selected];
    if (ids.length < 2) return true;
    const first = library.sources[ids[0]] as
      | { formatting?: { style?: string }; unit?: string }
      | undefined;
    if (!first) return false;
    return ids.every((id) => {
      const s = library!.sources[id] as
        | { formatting?: { style?: string }; unit?: string }
        | undefined;
      return (
        !!s &&
        s.formatting?.style === first.formatting?.style &&
        s.unit === first.unit
      );
    });
  }

  function ccDefaultMode(): CustomChartMode {
    const n = ccModal.selected.size;
    if (n <= 1) return "raw";
    return ccSelectedSharesScale() ? "raw" : "rebase";
  }

  // Bridge from the composer's library.json source map to the
  // chart-title module's SourceLookup signature. Used by every
  // title-derivation call below.
  function ccSourceLookup(sid: string) {
    const library = getLibrary();
    if (!library) return undefined;
    return library.sources[sid] as
      | { name?: string; shortName?: string }
      | undefined;
  }

  // Decide whether the current ccModal.title is still tracking the
  // auto-derived default. Used by both the modal opener and the
  // hover-merge customizer so they share one truth-source for "is
  // this title user-customized?". Pure logic lives in
  // chart-title.isTitleAuto; this wrapper just plugs the lookup in.
  function recomputeCcTitleAuto(): void {
    ccModal.titleAuto = isTitleAuto(
      ccModal.title,
      ccModal.selectedOrder,
      ccModal.op,
      ccSourceLookup,
    );
  }

  // If the title is still tracking the auto-derived default (no user
  // override yet), recompute it from the current sources/op and push
  // the new value into ccModal.title + the visible input. Called from
  // every source/op change handler. No-op when the user has typed a
  // custom title — we never overwrite intentional input.
  function maybeRefreshCcAutoTitle(): void {
    if (!ccModal.titleAuto) return;
    const next = deriveAutoTitle(
      ccModal.selectedOrder,
      ccModal.op,
      ccSourceLookup,
    );
    ccModal.title = next;
    const titleInput = shell.querySelector<HTMLInputElement>(
      "[data-role='cc-title']",
    );
    if (titleInput && titleInput.value !== next) {
      titleInput.value = next;
    }
  }

  function openCustomChartModal(editingId?: string): void {
    const library = getLibrary();
    const existing =
      editingId && state.inlineCharts[editingId]
        ? state.inlineCharts[editingId]
        : null;
    ccModal.editingId = existing ? (editingId as string) : null;
    ccModal.title = existing?.title ?? "";
    ccModal.selected = new Set<string>(existing?.sources ?? []);
    ccModal.selectedOrder = [...(existing?.sources ?? [])];
    ccModal.op = (existing?.op as ChartCombineOp | undefined) ?? null;
    // Auto-title tracking: we'll auto-update the title field on
    // source/op changes IFF the user hasn't typed a custom title yet.
    // Decide which bucket the loaded title falls into:
    //   - empty: fresh new chart, definitely auto.
    //   - matches what we'd derive right now: title was previously
    //     auto-derived and never customized; keep tracking.
    //   - anything else: user customized it (or it came from a
    //     curated chart with a hand-written title); stop tracking
    //     so we don't clobber it on the next source-swap.
    recomputeCcTitleAuto();
    ccModal.search = "";
    if (existing?.normalize) {
      ccModal.mode = existing.normalize as CustomChartMode;
      ccModal.modeIsExplicit = true;
    } else {
      ccModal.modeIsExplicit = false;
      ccModal.mode = ccDefaultMode();
    }
    ccModal.rightAxisSources = new Set<string>(
      existing?.rightAxisSources ?? [],
    );
    // Restore the log-scale flag from the saved spec; falls back to false
    // (linear) which is the safe default for any value distribution.
    ccModal.logScale =
      (existing as { scale?: string } | null)?.scale === "log";
    ccModal.blurb = existing?.blurb ?? "";
    ccModal.percentDisplay = (existing as { percentDisplay?: "percent" | "decimal" | "ratio" } | null)
      ?.percentDisplay;
    // Carry existing transform over (level / yoy_pct / index_100).
    const existingTransform = (existing as { transform?: "level" | "yoy_pct" | "index_100" } | null)
      ?.transform;
    ccModal.transform = existingTransform ?? "level";
    // Carry existing annotations over as textarea body. Empty when
    // editing a new chart; serialized via formatAnnotationLines on
    // load so the textarea reads in the same shape the user will
    // re-edit it in.
    const existingAnnotations = (existing as { annotations?: Annotation[] } | null)
      ?.annotations;
    ccModal.annotationsText = Array.isArray(existingAnnotations)
      ? formatAnnotationLines(existingAnnotations)
      : "";
    // Carry existing shading layers over so editing a chart keeps its
    // bands. New charts start with an empty list (no shading).
    const existingShading = (existing as { shading?: string[] } | null)?.shading;
    ccModal.shading = Array.isArray(existingShading) ? [...existingShading] : [];
    // Fresh tag-chip filter each time the modal opens. The user's prior
    // selection on a previous chart's compose session isn't relevant.
    ccModal.pickerTags = new Set<string>();
    ccModal.cdState = null;
    ccModal.cdDistrict = null;
    // Fresh geo state per open; pre-select for an editing chart that
    // already references a metro / country source, same logic as CD below.
    ccModal.geo = newGeoState();
    for (const sid of ccModal.selected) {
      const tags = (library?.sources[sid] as { tags?: string[] } | undefined)?.tags ?? [];
      for (const t of tags) {
        if (t.startsWith(`${METRO_TAG}:`) && !ccModal.geo.selectedMetroCbsa) {
          ccModal.geo.selectedMetroCbsa = t.slice(METRO_TAG.length + 1);
        }
        if (t.startsWith(`${COUNTRY_TAG}:`) && !ccModal.geo.selectedCountryCode) {
          ccModal.geo.selectedCountryCode = t.slice(COUNTRY_TAG.length + 1);
        }
      }
    }
    // Always reset pendingMerge here — only openMergeModal sets it, and
    // we don't want a previous merge that was cancelled to leak into
    // the next normal open.
    ccModal.pendingMerge = null;
    // If the chart being edited already references geo sources (CDs or
    // state-level), auto-engage the States & districts chip + pin the
    // state filter. Otherwise the user would open the modal and not see
    // their own already-selected geo sources in the picker list — they'd
    // be filtered out by the default-hide rule and there'd be no obvious
    // way to uncheck them. If multiple states are represented, we pick
    // the first encountered; the user can flip states from the dropdown.
    let firstGeoState: string | null = null;
    let firstGeoIsStateLevel = false;
    for (const sid of ccModal.selected) {
      const cd = parseCdSourceId(sid);
      if (cd) {
        firstGeoState = cd.state;
        break;
      }
      const st = parseStateSourceId(sid);
      if (st) {
        firstGeoState = st.state;
        firstGeoIsStateLevel = true;
        break;
      }
    }
    if (firstGeoState) {
      ccModal.pickerTags.add(CD_TAG);
      ccModal.cdState = firstGeoState;
      // If all the user's geo picks are state-level, pre-narrow the
      // district dropdown to "Statewide" so the picked sources are
      // immediately visible in the list rather than buried under CDs.
      let allStateLevel = true;
      for (const sid of ccModal.selected) {
        if (parseCdSourceId(sid)) {
          allStateLevel = false;
          break;
        }
      }
      if (firstGeoIsStateLevel && allStateLevel) {
        ccModal.cdDistrict = STATEWIDE_DISTRICT_CODE;
      }
    }

    const backdrop = shell.querySelector<HTMLElement>("[data-role='cc-modal']");
    if (!backdrop) return;
    backdrop.hidden = false;
    const heading = shell.querySelector<HTMLElement>("#cc-modal-title");
    if (heading) heading.textContent = existing ? "Edit chart" : "New custom chart";
    const createBtn = shell.querySelector<HTMLButtonElement>("[data-role='cc-create']");
    if (createBtn) createBtn.textContent = existing ? "Save changes" : "Create chart";
    const titleInput = shell.querySelector<HTMLInputElement>("[data-role='cc-title']");
    if (titleInput) {
      titleInput.value = ccModal.title;
      titleInput.focus();
    }
    const searchInput = shell.querySelector<HTMLInputElement>("[data-role='cc-source-search']");
    if (searchInput) searchInput.value = "";
    const blurbInput = shell.querySelector<HTMLTextAreaElement>(
      "[data-role='cc-blurb']",
    );
    if (blurbInput) blurbInput.value = ccModal.blurb;
    syncModeRadioFromState();
    syncLogUI();
    syncOpUI();
    syncShadingUI();
    syncTransformUI();
    syncAnnotationsUI();
    renderCcModalTagChips();
    // Geo-chip strip: render all three chips reflecting modal state,
    // wire event handlers idempotently (wireGeoChips guards via
    // dataset.wired).
    renderMetroChip("cc");
    renderCdChip("cc");
    renderCountryChip("cc");
    wireGeoChips("cc");
    renderCustomChartSources();
    updateCustomChartCreateState();
    renderCustomChartPreview();
  }

  function renderCcModalTagChips(): void {
    renderModalTagChips(
      "[data-role='cc-source-tags']",
      ccModal.pickerTags,
      () => {
        renderCcModalTagChips();
        renderCustomChartSources();
      },
      {
        getState: () => ccModal.cdState,
        setState: (v) => {
          ccModal.cdState = v;
        },
        getDistrict: () => ccModal.cdDistrict,
        setDistrict: (v) => {
          ccModal.cdDistrict = v;
        },
      },
    );
  }

  // Reflect ccModal.logScale + mode onto the log-scale checkbox: log is
  // exclusive with dual-axis, so the checkbox is forced unchecked + disabled
  // whenever dual-axis is the active mode.
  function syncLogUI(): void {
    const cb = shell.querySelector<HTMLInputElement>("[data-role='cc-log']");
    const wrap = shell.querySelector<HTMLElement>("[data-role='cc-log-wrap']");
    if (!cb || !wrap) return;
    const isDual = ccModal.mode === "dual-axis";
    if (isDual && ccModal.logScale) {
      // Mode-change made log invalid; clear the state flag so it doesn't
      // re-engage if the user flips back to raw/rebase.
      ccModal.logScale = false;
    }
    cb.disabled = isDual;
    cb.checked = ccModal.logScale && !isDual;
    wrap.classList.toggle("cc-log-opt-disabled", isDual);
  }

  // Reflect ccModal.op + selected count onto the operation UI: enable
  // when 2 sources picked, fill in the dropdown value, render the A/B
  // hint, toggle Swap visibility.
  function syncPercentDisplayUI(): void {
    const wrap = shell.querySelector<HTMLElement>(
      "[data-role='cc-percent-display-wrap']",
    );
    const select = shell.querySelector<HTMLSelectElement>(
      "[data-role='cc-percent-display-select']",
    );
    if (!wrap || !select) return;
    // Visible only when the chart's combine output COULD be percent
    // — op = divide on exactly 2 sources. Doesn't gate on unitClass
    // match (would require resolving derived sources); the dropdown
    // is a no-op when the output isn't percent anyway.
    wrap.hidden = !(ccModal.op === "divide" && ccModal.selected.size === 2);
    // "percent" is the default; undefined means default.
    select.value = ccModal.percentDisplay ?? "percent";
  }

  // Reflect ccModal.shading onto the six checkbox inputs each time the
  // modal opens or shading state changes elsewhere (e.g. via Hover-
  // Merge defaults later). Pure state-to-DOM sync; no event wiring.
  function syncShadingUI(): void {
    const wrap = shell.querySelector<HTMLElement>("[data-role='cc-shading']");
    if (!wrap) return;
    const have = new Set(ccModal.shading);
    wrap
      .querySelectorAll<HTMLInputElement>("input[type='checkbox']")
      .forEach((cb) => {
        cb.checked = have.has(cb.value);
      });
  }

  // Reflect ccModal.transform onto the select each time the modal
  // opens (or syncs after a chart-pick that changed defaults).
  function syncTransformUI(): void {
    const sel = shell.querySelector<HTMLSelectElement>(
      "[data-role='cc-transform-select']",
    );
    if (sel) sel.value = ccModal.transform;
  }

  // Reflect ccModal.annotationsText onto the textarea.
  function syncAnnotationsUI(): void {
    const ta = shell.querySelector<HTMLTextAreaElement>(
      "[data-role='cc-annotations']",
    );
    if (ta) ta.value = ccModal.annotationsText;
  }

  function syncOpUI(): void {
    const library = getLibrary();
    const wrap = shell.querySelector<HTMLElement>("[data-role='cc-op-wrap']");
    const sel = shell.querySelector<HTMLSelectElement>("[data-role='cc-op-select']");
    const hint = shell.querySelector<HTMLElement>("[data-role='cc-op-hint']");
    const swap = shell.querySelector<HTMLButtonElement>("[data-role='cc-op-swap']");
    if (!wrap || !sel || !hint || !swap) return;
    syncPercentDisplayUI();
    // Show Combine UI any time we have at least 2 selected sources.
    wrap.hidden = ccModal.selected.size < 2;
    if (ccModal.selected.size !== 2) {
      // Op needs exactly 2 sources. Disable but show the wrap if 2+ so
      // the user knows the option exists.
      sel.disabled = ccModal.selected.size !== 2;
    } else {
      sel.disabled = false;
    }
    sel.value = ccModal.op ?? "";
    if (ccModal.op && ccModal.selectedOrder.length === 2) {
      const [aId, bId] = ccModal.selectedOrder;
      const aLabel = library?.sources[aId]?.shortName ?? library?.sources[aId]?.name ?? aId;
      const bLabel = library?.sources[bId]?.shortName ?? library?.sources[bId]?.name ?? bId;
      const symbol = ccModal.op === "divide" ? "÷" : ccModal.op === "sum" ? "+" : ccModal.op === "multiply" ? "×" : "−";
      hint.textContent = `A: ${aLabel}   B: ${bLabel}   →   ${aLabel} ${symbol} ${bLabel}`;
      swap.hidden = false;
    } else {
      hint.textContent = ccModal.selected.size > 2
        ? "Combine requires exactly 2 sources."
        : "";
      swap.hidden = true;
    }
  }

  // Reflect ccModal.mode + selected-source count onto the radio inputs:
  // toggle the dual-axis option's enabled state and check the right radio.
  function syncModeRadioFromState(): void {
    const raw = shell.querySelector<HTMLInputElement>("[data-role='cc-mode-raw']");
    const reb = shell.querySelector<HTMLInputElement>("[data-role='cc-mode-rebase']");
    const rebWrap = shell.querySelector<HTMLElement>("[data-role='cc-mode-rebase-wrap']");
    const dual = shell.querySelector<HTMLInputElement>("[data-role='cc-mode-dual']");
    const dualWrap = shell.querySelector<HTMLElement>("[data-role='cc-mode-dual-wrap']");
    // Both rebase and dual-axis are multi-series concepts: with one source,
    // rebase is just a single line indexed to 100 (no comparison) and
    // dual-axis needs two series to assign to L/R. Disable both until 2+.
    const allowMulti = ccModal.selected.size >= 2;
    if (reb) reb.disabled = !allowMulti;
    if (rebWrap) rebWrap.classList.toggle("cc-mode-opt-disabled", !allowMulti);
    if (dual) dual.disabled = !allowMulti;
    if (dualWrap) dualWrap.classList.toggle("cc-mode-opt-disabled", !allowMulti);
    if (raw) raw.checked = ccModal.mode === "raw";
    if (reb) reb.checked = ccModal.mode === "rebase" && allowMulti;
    if (dual) dual.checked = ccModal.mode === "dual-axis" && allowMulti;
  }

  // For dual-axis with no explicit assignment, default the first picked
  // source to left and everything else to right.
  function defaultRightAxisSources(): Set<string> {
    const ids = [...ccModal.selected];
    if (ids.length < 2) return new Set();
    return new Set(ids.slice(1));
  }

  // Returns the current right-axis assignment, falling back to the default
  // split when the explicit set is empty (initial state for fresh dual-axis).
  function effectiveRightAxisSources(): Set<string> {
    if (ccModal.rightAxisSources.size > 0) return ccModal.rightAxisSources;
    return defaultRightAxisSources();
  }

  // Launch the cc-modal in "merge a single-source chart into another
  // chart" mode. The dragged end MUST be single-source (the caller is
  // expected to have checked); the base can have any number of sources
  // and the merged chart contains base.sources ∪ {dragged.source}. The
  // base contributes its title / blurb / defaultDelta to the merged
  // chart; the dragged contributes only its source. Both originals stay
  // in the dashboard until Create is clicked — Cancel leaves the
  // dashboard exactly as it was before the merge attempt started.
  function openMergeModal(
    base: { chartId: string; secIdx: number; chartIdx: number },
    dragged: { chartId: string; secIdx: number; chartIdx: number },
  ): void {
    const library = getLibrary();
    const baseSpec = chartEffectiveSpec(base.chartId);
    const draggedSpec = chartEffectiveSpec(dragged.chartId);
    if (draggedSpec.sources.length !== 1 || baseSpec.sources.length === 0) {
      // Defensive — caller should have checked, but bail rather than open
      // a misleading modal.
      return;
    }
    const draggedSource = draggedSpec.sources[0];
    if (baseSpec.sources.includes(draggedSource)) return; // duplicate-skip

    // Stamp the tip as seen — the user has discovered the feature.
    if (!isHoverMergeTipDismissed()) {
      dismissHoverMergeTip();
      // Re-render so the tip line goes away immediately on first use.
      // No-op if the tip wasn't rendered (e.g. already-dismissed users).
      renderComposition();
    }

    // Drive the modal through openCustomChartModal so all the standard
    // input wiring + render hooks run, then layer on the merge-specific
    // state. Pass no editingId so it opens in create mode.
    openCustomChartModal();
    // Base's metadata becomes the merged chart's metadata — but when the
    // base is a single-source chart whose title the user never customized,
    // recompose the title from the two sources so the merged tile reads
    // as a sensible combo ("VA-08 spending + WTI crude") instead of
    // inheriting a now-misleading single-source label.
    if (baseSpec.sources.length === 1 && baseTitleIsDefault(base.chartId)) {
      const baseSrcMeta = library?.sources[baseSpec.sources[0]] as
        | { name?: string; shortName?: string }
        | undefined;
      const draggedSrcMeta = library?.sources[draggedSource] as
        | { name?: string; shortName?: string }
        | undefined;
      const baseLabel =
        baseSrcMeta?.shortName ??
        baseSrcMeta?.name ??
        baseSpec.sources[0];
      const draggedLabel =
        draggedSrcMeta?.shortName ??
        draggedSrcMeta?.name ??
        draggedSource;
      ccModal.title = `${baseLabel} + ${draggedLabel}`;
    } else {
      ccModal.title = baseSpec.title;
    }
    ccModal.blurb = baseSpec.blurb ?? "";
    // Source order: keep base's existing order, then append dragged. This
    // preserves any (left,right) axis intent the base had — left-axis
    // sources stay in their leading slots, dragged becomes the new
    // trailing series. The user can rearrange via the modal's Swap (for
    // 2-source layouts) or the cc-modal source list ordering.
    const mergedSources = [...baseSpec.sources, draggedSource];
    ccModal.selected = new Set<string>(mergedSources);
    ccModal.selectedOrder = mergedSources;
    // Carry the base's rightAxis / normalize / scale forward so a user who
    // had carefully set up a dual-axis chart and is just adding a third
    // series doesn't lose their picks. We then re-evaluate dual-axis
    // viability below, since 3+ sources on a dual-axis chart may be
    // intentional but defaulting it off forces a recheck.
    if (isInlineId(base.chartId)) {
      const baseInline = state.inlineCharts[base.chartId];
      if (baseInline) {
        ccModal.mode = (baseInline.normalize as CustomChartMode | undefined) ?? "raw";
        ccModal.modeIsExplicit = !!baseInline.normalize;
        ccModal.rightAxisSources = new Set<string>(
          baseInline.rightAxisSources ?? [],
        );
        ccModal.logScale = baseInline.scale === "log";
      }
    }
    // If the base was dual-axis (a 2-series concern by design), adding a
    // 3rd source via merge isn't unambiguous — recompute a default mode
    // for the new mix rather than carry an awkward dual-axis forward. The
    // user can re-engage dual-axis explicitly inside the modal if they
    // actually want a 3-on-axes split.
    if (ccModal.mode === "dual-axis" && mergedSources.length > 2) {
      ccModal.mode = ccDefaultMode();
      ccModal.modeIsExplicit = false;
      ccModal.rightAxisSources = new Set<string>();
    }
    ccModal.pendingMerge = {
      baseChartId: base.chartId,
      baseSecIdx: base.secIdx,
      baseChartIdx: base.chartIdx,
      baseDefaultDelta: baseSpec.defaultDelta,
      draggedChartId: dragged.chartId,
      draggedSecIdx: dragged.secIdx,
      draggedChartIdx: dragged.chartIdx,
    };
    // Re-evaluate titleAuto now that the merge has finalized the title
    // and source list. When the merge auto-built "A + B" from default-
    // titled bases, it matches deriveCcAutoTitle and titleAuto stays
    // true — so a later source-swap still tracks. When the merge
    // inherited a hand-written baseSpec.title, the strings won't match
    // and titleAuto flips false so we never clobber the user's name.
    recomputeCcTitleAuto();
    // Update the title input + blurb textarea to reflect the seeded state.
    const titleInput = shell.querySelector<HTMLInputElement>(
      "[data-role='cc-title']",
    );
    if (titleInput) titleInput.value = ccModal.title;
    const blurbInput = shell.querySelector<HTMLTextAreaElement>(
      "[data-role='cc-blurb']",
    );
    if (blurbInput) blurbInput.value = ccModal.blurb;
    const heading = shell.querySelector<HTMLElement>("#cc-modal-title");
    if (heading) {
      heading.textContent = `Combine: ${baseSpec.title} + ${draggedSpec.title}`;
    }
    const createBtn = shell.querySelector<HTMLButtonElement>(
      "[data-role='cc-create']",
    );
    if (createBtn) createBtn.textContent = "Combine charts";
    // Reflect the seeded source selection in the source list + controls.
    syncModeRadioFromState();
    syncLogUI();
    syncOpUI();
    syncShadingUI();
    syncTransformUI();
    syncAnnotationsUI();
    renderCcModalTagChips();
    renderCustomChartSources();
    updateCustomChartCreateState();
    renderCustomChartPreview();
    track("compose_hover_merge_launched", {
      baseChartId: base.chartId,
      draggedChartId: dragged.chartId,
      baseSourceCount: baseSpec.sources.length,
      sources: packSourceIds(mergedSources),
    });
  }

  function closeCustomChartModal(): void {
    const backdrop = shell.querySelector<HTMLElement>("[data-role='cc-modal']");
    if (backdrop) backdrop.hidden = true;
    // Closing the modal — whether via Cancel, ×, ESC, or backdrop click —
    // clears any pending merge so a subsequent "+ Custom chart" doesn't
    // pick it back up. The Create handler clears pendingMerge before
    // closing on its own success path, so this is the cancel-side reset.
    ccModal.pendingMerge = null;
  }

  function updateCustomChartCreateState(): void {
    const btn = shell.querySelector<HTMLButtonElement>("[data-role='cc-create']");
    const count = shell.querySelector<HTMLElement>("[data-role='cc-count']");
    if (count) {
      const n = ccModal.selected.size;
      count.textContent = `${n} selected`;
    }
    if (btn) {
      // Title isn't required — an empty title gets a "Unnamed chart"
      // default on submit. Only source-picking is mandatory.
      const missingSources = ccModal.selected.size === 0;
      btn.disabled = missingSources;
      if (missingSources) {
        btn.title = "Pick at least one source first.";
      } else {
        btn.removeAttribute("title");
      }
    }
  }

  function filteredModalSources(): (LibrarySource & { tags?: string[] })[] {
    const library = getLibrary();
    if (!library) return [];
    const q = ccModal.search.trim().toLowerCase();
    // Same exclusion as filteredSources: CD_TAG is the chip's master flag
    // (gated by passesCdFilter), not a literal source tag.
    const tagsRequired = [...ccModal.pickerTags].filter((t) => t !== CD_TAG);
    // Inject derived sources at the top of the universe so the user sees
    // their own creations before the firehose of library sources. Each
    // derived source carries its inherited+custom tag set so the
    // picker-tags filter works uniformly.
    const derivedAsLib: (LibrarySource & { tags?: string[] })[] = Object.entries(
      state.inlineSources,
    ).map(
      ([id, spec]) => ({
        id,
        name: spec.name,
        shortName: spec.name,
        description: `Derived: ${describeDerivedExpr(id)}`,
        tags: spec.tags ?? [],
      } as LibrarySource & { tags?: string[] }),
    );
    const all: (LibrarySource & { tags?: string[]; searchText?: string })[] = [
      ...derivedAsLib,
      ...Object.values(library.sources),
    ];
    return all.filter((s) => {
      // Synthetic geo-discovery hints are emitted only for the main
      // Sources tab — they make no sense inside the cc-modal where
      // the user is mid-chart-creation and has already picked the
      // scope. Drop them here unconditionally.
      if (s.kind === "hint") return false;
      const sTags = s.tags ?? [];
      // CD-visibility gate, mirroring filteredSources(). Derived sources
      // never have the CD_TAG (we don't synthesize it onto inline-source
      // tag sets), so they're always exempt from this filter regardless
      // of cc-modal CD state — derived sources stay visible.
      if (
        !passesCdFilter(
          s.id,
          sTags,
          ccModal.pickerTags,
          ccModal.cdState,
          ccModal.cdDistrict,
          q,
        )
      ) {
        return false;
      }
      // Metro / country / CD chip drill-downs, mirroring the Sources
      // tab via the shared filter helpers. All three include the
      // 4-char name-unlock so typing "Abilene" / "Australia" /
      // "Texas" surfaces the matching geo sources without first
      // engaging the chip.
      if (!passesMetroFilter(sTags, ccModal.geo.selectedMetroCbsa, q)) return false;
      if (!passesCountryFilter(sTags, ccModal.geo.selectedCountryCode, q)) return false;
      if (!passesCountyFilter(s.id, sTags, q)) return false;
      for (const t of tagsRequired) {
        if (!sTags.includes(t)) return false;
      }
      if (q) {
        const hay =
          s.searchText ??
          `${s.name} ${s.shortName ?? ""} ${s.description ?? ""} ${s.id} ${sTags.join(" ")}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  // Render a chain of derived combinations as a string, recursively.
  function describeDerivedExpr(id: string): string {
    const library = getLibrary();
    if (!isDerivedId(id)) {
      const s = library?.sources[id];
      return s?.shortName ?? s?.name ?? id;
    }
    const spec = state.inlineSources[id];
    if (!spec) return id;
    const symbol = spec.op === "divide" ? "÷" : spec.op === "sum" ? "+" : spec.op === "multiply" ? "×" : "−";
    return `${describeDerivedExpr(spec.a)} ${symbol} ${describeDerivedExpr(spec.b)}`;
  }

  function renderCustomChartSources(): void {
    const host = shell.querySelector<HTMLElement>("[data-role='cc-source-list']");
    if (!host) return;
    const sources = filteredModalSources();
    host.innerHTML = "";
    if (sources.length === 0) {
      host.innerHTML = '<p class="muted small">No sources match.</p>';
      return;
    }
    // Sort alphabetically by display name so the list stays predictable under search.
    sources.sort((a, b) => (a.shortName ?? a.name).localeCompare(b.shortName ?? b.name));
    for (const s of sources) {
      const row = document.createElement("label");
      row.className = "cc-source-row";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = ccModal.selected.has(s.id);
      cb.addEventListener("change", () => {
        if (cb.checked) {
          ccModal.selected.add(s.id);
          if (!ccModal.selectedOrder.includes(s.id))
            ccModal.selectedOrder.push(s.id);
        } else {
          ccModal.selected.delete(s.id);
          ccModal.selectedOrder = ccModal.selectedOrder.filter((id) => id !== s.id);
        }
        // If user hasn't explicitly picked a mode, auto-default from scale
        // heuristics whenever the source set changes. If they have, keep
        // their pick — but flip rebase or dual-axis off when no longer 2+
        // sources, since neither concept is meaningful with a single series.
        if (!ccModal.modeIsExplicit) {
          ccModal.mode = ccDefaultMode();
        } else if (
          (ccModal.mode === "dual-axis" || ccModal.mode === "rebase") &&
          ccModal.selected.size < 2
        ) {
          ccModal.mode = "raw";
          ccModal.modeIsExplicit = false;
        }
        // Strip rightAxis assignment for sources that just got unchecked.
        if (!cb.checked) ccModal.rightAxisSources.delete(s.id);
        // Op requires exactly 2 sources; clear if no longer applicable.
        if (ccModal.op && ccModal.selected.size !== 2) {
          ccModal.op = null;
        }
        syncModeRadioFromState();
        syncLogUI();
        syncOpUI();
        updateCustomChartCreateState();
        renderCustomChartSources();
        renderCustomChartPreview();
        // Source set changed — re-check whether any typed annotation
        // dates fall outside the new union date range. Cheap; runs off
        // library.json data already in memory.
        updateCcAnnotationsWarning();
        // If the title was tracking the auto-derived default, swap it
        // to match the new source set. No-op when the user has typed
        // something custom (the flag stays false until they clear the
        // field).
        maybeRefreshCcAutoTitle();
      });
      row.appendChild(cb);
      const text = document.createElement("span");
      text.className = "cc-source-row-text";
      const primary = s.shortName ?? s.name;
      const secondary = s.shortName && s.shortName !== s.name ? s.name : "";
      text.innerHTML =
        `<span class="cc-source-primary">${escapeHtml(primary)}</span>` +
        (secondary ? `<span class="cc-source-secondary">${escapeHtml(secondary)}</span>` : "");
      row.appendChild(text);
      // Per-source L|R axis pill, only when dual-axis mode + this source is picked.
      if (ccModal.mode === "dual-axis" && ccModal.selected.has(s.id)) {
        const effRight = effectiveRightAxisSources();
        const isRight = effRight.has(s.id);
        const axisWrap = document.createElement("span");
        axisWrap.className = "cc-source-axis";
        const lBtn = document.createElement("button");
        lBtn.type = "button";
        lBtn.className = "cc-axis-pill" + (!isRight ? " cc-axis-pill-active" : "");
        lBtn.textContent = "L";
        lBtn.title = "Plot on the left axis";
        const rBtn = document.createElement("button");
        rBtn.type = "button";
        rBtn.className = "cc-axis-pill" + (isRight ? " cc-axis-pill-active" : "");
        rBtn.textContent = "R";
        rBtn.title = "Plot on the right axis";
        const setSide = (right: boolean, e: Event) => {
          e.preventDefault();
          e.stopPropagation();
          // Materialize the effective default into the explicit set the
          // first time the user touches an axis pill.
          if (ccModal.rightAxisSources.size === 0) {
            ccModal.rightAxisSources = new Set(effectiveRightAxisSources());
          }
          if (right) ccModal.rightAxisSources.add(s.id);
          else ccModal.rightAxisSources.delete(s.id);
          renderCustomChartSources();
          renderCustomChartPreview();
        };
        lBtn.addEventListener("click", (e) => setSide(false, e));
        rBtn.addEventListener("click", (e) => setSide(true, e));
        axisWrap.appendChild(lBtn);
        axisWrap.appendChild(rBtn);
        row.appendChild(axisWrap);
      }
      host.appendChild(row);
    }
  }

  // ---- Custom-chart preview rendering ----
  // Counter so a slow fetch from a stale modal state doesn't render over a
  // newer one when the user rapidly toggles sources.
  let ccPreviewToken = 0;

  /**
   * Build Plot.rectX shading marks for the cc-modal preview pane.
   * Mirrors src/components/ChartController.astro's shadingMarks: the
   * fill is passed as a function so Plot's color scale doesn't
   * categorize the hex strings into palette colors. Filters bands
   * to the plotted date range — bands fully outside the window are
   * dropped so they don't widen the x-domain.
   *
   * Without this, ccModal.shading was wired into the inlineChart on
   * Create but never reflected in the live preview. The user would
   * toggle "Presidential party" or "Fed chairs," see no change, and
   * assume the feature was broken — only discovering the bands
   * after Save → Preview / Open in dashboard.
   */
  function previewShadingMarks(
    keys: string[],
    domainStart: Date | null,
    domainEnd: Date | null,
  ): any[] {
    if (!keys || keys.length === 0) return [];
    const marks: any[] = [];
    const startMs = domainStart ? domainStart.getTime() : -Infinity;
    const endMs = domainEnd ? domainEnd.getTime() : Infinity;
    for (const key of keys) {
      const bands = bandsFor(key as ShadingKey);
      if (bands.length === 0) continue;
      const visible = bands
        .map((b) => ({
          ...b,
          startDate: new Date(b.start),
          endDate: new Date(b.end),
        }))
        .filter(
          (b) =>
            b.endDate.getTime() >= startMs && b.startDate.getTime() <= endMs,
        );
      if (visible.length === 0) continue;
      // Group bands by fill color, one Plot.rectX per group with a
      // CONSTANT fill string. Both column-string (`fill: "fill"`) and
      // function form (`fill: (d) => d.fill`) push values through
      // Plot's fill channel scale, which auto-categorizes hex
      // strings and assigns palette colors. A constant string is
      // not a channel encoding and bypasses the scale, so the
      // intended D/R blue+red, chair grays, etc. render literally.
      // Mirrors src/components/ChartController.astro's shadingMarks.
      const byFill = new Map<string, typeof visible>();
      for (const band of visible) {
        const list = byFill.get(band.fill);
        if (list) list.push(band);
        else byFill.set(band.fill, [band]);
      }
      for (const [fillColor, group] of byFill) {
        marks.push(
          Plot.rectX(group, {
            x1: "startDate",
            x2: "endDate",
            fill: fillColor,
            fillOpacity: SHADING_FILL_OPACITY,
            title: "label",
          }),
        );
      }
    }
    return marks;
  }

  async function renderCustomChartPreview(): Promise<void> {
    const plotHost = shell.querySelector<HTMLElement>("[data-role='cc-preview-plot']");
    const statusEl = shell.querySelector<HTMLElement>("[data-role='cc-preview-status']");
    const legendEl = shell.querySelector<HTMLElement>("[data-role='cc-preview-legend']");
    if (!plotHost || !statusEl || !legendEl) return;
    const token = ++ccPreviewToken;
    const ids = [...ccModal.selected];
    if (ids.length === 0) {
      plotHost.replaceChildren();
      legendEl.innerHTML = "";
      statusEl.textContent = "Pick a source to preview.";
      return;
    }
    statusEl.textContent = "Loading…";
    // Use selectedOrder so the user's explicit A/B order is honored when op
    // is set. Fall back to selection iteration order otherwise.
    const orderedIds = ccModal.selectedOrder.filter((id) =>
      ccModal.selected.has(id),
    );
    for (const id of ccModal.selected) {
      if (!orderedIds.includes(id)) orderedIds.push(id);
    }
    const series = (
      await Promise.all(orderedIds.map((id) => fetchSourceSeries(id)))
    ).filter((s): s is FetchedSeries => s !== null);
    if (token !== ccPreviewToken) return; // stale render

    if (series.length === 0) {
      plotHost.replaceChildren();
      legendEl.innerHTML = "";
      statusEl.textContent = "Couldn't load data for the selected sources.";
      return;
    }

    // Op short-circuit: if 2 sources + op set, collapse into a single
    // derived series and render as one line.
    if (ccModal.op && series.length === 2) {
      const a = series[0];
      const b = series[1];
      const aMap = new Map<string, number>();
      for (const p of a.points) aMap.set(p.t, p.v);
      const bMap = new Map<string, number>();
      for (const p of b.points) bMap.set(p.t, p.v);
      const all = new Set<string>();
      for (const p of a.points) all.add(p.t);
      for (const p of b.points) all.add(p.t);
      const ordered = [...all].sort();
      const combined: { t: Date; v: number }[] = [];
      let lastA: number | null = null;
      let lastB: number | null = null;
      for (const t of ordered) {
        if (aMap.has(t)) lastA = aMap.get(t)!;
        if (bMap.has(t)) lastB = bMap.get(t)!;
        if (lastA === null || lastB === null) continue;
        let v: number;
        if (ccModal.op === "divide") {
          if (lastB === 0) continue;
          v = lastA / lastB;
        } else if (ccModal.op === "sum") {
          v = lastA + lastB;
        } else {
          v = lastA - lastB;
        }
        combined.push({ t: new Date(t), v });
      }
      const symbol = ccModal.op === "divide" ? "÷" : ccModal.op === "sum" ? "+" : "−";
      statusEl.textContent = `${a.name} ${symbol} ${b.name}`;
      // Log scale on a derived single line is a legitimate ask (ratio of
      // market caps over decades, e.g.) so honor the checkbox here too.
      // Plot.lineY drops points where y ≤ 0 under log automatically, which
      // is fine — sums-that-go-negative or divisions-by-tiny-numbers will
      // simply not appear on the log view.
      const useLog = ccModal.logScale;
      // Shading bands behind the derived line. Splice in front of the
      // marks list so they paint BEHIND the lineY (Plot honors the
      // marks-array order for z-stacking).
      const opShading = previewShadingMarks(
        ccModal.shading,
        combined.length > 0 ? combined[0].t : null,
        combined.length > 0 ? combined[combined.length - 1].t : null,
      );
      const opPlot = Plot.plot({
        height: 220,
        width: plotHost.clientWidth || 360,
        marginLeft: 60,
        marginBottom: 24,
        marginTop: 8,
        marginRight: 12,
        style: {
          fontFamily:
            '"Inter Variable", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
          fontSize: "11px",
          color: "#55524C",
          background: "transparent",
        },
        x: { label: null, ticks: 4 },
        y: {
          label: null,
          grid: true,
          ticks: 4,
          type: useLog ? "log" : undefined,
        },
        marks: [
          ...opShading,
          Plot.lineY(combined, {
            x: "t",
            y: "v",
            stroke: CC_COLORS[0],
            strokeWidth: 1.5,
          }),
        ],
      }) as HTMLElement;
      plotHost.replaceChildren(opPlot);
      legendEl.innerHTML = `<li><span class="cc-legend-dot" style="background:${CC_COLORS[0]}"></span><span>${escapeHtml(a.name)} ${symbol} ${escapeHtml(b.name)}</span></li>`;
      return;
    }
    // Effective mode for rendering: dual-axis needs at least 2 sources, and
    // both axes must end up with at least one series after partitioning.
    let mode: CustomChartMode = ccModal.mode;
    if (mode === "dual-axis") {
      if (series.length < 2) mode = "rebase";
      else {
        const eff = effectiveRightAxisSources();
        const rightCount = series.filter((s) => eff.has(s.id)).length;
        const leftCount = series.length - rightCount;
        if (rightCount === 0 || leftCount === 0) mode = "rebase";
      }
    }
    statusEl.textContent =
      `${series.length} series · ${mode === "dual-axis" ? "dual-axis" : mode === "rebase" ? "rebased to 100" : "raw"}`;

    const colored = series.map((s, i) => ({
      ...s,
      color: CC_COLORS[i % CC_COLORS.length],
    }));

    const width = plotHost.clientWidth || 360;
    const baseStyle = {
      fontFamily:
        '"Inter Variable", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      fontSize: "11px",
      color: "#55524C",
      background: "transparent",
    };

    let plot: HTMLElement;
    if (mode === "dual-axis") {
      const eff = effectiveRightAxisSources();
      const leftSeries = colored.filter((s) => !eff.has(s.id));
      const rightSeries = colored.filter((s) => eff.has(s.id));
      // Left domain: min/max across all left series. Right domain: same on
      // the right side. Right values are rescaled to fit the left domain
      // for plotting; the right axis's tickFormat un-rescales.
      const leftPts = leftSeries.flatMap((s) => s.points);
      const rightPts = rightSeries.flatMap((s) => s.points);
      const leftMin = Math.min(...leftPts.map((p) => p.v));
      const leftMax = Math.max(...leftPts.map((p) => p.v));
      const rightMin = Math.min(...rightPts.map((p) => p.v));
      const rightMax = Math.max(...rightPts.map((p) => p.v));
      const lRange = leftMax - leftMin || 1;
      const rRange = rightMax - rightMin || 1;
      const rescaleR = (v: number) =>
        leftMin + ((v - rightMin) / rRange) * lRange;
      const unrescaleR = (yPos: number) =>
        rightMin + ((yPos - leftMin) / lRange) * rRange;
      const marks: any[] = [];
      // Shading first so the bands paint UNDER the lines below.
      // Domain bounds come from all series flattened — same x-window
      // both axes share.
      {
        const allPts = [...leftPts, ...rightPts];
        if (allPts.length > 0) {
          const ts = allPts.map((p) => new Date(p.t).getTime());
          const minDate = new Date(Math.min(...ts));
          const maxDate = new Date(Math.max(...ts));
          marks.push(...previewShadingMarks(ccModal.shading, minDate, maxDate));
        }
      }
      // A representative color per axis for the axis labels themselves: when
      // there's exactly one series on a side, use that series' color. With
      // multiple, use neutral so it doesn't claim allegiance to one line.
      const leftAxisColor =
        leftSeries.length === 1 ? leftSeries[0].color : "#55524C";
      const rightAxisColor =
        rightSeries.length === 1 ? rightSeries[0].color : "#55524C";
      for (const s of leftSeries) {
        const pts = s.points.map((p) => ({ t: new Date(p.t), v: p.v }));
        marks.push(
          Plot.lineY(pts, {
            x: "t",
            y: "v",
            stroke: s.color,
            strokeWidth: 1.4,
          }),
        );
      }
      for (const s of rightSeries) {
        const pts = s.points.map((p) => ({
          t: new Date(p.t),
          v: rescaleR(p.v),
        }));
        marks.push(
          Plot.lineY(pts, {
            x: "t",
            y: "v",
            stroke: s.color,
            strokeWidth: 1.4,
          }),
        );
      }
      marks.push(
        Plot.axisY({ anchor: "left", color: leftAxisColor, ticks: 4 }),
        Plot.axisY({
          anchor: "right",
          color: rightAxisColor,
          ticks: 4,
          tickFormat: (v: number) => unrescaleR(v).toFixed(2),
        }),
      );
      plot = Plot.plot({
        height: 220,
        width,
        marginLeft: 50,
        marginBottom: 24,
        marginTop: 8,
        marginRight: 50,
        style: baseStyle,
        x: { label: null, ticks: 4 },
        y: { label: null, grid: true, ticks: 4 },
        marks,
      }) as HTMLElement;
    } else {
      const marks: any[] = [];
      // Compute domain bounds across all visible series so shading
      // bands can be filtered to the plotted window. Shading goes
      // first in the marks list so it paints under the lines.
      let earliest: Date | null = null;
      let latest: Date | null = null;
      for (const s of colored) {
        if (s.points.length === 0) continue;
        const firstT = new Date(s.points[0].t);
        const lastT = new Date(s.points[s.points.length - 1].t);
        if (!earliest || firstT < earliest) earliest = firstT;
        if (!latest || lastT > latest) latest = lastT;
      }
      marks.push(...previewShadingMarks(ccModal.shading, earliest, latest));
      for (const s of colored) {
        const pts = s.points;
        if (pts.length < 2) continue;
        let plotPts: { t: Date; v: number }[];
        if (mode === "rebase") {
          const baseline = pts[0].v || 1;
          plotPts = pts.map((p) => ({
            t: new Date(p.t),
            v: (p.v / baseline) * 100,
          }));
        } else {
          plotPts = pts.map((p) => ({ t: new Date(p.t), v: p.v }));
        }
        marks.push(
          Plot.lineY(plotPts, {
            x: "t",
            y: "v",
            stroke: s.color,
            strokeWidth: 1.4,
          }),
        );
      }
      // Log scale only takes effect on the non-dual-axis branch (we
      // explicitly disallow log + dual-axis in the UI). We're already
      // inside the non-dual-axis branch here — TS has narrowed mode
      // to "raw" | "rebase" — so the previous `mode !== "dual-axis"`
      // guard was a tautology TS flagged. Keeping the comment as a
      // pointer for the parallel guard in the saved-spec branch.
      const useLog = ccModal.logScale;
      plot = Plot.plot({
        height: 220,
        width,
        marginLeft: 50,
        marginBottom: 24,
        marginTop: 8,
        marginRight: 12,
        style: baseStyle,
        x: { label: null, ticks: 4 },
        y: {
          label: mode === "rebase" ? "index (start = 100)" : null,
          grid: true,
          ticks: 4,
          type: useLog ? "log" : undefined,
        },
        marks,
      }) as HTMLElement;
    }
    plotHost.replaceChildren(plot);
    legendEl.innerHTML = colored
      .map(
        (s) =>
          `<li><span class="cc-legend-dot" style="background:${s.color}"></span><span>${escapeHtml(s.name)}</span></li>`,
      )
      .join("");
  }


  function wireCustomChartModal(): void {
    const backdrop = shell.querySelector<HTMLElement>("[data-role='cc-modal']");
    const closeBtn = shell.querySelector<HTMLButtonElement>("[data-role='cc-close']");
    const cancelBtn = shell.querySelector<HTMLButtonElement>("[data-role='cc-cancel']");
    const createBtn = shell.querySelector<HTMLButtonElement>("[data-role='cc-create']");
    const titleInput = shell.querySelector<HTMLInputElement>("[data-role='cc-title']");
    const searchInput = shell.querySelector<HTMLInputElement>("[data-role='cc-source-search']");
    const modeRadios = shell.querySelectorAll<HTMLInputElement>(
      "input[name='cc-mode']",
    );

    closeBtn?.addEventListener("click", closeCustomChartModal);
    cancelBtn?.addEventListener("click", closeCustomChartModal);
    // Click on the backdrop (outside the dialog) also closes.
    backdrop?.addEventListener("click", (e) => {
      if (e.target === backdrop) closeCustomChartModal();
    });
    // ESC closes the modal when it's open.
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !backdrop || backdrop.hidden) return;
      closeCustomChartModal();
    });
    titleInput?.addEventListener("input", () => {
      ccModal.title = titleInput.value;
      // Title is now user-controlled; stop auto-refreshing it on
      // source/op changes. Special case: clearing the field back to
      // empty is treated as "give me the default again" — flip the
      // flag back on and re-derive immediately so the field doesn't
      // look broken.
      if (titleInput.value === "") {
        ccModal.titleAuto = true;
        maybeRefreshCcAutoTitle();
      } else {
        ccModal.titleAuto = false;
      }
      updateCustomChartCreateState();
    });
    const blurbInput = shell.querySelector<HTMLTextAreaElement>(
      "[data-role='cc-blurb']",
    );
    blurbInput?.addEventListener("input", () => {
      ccModal.blurb = blurbInput.value;
    });
    const percentDisplaySelect = shell.querySelector<HTMLSelectElement>(
      "[data-role='cc-percent-display-select']",
    );
    percentDisplaySelect?.addEventListener("change", () => {
      const v = percentDisplaySelect.value;
      ccModal.percentDisplay =
        v === "decimal" || v === "ratio" ? v : undefined;
      // No re-render needed — this only affects the saved spec; the
      // chart picks up the flag at render time.
    });

    // Transform select (level / yoy_pct / index_100). Saved on the
    // inline chart's `transform` field; per-session pill overrides
    // happen in the dialog, not here.
    const transformSelect = shell.querySelector<HTMLSelectElement>(
      "[data-role='cc-transform-select']",
    );
    if (transformSelect) {
      transformSelect.value = ccModal.transform;
      transformSelect.addEventListener("change", () => {
        const v = transformSelect.value;
        ccModal.transform =
          v === "yoy_pct" || v === "index_100" ? v : "level";
        // No preview re-render needed — the cc-modal preview always
        // shows raw level; the transform only affects the saved
        // chart's dialog default.
      });
    }

    // Annotations textarea. Stored as raw text in ccModal; parsed
    // into the array shape only at save time via parseAnnotationLines.
    // Keeping the text in state means a malformed line doesn't get
    // silently dropped between edits.
    const annTextarea = shell.querySelector<HTMLTextAreaElement>(
      "[data-role='cc-annotations']",
    );
    if (annTextarea) {
      annTextarea.value = ccModal.annotationsText;
      annTextarea.addEventListener("input", () => {
        ccModal.annotationsText = annTextarea.value;
        // The cc-modal preview shows a raw chart — annotations are
        // a render-time overlay applied in the dialog. Skip the
        // preview re-render here; the user sees the result on save.
        updateCcAnnotationsWarning();
      });
    }
    // First paint: seed warning state based on whatever annotations +
    // sources the modal opened with (matters when editing an existing
    // inline chart whose annotations predate the current source set).
    updateCcAnnotationsWarning();

    // Background-shading checkboxes. Each toggle splices its key in or
    // out of ccModal.shading; the array is persisted as inlineChart.shading
    // on Create. Re-render the preview so the user sees the bands without
    // needing to close + reopen.
    const shadingWrap = shell.querySelector<HTMLElement>("[data-role='cc-shading']");
    shadingWrap?.querySelectorAll<HTMLInputElement>("input[type='checkbox']").forEach(
      (cb) => {
        cb.addEventListener("change", () => {
          const key = cb.value;
          const idx = ccModal.shading.indexOf(key);
          if (cb.checked && idx < 0) ccModal.shading.push(key);
          else if (!cb.checked && idx >= 0) ccModal.shading.splice(idx, 1);
          renderCustomChartPreview();
        });
      },
    );
    searchInput?.addEventListener("input", () => {
      ccModal.search = searchInput.value;
      renderCustomChartSources();
    });
    modeRadios.forEach((r) => {
      r.addEventListener("change", () => {
        if (!r.checked) return;
        ccModal.mode = r.value as CustomChartMode;
        ccModal.modeIsExplicit = true;
        // Re-render the source list so the L|R pills appear/disappear as the
        // mode toggles into/out of dual-axis.
        renderCustomChartSources();
        // Log scale is incompatible with dual-axis; keep the checkbox state
        // honest as the user flips modes.
        syncLogUI();
        renderCustomChartPreview();
      });
    });

    const logCheckbox = shell.querySelector<HTMLInputElement>(
      "[data-role='cc-log']",
    );
    logCheckbox?.addEventListener("change", () => {
      // Defensive: even though we disable the checkbox in dual-axis mode,
      // a keyboard focus + space-bar could still flip it. Ignore that.
      if (ccModal.mode === "dual-axis") {
        logCheckbox.checked = false;
        return;
      }
      ccModal.logScale = logCheckbox.checked;
      renderCustomChartPreview();
    });

    const opSelect = shell.querySelector<HTMLSelectElement>("[data-role='cc-op-select']");
    opSelect?.addEventListener("change", () => {
      ccModal.op = (opSelect.value as ChartCombineOp | "") || null;
      syncOpUI();
      renderCustomChartPreview();
      // Op affects the auto-title format ("A / B" vs "A vs. B"); refresh.
      maybeRefreshCcAutoTitle();
    });
    const opSwap = shell.querySelector<HTMLButtonElement>("[data-role='cc-op-swap']");
    opSwap?.addEventListener("click", () => {
      if (ccModal.selectedOrder.length === 2) {
        ccModal.selectedOrder = [
          ccModal.selectedOrder[1],
          ccModal.selectedOrder[0],
        ];
        syncOpUI();
        renderCustomChartPreview();
        // Swapping argument order changes auto-title for non-commutative
        // ops (divide, diff). Refresh.
        maybeRefreshCcAutoTitle();
      }
    });
    createBtn?.addEventListener("click", () => {
      // Use selectedOrder so the user's explicit A/B order is preserved
      // for op'd charts. Fall back to insertion order if needed.
      const sourceIds = ccModal.selectedOrder.filter((id) =>
        ccModal.selected.has(id),
      );
      // Append any selected sources that didn't make it into selectedOrder
      // (defensive — shouldn't happen given the change handler).
      for (const id of ccModal.selected) {
        if (!sourceIds.includes(id)) sourceIds.push(id);
      }
      if (sourceIds.length === 0) return;
      // Title is optional; empty (or whitespace-only) gets a default so
      // the user isn't forced to name what might be a quick exploration.
      // Multiple "Unnamed chart"s on one dashboard is a self-inflicted
      // aesthetic — fixable by clicking the chart to rename — rather
      // than a structural problem.
      const effectiveTitle = ccModal.title.trim() || "Unnamed chart";
      // Final mode: rebase and dual-axis both need at least 2 sources to be
      // meaningful (rebasing a single series is just "indexed to 100" with no
      // comparison; dual-axis has nothing to assign to L/R). Clamp down to raw.
      const mode: CustomChartMode =
        (ccModal.mode === "dual-axis" || ccModal.mode === "rebase") &&
        sourceIds.length < 2
          ? "raw"
          : ccModal.mode;
      // Resolve rightAxisSources only when dual-axis. Persist explicit
      // user picks; if the user never touched the L/R pills, persist the
      // default split (first source left, rest right) so the rendered
      // chart matches the preview the user saw.
      let rightAxisSources: string[] | undefined;
      if (mode === "dual-axis") {
        const eff = effectiveRightAxisSources();
        const filtered = sourceIds.filter((id) => eff.has(id));
        rightAxisSources = filtered.length > 0 ? filtered : undefined;
      }
      // Op only valid with exactly 2 sources.
      const opToSave: ChartCombineOp | undefined =
        ccModal.op && sourceIds.length === 2 ? ccModal.op : undefined;
      // Log scale only valid with raw or rebase modes. Coerce off when
      // dual-axis is the final mode to keep the saved spec internally
      // consistent (so a state surviving across refreshes doesn't get
      // re-armed by some future UI fix).
      const scaleToSave: "linear" | "log" | undefined =
        ccModal.logScale && mode !== "dual-axis" ? "log" : undefined;
      const blurbToSave = ccModal.blurb.trim() || undefined;
      if (ccModal.editingId) {
        // Edit mode: preserve any fields we don't expose (e.g. render).
        const existing = state.inlineCharts[ccModal.editingId] ?? {
          title: "",
          sources: [] as string[],
        };
        state.inlineCharts[ccModal.editingId] = {
          ...existing,
          title: effectiveTitle,
          sources: sourceIds,
          normalize: mode,
          scale: scaleToSave,
          rightAxisSources,
          op: opToSave,
          blurb: blurbToSave,
          // Only persist percentDisplay when the chart's combine output
          // could actually be percent (divide on 2 sources); otherwise
          // the flag is dead weight in the saved state.
          percentDisplay:
            opToSave === "divide" && sourceIds.length === 2
              ? ccModal.percentDisplay
              : undefined,
          // Persist shading layers — empty array stored as undefined so
          // the serialized state stays compact when no bands are picked.
          shading:
            ccModal.shading.length > 0
              ? [...ccModal.shading] as InlineChart["shading"]
              : undefined,
          // Persist transform only when non-level; "level" is the
          // implicit default so omitting it keeps the serialized
          // URL state compact for the common case.
          transform:
            ccModal.transform !== "level" ? ccModal.transform : undefined,
          // Parse annotations from the textarea body. Empty array
          // serializes to undefined to keep URL state compact.
          annotations: (() => {
            const arr = parseAnnotationLines(ccModal.annotationsText);
            return arr.length > 0 ? arr : undefined;
          })(),
        };
      } else {
        const id = INLINE_PREFIX + nanoid(8);
        state.inlineCharts[id] = {
          title: effectiveTitle,
          sources: sourceIds,
          normalize: mode,
          scale: scaleToSave,
          rightAxisSources,
          op: opToSave,
          blurb: blurbToSave,
          percentDisplay:
            opToSave === "divide" && sourceIds.length === 2
              ? ccModal.percentDisplay
              : undefined,
          shading:
            ccModal.shading.length > 0
              ? [...ccModal.shading] as InlineChart["shading"]
              : undefined,
          // Persist transform only when non-level; "level" is the
          // implicit default so omitting it keeps the serialized
          // URL state compact for the common case.
          transform:
            ccModal.transform !== "level" ? ccModal.transform : undefined,
          // Parse annotations from the textarea body. Empty array
          // serializes to undefined to keep URL state compact.
          annotations: (() => {
            const arr = parseAnnotationLines(ccModal.annotationsText);
            return arr.length > 0 ? arr : undefined;
          })(),
        };
        // Hover-merge path: the new chart replaces the BASE chart at its
        // section slot, and the DRAGGED chart is removed from its own
        // section. Base's defaultDelta (captured at merge launch) is
        // applied to the merged chart so the user's preferred window
        // survives the combine.
        const pm = ccModal.pendingMerge;
        if (pm) {
          if (pm.baseDefaultDelta) {
            state.inlineCharts[id].defaultDelta = pm.baseDefaultDelta;
          }
          const baseSec = state.sections[pm.baseSecIdx];
          const draggedSec = state.sections[pm.draggedSecIdx];
          // Remove the dragged chart first. If both are in the same section
          // and dragged was earlier, this shifts the base's index down by 1
          // — adjust before the replace.
          let baseIdx = pm.baseChartIdx;
          if (draggedSec) {
            draggedSec.charts.splice(pm.draggedChartIdx, 1);
            if (
              pm.baseSecIdx === pm.draggedSecIdx &&
              pm.draggedChartIdx < pm.baseChartIdx
            ) {
              baseIdx -= 1;
            }
          }
          if (baseSec && baseIdx >= 0 && baseIdx < baseSec.charts.length) {
            baseSec.charts.splice(baseIdx, 1, id);
            // Park the active-section focus on where the merged chart
            // landed so subsequent library adds land near it.
            store.activeSectionIdx = pm.baseSecIdx;
          } else if (baseSec) {
            // Defensive: indices stale (section reordered while modal open?).
            // Push to the end of the base section so the chart isn't lost.
            baseSec.charts.push(id);
          }
        } else {
          clampActiveSection();
          const target = state.sections[store.activeSectionIdx];
          if (target) target.charts.push(id);
        }
      }
      // Funnel telemetry: how often users create custom multi-source charts,
      // what scale modes (raw / rebase / dual-axis) they actually pick, and
      // which sources they combine. The source list lets us cross-check the
      // composition popularity signal against the library-add signal.
      track(
        ccModal.editingId
          ? "compose_custom_chart_edited"
          : ccModal.pendingMerge
            ? "compose_hover_merge_committed"
            : "compose_custom_chart_created",
        {
          sourceCount: sourceIds.length,
          mode,
          sources: packSourceIds(sourceIds),
        },
      );
      // Clear pendingMerge BEFORE closeCustomChartModal so the latter's
      // cancel-side reset is a no-op on the success path. (Both end up
      // null either way; this is just for readability.)
      ccModal.pendingMerge = null;
      writeUrl();
      renderComposition();
      closeCustomChartModal();
    });
  }


  return {
    openCustomChartModal,
    wireCustomChartModal,
    openMergeModal,
    renderCustomChartSources,
    renderCcModalTagChips,
  };
}