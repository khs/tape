/**
 * Derived-source modal (Plan 2d) -- the "+ Derived source" builder.
 *
 * A derived source = A op B (each of A/B a real source ID or another derived
 * ID, recursive), stored in state.inlineSources keyed by `derived:<nanoid>`.
 * Owns the A/B operand pickers, the auto-name + "rebuild total" / combine-hint
 * suggestion chips, and the create flow (optionally auto-adding the result as a
 * chart in the active section).
 *
 * Extracted from compose.astro via the create<Feature>(ctx) factory. The A/B
 * operands are picked via two shared <SourcePicker> islands (instanceId ds-a /
 * ds-b, mounted in compose); this module feeds them the user's derived sources
 * (set-extra-sources) + cross-disables each against the other side's pick
 * (set-disabled-ids), and listens for the source-picker:pick event. library is
 * read via getLibrary() per fn (guard narrowing preserved).
 * renderCustomChartSources is a cc-modal fn (still in compose), refreshed after
 * a create so an open cc-modal picks up the new source.
 */
import { nanoid } from "nanoid";
import { track } from "../track";
import { packSourceIds } from "../analytics-helpers";
import { DERIVED_PREFIX, INLINE_PREFIX, isDerivedId } from "./ids";
import type {
  UIState,
  ComposerStore,
  DerivedModalState,
  ChartCombineOp,
} from "./state";
import type { LibraryPayload, LibrarySource } from "./library";

export interface DerivedSourceModalContext {
  shell: HTMLElement;
  store: ComposerStore;
  state: UIState;
  getLibrary: () => LibraryPayload | null;
  checkComposeAction: (action: string) => Promise<boolean>;
  showSigninPrompt: (reason: string) => void;
  clampActiveSection: () => void;
  writeUrl: () => void;
  renderComposition: () => void;
  renderCustomChartSources: () => void;
}

export function createDerivedSourceModal(ctx: DerivedSourceModalContext) {
  const {
    shell,
    store,
    state,
    getLibrary,
    checkComposeAction,
    showSigninPrompt,
    clampActiveSection,
    writeUrl,
    renderComposition,
    renderCustomChartSources,
  } = ctx;
  const dsModal = store.dsModal;
  // Derived sources (the ones the user has already created) exposed to BOTH
  // operand SourcePickers as extraSources so they are pickable + recursive
  // derivation works. Real sources come from library.json inside SourcePicker
  // itself; only the derived ones need injecting. The " (derived)" suffix
  // distinguishes them in the picker results.
  function derivedExtraSources(): {
    id: string;
    name: string;
    tags: string[];
  }[] {
    return Object.entries(state.inlineSources).map(([id, spec]) => ({
      id,
      name: `${spec.name} (derived)`,
      tags: spec.tags ?? [],
    }));
  }

  function dsSourceLabel(id: string): string {
    const library = getLibrary();
    if (!id) return "?";
    if (isDerivedId(id)) return state.inlineSources[id]?.name ?? id;
    const s = library?.sources[id];
    return s?.shortName ?? s?.name ?? id;
  }

  // Resolve the tag set of a single source ID. Real sources read from
  // library.json (populated by pipelines/backfill_source_tags.py).
  // Derived sources read from state.inlineSources[id].tags, which
  // itself was inherited from its own parents at creation time, so
  // arbitrary nesting flattens correctly without re-walking the tree.
  function sourceTagsFor(id: string): string[] {
    const library = getLibrary();
    if (isDerivedId(id)) return state.inlineSources[id]?.tags ?? [];
    const s = library?.sources[id] as
      | (LibrarySource & { tags?: string[] })
      | undefined;
    return s?.tags ?? [];
  }

  // Derived sources' tag set = union(A.tags, B.tags) plus a "custom"
  // tag. Recursive derivation just works: when a derived source's
  // parent is itself derived, its tags already include "custom" + the
  // ancestor's parents' tags, so the union flattens correctly.
  function inheritedTagsForDerived(aId: string, bId: string): string[] {
    const s = new Set<string>([...sourceTagsFor(aId), ...sourceTagsFor(bId)]);
    s.add("custom");
    return [...s].sort();
  }

  // Equation-form name auto-derived from picked A, op, B. Used as both
  // the input's placeholder (so the user sees what they'll get if they
  // leave the field blank) and the fallback value on submit.
  function computeDerivedDefaultName(): string {
    if (!dsModal.a || !dsModal.b) return "";
    const symbol =
      dsModal.op === "divide"
        ? "÷"
        : dsModal.op === "sum"
          ? "+"
          : dsModal.op === "multiply"
            ? "×"
            : "−";
    return `${dsSourceLabel(dsModal.a)} ${symbol} ${dsSourceLabel(dsModal.b)}`;
  }

  function syncDerivedHint(): void {
    const hint = shell.querySelector<HTMLElement>("[data-role='ds-hint']");
    const create = shell.querySelector<HTMLButtonElement>("[data-role='ds-create']");
    const nameInput = shell.querySelector<HTMLInputElement>(
      "[data-role='ds-name']",
    );
    const defaultName = computeDerivedDefaultName();
    if (nameInput) {
      // Show the equation as the placeholder so the user sees what name
      // they'll get if they leave the field blank.
      nameInput.placeholder = defaultName || "e.g. Retail-gas / WTI";
    }
    if (hint) {
      const ready = !!(dsModal.a && dsModal.b && dsModal.a !== dsModal.b);
      hint.textContent = ready
        ? `→ ${dsModal.name.trim() || defaultName}`
        : !dsModal.a || !dsModal.b
          ? "Pick A and B."
          : dsModal.a === dsModal.b
            ? "A and B must be different."
            : "";
    }
    if (create) {
      const ready = !!(dsModal.a && dsModal.b && dsModal.a !== dsModal.b);
      create.disabled = !ready;
      if (!ready) {
        create.title = !dsModal.a || !dsModal.b
          ? "Pick A and B first."
          : "A and B must be different.";
      } else {
        create.removeAttribute("title");
      }
    }
    syncRebuildSuggestion();
    syncPxqSuggestion();
  }

  // A rate/share source can carry derivedFrom = { numerator, denominator,
  // scale } linking it back to the count it was divided out of (e.g.
  // "% adults 25+ with a bachelor's degree" → bachelors_plus ÷ adults_25plus).
  // When such a source is picked as A, we can offer "× <denominator>" to
  // rebuild the underlying total. The denominator must itself be a visible
  // (pickable) source; the numerator may be hidden, so we don't require it
  // here — the multiply engine reconstructs the count from rate × base.
  function rebuildCandidateFor(
    id: string,
  ): { numerator: string; denominator: string } | null {
    const library = getLibrary();
    if (!id || isDerivedId(id)) return null;
    const df = (
      library?.sources[id] as
        | { derivedFrom?: { numerator?: string; denominator?: string } }
        | undefined
    )?.derivedFrom;
    if (!df?.denominator) return null;
    if (!library?.sources[df.denominator]) return null;
    return { numerator: df.numerator ?? "", denominator: df.denominator };
  }

  // Show/refresh the "rebuild total" affordance based on the current A pick.
  // Driven entirely off dsModal.a + dsModal.op/b so it reflects whether the
  // suggestion has already been applied. Called from syncDerivedHint (which
  // fires on every operand/op change), so no separate wiring on each change.
  function syncRebuildSuggestion(): void {
    const wrap = shell.querySelector<HTMLElement>("[data-role='ds-rebuild']");
    const btn = shell.querySelector<HTMLButtonElement>(
      "[data-role='ds-rebuild-apply']",
    );
    const help = shell.querySelector<HTMLElement>("[data-role='ds-rebuild-help']");
    if (!wrap || !btn || !help) return;
    const cand = rebuildCandidateFor(dsModal.a);
    if (!cand) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    const denomLabel = dsSourceLabel(cand.denominator);
    const aLabel = dsSourceLabel(dsModal.a);
    const applied = dsModal.op === "multiply" && dsModal.b === cand.denominator;
    btn.textContent = applied ? `✓ × ${denomLabel}` : `× ${denomLabel}`;
    btn.classList.toggle("ds-rebuild-chip-active", applied);
    help.textContent = applied
      ? `Rebuilding the total: ${aLabel} × ${denomLabel}.`
      : `${aLabel} is a share. Multiply by ${denomLabel} to rebuild the underlying total.`;
  }

  // combineHint chip: A carries `combineHint { partner, op, resultLabel }`
  // (e.g. a NASS price linked to its quantity partner). Returns it when the
  // partner is a real, pickable source. Mirrors rebuildCandidateFor.
  function pxqCandidateFor(
    id: string,
  ): { partner: string; op: ChartCombineOp; resultLabel: string } | null {
    const library = getLibrary();
    if (!id || isDerivedId(id)) return null;
    const hint = (
      library?.sources[id] as
        | {
            combineHint?: {
              partner?: string;
              op?: ChartCombineOp;
              resultLabel?: string;
            };
          }
        | undefined
    )?.combineHint;
    if (!hint?.partner || !hint.op || !hint.resultLabel) return null;
    if (!library?.sources[hint.partner]) return null;
    return { partner: hint.partner, op: hint.op, resultLabel: hint.resultLabel };
  }

  // Show/refresh the combine-hint chip off the current A pick. Mirrors
  // syncRebuildSuggestion; called from syncDerivedHint alongside it.
  function syncPxqSuggestion(): void {
    const wrap = shell.querySelector<HTMLElement>("[data-role='ds-pxq']");
    const btn = shell.querySelector<HTMLButtonElement>(
      "[data-role='ds-pxq-apply']",
    );
    const help = shell.querySelector<HTMLElement>("[data-role='ds-pxq-help']");
    if (!wrap || !btn || !help) return;
    const cand = pxqCandidateFor(dsModal.a);
    if (!cand) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    const partnerLabel = dsSourceLabel(cand.partner);
    const sym = cand.op === "multiply" ? "×" : cand.op === "divide" ? "÷" : "+";
    const applied = dsModal.op === cand.op && dsModal.b === cand.partner;
    btn.textContent = applied
      ? `✓ ${sym} ${partnerLabel}`
      : `${sym} ${partnerLabel}`;
    btn.classList.toggle("ds-rebuild-chip-active", applied);
    help.textContent = applied
      ? `Showing ${cand.resultLabel}.`
      : `${sym} ${partnerLabel} → ${cand.resultLabel}.`;
  }

  // ---- SourcePicker plumbing -------------------------------------------
  // The A and B operands are picked via two shared <SourcePicker> islands
  // (instanceId ds-a / ds-b). We dispatch inbound events to feed them the
  // derived sources + cross-disable, and listen for the pick event.
  function dispatchToPicker(
    instanceId: string,
    type: string,
    detail: unknown,
  ): void {
    const root = shell.querySelector<HTMLElement>(
      `[data-spicker-instance='${instanceId}']`,
    );
    root?.dispatchEvent(new CustomEvent(type, { detail }));
  }

  function focusPickerSearch(instanceId: string): void {
    shell
      .querySelector<HTMLInputElement>(
        `[data-spicker-instance='${instanceId}'] [data-spicker-role='search']`,
      )
      ?.focus();
  }

  // Reflect the current A/B picks: update the picked-source labels and
  // cross-disable each picker against the other side's choice (you cannot
  // divide a source by itself). Replaces the old renderDsPicker re-render.
  function updateDsOperandUI(): void {
    const aCur = shell.querySelector<HTMLElement>("[data-role='ds-a-current']");
    const bCur = shell.querySelector<HTMLElement>("[data-role='ds-b-current']");
    if (aCur) {
      aCur.textContent = dsModal.a
        ? `Picked: ${dsSourceLabel(dsModal.a)}`
        : "No source picked yet.";
    }
    if (bCur) {
      bCur.textContent = dsModal.b
        ? `Picked: ${dsSourceLabel(dsModal.b)}`
        : "No source picked yet.";
    }
    dispatchToPicker("ds-a", "source-picker:set-disabled-ids", {
      ids: dsModal.b ? [dsModal.b] : [],
    });
    dispatchToPicker("ds-b", "source-picker:set-disabled-ids", {
      ids: dsModal.a ? [dsModal.a] : [],
    });
  }

  function openDerivedSourceModal(): void {
    dsModal.name = "";
    dsModal.op = "divide";
    dsModal.a = "";
    dsModal.b = "";
    dsModal.addAsChart = true;
    const backdrop = shell.querySelector<HTMLElement>("[data-role='ds-modal']");
    if (!backdrop) return;
    backdrop.hidden = false;
    const nameInput = shell.querySelector<HTMLInputElement>("[data-role='ds-name']");
    if (nameInput) nameInput.value = "";
    const opSelect = shell.querySelector<HTMLSelectElement>("[data-role='ds-op']");
    if (opSelect) opSelect.value = "divide";
    const addAsChartChk = shell.querySelector<HTMLInputElement>(
      "[data-role='ds-add-as-chart']",
    );
    if (addAsChartChk) addAsChartChk.checked = true;
    // Clear any stale quick-divisor highlight from a prior open.
    shell
      .querySelectorAll<HTMLButtonElement>("[data-role='ds-quick']")
      .forEach((c) => c.classList.remove("ds-quick-chip-active"));
    // Feed both pickers the user's derived sources (pickable as operands)
    // and clear any cross-disable left over from a prior open.
    const extras = derivedExtraSources();
    dispatchToPicker("ds-a", "source-picker:set-extra-sources", { sources: extras });
    dispatchToPicker("ds-b", "source-picker:set-extra-sources", { sources: extras });
    updateDsOperandUI();
    syncDerivedHint();
  }

  function closeDerivedSourceModal(): void {
    const backdrop = shell.querySelector<HTMLElement>("[data-role='ds-modal']");
    if (backdrop) backdrop.hidden = true;
  }

  function wireDerivedSourceModal(): void {
    const backdrop = shell.querySelector<HTMLElement>("[data-role='ds-modal']");
    const closeBtn = shell.querySelector<HTMLButtonElement>("[data-role='ds-close']");
    const cancelBtn = shell.querySelector<HTMLButtonElement>("[data-role='ds-cancel']");
    const createBtn = shell.querySelector<HTMLButtonElement>("[data-role='ds-create']");
    const nameInput = shell.querySelector<HTMLInputElement>("[data-role='ds-name']");
    const opSelect = shell.querySelector<HTMLSelectElement>("[data-role='ds-op']");

    closeBtn?.addEventListener("click", closeDerivedSourceModal);
    cancelBtn?.addEventListener("click", closeDerivedSourceModal);
    backdrop?.addEventListener("click", (e) => {
      if (e.target === backdrop) closeDerivedSourceModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !backdrop || backdrop.hidden) return;
      closeDerivedSourceModal();
    });
    nameInput?.addEventListener("input", () => {
      dsModal.name = nameInput.value;
      syncDerivedHint();
    });
    opSelect?.addEventListener("change", () => {
      dsModal.op = opSelect.value as DerivedModalState["op"];
      syncDerivedHint();
    });
    // Operand picks come from the two shared SourcePicker islands. Each
    // pick sets its side; the disabled-card render (set-disabled-ids)
    // already blocks picking the other side's source, but we guard too.
    const aPicker = shell.querySelector<HTMLElement>(
      "[data-spicker-instance='ds-a']",
    );
    const bPicker = shell.querySelector<HTMLElement>(
      "[data-spicker-instance='ds-b']",
    );
    aPicker?.addEventListener("source-picker:pick", (e) => {
      const detail = (e as CustomEvent).detail as { sourceId?: string };
      const id = detail?.sourceId;
      if (!id || id === dsModal.b) return;
      dsModal.a = id;
      updateDsOperandUI();
      syncDerivedHint();
    });
    bPicker?.addEventListener("source-picker:pick", (e) => {
      const detail = (e as CustomEvent).detail as { sourceId?: string };
      const id = detail?.sourceId;
      if (!id || id === dsModal.a) return;
      dsModal.b = id;
      updateDsOperandUI();
      syncDerivedHint();
    });

    // Rebuild-total chip: one click turns a picked share/rate (A) into its
    // underlying count by setting op=Multiply and B=<derivedFrom.denominator>.
    // Reads the candidate fresh on click so it always tracks the current A.
    const rebuildBtn = shell.querySelector<HTMLButtonElement>(
      "[data-role='ds-rebuild-apply']",
    );
    rebuildBtn?.addEventListener("click", () => {
      const cand = rebuildCandidateFor(dsModal.a);
      if (!cand) return;
      dsModal.op = "multiply";
      if (opSelect) opSelect.value = "multiply";
      dsModal.b = cand.denominator;
      updateDsOperandUI();
      syncDerivedHint();
      track("compose_rebuild_total", {
        rate: dsModal.a,
        denom: cand.denominator,
      });
    });
    // combineHint chip: one click sets op + B = partner and names the
    // result (e.g. NASS price × quantity → "Corn production value — Iowa").
    const pxqBtn = shell.querySelector<HTMLButtonElement>(
      "[data-role='ds-pxq-apply']",
    );
    pxqBtn?.addEventListener("click", () => {
      const cand = pxqCandidateFor(dsModal.a);
      if (!cand) return;
      dsModal.op = cand.op;
      if (opSelect) opSelect.value = cand.op;
      dsModal.b = cand.partner;
      if (!dsModal.name.trim()) {
        dsModal.name = cand.resultLabel;
        if (nameInput) nameInput.value = cand.resultLabel;
      }
      updateDsOperandUI();
      syncDerivedHint();
      track("compose_combine_hint", {
        a: dsModal.a,
        partner: cand.partner,
        op: cand.op,
      });
    });
    const addAsChartChk = shell.querySelector<HTMLInputElement>(
      "[data-role='ds-add-as-chart']",
    );
    addAsChartChk?.addEventListener("change", () => {
      dsModal.addAsChart = addAsChartChk.checked;
    });
    // Quick-divisor chips: one-click pre-fill of op + B with a commonly
    // requested denominator (population / GDP / employment). The user
    // still picks A; the auto-name handles "A ÷ B" generation. We used
    // to also seed the name field with a template like "per capita",
    // but that clobbered the auto-name flow — "per capita" alone loses
    // the A's identity ("CA federal $ ÷ US population" beats just
    // "per capita"). Templates dropped; the chip only sets op + B now.
    const quickChips = shell.querySelectorAll<HTMLButtonElement>(
      "[data-role='ds-quick']",
    );
    quickChips.forEach((chip) => {
      chip.addEventListener("click", () => {
        const id = chip.dataset.divisorId ?? "";
        if (!id) return;
        dsModal.op = "divide";
        if (opSelect) opSelect.value = "divide";
        dsModal.b = id;
        // If the user had picked the same source as A, clear A — we
        // can't divide a source by itself, and the picker would mark
        // the row "Already picked on the other side" anyway.
        if (dsModal.a === id) dsModal.a = "";
        // Reflect the new active chip — primarily a visual cue that
        // the click registered (the rest of the UI updates too, but
        // the chip itself is what they just touched).
        quickChips.forEach((c) => c.classList.remove("ds-quick-chip-active"));
        chip.classList.add("ds-quick-chip-active");
        updateDsOperandUI();
        syncDerivedHint();
        // Funnel telemetry: which quick divisor wins? Useful for
        // deciding whether to add more (CPI, hours worked, etc.).
        track("compose_quick_divisor_picked", { divisor: id });
        focusPickerSearch("ds-a");
      });
    });
    createBtn?.addEventListener("click", async () => {
      // Title is now optional — empty falls back to the auto-generated
      // "A {op} B" name. A and B still required and must differ.
      if (
        !dsModal.a ||
        !dsModal.b ||
        dsModal.a === dsModal.b
      )
        return;
      // Anon rate-limit gate. Derived-source creation draws from the
      // same per-IP budget as chart-adds — bot loops that generate
      // synthetic derived sources are the same threat shape as those
      // adding chart after chart.
      const allowed = await checkComposeAction("create_derived_source");
      if (!allowed) {
        closeDerivedSourceModal();
        showSigninPrompt("create_derived_source");
        return;
      }
      const effectiveName =
        dsModal.name.trim() || computeDerivedDefaultName();
      const id = DERIVED_PREFIX + nanoid(8);
      // Inherit parent tags + add "custom" so this new source shows up
      // under the custom-tag filter chip in the source picker (chip
      // only renders when at least one source has it; see Phase 5).
      const inheritedTags = inheritedTagsForDerived(dsModal.a, dsModal.b);
      state.inlineSources[id] = {
        op: dsModal.op,
        a: dsModal.a,
        b: dsModal.b,
        name: effectiveName,
        tags: inheritedTags,
      };
      // Optional auto-insert as a chart in the current section. The vast
      // majority of derived-source creations are "I want this ratio as a
      // tile now"; pre-checking the box and creating the chart here saves
      // the user from a follow-up trip through the cc-modal. Opt-out
      // covers the stockpiling-sources-for-later case.
      //
      // The auto-chart references BOTH parent sources with the op set,
      // not the freshly-created derived source. Same line either way
      // (combineTwo applied at render), but the multi-source-with-op
      // form preserves both component citations in the chart footer
      // and "Copy citation" output — feels more transparent than the
      // single-source-from-an-opaque-derived form.
      let autoChartCreated = false;
      if (dsModal.addAsChart) {
        clampActiveSection();
        const target = state.sections[store.activeSectionIdx];
        if (target) {
          const chartId = INLINE_PREFIX + nanoid(8);
          state.inlineCharts[chartId] = {
            title: effectiveName,
            sources: [dsModal.a, dsModal.b],
            normalize: "raw",
            op: dsModal.op,
          };
          target.charts.push(chartId);
          autoChartCreated = true;
        }
      }
      writeUrl();
      closeDerivedSourceModal();
      // Re-render the dashboard composition if we just appended a chart;
      // otherwise only the source-pickers need refreshing.
      if (autoChartCreated) renderComposition();
      // Refresh anything that lists sources (custom-chart modal, if open).
      renderCustomChartSources();
      // Funnel telemetry: derived sources are a power-user feature; tracking
      // op distribution tells us whether divide-ratios dominate (the case we
      // designed for) or sum/diff get real use. Including the operand source
      // IDs lets us spot common derived-source recipes (e.g. retail-gas/WTI).
      // `auto_chart` records whether the user opted into the "add as chart"
      // default — useful for tuning the default if usage skews the other way.
      track("compose_derived_source_created", {
        op: dsModal.op,
        sources: packSourceIds([dsModal.a, dsModal.b]),
        auto_chart: autoChartCreated ? 1 : 0,
      });
    });
  }


  return {
    openDerivedSourceModal,
    wireDerivedSourceModal,
  };
}