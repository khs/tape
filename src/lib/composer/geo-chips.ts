/**
 * Shared geo-chip subsystem (Plan 2d) -- the metro / country / congressional-
 * district filter chips in the geo strip across THREE surfaces: the Sources tab
 * (lib), the custom-chart modal (cc), and the derived-source modal (ds). Each
 * renderer takes a `surface` and resolves its config via getSurfaceConfig(surface)
 * -- that hub (geoSurfaceConfig) STAYS in compose because it wires each surface
 * to its own onChange / refreshTags / state (renderSourcesList,
 * renderCustomChartSources, renderDsPicker, ...).
 *
 * Extracted from compose.astro via createGeoChips(ctx). Only the 4 entry-point
 * renderers (renderMetroChip / renderCdChip / renderCountryChip / wireGeoChips)
 * are exported -- compose destructures them, uses them for the lib surface, and
 * passes them into the cc-modal / ds-modal ctx (so those modules are unchanged,
 * just sourced from here). The CD drill-down (appendCdDrillDown) stays in compose
 * and arrives via ctx. library is read via getLibrary() per fn.
 */
import { isRegionCode } from "../countries";
import type { GeoState } from "./state";
import type { LibraryPayload } from "./library";

export type GeoSurface = "lib" | "cc" | "ds";

export interface GeoSurfaceConfig {
  prefix: string;
  state: () => GeoState;
  onChange: () => void;
  track: (event: string, props: Record<string, unknown>) => void;
  cdSelectedTags: () => Set<string>;
  getCdState: () => string | null;
  setCdState: (v: string | null) => void;
  getCdDistrict: () => string | null;
  setCdDistrict: (v: string | null) => void;
  refreshTags: () => void;
}

export interface GeoChipsContext {
  shell: HTMLElement;
  getLibrary: () => LibraryPayload | null;
  getSurfaceConfig: (surface: GeoSurface) => GeoSurfaceConfig;
  appendCdDrillDown: (
    host: HTMLElement,
    selectedTags: Set<string>,
    getState: () => string | null,
    setState: (v: string | null) => void,
    getDistrict: () => string | null,
    setDistrict: (v: string | null) => void,
    rerender: () => void,
  ) => void;
  escapeHtml: (s: string) => string;
}

export function createGeoChips(ctx: GeoChipsContext) {
  const { shell, getLibrary, getSurfaceConfig, appendCdDrillDown, escapeHtml } = ctx;
  function geoQS<T extends HTMLElement>(prefix: string, suffix: string): T | null {
    return shell.querySelector<T>(`[data-role='${prefix}-${suffix}']`);
  }

  function renderMetroChip(surface: GeoSurface = "lib"): void {
    const library = getLibrary();
    const cfg = getSurfaceConfig(surface);
    const wrap = geoQS<HTMLElement>(cfg.prefix, "geo-chips");
    const chip = geoQS<HTMLButtonElement>(cfg.prefix, "metro-chip");
    const label = geoQS<HTMLElement>(cfg.prefix, "metro-label");
    const clear = geoQS<HTMLElement>(cfg.prefix, "metro-clear");
    if (!wrap || !chip || !label || !clear) return;
    const metros = library?.metros ?? {};
    const hasMetros = Object.keys(metros).length > 0;
    const hasCountries = Object.keys(library?.countries ?? {}).length > 0;
    wrap.hidden = !hasMetros && !hasCountries;
    chip.hidden = !hasMetros;
    if (!hasMetros) return;
    const state = cfg.state();
    if (state.selectedMetroCbsa) {
      const entry = metros[state.selectedMetroCbsa];
      const short = entry?.shortName ?? state.selectedMetroCbsa;
      label.textContent = short;
      chip.classList.add("lib-geo-chip-active");
      clear.hidden = false;
    } else {
      label.textContent = "US metro areas ▾";
      chip.classList.remove("lib-geo-chip-active");
      clear.hidden = true;
    }
    chip.setAttribute("aria-expanded", state.metroPopoverOpen ? "true" : "false");
  }

  function renderMetroList(surface: GeoSurface = "lib"): void {
    const library = getLibrary();
    const cfg = getSurfaceConfig(surface);
    const list = geoQS<HTMLElement>(cfg.prefix, "metro-list");
    if (!list) return;
    const metros = library?.metros ?? {};
    const codes = Object.keys(metros);
    const state = cfg.state();
    const q = state.metroSearchQuery.trim().toLowerCase();
    list.innerHTML = "";
    let shown = 0;
    for (const code of codes) {
      const entry = metros[code];
      const hay = (entry.shortName + " " + entry.name + " " + code).toLowerCase();
      if (q && !hay.includes(q)) continue;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "lib-geo-list-item" +
        (state.selectedMetroCbsa === code ? " lib-geo-list-item-active" : "");
      btn.setAttribute("role", "option");
      btn.setAttribute("aria-selected", state.selectedMetroCbsa === code ? "true" : "false");
      btn.innerHTML =
        `<span class="lib-geo-list-item-name">${escapeHtml(entry.shortName)}</span>` +
        `<span class="lib-geo-list-item-code muted small">${escapeHtml(code)}</span>`;
      btn.addEventListener("click", () => selectMetro(code, surface));
      list.appendChild(btn);
      shown += 1;
    }
    if (shown === 0) {
      const empty = document.createElement("p");
      empty.className = "muted small";
      empty.textContent = q ? "No metros match." : "No metros loaded.";
      list.appendChild(empty);
    }
  }

  function openMetroPopover(surface: GeoSurface = "lib"): void {
    const cfg = getSurfaceConfig(surface);
    const pop = geoQS<HTMLElement>(cfg.prefix, "metro-popover");
    if (!pop) return;
    cfg.state().metroPopoverOpen = true;
    pop.hidden = false;
    renderMetroList(surface);
    renderMetroChip(surface);
    queueMicrotask(() => {
      const search = geoQS<HTMLInputElement>(cfg.prefix, "metro-search");
      search?.focus();
    });
  }

  function closeMetroPopover(surface: GeoSurface = "lib"): void {
    const cfg = getSurfaceConfig(surface);
    const pop = geoQS<HTMLElement>(cfg.prefix, "metro-popover");
    if (!pop) return;
    cfg.state().metroPopoverOpen = false;
    pop.hidden = true;
    renderMetroChip(surface);
  }

  function selectMetro(cbsa: string, surface: GeoSurface = "lib"): void {
    const cfg = getSurfaceConfig(surface);
    cfg.state().selectedMetroCbsa = cbsa;
    closeMetroPopover(surface);
    renderMetroChip(surface);
    cfg.onChange();
    cfg.track("compose_metro_filter_set", { cbsa });
  }

  function clearMetroFilter(surface: GeoSurface = "lib"): void {
    const cfg = getSurfaceConfig(surface);
    const state = cfg.state();
    if (!state.selectedMetroCbsa) return;
    state.selectedMetroCbsa = null;
    renderMetroChip(surface);
    cfg.onChange();
    cfg.track("compose_metro_filter_cleared", {});
  }

  function renderCountryChip(surface: GeoSurface = "lib"): void {
    const library = getLibrary();
    const cfg = getSurfaceConfig(surface);
    const wrap = geoQS<HTMLElement>(cfg.prefix, "geo-chips");
    const chip = geoQS<HTMLButtonElement>(cfg.prefix, "country-chip");
    const label = geoQS<HTMLElement>(cfg.prefix, "country-label");
    const clear = geoQS<HTMLElement>(cfg.prefix, "country-clear");
    if (!wrap || !chip || !label || !clear) return;
    const countries = library?.countries ?? {};
    const hasCountries = Object.keys(countries).length > 0;
    const hasMetros = Object.keys(library?.metros ?? {}).length > 0;
    wrap.hidden = !hasMetros && !hasCountries;
    chip.hidden = !hasCountries;
    if (!hasCountries) return;
    const state = cfg.state();
    if (state.selectedCountryCode) {
      const entry = countries[state.selectedCountryCode];
      const name = entry?.name ?? state.selectedCountryCode;
      label.textContent = name;
      chip.classList.add("lib-geo-chip-active");
      clear.hidden = false;
    } else {
      label.textContent = "Regions and countries ▾";
      chip.classList.remove("lib-geo-chip-active");
      clear.hidden = true;
    }
    chip.setAttribute("aria-expanded", state.countryPopoverOpen ? "true" : "false");
  }

  function renderCountryList(surface: GeoSurface = "lib"): void {
    const library = getLibrary();
    const cfg = getSurfaceConfig(surface);
    const list = geoQS<HTMLElement>(cfg.prefix, "country-list");
    if (!list) return;
    const countries = library?.countries ?? {};
    const codes = Object.keys(countries);
    const state = cfg.state();
    const q = state.countrySearchQuery.trim().toLowerCase();
    list.innerHTML = "";
    // Two-section layout: regional aggregates (Sub-Saharan Africa, EU,
    // …) first because users coming to this chip are usually looking at
    // the big picture; then individual countries A–Z. Section headers
    // labeled so the visual hierarchy is obvious. Empty sections are
    // hidden so we don't show a "Regions" heading with nothing under it.
    const regions = codes.filter((c) => isRegionCode(c));
    const singles = codes.filter((c) => !isRegionCode(c));
    const renderItem = (code: string) => {
      const entry = countries[code];
      const hay = (entry.name + " " + code).toLowerCase();
      if (q && !hay.includes(q)) return null;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "lib-geo-list-item" +
        (state.selectedCountryCode === code ? " lib-geo-list-item-active" : "");
      btn.setAttribute("role", "option");
      btn.setAttribute("aria-selected", state.selectedCountryCode === code ? "true" : "false");
      btn.innerHTML =
        `<span class="lib-geo-list-item-name">${escapeHtml(entry.name)}</span>` +
        `<span class="lib-geo-list-item-code muted small">${escapeHtml(code)}</span>`;
      btn.addEventListener("click", () => selectCountry(code, surface));
      return btn;
    };
    const renderSection = (header: string, codeList: string[]) => {
      const items = codeList.map(renderItem).filter((b): b is HTMLButtonElement => !!b);
      if (items.length === 0) return 0;
      const h = document.createElement("p");
      h.className = "lib-geo-list-header";
      h.textContent = header;
      list.appendChild(h);
      for (const b of items) list.appendChild(b);
      return items.length;
    };
    const shown = renderSection("Regions", regions) + renderSection("Countries", singles);
    if (shown === 0) {
      const empty = document.createElement("p");
      empty.className = "muted small";
      empty.textContent = q ? "No countries or regions match." : "No countries loaded.";
      list.appendChild(empty);
    }
  }

  function openCountryPopover(surface: GeoSurface = "lib"): void {
    const cfg = getSurfaceConfig(surface);
    const pop = geoQS<HTMLElement>(cfg.prefix, "country-popover");
    if (!pop) return;
    cfg.state().countryPopoverOpen = true;
    pop.hidden = false;
    renderCountryList(surface);
    renderCountryChip(surface);
    queueMicrotask(() => {
      const search = geoQS<HTMLInputElement>(cfg.prefix, "country-search");
      search?.focus();
    });
  }

  function closeCountryPopover(surface: GeoSurface = "lib"): void {
    const cfg = getSurfaceConfig(surface);
    const pop = geoQS<HTMLElement>(cfg.prefix, "country-popover");
    if (!pop) return;
    cfg.state().countryPopoverOpen = false;
    pop.hidden = true;
    renderCountryChip(surface);
  }

  function selectCountry(code: string, surface: GeoSurface = "lib"): void {
    const cfg = getSurfaceConfig(surface);
    cfg.state().selectedCountryCode = code;
    closeCountryPopover(surface);
    renderCountryChip(surface);
    cfg.onChange();
    cfg.track("compose_country_filter_set", { code });
  }

  function clearCountryFilter(surface: GeoSurface = "lib"): void {
    const cfg = getSurfaceConfig(surface);
    const state = cfg.state();
    if (!state.selectedCountryCode) return;
    state.selectedCountryCode = null;
    renderCountryChip(surface);
    cfg.onChange();
    cfg.track("compose_country_filter_cleared", {});
  }

  // States & districts chip rendering. Sits in the geo strip alongside
  // the metro + country chips. Implemented as a clear-and-rebuild via
  // the existing appendCdDrillDown helper so the chip + state dropdown
  // + district dropdown all live as siblings inside the host element.
  // The onToggle callback re-renders the chip itself (to reflect the
  // new pickerTags state), the topical-tag row (counts reflect the new
  // CD-vs-not gate), and the source list (gate now affects which
  // sources show).
  function renderCdChip(surface: GeoSurface = "lib"): void {
    const cfg = getSurfaceConfig(surface);
    const host = geoQS<HTMLElement>(cfg.prefix, "cd-chip-host");
    if (!host) return;
    host.innerHTML = "";
    appendCdDrillDown(
      host,
      cfg.cdSelectedTags(),
      cfg.getCdState,
      cfg.setCdState,
      cfg.getCdDistrict,
      cfg.setCdDistrict,
      () => {
        renderCdChip(surface);
        cfg.refreshTags();
        cfg.onChange();
      },
    );
  }

  // Shared wiring helper. Hooks click + clear + popover-search + outside-
  // click + ESC for one surface. Reused by hydrate() for the Sources tab
  // and by openCustomChartModal / openDerivedSourceModal for the modals.
  function wireGeoChips(surface: GeoSurface): void {
    const cfg = getSurfaceConfig(surface);
    const wrap = geoQS<HTMLElement>(cfg.prefix, "geo-chips");
    const metroChip = geoQS<HTMLButtonElement>(cfg.prefix, "metro-chip");
    const metroClear = geoQS<HTMLElement>(cfg.prefix, "metro-clear");
    const metroSearch = geoQS<HTMLInputElement>(cfg.prefix, "metro-search");
    const countryChip = geoQS<HTMLButtonElement>(cfg.prefix, "country-chip");
    const countryClear = geoQS<HTMLElement>(cfg.prefix, "country-clear");
    const countrySearch = geoQS<HTMLInputElement>(cfg.prefix, "country-search");
    if (metroChip && !metroChip.dataset.wired) {
      metroChip.dataset.wired = "1";
      metroChip.addEventListener("click", (e) => {
        const target = e.target as HTMLElement | null;
        if (target && target.closest(`[data-role='${cfg.prefix}-metro-clear']`)) {
          e.stopPropagation();
          clearMetroFilter(surface);
          return;
        }
        const s = cfg.state();
        if (s.countryPopoverOpen) closeCountryPopover(surface);
        if (s.metroPopoverOpen) closeMetroPopover(surface);
        else openMetroPopover(surface);
      });
    }
    if (metroClear && !metroClear.dataset.wired) {
      metroClear.dataset.wired = "1";
      metroClear.addEventListener("click", (e) => {
        e.stopPropagation();
        clearMetroFilter(surface);
      });
    }
    if (metroSearch && !metroSearch.dataset.wired) {
      metroSearch.dataset.wired = "1";
      metroSearch.addEventListener("input", () => {
        cfg.state().metroSearchQuery = metroSearch.value;
        renderMetroList(surface);
      });
    }
    if (countryChip && !countryChip.dataset.wired) {
      countryChip.dataset.wired = "1";
      countryChip.addEventListener("click", (e) => {
        const target = e.target as HTMLElement | null;
        if (target && target.closest(`[data-role='${cfg.prefix}-country-clear']`)) {
          e.stopPropagation();
          clearCountryFilter(surface);
          return;
        }
        const s = cfg.state();
        if (s.metroPopoverOpen) closeMetroPopover(surface);
        if (s.countryPopoverOpen) closeCountryPopover(surface);
        else openCountryPopover(surface);
      });
    }
    if (countryClear && !countryClear.dataset.wired) {
      countryClear.dataset.wired = "1";
      countryClear.addEventListener("click", (e) => {
        e.stopPropagation();
        clearCountryFilter(surface);
      });
    }
    if (countrySearch && !countrySearch.dataset.wired) {
      countrySearch.dataset.wired = "1";
      countrySearch.addEventListener("input", () => {
        cfg.state().countrySearchQuery = countrySearch.value;
        renderCountryList(surface);
      });
    }
    if (wrap && !wrap.dataset.wired) {
      wrap.dataset.wired = "1";
      // Click-outside dismisses both popovers — but only for THIS
      // surface's wrap. Document-level listeners with surface-scoped
      // logic close on any outside click.
      document.addEventListener("click", (e) => {
        const s = cfg.state();
        if (!s.metroPopoverOpen && !s.countryPopoverOpen) return;
        const target = e.target as HTMLElement | null;
        if (!target) return;
        if (target.closest(`[data-role='${cfg.prefix}-geo-chips']`)) return;
        if (s.metroPopoverOpen) closeMetroPopover(surface);
        if (s.countryPopoverOpen) closeCountryPopover(surface);
      });
      document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        const s = cfg.state();
        if (s.metroPopoverOpen) closeMetroPopover(surface);
        if (s.countryPopoverOpen) closeCountryPopover(surface);
      });
    }
  }


  return { renderMetroChip, renderCdChip, renderCountryChip, wireGeoChips };
}