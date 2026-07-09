/**
 * Shared "list of saved dashboards" renderer used by both /me/ and the
 * signed-in home page. Mirrors the chrome /me/ originally shipped with
 * (Edit / Make a copy / Rename / Set URL / Delete row actions + a
 * `+ Make new dashboard` tile leading the list).
 *
 * Why a shared module: the home page was running a much thinner
 * card-grid view that the user explicitly called worse than /me/'s.
 * Two copies of ~140 lines of fetch / mutate / re-render logic would
 * drift; this module makes /me/ and the home page render the same
 * thing, and gives the home page an extra `excludeSlug` knob so the
 * "default dashboard" row can live in its own hero above the list
 * rather than appearing twice.
 *
 * The caller owns the `<ul>` host + decides when to re-render (after
 * mutation, after a slot the caller controls changes, etc.). Action
 * handlers are wired per-button inside this function, NOT via a
 * delegated listener on the host element — earlier home-page code
 * accumulated listeners on each refresh and the X-delete button
 * ended up firing the confirm prompt three times after a couple of
 * auth-state-change ticks.
 */
import type { SupabaseClient } from "@supabase/supabase-js";

import { DEFAULT_DASHBOARD_SLUG_KEY } from "./brand";
import { encodeComposedState, composedStateSchema } from "./composer-state";
import { validateSlug, escapeHtml } from "./dashboard-slug";
import type { DashboardRow } from "./supabase";

export type SavedDashboardRow = Pick<
  DashboardRow,
  "id" | "slug" | "title" | "updated_at"
> & {
  /**
   * Truthy when this row's state_json was saved with a `presetRef`
   * field — i.e. it's a thin pointer to a curated preset (the
   * walkthrough is the only such preset today). Drives whether the
   * row's Edit button renders: a preset-ref row IS a pointer by
   * design, and PATCHing it with edited state would flatten it to
   * a snapshot that no longer tracks canonical preset updates. The
   * `Make a copy` button stays available so users can fork.
   *
   * Populated via PostgREST's JSON projection
   * (`state_json->>presetRef`) so the list payload doesn't have to
   * carry every row's full state_json just to gate one button.
   */
  preset_ref?: string | null;
};

export interface RenderSavedDashboardsOptions {
  /** UL element that the renderer fills. Its previous children are
   *  cleared before each render. */
  host: HTMLElement;
  /** Site base URL (BASE_URL without trailing slash). */
  baseUrl: string;
  /** Supabase client (caller has already validated isSupabaseConfigured). */
  sb: SupabaseClient;
  /** Optional: slug to OMIT from the list, e.g. the home page's
   *  default-dashboard hero. The row still exists in saved_dashboards;
   *  this is purely a display filter. */
  excludeSlug?: string | null;
  /** Optional: slug currently set as default. Used to label the
   *  "Set as default" button per row ("Default" for the current default,
   *  "Set as default" for everyone else). When omitted, the default
   *  button isn't rendered at all (used by /me/ which doesn't care
   *  about a default). */
  defaultSlug?: string | null;
  /** Called when the user picks a new default. Receives the slug (or
   *  null when the user clears the default). Caller is expected to
   *  persist + re-render. */
  onSetDefault?: (slug: string | null) => void;
  /** Called after a successful rename / set-url / delete. Caller
   *  re-renders. */
  onMutate?: () => void;
}

export interface RenderSavedDashboardsResult {
  /** All rows fetched, before exclusion. */
  rows: SavedDashboardRow[];
  /** Rows the caller's hero might want to render (matches excludeSlug,
   *  if any). Undefined when excludeSlug wasn't set or wasn't found. */
  excludedRow: SavedDashboardRow | undefined;
}

// Slug validation + HTML escaping live in ./dashboard-slug.ts so they
// can be unit-tested without a DOM. Import unchanged behavior above.

// The "pinned home view" is a per-browser localStorage slug read by
// index.astro's redirect pre-paint. Delete / set-url below MUST keep it
// in sync: the /me/ caller doesn't wire defaultSlug/onSetDefault, so
// without a direct reconcile here a delete-or-rename of the pinned
// dashboard from /me/ would leave the pin pointing at a gone/old slug
// and every later visit to '/' would redirect to /u/<slug>/ and 404.
// Reuses DEFAULT_DASHBOARD_SLUG_KEY (lib/brand.ts) so the literal stays
// in one place; index.astro reads/writes the same key.
function readDefaultPin(): string | null {
  try {
    return localStorage.getItem(DEFAULT_DASHBOARD_SLUG_KEY);
  } catch {
    return null;
  }
}
function writeDefaultPin(slug: string | null): void {
  try {
    if (slug) localStorage.setItem(DEFAULT_DASHBOARD_SLUG_KEY, slug);
    else localStorage.removeItem(DEFAULT_DASHBOARD_SLUG_KEY);
  } catch {
    /* localStorage blocked — silently no-op. */
  }
}

function makeNewDashboardTile(baseUrl: string): HTMLLIElement {
  const li = document.createElement("li");
  li.className =
    "border hairline rounded p-4 bg-white flex items-center justify-between";
  li.innerHTML =
    `<div>
       <a class="text-base font-medium text-accent no-underline hover:underline" href="${baseUrl}/compose/">+ Make new dashboard</a>
       <div class="text-xs text-neutral-500 mt-1">Compose from scratch in the composer.</div>
     </div>
     <div class="flex gap-2 text-xs">
       <a class="underline text-neutral-500 no-underline hover:underline" href="${baseUrl}/compose/">Open composer &rarr;</a>
     </div>`;
  return li;
}

async function openInComposer(
  sb: SupabaseClient,
  baseUrl: string,
  id: string,
  mode: "edit" | "copy",
  slug: string,
): Promise<void> {
  const { data, error } = await sb
    .from("saved_dashboards")
    .select("state_json")
    .eq("id", id)
    .single();
  if (error) {
    alert(`Couldn't open dashboard: ${error.message}`);
    return;
  }
  const parsed = composedStateSchema.safeParse(data?.state_json);
  if (!parsed.success) {
    alert(
      "This dashboard's saved state can't be opened in the composer (schema mismatch).",
    );
    return;
  }
  // Belt-and-suspenders: the per-row Edit button is suppressed for
  // preset-ref rows above, but a stale UI / hand-crafted call could
  // still land here. Refuse mode="edit" and steer the user toward
  // Make a copy, which is the right verb for forking a preset.
  if (parsed.data.presetRef && mode === "edit") {
    alert(
      "This row is a live reference to a curated preset (the canonical walkthrough). Editing it in place would break the link — use Make a copy instead to fork it into your own dashboard.",
    );
    return;
  }
  const encoded = encodeComposedState({
    title: parsed.data.title,
    description: parsed.data.description,
    defaultDelta: parsed.data.defaultDelta,
    fixedRange: parsed.data.fixedRange,
    sections: parsed.data.sections,
    charts: parsed.data.charts,
    chartOverrides: parsed.data.chartOverrides,
    inlineCharts: parsed.data.inlineCharts,
    inlineSources: parsed.data.inlineSources,
    inlineMaps: parsed.data.inlineMaps,
  });
  const params =
    mode === "edit"
      ? `?d=${encoded}&edit=${encodeURIComponent(slug)}`
      : `?d=${encoded}&copy=1`;
  window.location.href = `${baseUrl}/compose/${params}`;
}

export async function renderSavedDashboardList(
  opts: RenderSavedDashboardsOptions,
): Promise<RenderSavedDashboardsResult | null> {
  const { host, baseUrl, sb, excludeSlug, defaultSlug, onSetDefault, onMutate } = opts;

  // `state_json->>presetRef` is PostgREST's JSON-projection syntax —
  // projects only the presetRef field as text. Lets us flag preset-
  // pointer rows without dragging every row's full state_json over
  // the wire. Returns null for rows that don't have a presetRef.
  const { data, error } = await sb
    .from("saved_dashboards")
    .select("id, slug, title, updated_at, preset_ref:state_json->>presetRef")
    .order("updated_at", { ascending: false });
  if (error) {
    host.innerHTML = `<li class="text-sm text-error">Failed to load: ${escapeHtml(error.message)}</li>`;
    return null;
  }
  const rows = (data ?? []) as SavedDashboardRow[];
  const excludedRow = excludeSlug
    ? rows.find((r) => r.slug === excludeSlug)
    : undefined;
  const visible = excludeSlug
    ? rows.filter((r) => r.slug !== excludeSlug)
    : rows;

  // Clear the host. innerHTML="" also drops any event listeners on
  // the children we're about to delete, so no leaks.
  host.innerHTML = "";

  host.appendChild(makeNewDashboardTile(baseUrl));

  if (visible.length === 0) {
    const hint = document.createElement("li");
    hint.className = "text-sm text-neutral-500 px-1";
    hint.textContent = excludedRow
      ? "Your other dashboards will appear here. Make a new one above."
      : "No saved dashboards yet — start one above.";
    host.appendChild(hint);
    return { rows, excludedRow };
  }

  for (const r of visible) {
    const item = document.createElement("li");
    item.className =
      "border hairline rounded p-4 bg-white flex items-center justify-between";
    const dateStr = new Date(r.updated_at).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
    const isDefault = defaultSlug != null && defaultSlug === r.slug;
    // "Set as default" only renders when the caller hooked it up. The
    // current default's button reads "Default ✓" and clears the slot
    // on click; everyone else's button promotes that row.
    const defaultBtn = onSetDefault
      ? isDefault
        ? `<button type="button" class="underline text-accent bg-transparent border-0 p-0 cursor-pointer" data-role="clear-default" title="Click to clear this default">Default &#10003;</button>`
        : `<button type="button" class="underline text-neutral-500 bg-transparent border-0 p-0 cursor-pointer" data-role="set-default" data-slug="${escapeHtml(r.slug)}">Set as default</button>`
      : "";
    // Preset-ref rows (today: the seeded walkthrough) don't get
    // Edit / Rename / Set URL — those would mutate the row in
    // ways that break the pointer-to-canonical-preset contract.
    // Make a copy stays available so users can fork into a fully
    // editable dashboard of their own.
    const isPresetRef = !!r.preset_ref;
    const editBtn = isPresetRef
      ? ""
      : `<button type="button" class="underline text-neutral-500 bg-transparent border-0 p-0 cursor-pointer" data-role="edit" data-id="${r.id}" data-slug="${escapeHtml(r.slug)}">Edit</button>`;
    const renameBtn = isPresetRef
      ? ""
      : `<button type="button" class="underline text-neutral-500 bg-transparent border-0 p-0 cursor-pointer" data-role="rename" data-id="${r.id}" data-current="${escapeHtml(r.title)}">Rename</button>`;
    const setUrlBtn = isPresetRef
      ? ""
      : `<button type="button" class="underline text-neutral-500 bg-transparent border-0 p-0 cursor-pointer" data-role="set-url" data-id="${r.id}" data-current="${escapeHtml(r.slug)}">Set URL</button>`;
    // Subtitle nudge — when the row is a preset-ref, surface what
    // the row IS so users aren't confused about why some actions
    // are missing. "Live walkthrough" reads as a feature, not a bug.
    const subtitleSuffix = isPresetRef
      ? ` <span class="text-accent">· Live walkthrough</span>`
      : "";
    item.innerHTML =
      `<div>
         <a class="text-base font-medium text-neutral-900 no-underline hover:underline" href="${baseUrl}/u/${encodeURIComponent(r.slug)}/">${escapeHtml(r.title)}</a>
         <div class="text-xs text-neutral-500 mt-1">Updated ${dateStr}${subtitleSuffix}</div>
       </div>
       <div class="flex gap-2 text-xs">
         ${editBtn}
         <button type="button" class="underline text-neutral-500 bg-transparent border-0 p-0 cursor-pointer" data-role="copy" data-id="${r.id}" data-slug="${escapeHtml(r.slug)}">Make a copy</button>
         ${renameBtn}
         ${setUrlBtn}
         ${defaultBtn}
         <button type="button" class="underline text-error bg-transparent border-0 p-0 cursor-pointer" data-role="delete" data-id="${r.id}" data-slug="${escapeHtml(r.slug)}" data-title="${escapeHtml(r.title)}">Delete</button>
       </div>`;
    host.appendChild(item);
  }

  // Wire per-button handlers. Per-button (not delegated on host) is
  // deliberate — the home page used to delegate to <ul>, then call
  // render() again on every auth-state-change tick, which left N
  // copies of the listener attached and made the Delete-confirm
  // dialog fire N times. With per-button binding + innerHTML clear
  // above, the old listeners die with their elements.

  host.querySelectorAll<HTMLButtonElement>(
    "[data-role='edit'], [data-role='copy']",
  ).forEach((b) => {
    b.addEventListener("click", async () => {
      const id = b.dataset.id;
      const slug = b.dataset.slug;
      if (!id || !slug) return;
      const mode = b.dataset.role === "copy" ? "copy" : "edit";
      b.disabled = true;
      const orig = b.textContent;
      b.textContent = "Opening…";
      try {
        await openInComposer(sb, baseUrl, id, mode, slug);
      } finally {
        b.disabled = false;
        b.textContent = orig;
      }
    });
  });

  host.querySelectorAll<HTMLButtonElement>("[data-role='rename']").forEach((b) => {
    b.addEventListener("click", async () => {
      const id = b.dataset.id!;
      const current = b.dataset.current ?? "";
      const next = prompt("New name:", current);
      if (next === null) return;
      const title = next.trim();
      if (title === "" || title === current) return;
      const { data: row, error: fetchErr } = await sb
        .from("saved_dashboards")
        .select("state_json")
        .eq("id", id)
        .single();
      if (fetchErr) {
        alert(fetchErr.message);
        return;
      }
      const state = {
        ...((row?.state_json as Record<string, unknown>) ?? {}),
        title,
      };
      // .select() returns the affected rows so we can distinguish a
      // real write from a zero-row no-op. Without it, an RLS-filtered
      // or stale-token update returns no error and the UI would re-
      // render as if the rename stuck though nothing changed. Mirrors
      // the composer's zero-row guard in custom.astro.
      const { data: updRows, error: updErr } = await sb
        .from("saved_dashboards")
        .update({ title, state_json: state })
        .eq("id", id)
        .select();
      if (updErr) {
        alert(updErr.message);
        return;
      }
      if (!updRows || updRows.length === 0) {
        alert(
          "The rename didn't save. You might be signed out or not the owner of this dashboard. Please refresh and try again.",
        );
        return;
      }
      onMutate?.();
    });
  });

  host.querySelectorAll<HTMLButtonElement>("[data-role='set-url']").forEach((b) => {
    b.addEventListener("click", async () => {
      const id = b.dataset.id!;
      const current = b.dataset.current ?? "";
      const raw = prompt(
        "Custom URL — lowercase letters, digits, and dashes. Will be available at /u/<slug>/. Renaming makes the old URL free again, so anyone (including you) could grab it later.",
        current,
      );
      if (raw === null) return;
      const next = raw.trim().toLowerCase();
      if (next === "" || next === current) return;
      const err = validateSlug(next);
      if (err) {
        alert(err);
        return;
      }
      // .select() surfaces the affected rows so an RLS-filtered / stale-
      // token write (zero rows, no error) is caught instead of being
      // treated as a successful rename. Mirrors custom.astro's guard.
      const { data: updRows, error: updErr } = await sb
        .from("saved_dashboards")
        .update({ slug: next })
        .eq("id", id)
        .select();
      if (updErr) {
        const msg =
          (updErr as { code?: string }).code === "23505"
            ? `"/u/${next}/" is already taken — pick another.`
            : updErr.message;
        alert(msg);
        return;
      }
      if (!updRows || updRows.length === 0) {
        alert(
          "The URL change didn't save. You might be signed out or not the owner of this dashboard. Please refresh and try again.",
        );
        return;
      }
      // Edge-cache note: the freed old slug and the new /u/<slug>/ both
      // rely on the page's 60s s-maxage + stale-while-revalidate to self-
      // heal. We deliberately don't purge the edge here; a brief window
      // where the old URL still serves is expected, not a broken rename.
      //
      // Reconcile the pinned home view (localStorage) UNCONDITIONALLY —
      // the /me/ caller wires neither defaultSlug nor onSetDefault, so
      // without this a set-url from /me/ would strand the pin on the
      // freed old slug and every later visit to '/' would 404 on
      // /u/<old-slug>/. Migrate the pin to the new slug.
      if (readDefaultPin() === current) {
        writeDefaultPin(next);
      }
      // If the user just renamed the slug currently set as default,
      // poke the caller so it can migrate the stored default + re-render
      // its hero (home page only; onSetDefault is undefined on /me/).
      if (defaultSlug && defaultSlug === current && onSetDefault) {
        onSetDefault(next);
      }
      onMutate?.();
    });
  });

  if (onSetDefault) {
    host.querySelectorAll<HTMLButtonElement>("[data-role='set-default']").forEach((b) => {
      b.addEventListener("click", () => {
        const slug = b.dataset.slug;
        if (!slug) return;
        onSetDefault(slug);
      });
    });
    host.querySelectorAll<HTMLButtonElement>("[data-role='clear-default']").forEach((b) => {
      b.addEventListener("click", () => onSetDefault(null));
    });
  }

  host.querySelectorAll<HTMLButtonElement>("[data-role='delete']").forEach((b) => {
    b.addEventListener("click", async () => {
      const id = b.dataset.id!;
      const title = b.dataset.title ?? "this dashboard";
      const slug = b.dataset.slug ?? "";
      if (!confirm(`Delete "${title}"? This can't be undone.`)) return;
      // .select() returns the deleted rows so a zero-row delete (RLS
      // filtered the row out, or a stale token) is caught rather than
      // being reported to the user as a successful delete. Mirrors
      // custom.astro's zero-row guard on writes.
      const { data: delRows, error: delErr } = await sb
        .from("saved_dashboards")
        .delete()
        .eq("id", id)
        .select();
      if (delErr) {
        alert(delErr.message);
        return;
      }
      if (!delRows || delRows.length === 0) {
        alert(
          "Nothing was deleted. You might be signed out or not the owner of this dashboard. Please refresh and try again.",
        );
        return;
      }
      // Edge-cache note: /u/<slug>/ can keep serving the deleted
      // dashboard from the edge for up to the page's 60s s-maxage (then
      // stale-while-revalidate self-heals to a 404). We deliberately
      // don't purge the edge here; that brief staleness is acceptable,
      // not a broken delete.
      //
      // Reconcile the pinned home view (localStorage) UNCONDITIONALLY —
      // the /me/ caller wires neither defaultSlug nor onSetDefault, so
      // without this a delete of the pinned dashboard from /me/ would
      // strand the pin and every later visit to '/' would redirect to
      // /u/<gone-slug>/ and 404. Clear the pin when it points at the row
      // we just deleted.
      if (readDefaultPin() === slug) {
        writeDefaultPin(null);
      }
      // If the deleted row was the current default, also poke the caller
      // so it can clear its slot + re-render the hero (home page only;
      // onSetDefault is undefined on /me/).
      if (defaultSlug && defaultSlug === slug && onSetDefault) {
        onSetDefault(null);
      }
      onMutate?.();
    });
  });

  return { rows, excludedRow };
}
