/**
 * Composer state types + the single mutable store.
 *
 * Lifted from compose.astro's script-scope declarations (Plan 2c) so that the
 * per-feature modules extracted in 2d (sources-tab, cc-modal, ds-modal, maps,
 * generators, share) can import ONE shared store instead of closing over the
 * page's locals.
 *
 * Usage in compose.astro (the "alias trick" — keeps ~700 existing references
 * unchanged):
 *
 *   const store = createComposerStore();
 *   const state    = store.state;     // never reassigned → alias is safe
 *   const ccModal  = store.ccModal;   // (the 2d modules alias via ctx)
 *   const dsModal  = store.dsModal;
 *
 * The reassigned scalar (`activeSectionIdx`) is read/written as `store.x`
 * directly — it can't be aliased because reassigning a local wouldn't
 * propagate to the store (and vice-versa). (The old Sources-tab filter
 * scalars + libGeo left with Plan 3c — the lib SourcePicker island owns
 * its own search / tag / geo state.)
 *
 * `library` is intentionally NOT in the store yet: it stays a local `let` in
 * compose.astro (its `LibraryPayload` type lives there). 2d folds it in when a
 * module needs it.
 */
import type { DeltaWindow } from "../deltas";
import type { InlineChart, InlineMap, InlineSource } from "../composer-state";

export type ChartOverride = {
  title?: string;
  defaultDelta?: DeltaWindow;
  blurb?: string;
};

export interface UISection {
  title: string;
  description: string;
  charts: string[];
  /** Safe-subset markdown body. When charts is empty AND markdown is set, the
   *  section renders as a pure-markdown narrative block. */
  markdown?: string;
  defaultDelta?: DeltaWindow;
  fixedRange?: { start: string; end: string };
}

export interface UIState {
  title: string;
  description: string;
  defaultDelta: DeltaWindow | "";
  /** When set, takes precedence over defaultDelta; pinned [start, end]. */
  fixedRange?: { start: string; end: string };
  sections: UISection[];
  inlineCharts: Record<string, InlineChart>;
  inlineSources: Record<string, InlineSource>;
  /** Ad-hoc maps built in the Maps tab. Keyed by `inlinemap:<id>`. */
  inlineMaps: Record<string, InlineMap>;
  chartOverrides: Record<string, ChartOverride>;
}

/** Per-surface metro + country drill-down state. Only the modal states
 *  (ccModal.geo / dsModal.geo) carry one now — the Sources tab's copy left
 *  with Plan 3c (its SourcePicker island owns its own geo state). */
export interface GeoState {
  selectedMetroCbsa: string | null;
  selectedCountryCode: string | null;
  metroPopoverOpen: boolean;
  countryPopoverOpen: boolean;
  metroSearchQuery: string;
  countrySearchQuery: string;
}

export type CustomChartMode = "raw" | "rebase" | "dual-axis";
export type ChartCombineOp = "divide" | "sum" | "diff" | "multiply";

export interface CustomChartModalState {
  editingId: string | null;
  title: string;
  titleAuto: boolean;
  selected: Set<string>;
  selectedOrder: string[];
  search: string;
  mode: CustomChartMode;
  modeIsExplicit: boolean;
  rightAxisSources: Set<string>;
  op: ChartCombineOp | null;
  logScale: boolean;
  blurb: string;
  pickerTags: Set<string>;
  cdState: string | null;
  cdDistrict: string | null;
  geo: GeoState;
  percentDisplay: "percent" | "decimal" | "ratio" | undefined;
  transform: "level" | "yoy_pct" | "index_100";
  annotationsText: string;
  shading: string[];
  pendingMerge: {
    baseChartId: string;
    baseSecIdx: number;
    baseChartIdx: number;
    baseDefaultDelta: DeltaWindow | undefined;
    draggedChartId: string;
    draggedSecIdx: number;
    draggedChartIdx: number;
  } | null;
}

export interface DerivedModalState {
  name: string;
  op: "divide" | "sum" | "diff" | "multiply";
  a: string;
  b: string;
  aSearch: string;
  bSearch: string;
  addAsChart: boolean;
  pickerTags: Set<string>;
  cdState: string | null;
  cdDistrict: string | null;
  geo: GeoState;
}

/** Default sections for a fresh / reset composer. */
export const defaultSections = (): UISection[] => [
  { title: "Overview", description: "", charts: [] as string[] },
];

export const newGeoState = (): GeoState => ({
  selectedMetroCbsa: null,
  selectedCountryCode: null,
  metroPopoverOpen: false,
  countryPopoverOpen: false,
  metroSearchQuery: "",
  countrySearchQuery: "",
});

/** The composer's mutable state, in one object. See the module header for the
 *  alias-trick wiring in compose.astro. */
export interface ComposerStore {
  state: UIState;
  ccModal: CustomChartModalState;
  dsModal: DerivedModalState;
  activeSectionIdx: number;
}

export function createComposerStore(): ComposerStore {
  return {
    state: {
      title: "",
      description: "",
      defaultDelta: "",
      sections: defaultSections(),
      inlineCharts: {},
      inlineSources: {},
      inlineMaps: {},
      chartOverrides: {},
    },
    ccModal: {
      editingId: null,
      title: "",
      titleAuto: true,
      selected: new Set<string>(),
      selectedOrder: [],
      search: "",
      mode: "raw",
      modeIsExplicit: false,
      rightAxisSources: new Set<string>(),
      op: null,
      blurb: "",
      logScale: false,
      pickerTags: new Set<string>(),
      cdState: null,
      cdDistrict: null,
      geo: newGeoState(),
      percentDisplay: undefined,
      transform: "level",
      annotationsText: "",
      shading: [],
      pendingMerge: null,
    },
    dsModal: {
      name: "",
      op: "divide",
      a: "",
      b: "",
      aSearch: "",
      bSearch: "",
      addAsChart: true,
      pickerTags: new Set<string>(),
      cdState: null,
      cdDistrict: null,
      geo: newGeoState(),
    },
    activeSectionIdx: 0,
  };
}
