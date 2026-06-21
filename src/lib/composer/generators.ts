/**
 * Generators tab — the "mass-generate a dashboard" builder: template + entity
 * (preset / custom / all) pickers, the indicator-vs-profile layouts, and the
 * two terminal generate functions that fan a template across many entities (or
 * one section per entity profile) into the dashboard.
 *
 * Extracted from compose.astro (Plan 2d) via the create<Feature>(ctx) factory.
 * All mutable state (generators, the fetched index, the wired guard) and the
 * Gen* types live inside the factory. No `library` coupling — the entity /
 * template universe is a separate /generators-index.json fetch. nanoid / track /
 * filterUsablePresets come in as imports; everything that crosses into the rest
 * of the page (render, writeUrl, the rate-limit gate, section clamp, escapeHtml)
 * comes through ctx.
 */
import { nanoid } from "nanoid";
import { track } from "../track";
import { INLINE_PREFIX } from "./ids";
import { filterUsablePresets, type PresetDef } from "../generator-presets";
import { GENERATOR_TOPICS, topicForTemplate } from "./generator-topics";
import type { UIState, UISection, ComposerStore } from "./state";

export interface GeneratorsTabContext {
  shell: HTMLElement;
  baseUrl: string;
  state: UIState;
  store: ComposerStore;
  escapeHtml: (s: string) => string;
  renderComposition: () => void;
  writeUrl: () => void;
  checkComposeAction: (action: string) => Promise<boolean>;
  showSigninPrompt: (reason: string) => void;
  clampActiveSection: () => void;
}

export function createGeneratorsTab(ctx: GeneratorsTabContext) {
  const {
    shell,
    baseUrl,
    state,
    store,
    escapeHtml,
    renderComposition,
    writeUrl,
    checkComposeAction,
    showSigninPrompt,
    clampActiveSection,
  } = ctx;
  // ---- Generators tab --------------------------------------------------
  //
  // Mass-compose: pick a series template + a set of entities (MSAs /
  // states / countries), get one inline-chart per entity dropped into
  // a section. The catalog of templates is shipped at build time as
  // public/generators-index.json by
  // pipelines/_generate_generators_index.py — we lazy-fetch it on
  // first Generators-tab open.

  interface GenEntity {
    short: string;
    name: string;
    // Optional latest-known total population. Attached by the
    // index-builder pipeline for metros, states, and countries where
    // a population time-series exists on disk. Powers the sort-by
    // control in the Generators tab.
    pop?: number;
  }
  interface GenPreset {
    label: string;
    codes: string[];
  }
  interface GenTemplate {
    id: string;
    label: string;
    description: string;
    tags: string[];
    sourceMap: Record<string, string>;
    count: number;
  }
  interface GenGeoBlock {
    label: string;
    entities: Record<string, GenEntity>;
    presets: Record<string, GenPreset>;
    templates: GenTemplate[];
    // Canonical template order for profile mode. See
    // pipelines/_generate_generators_index.py PROFILE_ORDER for the
    // hand-curated ordering. Optional for back-compat with older
    // index builds; client falls back to `templates` order.
    profileOrder?: string[];
  }
  interface GeneratorsIndex {
    v: 1;
    lastUpdated: string;
    geoTypes: Record<"metro" | "state" | "country", GenGeoBlock>;
  }

  type GenGeo = "metro" | "state" | "country";
  type GenMode = "all" | "preset" | "custom";
  type GenSort = "alpha" | "pop";
  /**
   * Generators-tab layout flavor:
   *   "indicator" — one template × many entities (the original flow).
   *   "profile"   — one entity × many templates (the new "show me
   *                 everything we have about Virginia" flow). Uses the
   *                 generators-index `profileOrder` for the curated
   *                 template ordering.
   */
  type GenLayout = "indicator" | "profile";

  interface GeneratorsBuilderState {
    geo: GenGeo;
    layout: GenLayout;
    templateId: string | null;
    mode: GenMode;
    preset: string | null;
    selected: Set<string>;      // entity codes for custom mode
    templateSearch: string;
    entitySearch: string;
    sectionTitle: string;
    // Drives both the Custom-mode entity-list order AND the order in
    // which tiles get appended to the section on Generate. "alpha"
    // uses the entity's short name; "pop" uses entity.pop descending
    // and falls back to alpha for entities missing a population.
    sort: GenSort;
    // Profile-mode state.
    profileEntity: string | null;
    profileSearch: string;
  }

  const generators: GeneratorsBuilderState = {
    geo: "metro",
    layout: "indicator",
    templateId: null,
    mode: "all",
    preset: null,
    selected: new Set<string>(),
    templateSearch: "",
    entitySearch: "",
    sectionTitle: "",
    sort: "alpha",
    profileEntity: null,
    profileSearch: "",
  };

  // Compact human-readable formatter for population numbers shown in
  // the Custom-mode entity rows when sort=pop. Uses M for millions,
  // K for thousands; falls back to a comma-grouped integer for the
  // small countries (Cayman Islands ~74k still reads cleanly).
  function formatEntityPop(n: number): string {
    if (!Number.isFinite(n)) return "";
    if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)} B`;
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)} M`;
    if (n >= 10_000) return `${(n / 1_000).toFixed(0)} K`;
    return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  // Shared sort comparator for entity lists + generated tile order.
  // Pulled out so renderGenCustomList() and generateMassDashboard()
  // can't drift apart on ordering rules.
  function genEntityComparator(
    geo: GenGeo,
    sort: GenSort,
  ): (a: string, b: string) => number {
    if (!generatorsIndex) {
      return (a, b) => a.localeCompare(b);
    }
    const block = generatorsIndex.geoTypes[geo];
    const labelOf = (code: string): string =>
      (block.entities[code]?.short ?? code).toLowerCase();
    const popOf = (code: string): number | null => {
      const p = block.entities[code]?.pop;
      return typeof p === "number" && Number.isFinite(p) ? p : null;
    };
    if (sort === "pop") {
      return (a, b) => {
        const pa = popOf(a);
        const pb = popOf(b);
        // Missing pops sort to the bottom; both-missing fall through
        // to alphabetical so the order stays deterministic.
        if (pa == null && pb == null) return labelOf(a).localeCompare(labelOf(b));
        if (pa == null) return 1;
        if (pb == null) return -1;
        if (pb !== pa) return pb - pa; // descending
        return labelOf(a).localeCompare(labelOf(b));
      };
    }
    return (a, b) => labelOf(a).localeCompare(labelOf(b));
  }

  let generatorsIndex: GeneratorsIndex | null = null;
  let generatorsWired = false;

  async function loadGeneratorsIndex(): Promise<GeneratorsIndex | null> {
    if (generatorsIndex) return generatorsIndex;
    try {
      const r = await fetch(`${baseUrl}/generators-index.json`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      generatorsIndex = (await r.json()) as GeneratorsIndex;
      return generatorsIndex;
    } catch (e) {
      console.warn("generators-index fetch failed:", e);
      return null;
    }
  }

  function currentTemplate(): GenTemplate | null {
    if (!generatorsIndex || !generators.templateId) return null;
    const block = generatorsIndex.geoTypes[generators.geo];
    return block.templates.find((t) => t.id === generators.templateId) ?? null;
  }

  function renderGenTemplateList(): void {
    const sel = shell.querySelector<HTMLSelectElement>(
      "[data-role='gen-template']",
    );
    const info = shell.querySelector<HTMLElement>(
      "[data-role='gen-template-info']",
    );
    if (!sel || !generatorsIndex) return;
    const block = generatorsIndex.geoTypes[generators.geo];
    const q = generators.templateSearch.toLowerCase().trim();
    const matches = block.templates.filter((t) => {
      if (!q) return true;
      return (
        t.label.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q)
      );
    });
    // Group templates by topic and render as <optgroup>s in topic order so
    // related indicators (all water use, all NAEP scores, …) sit together
    // instead of one flat list. Topic is derived by id pattern, so new
    // templates self-group — see generator-topics.ts.
    const byTopic = new Map<string, typeof matches>();
    for (const t of matches) {
      const topic = topicForTemplate(t.id);
      const bucket = byTopic.get(topic);
      if (bucket) bucket.push(t);
      else byTopic.set(topic, [t]);
    }
    sel.innerHTML = GENERATOR_TOPICS.filter((g) => byTopic.has(g.id))
      .map((g) => {
        const opts = byTopic
          .get(g.id)!
          .slice()
          .sort((a, b) => a.label.localeCompare(b.label))
          .map(
            (t) =>
              `<option value="${escapeHtml(t.id)}">${escapeHtml(t.label)} (${t.count})</option>`,
          )
          .join("");
        return `<optgroup label="${escapeHtml(g.label)}">${opts}</optgroup>`;
      })
      .join("");
    // Preserve selection if still in the filtered set; else pick the
    // first match (so the form is always actionable).
    if (
      generators.templateId &&
      matches.some((t) => t.id === generators.templateId)
    ) {
      sel.value = generators.templateId;
    } else if (matches.length > 0) {
      generators.templateId = matches[0].id;
      sel.value = matches[0].id;
    } else {
      generators.templateId = null;
    }
    // Description + entity-count summary line.
    const t = currentTemplate();
    if (info) {
      if (t) {
        info.textContent = t.description
          ? `${t.description}  · ${t.count} ${generators.geo} entities have data.`
          : `${t.count} ${generators.geo} entities have data.`;
      } else if (matches.length === 0) {
        info.textContent = "No templates match this filter.";
      } else {
        info.textContent = "";
      }
    }
    renderGenEntityUI();
  }

  function renderGenPresets(): void {
    const wrap = shell.querySelector<HTMLElement>("[data-role='gen-preset-wrap']");
    const sel = shell.querySelector<HTMLSelectElement>("[data-role='gen-preset']");
    if (!wrap || !sel || !generatorsIndex) return;
    // Build the usable-preset set FIRST — we use it both to populate
    // the dropdown AND to decide whether the Preset mode radio should
    // be enabled at all. Filtering rule (author request, 2026):
    //
    //   "A preset should only show if at least half its membership
    //    is present, and all presets should display, for the indicator,
    //    how many of their members have valid data (so we might see
    //    'BRICS (4/5)')."
    //
    // present = preset members AND in the current template's source
    //           map (the indicator has data for them).
    // total   = canonical group size from preset.total when set
    //           (e.g. G7 = 7, BRICS = 5, Top 12 metros = 12), else
    //           preset.codes.length (region presets where the codes
    //           list IS the canonical definition).
    //
    // Drop the preset entirely when present * 2 < total (less than
    // half). Always render the count as "present/total" so the reader
    // sees the coverage at a glance — "Top 12 (10/12)" tells them
    // immediately which canonical group it is + that 2 are missing.
    const block = generatorsIndex.geoTypes[generators.geo];
    const t = currentTemplate();
    const availableEntities = new Set(t ? Object.keys(t.sourceMap) : []);
    // Half-coverage filter + present/total counts come from the
    // generator-presets lib so the rule is one place + unit-testable.
    // See src/lib/generator-presets.ts + .test.ts for the spec.
    const usablePresets = filterUsablePresets(
      block.presets as Record<string, PresetDef>,
      availableEntities,
    );
    // Toggle the Preset radio button + its label based on whether
    // there's anything to pick. Disabled radio + dimmed label tells
    // the reader "this mode wouldn't do anything for the indicator
    // you've selected" without removing the option entirely (which
    // would leave them wondering where it went between templates).
    const presetRadio = shell.querySelector<HTMLInputElement>(
      "input[data-role='gen-mode'][value='preset']",
    );
    if (presetRadio) {
      const hasUsable = usablePresets.length > 0;
      presetRadio.disabled = !hasUsable;
      // Walk up to the <label> wrapper to dim the entire row, not
      // just the radio dot. .map-radio-row-disabled is added in CSS
      // below alongside the existing .map-radio-row rule.
      const labelRow = presetRadio.closest<HTMLElement>(".map-radio-row");
      if (labelRow) {
        labelRow.classList.toggle("map-radio-row-disabled", !hasUsable);
        labelRow.title = hasUsable
          ? ""
          : "No presets available for this indicator + geography combination.";
      }
      // If the user was on "preset" mode and it just became invalid
      // (e.g. they switched indicators), fall back to "all" mode so
      // the chart-preview area doesn't stick at an empty-chart state.
      if (!hasUsable && generators.mode === "preset") {
        generators.mode = "all";
        const allRadio = shell.querySelector<HTMLInputElement>(
          "input[data-role='gen-mode'][value='all']",
        );
        if (allRadio) allRadio.checked = true;
      }
    }
    if (generators.mode !== "preset") {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    const opts: string[] = usablePresets.map(
      (p) =>
        `<option value="${escapeHtml(p.key)}">${escapeHtml(p.label)} (${p.present}/${p.total})</option>`,
    );
    sel.innerHTML = opts.join("");
    if (generators.preset && opts.some((o) => o.includes(`value="${generators.preset}"`))) {
      sel.value = generators.preset;
    } else if (sel.options.length > 0) {
      generators.preset = sel.options[0].value;
      sel.value = generators.preset;
    } else {
      generators.preset = null;
    }
  }

  function renderGenCustomList(): void {
    const wrap = shell.querySelector<HTMLElement>("[data-role='gen-custom-wrap']");
    const list = shell.querySelector<HTMLElement>("[data-role='gen-entity-list']");
    if (!wrap || !list || !generatorsIndex) return;
    if (generators.mode !== "custom") {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    const block = generatorsIndex.geoTypes[generators.geo];
    const t = currentTemplate();
    const available = t ? Object.keys(t.sourceMap) : Object.keys(block.entities);
    const q = generators.entitySearch.toLowerCase().trim();
    // Filter + alphabetize by name. Cap at 200 entries for the metro
    // case (393 MSAs would otherwise drown the panel).
    const filtered = available
      .filter((code) => {
        if (!q) return true;
        const e = block.entities[code];
        if (!e) return false;
        return (
          e.short.toLowerCase().includes(q) ||
          e.name.toLowerCase().includes(q) ||
          code.includes(q)
        );
      })
      .sort(genEntityComparator(generators.geo, generators.sort));
    const VISIBLE_CAP = 200;
    const shown = filtered.slice(0, VISIBLE_CAP);
    const items = shown.map((code) => {
      const e = block.entities[code];
      // Append population to the row label when sorting by population
      // so users can see the values driving the order.
      const popSuffix =
        generators.sort === "pop" && typeof e?.pop === "number"
          ? ` — ${formatEntityPop(e.pop)}`
          : "";
      const label = e
        ? `${escapeHtml(e.name)} (${escapeHtml(code)})${popSuffix}`
        : escapeHtml(code);
      const checked = generators.selected.has(code) ? " checked" : "";
      return (
        `<label class="gen-entity-row">` +
        `<input type="checkbox" data-role="gen-entity-check" value="${escapeHtml(code)}"${checked} />` +
        `<span>${label}</span>` +
        `</label>`
      );
    });
    if (filtered.length > VISIBLE_CAP) {
      items.push(
        `<p class="muted small">Showing first ${VISIBLE_CAP} of ${filtered.length}. Refine the search.</p>`,
      );
    }
    if (items.length === 0) {
      items.push(`<p class="muted small">No entities match.</p>`);
    }
    list.innerHTML = items.join("");
    // Re-wire checkbox listeners (innerHTML clobbers them).
    list.querySelectorAll<HTMLInputElement>(
      "input[data-role='gen-entity-check']",
    ).forEach((el) => {
      el.addEventListener("change", () => {
        if (el.checked) generators.selected.add(el.value);
        else generators.selected.delete(el.value);
        updateGenReadout();
      });
    });
  }

  function renderGenEntityUI(): void {
    renderGenPresets();
    renderGenCustomList();
    updateGenReadout();
  }

  function effectiveSelectedEntities(): string[] {
    if (!generatorsIndex) return [];
    const t = currentTemplate();
    if (!t) return [];
    const available = Object.keys(t.sourceMap);
    if (generators.mode === "all") return available;
    if (generators.mode === "preset") {
      if (!generators.preset) return [];
      const preset = generatorsIndex.geoTypes[generators.geo].presets[generators.preset];
      if (!preset) return [];
      // Silent-skip: filter to entities that the template actually has.
      return preset.codes.filter((c) => c in t.sourceMap);
    }
    // custom
    return [...generators.selected].filter((c) => c in t.sourceMap);
  }

  /** Profile flavor: how many indicator tiles the picked entity yields
   *  (indicators that actually have data for it). 0 when no entity picked. */
  function profileAvailableCount(): number {
    if (!generatorsIndex || !generators.profileEntity) return 0;
    const block = generatorsIndex.geoTypes[generators.geo];
    const order = block.profileOrder ?? block.templates.map((t) => t.id);
    const byId = new Map(block.templates.map((t) => [t.id, t]));
    let n = 0;
    for (const tid of order) {
      const tpl = byId.get(tid);
      if (tpl && tpl.sourceMap[generators.profileEntity]) n++;
    }
    return n;
  }

  // Share URL is base64url(JSON(state)); ~150 bytes/tile post-encoding, so
  // above ~70 tiles it overflows and the user must save to their account.
  const GEN_URL_SAFE_TILE_BUDGET = 70;
  function genUrlHint(tiles: number): string {
    return tiles > GEN_URL_SAFE_TILE_BUDGET
      ? " · share URL too long for this many tiles — Save to my account will be required."
      : "";
  }

  function updateGenReadout(): void {
    const readout = shell.querySelector<HTMLElement>(
      "[data-role='gen-readout']",
    );
    if (!readout) return;
    // Profile flavor counts indicators-for-the-entity (the tile count), NOT
    // entities — otherwise it reports the entity count (e.g. 393 metros) and
    // contradicts the "you'll get N tiles" caption above the dropdown.
    if (generators.layout === "profile") {
      if (!generators.profileEntity) {
        readout.textContent = "";
        return;
      }
      const n = profileAvailableCount();
      readout.textContent =
        n === 0
          ? "No indicators have data for this entity."
          : `${n} chart${n === 1 ? "" : "s"} will be generated.${genUrlHint(n)}`;
      return;
    }
    const t = currentTemplate();
    if (!t) {
      readout.textContent = "Pick a series template first.";
      return;
    }
    const eff = effectiveSelectedEntities();
    if (eff.length === 0) {
      readout.textContent = "No entities selected.";
      return;
    }
    // Skip count: requested but unavailable.
    let requested = 0;
    if (generators.mode === "all") {
      requested = Object.keys(generatorsIndex!.geoTypes[generators.geo].entities).length;
    } else if (generators.mode === "preset") {
      const preset = generators.preset
        ? generatorsIndex!.geoTypes[generators.geo].presets[generators.preset]
        : null;
      requested = preset ? preset.codes.length : 0;
    } else {
      requested = generators.selected.size;
    }
    const skip = requested - eff.length;
    const urlHint = genUrlHint(eff.length);
    if (skip > 0) {
      readout.textContent =
        `${eff.length} chart${eff.length === 1 ? "" : "s"} will be generated · ${skip} skipped (no data for this template).${urlHint}`;
    } else {
      readout.textContent =
        `${eff.length} chart${eff.length === 1 ? "" : "s"} will be generated.${urlHint}`;
    }
  }

  async function renderGeneratorsBuilder(): Promise<void> {
    const idx = await loadGeneratorsIndex();
    if (!idx) {
      const panel = shell.querySelector<HTMLElement>(
        "[data-role='lib-panel-generators']",
      );
      if (panel) {
        panel.innerHTML =
          '<p class="muted small">Could not load the generators catalog. Please try again later.</p>';
      }
      return;
    }
    if (generatorsWired) {
      renderGenTemplateList();
      return;
    }
    generatorsWired = true;

    // Layout radio — "By indicator" (template × entities) vs.
    // "Profile" (entity × templates). Drives which sub-panels render.
    shell.querySelectorAll<HTMLInputElement>(
      "input[data-role='gen-layout']",
    ).forEach((el) => {
      if (el.value === generators.layout) el.checked = true;
      el.addEventListener("change", () => {
        if (!el.checked) return;
        generators.layout = el.value as GenLayout;
        // Reset profile selection when switching layouts; the dropdown
        // would otherwise carry the previous geo's last pick which
        // can't roundtrip cleanly across modes.
        generators.profileEntity = null;
        syncGenLayoutVisibility();
        renderGenTemplateList();
        renderGenProfileEntityList();
        updateGenReadout();
      });
    });

    // Geo radio
    shell.querySelectorAll<HTMLInputElement>(
      "input[data-role='gen-geo']",
    ).forEach((el) => {
      if (el.value === generators.geo) el.checked = true;
      el.addEventListener("change", () => {
        if (!el.checked) return;
        generators.geo = el.value as GenGeo;
        // Reset template + mode-specific state when geo changes (an
        // MSA-mode preset like "Northeast" doesn't translate to
        // country mode etc.).
        generators.templateId = null;
        generators.preset = null;
        generators.selected.clear();
        generators.profileEntity = null;
        renderGenTemplateList();
        renderGenProfileEntityList();
      });
    });
    // Mode radio
    shell.querySelectorAll<HTMLInputElement>(
      "input[data-role='gen-mode']",
    ).forEach((el) => {
      if (el.value === generators.mode) el.checked = true;
      el.addEventListener("change", () => {
        if (!el.checked) return;
        generators.mode = el.value as GenMode;
        renderGenEntityUI();
      });
    });

    // Sort radio (alphabetical / by-population). Affects the Custom
    // entity list rendering AND the order generated tiles land in.
    shell.querySelectorAll<HTMLInputElement>(
      "input[data-role='gen-sort']",
    ).forEach((el) => {
      if (el.value === generators.sort) el.checked = true;
      el.addEventListener("change", () => {
        if (!el.checked) return;
        generators.sort = el.value as GenSort;
        renderGenCustomList();
      });
    });

    // Template search + dropdown
    const tplSearch = shell.querySelector<HTMLInputElement>(
      "[data-role='gen-template-search']",
    );
    if (tplSearch) {
      tplSearch.addEventListener("input", () => {
        generators.templateSearch = tplSearch.value;
        renderGenTemplateList();
      });
    }
    const tplSel = shell.querySelector<HTMLSelectElement>(
      "[data-role='gen-template']",
    );
    if (tplSel) {
      tplSel.addEventListener("change", () => {
        generators.templateId = tplSel.value || null;
        // Clear the custom selection — the previous template's entities
        // may not all map to the new one.
        generators.selected.clear();
        renderGenTemplateList();
      });
    }

    // Preset dropdown
    const presetSel = shell.querySelector<HTMLSelectElement>(
      "[data-role='gen-preset']",
    );
    if (presetSel) {
      presetSel.addEventListener("change", () => {
        generators.preset = presetSel.value || null;
        updateGenReadout();
      });
    }

    // Custom search + bulk select / clear
    const entSearch = shell.querySelector<HTMLInputElement>(
      "[data-role='gen-entity-search']",
    );
    if (entSearch) {
      entSearch.addEventListener("input", () => {
        generators.entitySearch = entSearch.value;
        renderGenCustomList();
      });
    }
    const selAll = shell.querySelector<HTMLButtonElement>(
      "[data-role='gen-entity-all']",
    );
    if (selAll) {
      selAll.addEventListener("click", () => {
        // Add every currently-visible entity code to the selected set.
        const list = shell.querySelector<HTMLElement>(
          "[data-role='gen-entity-list']",
        );
        if (!list) return;
        list.querySelectorAll<HTMLInputElement>(
          "input[data-role='gen-entity-check']",
        ).forEach((el) => {
          el.checked = true;
          generators.selected.add(el.value);
        });
        updateGenReadout();
      });
    }
    const selNone = shell.querySelector<HTMLButtonElement>(
      "[data-role='gen-entity-none']",
    );
    if (selNone) {
      selNone.addEventListener("click", () => {
        generators.selected.clear();
        renderGenCustomList();
      });
    }

    // Section title input
    const titleInput = shell.querySelector<HTMLInputElement>(
      "[data-role='gen-section-title']",
    );
    if (titleInput) {
      titleInput.addEventListener("input", () => {
        generators.sectionTitle = titleInput.value;
      });
    }

    // Profile mode: entity search + single-select
    const profSearch = shell.querySelector<HTMLInputElement>(
      "[data-role='gen-profile-search']",
    );
    if (profSearch) {
      profSearch.addEventListener("input", () => {
        generators.profileSearch = profSearch.value;
        renderGenProfileEntityList();
      });
    }
    const profSel = shell.querySelector<HTMLSelectElement>(
      "[data-role='gen-profile-entity']",
    );
    if (profSel) {
      profSel.addEventListener("change", () => {
        generators.profileEntity = profSel.value || null;
        updateGenProfileInfo();
        updateGenReadout();
      });
    }

    // Generate button
    const addBtn = shell.querySelector<HTMLButtonElement>(
      "[data-role='gen-add-btn']",
    );
    if (addBtn) {
      addBtn.addEventListener("click", () => {
        void generateMassDashboard();
      });
    }

    syncGenLayoutVisibility();
    renderGenTemplateList();
    renderGenProfileEntityList();
  }

  /**
   * Show/hide the right sub-panels based on the layout choice. Profile
   * mode hides the template picker + the entities sub-form (because
   * the user picks one entity instead, and templates come from the
   * profileOrder list). Indicator mode hides the profile picker.
   */
  function syncGenLayoutVisibility(): void {
    const tplWrap = shell.querySelector<HTMLElement>(
      "[data-role='gen-template-wrap']",
    );
    const entSection = shell.querySelector<HTMLElement>(
      "[data-role='gen-entity-section']",
    );
    const profWrap = shell.querySelector<HTMLElement>(
      "[data-role='gen-profile-wrap']",
    );
    const profile = generators.layout === "profile";
    if (tplWrap) tplWrap.hidden = profile;
    if (entSection) entSection.hidden = profile;
    if (profWrap) profWrap.hidden = !profile;
  }

  /**
   * Render the profile-mode single-entity dropdown. Filters by
   * `generators.profileSearch` and orders by current sort (alpha or
   * pop). Adds an entity count to the placeholder so the user knows
   * how many candidates are available.
   */
  function renderGenProfileEntityList(): void {
    const sel = shell.querySelector<HTMLSelectElement>(
      "[data-role='gen-profile-entity']",
    );
    if (!sel || !generatorsIndex) return;
    const block = generatorsIndex.geoTypes[generators.geo];
    const codes = Object.keys(block.entities);
    const q = generators.profileSearch.trim().toLowerCase();
    const filtered = q
      ? codes.filter((c) => {
          const e = block.entities[c];
          return (
            c.toLowerCase().includes(q) ||
            e.short.toLowerCase().includes(q) ||
            e.name.toLowerCase().includes(q)
          );
        })
      : codes;
    const cmp = genEntityComparator(generators.geo, generators.sort);
    filtered.sort(cmp);
    // Build options. Show the long name so DMV-area metros differentiate
    // by state suffix; population in K/M for context where present.
    const opts: string[] = [];
    opts.push(`<option value="">— pick a ${block.label.toLowerCase()} —</option>`);
    for (const c of filtered) {
      const e = block.entities[c];
      const pop = e.pop != null ? ` (${formatEntityPop(e.pop)})` : "";
      const selected = c === generators.profileEntity ? " selected" : "";
      opts.push(
        `<option value="${escapeHtml(c)}"${selected}>${escapeHtml(e.name)}${pop}</option>`,
      );
    }
    sel.innerHTML = opts.join("");
    updateGenProfileInfo();
  }

  /**
   * Update the small caption under the profile-entity dropdown with a
   * count of how many templates the picked entity actually has data
   * for. The user gets that many tiles when they hit Generate.
   */
  function updateGenProfileInfo(): void {
    const info = shell.querySelector<HTMLElement>(
      "[data-role='gen-profile-info']",
    );
    if (!info || !generatorsIndex) return;
    const block = generatorsIndex.geoTypes[generators.geo];
    if (!generators.profileEntity) {
      info.textContent = "Pick an entity to see how many indicators are available.";
      return;
    }
    const order = block.profileOrder ?? block.templates.map((t) => t.id);
    const templatesById = new Map(block.templates.map((t) => [t.id, t]));
    let available = 0;
    for (const tid of order) {
      const tpl = templatesById.get(tid);
      if (tpl && tpl.sourceMap[generators.profileEntity]) available++;
    }
    const total = block.templates.length;
    info.textContent =
      `${available} of ${total} available indicators have data for this entity — ` +
      `you'll get ${available} tiles.`;
  }

  async function generateMassDashboard(): Promise<void> {
    if (!generatorsIndex) return;
    if (generators.layout === "profile") {
      await generateEntityProfile();
      return;
    }
    const t = currentTemplate();
    if (!t) {
      const readout = shell.querySelector<HTMLElement>(
        "[data-role='gen-readout']",
      );
      if (readout) readout.textContent = "Pick a series template first.";
      return;
    }
    const eff = effectiveSelectedEntities();
    if (eff.length === 0) {
      const readout = shell.querySelector<HTMLElement>(
        "[data-role='gen-readout']",
      );
      if (readout) readout.textContent = "Select at least one entity.";
      return;
    }
    const allowed = await checkComposeAction("generate_mass_dashboard");
    if (!allowed) {
      showSigninPrompt("generate_mass_dashboard");
      return;
    }
    const block = generatorsIndex.geoTypes[generators.geo];

    // Decide whether to drop the generated charts into a NEW section
    // or append to the currently-active one. Title set => new section;
    // blank => active section.
    let target: UISection;
    const sectionTitle = generators.sectionTitle.trim();
    if (sectionTitle) {
      target = {
        title: sectionTitle,
        description: "",
        charts: [],
      };
      state.sections.push(target);
      store.activeSectionIdx = state.sections.length - 1;
    } else {
      clampActiveSection();
      target = state.sections[store.activeSectionIdx];
      if (!target) return;
    }

    // Mint one inline-chart per entity. Title each tile with the
    // entity's short name (e.g. "Boston") so the section reads as
    // a per-region grid rather than 50 copies of the same title.
    // The order respects the user's sort-by choice — alphabetical
    // (default) or population (largest first; entities lacking a
    // pop fall back to alpha at the end of the list).
    const order = eff.slice().sort(
      genEntityComparator(generators.geo, generators.sort),
    );
    let added = 0;
    for (const code of order) {
      const sourceId = t.sourceMap[code];
      if (!sourceId) continue;
      const entity = block.entities[code];
      const tileTitle = entity?.short ?? code;
      const chartId = INLINE_PREFIX + nanoid(8);
      state.inlineCharts[chartId] = {
        title: tileTitle,
        sources: [sourceId],
        normalize: "raw",
      };
      target.charts.push(chartId);
      added += 1;
    }

    writeUrl();
    renderComposition();
    track("compose_mass_dashboard_generated", {
      geo: generators.geo,
      template: t.id,
      mode: generators.mode,
      preset: generators.preset ?? "",
      addedTiles: added,
      newSection: !!sectionTitle,
    });

    // Reset the section-title input + custom selection so the next
    // generate stacks cleanly (typical pattern: NE in one section,
    // then South in the next).
    if (sectionTitle) {
      generators.sectionTitle = "";
      const titleInput = shell.querySelector<HTMLInputElement>(
        "[data-role='gen-section-title']",
      );
      if (titleInput) titleInput.value = "";
    }
    const readout = shell.querySelector<HTMLElement>(
      "[data-role='gen-readout']",
    );
    if (readout) {
      const where = sectionTitle ? `new section "${sectionTitle}"` : "active section";
      const overflowBanner = shell.querySelector<HTMLElement>(
        "[data-role='url-overflow']",
      );
      const overflowed = overflowBanner && !overflowBanner.hidden;
      readout.textContent = overflowed
        ? `Added ${added} chart${added === 1 ? "" : "s"} to ${where} (URL is full — see banner above to save).`
        : `Added ${added} chart${added === 1 ? "" : "s"} to ${where}.`;
    }
  }

  /**
   * Profile-mode generation: one entity × every available indicator
   * for that entity, ordered by the geo block's profileOrder. Emits
   * a single-source tile per template-with-data, titled by the
   * template's label so the section reads like a dossier:
   *   Total population
   *   Median household income
   *   People in poverty
   *   ...
   *
   * Default section title is "<entity name> profile" when blank.
   */
  async function generateEntityProfile(): Promise<void> {
    if (!generatorsIndex) return;
    const readout = shell.querySelector<HTMLElement>(
      "[data-role='gen-readout']",
    );
    const code = generators.profileEntity;
    if (!code) {
      if (readout) readout.textContent = "Pick an entity first.";
      return;
    }
    const block = generatorsIndex.geoTypes[generators.geo];
    const entity = block.entities[code];
    if (!entity) {
      if (readout) readout.textContent = "Unknown entity — try a different pick.";
      return;
    }
    const allowed = await checkComposeAction("generate_mass_dashboard");
    if (!allowed) {
      showSigninPrompt("generate_mass_dashboard");
      return;
    }

    // Build the ordered list of (templateId, sourceId) pairs: only
    // templates where this entity actually has data, in profileOrder.
    const order = block.profileOrder ?? block.templates.map((t) => t.id);
    const templatesById = new Map(block.templates.map((t) => [t.id, t]));
    const tiles: { templateLabel: string; sourceId: string }[] = [];
    for (const tid of order) {
      const tpl = templatesById.get(tid);
      if (!tpl) continue;
      const sourceId = tpl.sourceMap[code];
      if (!sourceId) continue;
      tiles.push({ templateLabel: tpl.label, sourceId });
    }
    if (tiles.length === 0) {
      if (readout) readout.textContent = "No indicators have data for this entity.";
      return;
    }

    // Title default: "<entity name> profile". User-supplied title in
    // the section-title input overrides. A bare entity short name (no
    // "profile" suffix) avoids stuttering when the section is then
    // embedded in a larger dashboard titled "State comparisons" etc.
    let sectionTitle = generators.sectionTitle.trim();
    if (!sectionTitle) sectionTitle = `${entity.short} profile`;
    const target: UISection = {
      title: sectionTitle,
      description: "",
      charts: [],
    };
    state.sections.push(target);
    store.activeSectionIdx = state.sections.length - 1;

    let added = 0;
    for (const { templateLabel, sourceId } of tiles) {
      const chartId = INLINE_PREFIX + nanoid(8);
      // Tile title is the template label (the human series name) —
      // matches how a dossier-style profile reads, vs the "By indicator"
      // flow which titles each tile by entity.
      state.inlineCharts[chartId] = {
        title: templateLabel,
        sources: [sourceId],
        normalize: "raw",
      };
      target.charts.push(chartId);
      added += 1;
    }

    writeUrl();
    renderComposition();
    track("compose_mass_dashboard_generated", {
      geo: generators.geo,
      template: "__profile__",
      mode: "profile",
      preset: "",
      addedTiles: added,
      newSection: true,
    });

    // Clear the title input so a subsequent profile generation in the
    // same session stacks cleanly with its own auto-title.
    generators.sectionTitle = "";
    const titleInput = shell.querySelector<HTMLInputElement>(
      "[data-role='gen-section-title']",
    );
    if (titleInput) titleInput.value = "";
    if (readout) {
      const overflowBanner = shell.querySelector<HTMLElement>(
        "[data-role='url-overflow']",
      );
      const overflowed = overflowBanner && !overflowBanner.hidden;
      readout.textContent = overflowed
        ? `Added ${added} tile${added === 1 ? "" : "s"} to "${sectionTitle}" (URL is full — see banner above to save).`
        : `Added ${added} tile${added === 1 ? "" : "s"} to "${sectionTitle}".`;
    }
  }


  return { renderGeneratorsBuilder };
}