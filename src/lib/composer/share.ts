/**
 * Composed-state serialization for the composer: the "referenced inline defs"
 * collectors, the single-tile + full-dashboard share-URL writers, and the
 * URL-length warning / overflow banners.
 *
 * Extracted from compose.astro (Plan 2d). Built via a factory (like 2b's
 * createComposerGeoFilters) so it can close over the page's shell / baseUrl /
 * store state without importing the page module.
 *
 * `editingSlug` is read through a getter rather than captured: the page sets
 * it during URL hydration (hydrateFromUrl), which can run after this factory
 * is constructed, and the save flow can change it later.
 *
 * The referenced-inline collectors and buildComposedState are module-level
 * and exported: the page's "Save to my account" path calls buildComposedState
 * to serialize the SAME state object the share URL encodes, so the persisted
 * state_json can't drift from the ?d= URL state. (The Save path used to
 * hand-roll a subset that silently dropped inlineMaps and the per-section
 * defaultDelta / fixedRange windows.)
 */
import {
  encodeComposedState,
  type ComposedState,
  type InlineChart,
  type InlineMap,
  type InlineSource,
} from "../composer-state";
import type { DeltaWindow } from "../deltas";
import { isInlineId, isInlineMapId, isDerivedId } from "./ids";
import type { UIState, ChartOverride } from "./state";

export interface ShareUrlContext {
  /** The composer shell root — owns the URL-length / preview-link DOM. */
  shell: HTMLElement;
  /** Site base URL, for the /custom/?d= preview links. */
  baseUrl: string;
  /** The live composer state (store.state) — read-only in here. */
  state: UIState;
  /** Reads the current edit slug live (hydrate may set it after build). */
  getEditingSlug: () => string | null;
}

export interface ShareUrl {
  writeUrl: () => void;
  singleChartPreviewUrl: (chartId: string) => string;
}

// Collect only the inline-chart IDs that are actually referenced by some
// section, so removing a chart also prunes its orphaned inline spec.
function referencedInlineCharts(
  state: UIState,
): Record<string, InlineChart> | undefined {
  const refs: Record<string, InlineChart> = {};
  for (const sec of state.sections) {
    for (const cid of sec.charts) {
      if (isInlineId(cid) && state.inlineCharts[cid]) {
        refs[cid] = state.inlineCharts[cid];
      }
    }
  }
  return Object.keys(refs).length > 0 ? refs : undefined;
}

// Parallel to referencedInlineCharts but for inline maps. Drops any
// map spec whose ID isn't referenced by a section's chart list.
function referencedInlineMaps(
  state: UIState,
): Record<string, InlineMap> | undefined {
  const refs: Record<string, InlineMap> = {};
  for (const sec of state.sections) {
    for (const cid of sec.charts) {
      if (isInlineMapId(cid) && state.inlineMaps[cid]) {
        refs[cid] = state.inlineMaps[cid];
      }
    }
  }
  return Object.keys(refs).length > 0 ? refs : undefined;
}

// Walk the dashboard for transitive references to inline (derived)
// sources — any source ID with the derived: prefix used either by an
// inline chart's sources list or by another derived source's a/b.
// Drops entries that aren't reachable so renaming/removing a chart
// doesn't leave orphans in the saved state.
function referencedInlineSources(
  state: UIState,
): Record<string, InlineSource> | undefined {
  if (Object.keys(state.inlineSources).length === 0) return undefined;
  const reachable = new Set<string>();
  function visit(id: string): void {
    if (!isDerivedId(id)) return;
    if (reachable.has(id)) return;
    const spec = state.inlineSources[id];
    if (!spec) return;
    reachable.add(id);
    visit(spec.a);
    visit(spec.b);
  }
  // Seed from all inline-chart sources currently in use.
  for (const sec of state.sections) {
    for (const cid of sec.charts) {
      if (!isInlineId(cid)) continue;
      const ic = state.inlineCharts[cid];
      if (!ic) continue;
      for (const sid of ic.sources) visit(sid);
    }
  }
  if (reachable.size === 0) return undefined;
  const out: Record<string, InlineSource> = {};
  for (const id of reachable) out[id] = state.inlineSources[id];
  return out;
}

// Strip empty values from chart overrides, drop overrides for charts no
// longer referenced, and return undefined when nothing's left.
function referencedChartOverrides(
  state: UIState,
): Record<string, ChartOverride> | undefined {
  const referenced = new Set<string>();
  for (const sec of state.sections) for (const cid of sec.charts) referenced.add(cid);
  const refs: Record<string, ChartOverride> = {};
  for (const [cid, ov] of Object.entries(state.chartOverrides)) {
    if (!referenced.has(cid)) continue;
    const trimmed: ChartOverride = {};
    if (ov.title && ov.title.trim()) trimmed.title = ov.title.trim();
    if (ov.defaultDelta) trimmed.defaultDelta = ov.defaultDelta;
    if (ov.blurb && ov.blurb.trim()) trimmed.blurb = ov.blurb.trim();
    if (Object.keys(trimmed).length > 0) refs[cid] = trimmed;
  }
  return Object.keys(refs).length > 0 ? refs : undefined;
}

/**
 * Assemble the full composed-state object (everything except the version
 * stamp `v`). This is the ONE serializer shared by the share-URL writer
 * (writeUrl, below) and compose.astro's "Save to my account" handler, so the
 * persisted state_json is identical to the ?d= URL state. Undefined-valued
 * fields are dropped downstream: encodeComposedState strips them via a JSON
 * round-trip, and JSON.stringify drops them from the Supabase request body.
 */
export function buildComposedState(state: UIState): Omit<ComposedState, "v"> {
  const clean: Omit<ComposedState, "v"> = {
    title: state.title || undefined,
    description: state.description || undefined,
    defaultDelta: (state.defaultDelta || undefined) as DeltaWindow | undefined,
    fixedRange: state.fixedRange,
    sections: state.sections
      // Keep a section if it has charts OR a non-empty markdown
      // body (markdown-only narrative sections).
      .filter(
        (s) =>
          s.charts.length > 0 ||
          (s.markdown && s.markdown.trim().length > 0),
      )
      .map((s) => ({
        title: s.title,
        description: s.description || undefined,
        charts: [...s.charts],
        markdown:
          s.markdown && s.markdown.trim().length > 0 ? s.markdown : undefined,
        defaultDelta: s.defaultDelta,
        fixedRange: s.fixedRange,
      })),
    inlineCharts: referencedInlineCharts(state),
    inlineSources: referencedInlineSources(state),
    inlineMaps: referencedInlineMaps(state),
    chartOverrides: referencedChartOverrides(state),
  };
  if (!clean.sections || clean.sections.length === 0) delete clean.sections;
  if (!clean.inlineCharts) delete clean.inlineCharts;
  if (!clean.inlineSources) delete clean.inlineSources;
  if (!clean.inlineMaps) delete clean.inlineMaps;
  if (!clean.chartOverrides) delete clean.chartOverrides;
  return clean;
}

export function createShareUrl(ctx: ShareUrlContext): ShareUrl {
  const { shell, baseUrl, state, getEditingSlug } = ctx;

  // URL-length thresholds (chars of the FULL share URL, including
  // /custom/?d= prefix). Vercel + most CDNs start returning 414 at
  // ~14-16 KB; we leave headroom because the preview link adds the
  // /custom/?d= scaffolding on top of the encoded state.
  //   < SOFT          → no banner
  //   SOFT  .. HARD   → soft "getting long" banner; URL still written
  //   >= HARD         → hard overflow banner; URL NOT written (the
  //                     last small-enough URL stays in the bar, so a
  //                     refresh won't 414). The in-memory state still
  //                     has the new tiles, so the user sees them; the
  //                     banner explains that saving to account is the
  //                     way to persist past a refresh.
  const SHARE_URL_WARN_AT = 7000;
  const SHARE_URL_HARD_LIMIT = 12000;

  // Build a /custom/ preview URL scoped to a SINGLE tile: the same encoded
  // state the full Preview uses, but with `sections` collapsed to just this
  // one chart. Carries the full referenced inline defs so the chart's
  // sources/derived-sources/overrides all resolve; it's strictly smaller
  // than the full-dashboard preview (one section vs many, same defs), so it
  // can't overflow the share-URL limit when the main Preview didn't. Opened
  // in a new tab so the composer session is preserved.
  function singleChartPreviewUrl(chartId: string): string {
    // Carry the time window the user is viewing so the preview opens at
    // the same timeframe — not the chart's own defaultDelta. Effective
    // window = the chart's section setting if any, else the dashboard
    // default; a pinned fixedRange (which overrides defaultDelta) is
    // carried the same way. Without this, the single-tile preview lost
    // the dashboard timeframe and silently fell back to each chart's
    // own default — the reported mismatch.
    const owningSection = state.sections.find((s) =>
      s.charts.includes(chartId),
    );
    const effectiveDelta = ((owningSection?.defaultDelta as
      | DeltaWindow
      | undefined) || (state.defaultDelta || undefined)) as
      | DeltaWindow
      | undefined;
    const effectiveFixedRange = owningSection?.fixedRange ?? state.fixedRange;
    const clean: Omit<ComposedState, "v"> = {
      defaultDelta: effectiveDelta,
      fixedRange: effectiveFixedRange,
      sections: [
        {
          title: "",
          description: undefined,
          charts: [chartId],
          markdown: undefined,
          defaultDelta: undefined,
          fixedRange: undefined,
        },
      ],
      inlineCharts: referencedInlineCharts(state),
      inlineSources: referencedInlineSources(state),
      inlineMaps: referencedInlineMaps(state),
      chartOverrides: referencedChartOverrides(state),
    };
    if (!clean.defaultDelta) delete clean.defaultDelta;
    if (!clean.fixedRange) delete clean.fixedRange;
    if (!clean.inlineCharts) delete clean.inlineCharts;
    if (!clean.inlineSources) delete clean.inlineSources;
    if (!clean.inlineMaps) delete clean.inlineMaps;
    if (!clean.chartOverrides) delete clean.chartOverrides;
    return `${baseUrl}/custom/?d=${encodeComposedState(clean)}`;
  }

  function writeUrl(): void {
    const clean = buildComposedState(state);
    const encoded = encodeComposedState(clean);
    const url = new URL(window.location.href);
    if (Object.keys(clean).length === 0) {
      url.searchParams.delete("d");
    } else {
      url.searchParams.set("d", encoded);
    }
    const shareUrlLen = url.toString().length;

    const warnBanner = shell.querySelector<HTMLElement>("[data-role='url-warn']");
    const warnLen = shell.querySelector<HTMLElement>("[data-role='url-warn-len']");
    const overflowBanner = shell.querySelector<HTMLElement>("[data-role='url-overflow']");
    const overflowLen = shell.querySelector<HTMLElement>("[data-role='url-overflow-len']");
    const overflowCount = shell.querySelector<HTMLElement>("[data-role='url-overflow-count']");
    const previewLinks = shell.querySelectorAll<HTMLAnchorElement>("[data-role='preview-link']");
    const copyShareBtn = shell.querySelector<HTMLButtonElement>("[data-role='copy-share']");

    // Over the hard limit the URL bar keeps the LAST short-enough URL (see the
    // branch below), so Copy-link + Preview would silently share a dashboard
    // missing the tiles the user just added. Lock those two controls while
    // over the limit; "Save to my account" stays the working path (its button
    // lives outside this toggle). Re-enabled the moment the URL fits again.
    function setShareControlsOverflowed(overflowed: boolean): void {
      if (copyShareBtn) {
        copyShareBtn.disabled = overflowed;
        copyShareBtn.setAttribute("aria-disabled", overflowed ? "true" : "false");
        copyShareBtn.title = overflowed
          ? "This composition is too large to share by link. Save it to your account for a short /u/ link."
          : "";
      }
      previewLinks.forEach((el) => {
        if (overflowed) {
          el.setAttribute("aria-disabled", "true");
          el.setAttribute("tabindex", "-1");
          el.style.pointerEvents = "none";
          el.style.opacity = "0.5";
        } else {
          el.removeAttribute("aria-disabled");
          el.removeAttribute("tabindex");
          el.style.pointerEvents = "";
          el.style.opacity = "";
        }
      });
    }

    if (shareUrlLen >= SHARE_URL_HARD_LIMIT) {
      // Don't replaceState — keeps the last short-enough URL in the
      // bar so a refresh still loads SOMETHING (just an older
      // checkpoint). Don't update the preview link either, for the
      // same reason.
      if (warnBanner) warnBanner.hidden = true;
      if (overflowBanner) {
        overflowBanner.hidden = false;
        if (overflowLen) overflowLen.textContent = String(shareUrlLen);
        if (overflowCount) {
          const tiles = state.sections.reduce(
            (acc, s) => acc + s.charts.length, 0,
          );
          overflowCount.textContent = String(tiles);
        }
      }
      // Lock the share controls so the stale short URL can't be copied /
      // opened without the user knowing it's out of date.
      setShareControlsOverflowed(true);
      return;
    }

    window.history.replaceState(null, "", url.toString());
    // Under the limit (or never over it): the URL in the bar now reflects
    // the current state, so the share controls are safe to use again.
    setShareControlsOverflowed(false);
    if (previewLinks.length) {
      // When editing an existing saved dashboard, carry the edit slug
      // through to /custom/. Without this hand-off, Preview lands on
      // a fresh /custom/ that thinks it's a brand-new composition and
      // its Save button would insert a new row instead of updating
      // the original — bug the user reported as "Preview treats it
      // as a whole new dashboard."
      const slug = getEditingSlug();
      const editQuery = slug
        ? `&edit=${encodeURIComponent(slug)}`
        : "";
      const href = `${baseUrl}/custom/?d=${encoded}${editQuery}`;
      // There can be more than one (top toolbar + bottom "Show
      // dashboard" CTA); keep every preview link in sync.
      previewLinks.forEach((el) => {
        el.href = href;
      });
    }

    if (overflowBanner) overflowBanner.hidden = true;
    if (warnBanner) {
      if (shareUrlLen >= SHARE_URL_WARN_AT) {
        warnBanner.hidden = false;
        if (warnLen) warnLen.textContent = String(shareUrlLen);
      } else {
        warnBanner.hidden = true;
      }
    }
  }

  return {
    writeUrl,
    singleChartPreviewUrl,
  };
}
