/**
 * Maps tab — the "build a tract / block-group map" form: indicator / vintage /
 * geo / state pickers, the d3 bbox-brush preview, and adding the finished map
 * to the dashboard as an inline map.
 *
 * Extracted from compose.astro (Plan 2d) via the create<Feature>(ctx) factory.
 * All mutable state (mapBuilder, the topojson cache, the wired guard) and the
 * static indicator/state lookup tables live inside the factory. No `library`
 * coupling. d3/topojson + nanoid/track come in as imports; everything that
 * crosses into the rest of the page (render, writeUrl, the rate-limit gate,
 * section clamp, escapeHtml) comes through ctx.
 */
import { geoAlbers, geoPath } from "d3-geo";
import { select as d3select } from "d3-selection";
import { brush as d3brush } from "d3-brush";
import { feature as topoFeature } from "topojson-client";
import { nanoid } from "nanoid";
import { track } from "../track";
import { INLINEMAP_PREFIX } from "./ids";
import type { InlineMap } from "../composer-state";
import type { UIState, ComposerStore } from "./state";

export interface MapsTabContext {
  shell: HTMLElement;
  state: UIState;
  store: ComposerStore;
  /** Topojson fetch cache — shared with the tile-preview thumbnails in compose. */
  mapBboxTopoCache: Map<string, unknown>;
  escapeHtml: (s: string) => string;
  renderComposition: () => void;
  writeUrl: () => void;
  checkComposeAction: (action: string) => Promise<boolean>;
  showSigninPrompt: (reason: string) => void;
  clampActiveSection: () => void;
}

export function createMapsTab(ctx: MapsTabContext) {
  const {
    shell,
    state,
    store,
    mapBboxTopoCache,
    escapeHtml,
    renderComposition,
    writeUrl,
    checkComposeAction,
    showSigninPrompt,
    clampActiveSection,
  } = ctx;
  // ---- Maps tab ---------------------------------------------------------
  //
  // The Maps tab is form-driven (not search-driven): the input set is
  // a 5-axis cross-product (indicator × vintage × geo × state × color)
  // plus an optional bbox. The form's values live in `mapBuilder`,
  // a module-scope state object that survives tab switches (the form
  // DOM gets re-shown without losing the user's progress).
  //
  // "Add map to dashboard" snapshots the current mapBuilder values
  // into a fresh `inlinemap:<id>` entry on `state.inlineMaps`, appends
  // the reference to the active section, and writes URL state. The
  // server-side `resolve-dashboard.ts` synthesizes a CollectionEntry
  // shape from the InlineMap spec; ChartMap.astro takes it from
  // there.

  type MapGeo = "state" | "county" | "tract" | "block-group";

  // 50 states + DC, matching the per-state data + topology coverage.
  const MAP_STATES: ReadonlyArray<readonly [string, string]> = [
    ["AL", "Alabama"], ["AK", "Alaska"], ["AZ", "Arizona"],
    ["AR", "Arkansas"], ["CA", "California"], ["CO", "Colorado"],
    ["CT", "Connecticut"], ["DE", "Delaware"], ["DC", "District of Columbia"],
    ["FL", "Florida"], ["GA", "Georgia"], ["HI", "Hawaii"],
    ["ID", "Idaho"], ["IL", "Illinois"], ["IN", "Indiana"],
    ["IA", "Iowa"], ["KS", "Kansas"], ["KY", "Kentucky"],
    ["LA", "Louisiana"], ["ME", "Maine"], ["MD", "Maryland"],
    ["MA", "Massachusetts"], ["MI", "Michigan"], ["MN", "Minnesota"],
    ["MS", "Mississippi"], ["MO", "Missouri"], ["MT", "Montana"],
    ["NE", "Nebraska"], ["NV", "Nevada"], ["NH", "New Hampshire"],
    ["NJ", "New Jersey"], ["NM", "New Mexico"], ["NY", "New York"],
    ["NC", "North Carolina"], ["ND", "North Dakota"], ["OH", "Ohio"],
    ["OK", "Oklahoma"], ["OR", "Oregon"], ["PA", "Pennsylvania"],
    ["RI", "Rhode Island"], ["SC", "South Carolina"],
    ["SD", "South Dakota"], ["TN", "Tennessee"], ["TX", "Texas"],
    ["UT", "Utah"], ["VT", "Vermont"], ["VA", "Virginia"],
    ["WA", "Washington"], ["WV", "West Virginia"],
    ["WI", "Wisconsin"], ["WY", "Wyoming"],
  ];

  const MAP_INDICATOR_LABELS: Record<string, string> = {
    // The original 4 — also the only indicators with county / tract /
    // block-group snapshots on disk (those come from direct Census API
    // calls in census_acs_choropleth.py).
    poverty_rate: "Poverty rate",
    median_hh_income: "Median household income",
    bachelors_plus_pct: "Bachelor's+ share (adults 25+)",
    foreign_born_pct: "Foreign-born share",
    // The rest — state-level only. Derived from acs_state time-series
    // by pipelines/census_acs_choropleth_derive_state.py.
    masters_plus_pct: "Master's+ share (adults 25+)",
    owner_occupied_pct: "Owner-occupied housing share",
    broadband_households_pct: "Broadband subscription share",
    median_gross_rent: "Median gross rent",
    median_home_value: "Median home value",
    households_no_vehicle_pct: "Households with no vehicle",
    workers_wfh_pct: "Work-from-home workers",
    median_commute_minutes: "Median one-way commute",
    population_65_plus_pct: "Share of population 65+",
    population_under_18_pct: "Share of population under 18",
    median_age: "Median age",
    movers_last_year_pct: "Moved in the last year",
    born_same_state_pct: "Born in current state",
    people_with_disability_pct: "People with a disability",
    veterans_pct: "Veterans (adults 18+)",
    population: "Total population",
  };

  // Earliest vintage with derived snapshot data, per indicator.
  // The original 4 are filled all the way back to 2010 by direct
  // census_acs_choropleth.py API calls. The rest come from
  // census_acs_choropleth_derive_state.py (state-only) and bottom
  // out at the earliest year their numerator + denominator series
  // were published. The slider in the Maps tab gets clamped to the
  // selected indicator's min so the user doesn't pick a vintage that
  // would render an empty chart.
  const MAP_INDICATOR_MIN_VINTAGE: Record<string, string> = {
    poverty_rate: "2010",
    median_hh_income: "2010",
    bachelors_plus_pct: "2010",
    foreign_born_pct: "2010",
    masters_plus_pct: "2017",
    owner_occupied_pct: "2017",
    broadband_households_pct: "2017",
    median_gross_rent: "2017",
    median_home_value: "2017",
    households_no_vehicle_pct: "2015",
    workers_wfh_pct: "2015",
    median_commute_minutes: "2015",
    median_age: "2015",
    population_65_plus_pct: "2017",
    population_under_18_pct: "2017",
    movers_last_year_pct: "2015",
    born_same_state_pct: "2017",
    people_with_disability_pct: "2015",
    veterans_pct: "2017",
    population: "2017",
  };

  // Which indicators are available at each geography level. State has
  // the full deck; county / tract / block-group are limited to the 4
  // that census_acs_choropleth.py fetches directly from the API.
  const MAP_INDICATORS_BY_GEO: Record<string, string[]> = {
    state: [
      "poverty_rate",
      "median_hh_income",
      "bachelors_plus_pct",
      "masters_plus_pct",
      "foreign_born_pct",
      "owner_occupied_pct",
      "broadband_households_pct",
      "median_gross_rent",
      "median_home_value",
      "households_no_vehicle_pct",
      "workers_wfh_pct",
      "median_commute_minutes",
      "median_age",
      "population_65_plus_pct",
      "population_under_18_pct",
      "movers_last_year_pct",
      "born_same_state_pct",
      "people_with_disability_pct",
      "veterans_pct",
      "population",
    ],
    county: [
      "poverty_rate",
      "median_hh_income",
      "bachelors_plus_pct",
      "foreign_born_pct",
    ],
    tract: [
      "poverty_rate",
      "median_hh_income",
      "bachelors_plus_pct",
      "foreign_born_pct",
    ],
    "block-group": [
      // BG only — Census publishes a much narrower set of indicators at
      // block-group resolution. poverty_rate and foreign_born_pct aren't
      // published at this level (the API returns nulls).
      "median_hh_income",
      "bachelors_plus_pct",
    ],
  };

  interface MapBuilderState {
    indicator: string;
    vintage: string;
    geo: MapGeo;
    /** Selected state codes (uppercase 2-letter) for tract/BG geos.
     *  Empty for state/county. Capped at 4 to keep regional bundles
     *  (DMV, NY-tri-state, SF-Bay-area, Bos-Wash corridor) inside a
     *  reasonable payload — four state TopoJSONs at tract resolution
     *  is ~40-60MB raw, ~10-15MB gzipped, which is the upper bound
     *  we want to ship to a tile. */
    states: string[];
    colorScheme: string;
    colorScale: "linear" | "log";
    bbox: [number, number, number, number] | null;
    customTitle: string;
  }

  // Cap on number of states the multi-select accepts. Beyond ~4 the
  // boundary payload + render time degrade noticeably; the user can
  // always switch to county geo (US-wide) for broader coverage.
  const MAP_MAX_STATES = 4;

  const mapBuilder: MapBuilderState = {
    indicator: "poverty_rate",
    vintage: "2022",
    geo: "county",
    states: ["VA"],
    colorScheme: "viridis",
    colorScale: "linear",
    bbox: null,
    customTitle: "",
  };

  // First tab-switch into "maps" wires up event listeners. Subsequent
  // switches re-call renderMapBuilder() which is a no-op past this point;
  // the form DOM retains its values.
  let mapBuilderWired = false;

  // Monotonic cancellation token for in-flight bbox previews. Each new
  // selection (via updateMapBuilderUI) and each renderMapBboxPreview entry
  // bumps it; a preview whose captured token is stale bails before it can
  // overwrite the current preview or wire a brush with a stale projection.
  let bboxPreviewGen = 0;

  function defaultMapTitle(): string {
    const ind = MAP_INDICATOR_LABELS[mapBuilder.indicator] ?? mapBuilder.indicator;
    if (mapBuilder.geo === "state" || mapBuilder.geo === "county") {
      const geoLabel = mapBuilder.geo === "state" ? "state" : "county";
      return `${ind} by ${geoLabel} — US (${mapBuilder.vintage})`;
    }
    const geoLabel = mapBuilder.geo === "block-group" ? "block group" : "tract";
    if (mapBuilder.states.length === 0) {
      return `${ind} by ${geoLabel} — pick a state (${mapBuilder.vintage})`;
    }
    // Multi-state titles use the state codes joined by "+" to keep the
    // tile heading scannable (e.g., "Poverty rate by tract — VA+MD+DC
    // (2022)"). Single-state uses the full state name for readability.
    const regionName =
      mapBuilder.states.length === 1
        ? (MAP_STATES.find(([c]) => c === mapBuilder.states[0])?.[1]
            ?? mapBuilder.states[0])
        : mapBuilder.states.join("+");
    return `${ind} by ${geoLabel} — ${regionName} (${mapBuilder.vintage})`;
  }

  function updateMapBboxReadout(): void {
    const readout = shell.querySelector<HTMLElement>(
      "[data-role='map-bbox-readout']",
    );
    if (!readout) return;
    if (!mapBuilder.bbox) {
      readout.textContent = "No area selected — full state shown";
      return;
    }
    const [w, s, e, n] = mapBuilder.bbox;
    readout.textContent =
      `bbox: W ${w.toFixed(2)}° S ${s.toFixed(2)}° E ${e.toFixed(2)}° N ${n.toFixed(2)}°`;
  }

  function renderMapIndicatorOptions(): void {
    const sel = shell.querySelector<HTMLSelectElement>(
      "[data-role='map-indicator']",
    );
    const info = shell.querySelector<HTMLElement>(
      "[data-role='map-indicator-info']",
    );
    if (!sel) return;
    const supported =
      MAP_INDICATORS_BY_GEO[mapBuilder.geo] ?? MAP_INDICATORS_BY_GEO.state;
    // If the current selection isn't available at this geo, fall back
    // to the first supported option. (E.g. user picks `median_age` at
    // state, then switches geo to county — median_age has no county
    // data, so reset to poverty_rate.)
    if (!supported.includes(mapBuilder.indicator)) {
      mapBuilder.indicator = supported[0];
    }
    sel.innerHTML = supported
      .map(
        (id) =>
          `<option value="${id}">${escapeHtml(MAP_INDICATOR_LABELS[id] ?? id)}</option>`,
      )
      .join("");
    sel.value = mapBuilder.indicator;
    if (info) {
      if (mapBuilder.geo === "state") {
        info.textContent = `${supported.length} indicators available at state level.`;
      } else if (mapBuilder.geo === "block-group") {
        info.textContent =
          "Census only publishes 2 of these indicators at block-group resolution.";
      } else {
        info.textContent = `${supported.length} indicators available at ${mapBuilder.geo} level. Switch to State for the full set.`;
      }
    }
    // Clamp the vintage slider's min so picking a later-starting
    // indicator can't yield an empty-data render.
    const vintageInput = shell.querySelector<HTMLInputElement>(
      "[data-role='map-vintage']",
    );
    const vintageReadout = shell.querySelector<HTMLElement>(
      "[data-role='map-vintage-readout']",
    );
    if (vintageInput) {
      const minVintage =
        MAP_INDICATOR_MIN_VINTAGE[mapBuilder.indicator] ?? "2010";
      vintageInput.min = minVintage;
      if (parseInt(mapBuilder.vintage, 10) < parseInt(minVintage, 10)) {
        mapBuilder.vintage = minVintage;
        vintageInput.value = minVintage;
        if (vintageReadout) vintageReadout.textContent = minVintage;
      }
    }
  }

  function updateMapBuilderUI(): void {
    // A selection changed — invalidate any in-flight bbox preview so a
    // slow stale topology fetch can't clobber the fresh one.
    bboxPreviewGen++;
    const needsState =
      mapBuilder.geo === "tract" || mapBuilder.geo === "block-group";
    const stateField = shell.querySelector<HTMLElement>(
      "[data-role='map-state-field']",
    );
    if (stateField) stateField.hidden = !needsState;
    const warning = shell.querySelector<HTMLElement>(
      "[data-role='map-geo-warning']",
    );
    if (warning) warning.hidden = !needsState;
    // Rebuild the indicator dropdown for the current geo. Done before
    // the title placeholder lookup so defaultMapTitle() picks up the
    // (potentially reset) indicator label.
    renderMapIndicatorOptions();
    // Refresh the auto-title placeholder so the user sees what the
    // default would be at a glance.
    const titleInput = shell.querySelector<HTMLInputElement>(
      "[data-role='map-title']",
    );
    if (titleInput) titleInput.placeholder = defaultMapTitle();
    // If the bbox preview is currently open, re-render it with the new
    // state/geo selection.
    const bboxDetails = shell.querySelector<HTMLDetailsElement>(
      "[data-role='map-bbox-details']",
    );
    if (bboxDetails && bboxDetails.open) {
      void renderMapBboxPreview();
    }
    updateMapBboxReadout();
  }

  async function renderMapBboxPreview(): Promise<void> {
    // Capture a cancellation token. If a newer selection (or preview) bumps
    // bboxPreviewGen while this one awaits the topology fetch, the post-await
    // guard below bails so we never overwrite the current preview or wire a
    // brush with a stale projection.
    const gen = ++bboxPreviewGen;
    const preview = shell.querySelector<HTMLElement>(
      "[data-role='map-bbox-preview']",
    );
    if (!preview) return;
    const needsState =
      mapBuilder.geo === "tract" || mapBuilder.geo === "block-group";
    if (!needsState) {
      preview.innerHTML =
        '<p class="muted small">bbox is only useful at tract or block-group resolution. State and county maps already cover the whole area at a glance.</p>';
      return;
    }
    preview.innerHTML = '<p class="muted small">Loading state outlines…</p>';
    // Always use the TRACT topology for the preview, even when the user
    // picked block-group — tracts are 1/5 the size, render fast, and give
    // the same sense of state shape for drawing. ALL selected states are
    // loaded and fit into one preview, so adding a state (Ctrl-click)
    // expands the drawable area to match the actual coverage; the bbox
    // clips features from every selected state at render time.
    const previewStates = mapBuilder.states;
    if (previewStates.length === 0) {
      preview.innerHTML =
        '<p class="muted small">Pick at least one state above to enable bbox drawing.</p>';
      return;
    }
    // Topojson and d3-geo types are picky about Topology<Objects<...>>
    // generics; the JSON we ship is plain JSON, so the casts are
    // unavoidable. Fetch each selected state's tracts (cached per state)
    // and concatenate the features for a combined-extent preview. A
    // state whose topology fails to load is skipped rather than aborting
    // the whole preview.
    const featureGroups = await Promise.all(
      previewStates.map(async (st) => {
        const topoUrl = `/maps/${st.toLowerCase()}-tracts-topo.json`;
        let topo = mapBboxTopoCache.get(topoUrl) as
          | { type: "Topology"; objects: Record<string, unknown>; arcs: unknown[] }
          | undefined;
        if (!topo) {
          try {
            const resp = await fetch(topoUrl);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            topo = await resp.json();
            mapBboxTopoCache.set(topoUrl, topo);
          } catch {
            return null;
          }
        }
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const fc = topoFeature(topo as any, (topo as any).objects.tracts) as
          unknown as { features: unknown[] };
        return fc.features;
      }),
    );
    // A newer selection superseded this preview while the topology was
    // fetching — bail before any DOM write / brush wiring.
    if (gen !== bboxPreviewGen) return;
    const features = featureGroups
      .filter((g): g is unknown[] => g !== null)
      .flat();
    if (features.length === 0) {
      preview.innerHTML =
        `<p class="muted small">Could not load topology for ${previewStates.join(", ")}.</p>`;
      return;
    }
    const width = 360, height = 280;
    const combinedFc = { type: "FeatureCollection", features };
    const projection = geoAlbers().fitSize([width, height], combinedFc as never);
    const pathGen = geoPath(projection);

    preview.innerHTML = "";
    const svgEl = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svgEl.setAttribute("width", String(width));
    svgEl.setAttribute("height", String(height));
    svgEl.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svgEl.classList.add("map-bbox-svg");
    preview.appendChild(svgEl);
    const tractsG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    svgEl.appendChild(tractsG);
    for (const f of (features as Array<{ id?: string }>)) {
      const d = pathGen(f as never);
      if (!d) continue;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      path.setAttribute("fill", "#eef0f3");
      path.setAttribute("stroke", "#cbd0d5");
      path.setAttribute("stroke-width", "0.3");
      tractsG.appendChild(path);
    }
    const brushG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    brushG.classList.add("map-bbox-brush");
    svgEl.appendChild(brushG);

    const brush = d3brush()
      .extent([[0, 0], [width, height]])
      .on("end", (event: { selection?: [[number, number], [number, number]] }) => {
        if (!event.selection) {
          mapBuilder.bbox = null;
          updateMapBboxReadout();
          return;
        }
        const [[x0, y0], [x1, y1]] = event.selection;
        // y0 is the TOP edge of the brush rectangle (smaller pixel y =
        // higher latitude). projection.invert([px, py]) returns [lng, lat].
        const tl = projection.invert?.([x0, y0]);
        const br = projection.invert?.([x1, y1]);
        if (!tl || !br) return;
        const [west, north] = tl;
        const [east, south] = br;
        mapBuilder.bbox = [
          Math.min(west, east),
          Math.min(south, north),
          Math.max(west, east),
          Math.max(south, north),
        ];
        updateMapBboxReadout();
      });
    d3select(brushG as unknown as Element).call(
      brush as unknown as (s: unknown) => unknown,
    );
    // Restore prior brush selection if a bbox was previously set.
    if (mapBuilder.bbox) {
      const [w, s, e, n] = mapBuilder.bbox;
      const tl = projection([w, n]);
      const br = projection([e, s]);
      if (tl && br) {
        brush.move(
          d3select(brushG as unknown as Element) as unknown as never,
          [[tl[0], tl[1]], [br[0], br[1]]] as never,
        );
      }
    }
  }

  function renderMapBuilder(): void {
    if (mapBuilderWired) {
      updateMapBuilderUI();
      return;
    }
    mapBuilderWired = true;

    // Populate state multi-select.
    const stateSelect = shell.querySelector<HTMLSelectElement>(
      "[data-role='map-state']",
    );
    const stateReadout = shell.querySelector<HTMLElement>(
      "[data-role='map-state-readout']",
    );
    function syncStateSelectFromBuilder(): void {
      if (!stateSelect) return;
      const selected = new Set(mapBuilder.states);
      Array.from(stateSelect.options).forEach((opt) => {
        opt.selected = selected.has(opt.value);
      });
      if (stateReadout) {
        if (mapBuilder.states.length === 0) {
          stateReadout.textContent = "No states selected.";
        } else if (mapBuilder.states.length === 1) {
          const name =
            MAP_STATES.find(([c]) => c === mapBuilder.states[0])?.[1]
              ?? mapBuilder.states[0];
          stateReadout.textContent = `Selected: ${name}.`;
        } else {
          stateReadout.textContent =
            `Selected: ${mapBuilder.states.join(", ")} (${mapBuilder.states.length} of ${MAP_MAX_STATES} max).`;
        }
      }
    }
    if (stateSelect) {
      stateSelect.innerHTML = MAP_STATES.map(
        ([code, name]) => `<option value="${code}">${name}</option>`,
      ).join("");
      syncStateSelectFromBuilder();
    }

    // Wire each form input.
    const indicatorSel = shell.querySelector<HTMLSelectElement>(
      "[data-role='map-indicator']",
    );
    if (indicatorSel) {
      indicatorSel.value = mapBuilder.indicator;
      indicatorSel.addEventListener("change", () => {
        mapBuilder.indicator = indicatorSel.value;
        updateMapBuilderUI();
      });
    }
    if (stateSelect) {
      stateSelect.addEventListener("change", () => {
        const picked = Array.from(stateSelect.selectedOptions).map(
          (o) => o.value,
        );
        if (picked.length > MAP_MAX_STATES) {
          // User over-selected — keep the first N (in option-list
          // order), then push the trimmed set back to the <select> so
          // the cap is visible. The native multi-select doesn't have
          // a "disable past N" mode; rebuilding the selection here is
          // the cheapest fix.
          mapBuilder.states = picked.slice(0, MAP_MAX_STATES);
          syncStateSelectFromBuilder();
          if (stateReadout) {
            stateReadout.textContent =
              `${MAP_MAX_STATES}-state max — extras unselected.`;
          }
        } else {
          mapBuilder.states = picked;
          syncStateSelectFromBuilder();
        }
        // State set changes invalidate any drawn bbox (different coords).
        mapBuilder.bbox = null;
        updateMapBuilderUI();
      });
    }

    // Region-preset chips. Each carries a comma-separated state list
    // in data-states; clicking pushes it through the same set/cap path
    // as the multi-select to keep validation centralized.
    shell.querySelectorAll<HTMLButtonElement>(
      "[data-role='map-region-preset']",
    ).forEach((chip) => {
      chip.addEventListener("click", () => {
        const raw = (chip.dataset.states ?? "").trim();
        if (!raw) return;
        const picks = raw
          .split(",")
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean)
          .slice(0, MAP_MAX_STATES);
        mapBuilder.states = picks;
        mapBuilder.bbox = null;
        syncStateSelectFromBuilder();
        updateMapBuilderUI();
        track("compose_map_region_preset_picked", {
          label: chip.textContent ?? "",
          states: picks.join(","),
        });
      });
    });
    const colorSel = shell.querySelector<HTMLSelectElement>(
      "[data-role='map-color-scheme']",
    );
    if (colorSel) {
      colorSel.value = mapBuilder.colorScheme;
      colorSel.addEventListener("change", () => {
        mapBuilder.colorScheme = colorSel.value;
      });
    }
    shell.querySelectorAll<HTMLInputElement>(
      "input[data-role='map-geo']",
    ).forEach((el) => {
      if (el.value === mapBuilder.geo) el.checked = true;
      el.addEventListener("change", () => {
        if (el.checked) {
          mapBuilder.geo = el.value as MapGeo;
          // Geo change invalidates any drawn bbox: a tract-scale bbox
          // would filter a county/state map to near-empty, and the coords
          // differ per projection. Mirror the state-select handler.
          mapBuilder.bbox = null;
          updateMapBuilderUI();
        }
      });
    });
    shell.querySelectorAll<HTMLInputElement>(
      "input[data-role='map-scale']",
    ).forEach((el) => {
      if (el.value === mapBuilder.colorScale) el.checked = true;
      el.addEventListener("change", () => {
        if (el.checked) {
          mapBuilder.colorScale = el.value as "linear" | "log";
        }
      });
    });
    const vintageInput = shell.querySelector<HTMLInputElement>(
      "[data-role='map-vintage']",
    );
    const vintageReadout = shell.querySelector<HTMLElement>(
      "[data-role='map-vintage-readout']",
    );
    if (vintageInput && vintageReadout) {
      vintageInput.value = mapBuilder.vintage;
      vintageReadout.textContent = mapBuilder.vintage;
      vintageInput.addEventListener("input", () => {
        mapBuilder.vintage = vintageInput.value;
        vintageReadout.textContent = vintageInput.value;
        updateMapBuilderUI();
      });
    }
    const titleInput = shell.querySelector<HTMLInputElement>(
      "[data-role='map-title']",
    );
    if (titleInput) {
      titleInput.value = mapBuilder.customTitle;
      titleInput.addEventListener("input", () => {
        mapBuilder.customTitle = titleInput.value;
      });
    }
    // BBox: render on first details-open. The preview is heavy (~360px
    // svg + a few thousand tract polygons for big states) so lazy-load
    // it rather than always rendering.
    const bboxDetails = shell.querySelector<HTMLDetailsElement>(
      "[data-role='map-bbox-details']",
    );
    if (bboxDetails) {
      bboxDetails.addEventListener("toggle", () => {
        if (bboxDetails.open) void renderMapBboxPreview();
      });
    }
    const bboxClear = shell.querySelector<HTMLButtonElement>(
      "[data-role='map-bbox-clear']",
    );
    if (bboxClear) {
      bboxClear.addEventListener("click", () => {
        mapBuilder.bbox = null;
        // Re-render so the brush rectangle disappears too.
        void renderMapBboxPreview();
      });
    }
    const addBtn = shell.querySelector<HTMLButtonElement>(
      "[data-role='map-add-btn']",
    );
    if (addBtn) {
      addBtn.addEventListener("click", async () => {
        // Guard against a double-click appending two identical maps (and
        // burning two anon rate-limit actions). Disable while in flight,
        // re-enable once addMapToDashboard settles.
        if (addBtn.disabled) return;
        addBtn.disabled = true;
        try {
          await addMapToDashboard();
        } finally {
          addBtn.disabled = false;
        }
      });
    }

    updateMapBuilderUI();
  }

  async function addMapToDashboard(): Promise<void> {
    clampActiveSection();
    const target = state.sections[store.activeSectionIdx];
    if (!target) return;
    const needsState =
      mapBuilder.geo === "tract" || mapBuilder.geo === "block-group";
    // Validate the state selection BEFORE consuming the rate-limit gate,
    // so an invalid submit (no state picked for a tract/block-group map)
    // never burns an anon action or pops a spurious sign-in prompt.
    if (needsState && mapBuilder.states.length === 0) {
      alert("Pick at least one state for a tract or block-group map.");
      return;
    }
    const allowed = await checkComposeAction("add_map_to_dashboard");
    if (!allowed) {
      showSigninPrompt("add_map_to_dashboard");
      return;
    }
    const mapId = INLINEMAP_PREFIX + nanoid(8);
    const title = mapBuilder.customTitle.trim() || defaultMapTitle();
    // Single-state tract/BG: keep `state` for back-compat (existing
    // saved dashboards + the map renderer's pre-multi paths
    // both read state when states[] is absent). Multi-state: set
    // states[] and leave boundaryFile undefined so the renderer
    // derives one `/maps/<st>-<seg>-topo.json` per state and merges
    // the FeatureCollections client-side.
    const entry: InlineMap = {
      title,
      geo: mapBuilder.geo,
      indicator: mapBuilder.indicator,
      vintage: mapBuilder.vintage,
      // Only tract/block-group maps carry a bbox. A state or county map must
      // never inherit a stale bbox (from a prior tract selection) that would
      // filter it to near-empty.
      bbox: needsState ? (mapBuilder.bbox ?? undefined) : undefined,
      colorScheme: mapBuilder.colorScheme,
      colorScale: mapBuilder.colorScale,
    };
    if (needsState) {
      if (mapBuilder.states.length === 1) {
        entry.state = mapBuilder.states[0];
        // boundaryFile kept for back-compat — existing /u/<slug>/
        // dashboards reference state-specific boundary URLs and the
        // single-state pre-multi render path still uses it.
        entry.boundaryFile =
          mapBuilder.geo === "block-group"
            ? `/maps/${mapBuilder.states[0].toLowerCase()}-block-groups-topo.json`
            : `/maps/${mapBuilder.states[0].toLowerCase()}-tracts-topo.json`;
      } else {
        entry.states = [...mapBuilder.states];
        // boundaryFile intentionally absent — ChartMap derives
        // per-state URLs from states[] when the explicit file isn't
        // set and merges the topologies client-side.
      }
    }
    state.inlineMaps[mapId] = entry;
    target.charts.push(mapId);
    writeUrl();
    renderComposition();
    track("compose_map_added", {
      indicator: mapBuilder.indicator,
      geo: mapBuilder.geo,
      vintage: mapBuilder.vintage,
      states: needsState ? mapBuilder.states.join(",") : "",
      stateCount: needsState ? mapBuilder.states.length : 0,
      hasBbox: mapBuilder.bbox != null,
    });
    // Reset custom title so the next add gets the auto-generated default.
    mapBuilder.customTitle = "";
    if (titleInputForReset()) titleInputForReset()!.value = "";
  }

  function titleInputForReset(): HTMLInputElement | null {
    return shell.querySelector<HTMLInputElement>("[data-role='map-title']");
  }


  return { renderMapBuilder };
}