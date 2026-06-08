/**
 * Shared modal tag-chip strip (Plan 2d).
 *
 * Extracted from compose.astro because BOTH the custom-chart modal
 * (renderCcModalTagChips) and the derived-source modal (renderDsModalTagChips)
 * render the same topical tag-chip strip from the same tag universe.
 * `renderModalTagChips` is the generic chip-strip builder; the caller supplies
 * the active-tag set + a re-render callback (different per modal). Its private
 * `allPickableSourceTags` helper computes the union of tags across every
 * pickable source (library + derived).
 *
 * Geo chips (congressional-district / metro / country) are deliberately NOT
 * here — they render in the geo-chips strip ABOVE this row (renderCdChip /
 * renderMetroChip / renderCountryChip + wireGeoChips), so the master geo tags
 * are filtered out below. This module is only the topical-tag pills the two
 * modals share. The `_cdGetters` param is accepted for call-site symmetry with
 * the geo strip but is unused here.
 *
 * Built as a create<Feature>(ctx) factory (like the other 2d modules) so the
 * shell / library / state deps stay encapsulated; build ONE instance and pass
 * `renderModalTagChips` to both modal code paths.
 */
import { CD_TAG, STATE_TAG } from "../congressional-districts";
import { METRO_TAG } from "../geographic-regions";
import { COUNTRY_TAG } from "../countries";
import type { LibraryPayload, LibrarySource } from "./library";
import type { UIState } from "./state";

export interface ModalTagChipsContext {
  shell: HTMLElement;
  getLibrary: () => LibraryPayload | null;
  /** For state.inlineSources tags — derived sources contribute their own tags. */
  state: UIState;
}

export function createModalTagChips(ctx: ModalTagChipsContext) {
  const { shell, getLibrary, state } = ctx;

  // Union of every tag across the universe of pickable sources (library +
  // derived). The "custom" tag is implicitly only present when at least one
  // derived source exists (that's where it comes from), so the "hide the
  // custom chip when there are no custom sources" behavior comes for free.
  function allPickableSourceTags(): string[] {
    const s = new Set<string>();
    const addTag = (t: string) => {
      // Synthetic per-entity tags (metro:35620, country-specific:JPN, …) never
      // appear as standalone pills — they're surfaced through the master chips'
      // drilldowns instead. Strip them so the chip strip stays readable; the
      // master METRO_TAG / COUNTRY_TAG values themselves stay.
      if (t.startsWith(`${METRO_TAG}:`)) return;
      if (t.startsWith(`${COUNTRY_TAG}:`)) return;
      s.add(t);
    };
    const lib = getLibrary();
    if (lib) {
      for (const id of Object.keys(lib.sources)) {
        const src = lib.sources[id] as LibrarySource & { tags?: string[] };
        for (const t of src.tags ?? []) addTag(t);
      }
    }
    for (const spec of Object.values(state.inlineSources)) {
      for (const t of spec.tags ?? []) addTag(t);
    }
    return [...s].sort();
  }

  // Generic chip-strip builder shared between the cc-modal source picker and
  // the ds-modal operand pickers. Caller supplies the active-tag set + the
  // re-render callback (different functions per modal). Geo chips (CD / metro /
  // country) live in the geo strip above this row, so the master geo tags are
  // filtered out here; only topical tags render.
  function renderModalTagChips(
    hostSelector: string,
    selected: Set<string>,
    onToggle: () => void,
    _cdGetters: {
      getState: () => string | null;
      setState: (v: string | null) => void;
      getDistrict: () => string | null;
      setDistrict: (v: string | null) => void;
    },
  ): void {
    const host = shell.querySelector<HTMLElement>(hostSelector);
    if (!host) return;
    const tags = allPickableSourceTags();
    host.innerHTML = "";
    if (tags.length === 0) return;
    const makeChip = (tag: string, label: string, active: boolean) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tag-pill" + (active ? " tag-pill-active" : "");
      b.textContent = label;
      b.addEventListener("click", (e) => {
        e.preventDefault();
        if (tag === "") {
          selected.clear();
        } else if (selected.has(tag)) {
          selected.delete(tag);
        } else {
          selected.add(tag);
        }
        onToggle();
      });
      return b;
    };
    host.appendChild(makeChip("", "all", selected.size === 0));
    // CD / METRO / COUNTRY chips live in the geo-chips strip ABOVE this row;
    // topical tags only here. (See renderCdChip / renderMetroChip /
    // renderCountryChip + wireGeoChips for the geo strip wiring.)
    for (const t of tags) {
      if (t === CD_TAG || t === STATE_TAG) continue;
      if (t === METRO_TAG || t === COUNTRY_TAG) continue;
      host.appendChild(makeChip(t, t, selected.has(t)));
    }
  }

  return { renderModalTagChips };
}
