/**
 * Charts library tab + lib-tab switcher (Plan 2d) -- the left-rail
 * "Pregenerated charts" browsing UI on the compose page, plus
 * setActiveLibTab (which swaps the Sources / Charts / Maps / Generators
 * panels). The Sources tab itself is a <SourcePicker> island (Plan 3c)
 * that owns its own search / geo chips / tag chips / hint cards / result
 * list -- compose wires its source-picker:pick event to addSourceAsChart
 * and its source-picker:hint "maps-tab" chip to setActiveLibTab("maps").
 *
 * Extracted from compose.astro via createSourcesTab(ctx). Adding a chart
 * as a tile (addChart) and rendering the Maps / Generators tabs
 * (renderMapBuilder / renderGeneratorsBuilder) come via ctx.
 * chartsSelectedTags is owned here; chartsSearchQuery is read through a
 * getter (compose wire() owns the input). library via getLibrary() per fn.
 */
import { track } from "../track";
import type { LibraryPayload, LibraryChart } from "./library";

type LibTab = "sources" | "charts" | "maps" | "generators";

export interface SourcesTabContext {
  shell: HTMLElement;
  getLibrary: () => LibraryPayload | null;
  getChartsSearchQuery: () => string;
  escapeHtml: (s: string) => string;
  addChart: (chartId: string) => Promise<void>;
  renderMapBuilder: () => void;
  renderGeneratorsBuilder: () => void;
}

export function createSourcesTab(ctx: SourcesTabContext) {
  const {
    shell,
    getLibrary,
    getChartsSearchQuery,
    escapeHtml,
    addChart,
    renderMapBuilder,
    renderGeneratorsBuilder,
  } = ctx;
  // Charts-tab topical tag selection (cluster-internal). The Sources tab
  // has no compose-side filter state anymore -- its SourcePicker island
  // owns its own search / tag / geo state.
  const chartsSelectedTags: Set<string> = new Set<string>();
  function allChartTags(): string[] {
    const library = getLibrary();
    if (!library) return [];
    const s = new Set<string>();
    for (const c of library.charts) for (const t of c.tags) s.add(t);
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
      card.addEventListener("click", async () => {
        // Double-click guard: addChart's dedup check (target.charts.includes)
        // runs before its own await, so two rapid clicks both pass it and
        // append the same library chart twice. Disable the card synchronously
        // for the duration of the add so the second click is a no-op; re-enable
        // afterwards so a deliberate later re-add still works (addChart's dedup
        // then correctly bails once the tile is present).
        if (card.disabled) return;
        card.disabled = true;
        try {
          await addChart(c.id);
        } finally {
          card.disabled = false;
        }
      });
      host.appendChild(card);
      }
    }
  }

  // Switch which library tab is showing. Tab buttons toggle aria-selected
  // + an active class; the panels are direct siblings with `hidden`
  // attributes that swap. Re-renders the newly-active tab in case its
  // data changed since last view (the Sources tab is exempt -- its
  // SourcePicker island re-renders itself on its own state changes).
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
    // (tab === "sources" needs no re-render call -- the SourcePicker
    // island self-manages its search / filters / results.)
    if (tab === "charts") {
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
    renderChartsList,
    renderTagFiltersCharts,
    setActiveLibTab,
  };
}