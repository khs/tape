/**
 * Sources / Charts library tab (Plan 2d) -- the left-rail "Sources" + "Charts"
 * browsing UI on the compose page (the "lib" surface). Owns the tag-filter
 * strips, the filtered source/chart universes, the result-list renderers, the
 * source-hint chips (engageHintChip), and the tab switcher (setActiveLibTab).
 *
 * Extracted from compose.astro via createSourcesTab(ctx). The geo filter
 * predicates (passes*) come from geo-filter via ctx; the geo strip lives in
 * geo-chips.ts. geoSurfaceConfig STAYS in compose and calls renderSourcesList /
 * renderTagFiltersSources for the lib surface, so those are exported. Adding a
 * source/chart as a tile (addChart / addSourceAsChart) and switching to the
 * Maps / Generators tabs (renderMapBuilder / renderGeneratorsBuilder) come via
 * ctx. chartsSelectedTags is owned here; chartsSearchQuery is read through a
 * getter (compose wire() owns the input); sourcesSelectedTags stays in compose
 * (geoSurfaceConfig reads it). library is read via getLibrary() per fn.
 */
import { track } from "../track";
import {
  CD_TAG,
  STATE_TAG,
  parseCdSourceId,
  parseStateSourceId,
  formatCdShortLabel,
} from "../congressional-districts";
import { METRO_TAG } from "../geographic-regions";
import { COUNTRY_TAG } from "../countries";
import type { ComposerStore, GeoState } from "./state";
import type { LibraryPayload, LibrarySource, LibraryChart } from "./library";
import type { ComposerGeoFilters } from "./geo-filter";

type LibTab = "sources" | "charts" | "maps" | "generators";

export interface SourcesTabContext {
  shell: HTMLElement;
  store: ComposerStore;
  getLibrary: () => LibraryPayload | null;
  getChartsSearchQuery: () => string;
  sourcesSelectedTags: Set<string>;
  libGeo: GeoState;
  passesCdFilter: ComposerGeoFilters["passesCdFilter"];
  passesMetroFilter: ComposerGeoFilters["passesMetroFilter"];
  passesCountryFilter: ComposerGeoFilters["passesCountryFilter"];
  passesCountyFilter: ComposerGeoFilters["passesCountyFilter"];
  escapeHtml: (s: string) => string;
  addChart: (chartId: string) => Promise<void>;
  addSourceAsChart: (sourceId: string) => Promise<void>;
  renderMapBuilder: () => void;
  renderGeneratorsBuilder: () => void;
}

export function createSourcesTab(ctx: SourcesTabContext) {
  const {
    shell,
    store,
    getLibrary,
    getChartsSearchQuery,
    sourcesSelectedTags,
    libGeo,
    passesCdFilter,
    passesMetroFilter,
    passesCountryFilter,
    passesCountyFilter,
    escapeHtml,
    addChart,
    addSourceAsChart,
    renderMapBuilder,
    renderGeneratorsBuilder,
  } = ctx;
  // Charts-tab topical tag selection (cluster-internal). The Sources-tab
  // equivalent (sourcesSelectedTags) stays in compose -- geoSurfaceConfig reads
  // it for the CD chip gate -- and arrives via ctx.
  const chartsSelectedTags: Set<string> = new Set<string>();
  function allChartTags(): string[] {
    const library = getLibrary();
    if (!library) return [];
    const s = new Set<string>();
    for (const c of library.charts) for (const t of c.tags) s.add(t);
    return [...s].sort();
  }

  function allSourceTags(): string[] {
    const library = getLibrary();
    if (!library) return [];
    const s = new Set<string>();
    for (const id of Object.keys(library.sources)) {
      const src = library.sources[id] as LibrarySource & { tags?: string[] };
      for (const t of src.tags ?? []) {
        // Hide synthetic metro tags from the tag-pill strip — they're
        // surfaced through the dedicated Metro chip + dropdown instead.
        // Filters both the bare `metro` tag and per-CBSA `metro:35620`
        // entries; users still see them via the geo chip's UI.
        if (t === METRO_TAG || t.startsWith(`${METRO_TAG}:`)) continue;
        // Same idea for country/region synthetic tags — surfaced via
        // the "Countries & regions" chip, not the topical pill strip.
        if (t === COUNTRY_TAG || t.startsWith(`${COUNTRY_TAG}:`)) continue;
        s.add(t);
      }
    }
    return [...s].sort();
  }

  function filteredCharts(): LibraryChart[] {
    const library = getLibrary();
    if (!library) return [];
    const q = getChartsSearchQuery().trim().toLowerCase();
    const tagsRequired = [...chartsSelectedTags];
    return library.charts.filter((c) => {
      // Multi-tag: every selected tag must be present (AND).
      for (const t of tagsRequired) {
        if (!c.tags.includes(t)) return false;
      }
      if (q) {
        // Server pre-built searchText (lowercased) when available; otherwise
        // synthesize from id/title/tags.
        const hay =
          (c as LibraryChart & { searchText?: string }).searchText ??
          (c.title + " " + c.id + " " + c.tags.join(" ")).toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  // Parallel to filteredCharts but over the source universe. Sources
  // have tags + searchText set on the server by library.json.ts; we
  // mirror the AND-across-tags / case-insensitive search semantics.
  function filteredSources(): (LibrarySource & {
    id: string;
    tags: string[];
    searchText: string;
  })[] {
    const library = getLibrary();
    if (!library) return [];
    const q = store.sourcesSearchQuery.trim().toLowerCase();
    // CD_TAG in the selected set is the master "States & districts" chip
    // toggle, not a literal tag a source must carry — passesCdFilter
    // already enforces the geo gate. State-level sources have STATE_TAG
    // (not CD_TAG), so leaving CD_TAG in the AND list rejects them.
    const tagsRequired = [...sourcesSelectedTags].filter((t) => t !== CD_TAG);
    const out: (LibrarySource & {
      id: string;
      tags: string[];
      searchText: string;
    })[] = [];
    for (const id of Object.keys(library.sources)) {
      const src = library.sources[id] as LibrarySource & {
        id?: string;
        tags?: string[];
        searchText?: string;
      };
      const tags = src.tags ?? [];
      // CD-visibility gate runs before tag-AND so that a user with the CD
      // chip off never sees any CD source, regardless of what other tag
      // chips they've selected.
      if (
        !passesCdFilter(
          id,
          tags,
          sourcesSelectedTags,
          store.sourcesCdState,
          store.sourcesCdDistrict,
          q,
        )
      ) {
        continue;
      }
      let ok = true;
      for (const t of tagsRequired) {
        if (!tags.includes(t)) {
          ok = false;
          break;
        }
      }
      if (!ok) continue;
      if (!passesMetroFilter(tags, libGeo.selectedMetroCbsa, q)) continue;
      if (!passesCountryFilter(tags, libGeo.selectedCountryCode, q)) continue;
      if (!passesCountyFilter(id, tags, q)) continue;
      // Synthetic geo-discovery hints (kind === "hint"): drop when
      // the query is empty so they don't clutter an unprompted browse.
      // When a query exists, they share the same text-search match
      // logic as real sources — their server-built searchText
      // intentionally covers every series name available at the
      // hint's level plus level-name synonyms.
      if (src.kind === "hint" && !q) continue;
      if (q) {
        const hay =
          src.searchText ??
          (src.name + " " + (src.shortName ?? "") + " " + id + " " + tags.join(" "))
            .toLowerCase();
        if (!hay.includes(q)) continue;
      }
      out.push({
        ...src,
        id,
        tags,
        searchText: src.searchText ?? "",
      });
    }
    // Source-picker ordering: by name. The categoryLabel-style folder
    // grouping used for charts doesn't help much for sources whose IDs
    // are mostly pipeline/<ticker> — a flat alphabetical list reads
    // cleaner. Hint cards stay together at the TOP regardless of
    // the alphabetical sort below, ordered by the hint.order field
    // (country → state → cd → metro → county → tract → bg).
    out.sort((a, b) => {
      const aIsHint = a.kind === "hint";
      const bIsHint = b.kind === "hint";
      if (aIsHint && !bIsHint) return -1;
      if (bIsHint && !aIsHint) return 1;
      if (aIsHint && bIsHint) {
        const ao = (a as LibrarySource & { order?: number }).order ?? 0;
        const bo = (b as LibrarySource & { order?: number }).order ?? 0;
        return ao - bo;
      }
      return a.name.localeCompare(b.name);
    });
    return out;
  }

  // Pretty label for the chart-folder prefix used as a category grouping.
  function categoryLabel(prefix: string): string {
    const map: Record<string, string> = {
      "us-macro": "US macro",
      "real-estate": "Real estate",
      tech: "Tech",
      stocks: "Stocks",
      countries: "Countries",
      commodities: "Commodities",
      markets: "Markets",
      oil: "Oil & energy",
      crypto: "Crypto",
      fx: "FX",
      government: "Government finances",
    };
    return map[prefix] ?? prefix;
  }

  function renderTagFiltersCharts(): void {
    const library = getLibrary();
    const host = shell.querySelector<HTMLElement>(
      "[data-role='tag-filters-charts']",
    );
    if (!host || !library) return;
    const tags = allChartTags();
    host.innerHTML = "";
    const makeBtn = (tag: string, label: string, active: boolean) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tag-pill" + (active ? " tag-pill-active" : "");
      b.textContent = label;
      b.addEventListener("click", () => {
        if (tag === "") {
          chartsSelectedTags.clear();
        } else if (chartsSelectedTags.has(tag)) {
          chartsSelectedTags.delete(tag);
        } else {
          chartsSelectedTags.add(tag);
        }
        renderTagFiltersCharts();
        renderChartsList();
      });
      return b;
    };
    host.appendChild(
      makeBtn("", `all (${library.charts.length})`, chartsSelectedTags.size === 0),
    );
    for (const t of tags) {
      const count = library.charts.filter((c) => c.tags.includes(t)).length;
      host.appendChild(makeBtn(t, `${t} (${count})`, chartsSelectedTags.has(t)));
    }
  }


  function renderTagFiltersSources(): void {
    const library = getLibrary();
    const host = shell.querySelector<HTMLElement>(
      "[data-role='tag-filters-sources']",
    );
    if (!host || !library) return;
    const tags = allSourceTags();
    host.innerHTML = "";
    // Counts must reflect the SAME filter pipeline the source list uses
    // — chip state + search query + selected topical tags. Otherwise
    // the user sees "fiscal (6)" with "abil" typed, clicks fiscal, and
    // gets zero results because all six fiscal sources fail the
    // metro-only narrowing.
    //
    // Performance: one walk of `library.sources` instead of N tags ×
    // sources. For each source that passes the current filters, we
    // bump a counter for each of its topical tags (so we know exactly
    // how many results adding that tag would yield). 20k sources × ~5
    // tags each beats 50 tags × 20k sources × 3 unlock-cost-per-source
    // by ~3 orders of magnitude — the previous shape froze the UI
    // around the 4-char unlock boundary.
    const q = store.sourcesSearchQuery.trim().toLowerCase();
    const tagsRequired = [...sourcesSelectedTags].filter((t) => t !== CD_TAG);
    const libSources = library.sources;
    let allCount = 0;
    const tagCounts = new Map<string, number>();
    for (const id of Object.keys(libSources)) {
      const src = libSources[id] as LibrarySource & {
        tags?: string[];
        searchText?: string;
      };
      const sTags = src.tags ?? [];
      if (!passesCdFilter(id, sTags, sourcesSelectedTags, store.sourcesCdState, store.sourcesCdDistrict, q)) continue;
      if (!passesMetroFilter(sTags, libGeo.selectedMetroCbsa, q)) continue;
      if (!passesCountryFilter(sTags, libGeo.selectedCountryCode, q)) continue;
      if (!passesCountyFilter(id, sTags, q)) continue;
      let ok = true;
      for (const t of tagsRequired) {
        if (!sTags.includes(t)) { ok = false; break; }
      }
      if (!ok) continue;
      if (q) {
        const hay = src.searchText ??
          (src.name + " " + (src.shortName ?? "") + " " + id + " " + sTags.join(" ")).toLowerCase();
        if (!hay.includes(q)) continue;
      }
      allCount += 1;
      // Bucket per-tag for pill counts. Skip geo synthetic tags —
      // they're rendered through the geo chips, not as topical pills.
      for (const t of sTags) {
        if (t === CD_TAG || t === STATE_TAG) continue;
        if (t === COUNTRY_TAG || t.startsWith(`${COUNTRY_TAG}:`)) continue;
        if (t === METRO_TAG || t.startsWith(`${METRO_TAG}:`)) continue;
        tagCounts.set(t, (tagCounts.get(t) ?? 0) + 1);
      }
    }
    const makeBtn = (tag: string, label: string, active: boolean) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tag-pill" + (active ? " tag-pill-active" : "");
      b.textContent = label;
      b.addEventListener("click", () => {
        if (tag === "") {
          sourcesSelectedTags.clear();
          store.sourcesCdState = null;
          store.sourcesCdDistrict = null;
        } else if (sourcesSelectedTags.has(tag)) {
          sourcesSelectedTags.delete(tag);
        } else {
          sourcesSelectedTags.add(tag);
        }
        renderTagFiltersSources();
        renderSourcesList();
      });
      return b;
    };
    host.appendChild(
      makeBtn("", `all (${allCount})`, sourcesSelectedTags.size === 0),
    );
    // The CD / metro / country chips live in the geo strip ABOVE this
    // row (renderCdChip, renderMetroChip, renderCountryChip). Topical
    // tags only here.
    // Geo breakdown active = a metro, country, or congressional-district
    // filter is engaged. At the plain "All" level a topical tag matching
    // only 1-2 sources is more clutter than help, so require >=3 to show
    // its pill; inside a geo drill-down (where per-place counts are
    // naturally small) keep the looser >=1 so refinements stay visible.
    const geoBreakdownActive =
      !!libGeo.selectedMetroCbsa ||
      !!libGeo.selectedCountryCode ||
      sourcesSelectedTags.has(CD_TAG);
    const minTagCount = geoBreakdownActive ? 1 : 3;
    for (const t of tags) {
      if (t === CD_TAG || t === STATE_TAG) continue; // surfaced via CD chip
      if (t === COUNTRY_TAG || t.startsWith(`${COUNTRY_TAG}:`)) continue; // country chip
      const count = tagCounts.get(t) ?? 0;
      // Hide sparse pills: a 0-count pill yields nothing, and at the All
      // level a 1-2 count pill is just noise (see minTagCount above).
      if (count < minTagCount) continue;
      host.appendChild(makeBtn(t, `${t} (${count})`, sourcesSelectedTags.has(t)));
    }
  }


  function renderChartsList(): void {
    const host = shell.querySelector<HTMLElement>(
      "[data-role='lib-results-charts']",
    );
    if (!host) return;
    const charts = filteredCharts();
    host.innerHTML = "";
    if (charts.length === 0) {
      host.innerHTML =
        '<p class="muted small">No charts match. Feel free to request one at <a href="mailto:keller.scholl@gmail.com">keller.scholl@gmail.com</a>.</p>';
      return;
    }
    // Group by chart-folder prefix (e.g. "us-macro/foo" → "us-macro"). Keeps
    // the result list scannable when many results are returned.
    const groups = new Map<string, LibraryChart[]>();
    for (const c of charts) {
      const prefix = c.id.includes("/") ? c.id.split("/")[0] : "other";
      if (!groups.has(prefix)) groups.set(prefix, []);
      groups.get(prefix)!.push(c);
    }
    const orderedPrefixes = [...groups.keys()].sort((a, b) =>
      categoryLabel(a).localeCompare(categoryLabel(b)),
    );
    for (const prefix of orderedPrefixes) {
      const group = groups.get(prefix)!;
      const heading = document.createElement("div");
      heading.className = "lib-group-heading";
      heading.textContent = `${categoryLabel(prefix)} (${group.length})`;
      host.appendChild(heading);
      for (const c of group) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "chart-card";
      card.dataset.chartId = c.id;
      card.innerHTML =
        `<div class="chart-card-title">${escapeHtml(c.title)}</div>` +
        `<div class="chart-card-meta">${c.tags.map(escapeHtml).join(" \u00b7 ")}</div>`;
      card.addEventListener("click", () => {
        void addChart(c.id);
      });
      host.appendChild(card);
      }
    }
  }

  // Parallel renderer for the Sources tab. Each card shows the source
  // name, short-name/ticker if distinct, the tag list, and a one-line
  // description. Clicking adds the source as a single-series inline
  // chart to the active section \u2014 the dominant case is "track this".
  function renderSourcesList(): void {
    const host = shell.querySelector<HTMLElement>(
      "[data-role='lib-results-sources']",
    );
    if (!host) return;
    const sources = filteredSources();
    host.innerHTML = "";
    if (sources.length === 0) {
      // Tailored empty-state copy for the CD drill-down: an unfiltered
      // empty list almost certainly means the user activated the CD
      // chip and hasn't picked a state yet, not that we have no data.
      if (sourcesSelectedTags.has(CD_TAG) && !store.sourcesCdState) {
        host.innerHTML =
          '<p class="muted small">Pick a state above to see its statewide and congressional-district series.</p>';
      } else {
        host.innerHTML =
          '<p class="muted small">No sources match. Feel free to request one at <a href="mailto:keller.scholl@gmail.com">keller.scholl@gmail.com</a>.</p>';
      }
      return;
    }
    for (const s of sources) {
      // Synthetic hint cards: render with a distinct style + a click
      // handler that engages the relevant geo chip instead of adding
      // a chart. Hints never become inline sources / charts \u2014 they
      // exist purely to bridge the discoverability gap between
      // "search for unemployment" and "geographic data exists at
      // level X." Sourced from src/lib/source-hints.ts.
      if (s.kind === "hint") {
        const chip = (s as LibrarySource & { chip?: string }).chip ?? "";
        const card = document.createElement("button");
        card.type = "button";
        card.className = "source-card source-card-hint";
        card.dataset.sourceId = s.id;
        card.dataset.hintChip = chip;
        const desc = s.description
          ? `<div class="source-card-desc">${escapeHtml(s.description)}</div>`
          : "";
        card.innerHTML =
          `<div class="source-card-title"><span class="source-card-hint-eyebrow">See also</span>${escapeHtml(s.name)}</div>` +
          desc;
        card.addEventListener("click", () => engageHintChip(chip));
        host.appendChild(card);
        continue;
      }
      const card = document.createElement("button");
      card.type = "button";
      card.className = "source-card";
      card.dataset.sourceId = s.id;
      // Geo sources get a state/district badge regardless of the source's
      // own shortName \u2014 when the user is browsing a state's series, the
      // district code is what they're scanning for. CDs read as "TX-12";
      // state-level series read as "TX statewide" so the two scopes are
      // visually distinct in the same list.
      const cdParsed = parseCdSourceId(s.id);
      const statePar = parseStateSourceId(s.id);
      let geoBadge = "";
      if (cdParsed) {
        geoBadge =
          `<span class="source-card-short source-card-cd-badge">${escapeHtml(formatCdShortLabel(cdParsed.state, cdParsed.district))}</span>`;
      } else if (statePar) {
        geoBadge =
          `<span class="source-card-short source-card-cd-badge">${escapeHtml(`${statePar.state.toUpperCase()} statewide`)}</span>`;
      }
      const shortBadge =
        !cdParsed && !statePar && s.shortName && s.shortName !== s.name
          ? `<span class="source-card-short">${escapeHtml(s.shortName)}</span>`
          : "";
      const tagsLine =
        s.tags.length > 0
          ? `<div class="source-card-tags">${s.tags.map(escapeHtml).join(" \u00b7 ")}</div>`
          : "";
      const desc = s.description
        ? `<div class="source-card-desc">${escapeHtml(s.description)}</div>`
        : "";
      card.innerHTML =
        `<div class="source-card-title">${escapeHtml(s.name)}${geoBadge}${shortBadge}</div>` +
        desc +
        tagsLine;
      card.addEventListener("click", () => {
        void addSourceAsChart(s.id);
      });
      host.appendChild(card);
    }
  }

  /**
   * Handle a click on a source-hint card. Engages the relevant
   * geo chip + clears the search field so the user sees the
   * sources that were hiding behind the chip. For tract / block-
   * group hints (chip === "maps-tab") we switch to the Maps tab
   * since those levels live there, not in Sources.
   */
  function engageHintChip(chip: string): void {
    const searchInput = shell.querySelector<HTMLInputElement>(
      "[data-role='lib-sources-search']",
    );
    if (chip === "maps-tab") {
      setActiveLibTab("maps");
      return;
    }
    if (chip === "metro") {
      // Open the metro popover so the user can pick a CBSA. No
      // default selection \u2014 they have to choose.
      const trigger = shell.querySelector<HTMLButtonElement>(
        "[data-role='lib-metro-chip']",
      );
      trigger?.click();
      // Clear the typed search so the chip's full result list is
      // visible (the search filter would otherwise still apply).
      if (searchInput) {
        searchInput.value = "";
        store.sourcesSearchQuery = "";
      }
      renderTagFiltersSources();
      renderSourcesList();
      return;
    }
    if (chip === "country") {
      const trigger = shell.querySelector<HTMLButtonElement>(
        "[data-role='lib-country-chip']",
      );
      trigger?.click();
      if (searchInput) {
        searchInput.value = "";
        store.sourcesSearchQuery = "";
      }
      renderTagFiltersSources();
      renderSourcesList();
      return;
    }
    if (chip === "cd") {
      // States & districts chip toggles via the tag-pill set
      // (CD_TAG sits in sourcesSelectedTags). Add it if missing
      // and clear the search.
      sourcesSelectedTags.add(CD_TAG);
      if (searchInput) {
        searchInput.value = "";
        store.sourcesSearchQuery = "";
      }
      renderTagFiltersSources();
      renderSourcesList();
      return;
    }
    if (chip === "county") {
      // No dedicated county chip yet \u2014 the hint copy instructs the
      // user to type the county name. We can't engage anything
      // useful programmatically; leave the search field intact so
      // they can continue typing.
      return;
    }
  }

  // Switch which library tab is showing. Tab buttons toggle aria-selected
  // + an active class; the two panels are direct siblings with `hidden`
  // attributes that swap. Re-renders the active tab in case its data
  // has changed since last view (e.g., a derived source was just added,
  // which the Sources tab should now show in its list).
  function setActiveLibTab(tab: LibTab): void {
    shell.querySelectorAll<HTMLButtonElement>("[data-role='lib-tab']").forEach((btn) => {
      const active = btn.dataset.tab === tab;
      btn.classList.toggle("lib-tab-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    // Tag the library shell with which tab is active so CSS can react —
    // the Maps tab specifically wants to cancel the panel-local
    // max-height so its "+ Add map" button can't get tucked under a
    // scrollbar. Other tabs keep the height cap (their result lists
    // scroll internally instead).
    const libraryHost = shell.querySelector<HTMLElement>(".composer-library");
    if (libraryHost) libraryHost.dataset.activeTab = tab;
    const panelSources = shell.querySelector<HTMLElement>(
      "[data-role='lib-panel-sources']",
    );
    const panelCharts = shell.querySelector<HTMLElement>(
      "[data-role='lib-panel-charts']",
    );
    const panelMaps = shell.querySelector<HTMLElement>(
      "[data-role='lib-panel-maps']",
    );
    const panelGenerators = shell.querySelector<HTMLElement>(
      "[data-role='lib-panel-generators']",
    );
    if (panelSources) panelSources.hidden = tab !== "sources";
    if (panelCharts) panelCharts.hidden = tab !== "charts";
    if (panelMaps) panelMaps.hidden = tab !== "maps";
    if (panelGenerators) panelGenerators.hidden = tab !== "generators";
    if (tab === "sources") {
      renderTagFiltersSources();
      renderSourcesList();
    } else if (tab === "charts") {
      renderTagFiltersCharts();
      renderChartsList();
    } else if (tab === "maps") {
      renderMapBuilder();
    } else if (tab === "generators") {
      void renderGeneratorsBuilder();
    }
    track("compose_lib_tab_switched", { tab });
  }


  return {
    renderTagFiltersSources,
    renderSourcesList,
    renderChartsList,
    renderTagFiltersCharts,
    setActiveLibTab,
  };
}