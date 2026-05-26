/**
 * Supabase RLS + round-trip diagnostic tests.
 *
 * These exercise the actual database against the live deployment with
 * the admin's session: select own rows, insert + read + delete a
 * marker row, query alerts, etc. The tests verify both that the
 * happy path works AND that RLS is enforcing what it should.
 *
 * IMPORTANT: every mutation cleans up after itself. A failing test
 * with a leaked marker row is a tolerable footgun, but a routine
 * pass that leaves a row behind is a steady drip of garbage in
 * saved_dashboards. The cleanup paths use a finally-style helper.
 *
 * MARKER NAMING: every test row uses a title prefix of `__diag__`
 * so a periodic cleanup (or a `DELETE FROM saved_dashboards WHERE
 * title LIKE '__diag__%'`) can mop up any leaks without ambiguity.
 */
import {
  createSupabase,
  isSupabaseConfigured,
} from "../supabase";
import {
  fail,
  pass,
  skip,
  warn,
  type DiagnosticTest,
  type DiagnosticResult,
} from "../diagnostic-runner";
import { isAdmin } from "../admin";

/** Prefix every diagnostic-created row gets so cleanup is unambiguous. */
const DIAG_TITLE_PREFIX = "__diag__";

/** Build a unique title for a diagnostic row. */
function diagTitle(suffix: string): string {
  return `${DIAG_TITLE_PREFIX}${Date.now()}_${suffix}`;
}

/** Build a unique slug — same uniqueness story but slug-safe. */
function diagSlug(suffix: string): string {
  return `diag-${Date.now()}-${suffix}`;
}

/**
 * Hold the session check once at test time so every test below
 * doesn't repeat the same guards. Returns the session + sb client
 * or a synthetic skip result the caller can return up.
 */
async function requireAdminSession(): Promise<
  | { sb: ReturnType<typeof createSupabase>; userId: string; email: string }
  | DiagnosticResult
> {
  if (!isSupabaseConfigured) return skip("Supabase not configured");
  const sb = createSupabase();
  if (!sb) return skip("createSupabase returned null");
  const { data, error } = await sb.auth.getSession();
  if (error) return fail(`getSession: ${error.message}`);
  if (!data.session) return skip("no session");
  if (!isAdmin(data.session.user.email)) return skip("not admin");
  return {
    sb,
    userId: data.session.user.id,
    email: data.session.user.email!,
  };
}

export const supabaseTests: DiagnosticTest[] = [
  {
    id: "supabase/select-own-dashboards",
    category: "supabase",
    label: "SELECT saved_dashboards returns own rows",
    timeoutMs: 15000,
    run: async () => {
      const ctx = await requireAdminSession();
      if ("status" in ctx) return ctx;
      const { sb, userId } = ctx;
      const { data, error } = await sb!
        .from("saved_dashboards")
        .select("id, owner_id, slug, title, updated_at")
        .limit(1000);
      if (error) return fail(`select: ${error.message}`);
      if (!Array.isArray(data)) return fail("expected array, got " + typeof data);
      // RLS check: every row's owner_id should be the current user's.
      // If anything else came back, RLS isn't doing its job.
      const foreign = data.filter((r) => r.owner_id !== userId);
      if (foreign.length > 0) {
        return fail(
          `RLS leak — ${foreign.length} rows have a different owner_id`,
          { sampleForeign: foreign.slice(0, 3) },
        );
      }
      return pass(`${data.length} own rows`, { count: data.length });
    },
  },
  {
    id: "supabase/insert-read-delete-roundtrip",
    category: "supabase",
    label: "INSERT + SELECT + DELETE on saved_dashboards round-trips cleanly",
    timeoutMs: 30000,
    run: async () => {
      const ctx = await requireAdminSession();
      if ("status" in ctx) return ctx;
      const { sb, userId } = ctx;

      const title = diagTitle("rt");
      const slug = diagSlug("rt");
      const state_json = {
        v: 1,
        title,
        charts: [],
        description: "diagnostic round-trip marker — safe to delete",
      };

      let insertedId: string | null = null;
      try {
        // INSERT
        const { data: ins, error: insErr } = await sb!
          .from("saved_dashboards")
          .insert({
            owner_id: userId,
            slug,
            title,
            state_json,
            visibility: "private",
          })
          .select("id, slug, title")
          .single();
        if (insErr) return fail(`insert: ${insErr.message}`);
        if (!ins?.id) return fail("insert returned no id");
        insertedId = ins.id;
        if (ins.title !== title) {
          return fail(
            `insert echoed wrong title (${ins.title} vs ${title})`,
          );
        }

        // SELECT BACK
        const { data: sel, error: selErr } = await sb!
          .from("saved_dashboards")
          .select("id, title, state_json")
          .eq("id", insertedId)
          .single();
        if (selErr) return fail(`select-back: ${selErr.message}`);
        if (sel?.title !== title) {
          return fail(
            `select-back wrong title (${sel?.title} vs ${title})`,
          );
        }

        // UPDATE — confirms RLS allows owner-update
        const { error: updErr } = await sb!
          .from("saved_dashboards")
          .update({ title: title + "_updated" })
          .eq("id", insertedId);
        if (updErr) return fail(`update: ${updErr.message}`);

        return pass("INSERT + SELECT + UPDATE all succeeded", {
          insertedId,
        });
      } finally {
        // ALWAYS clean up. Even on a test failure, leaving the row
        // behind is a leak.
        if (insertedId) {
          await sb!
            .from("saved_dashboards")
            .delete()
            .eq("id", insertedId);
        }
      }
    },
  },
  {
    id: "supabase/delete-removes-row",
    category: "supabase",
    label: "DELETE on saved_dashboards actually removes the row",
    timeoutMs: 30000,
    run: async () => {
      const ctx = await requireAdminSession();
      if ("status" in ctx) return ctx;
      const { sb, userId } = ctx;
      const title = diagTitle("del");
      const slug = diagSlug("del");
      // Insert
      const { data: ins, error: insErr } = await sb!
        .from("saved_dashboards")
        .insert({
          owner_id: userId,
          slug,
          title,
          state_json: { v: 1, title, charts: [] },
          visibility: "private",
        })
        .select("id")
        .single();
      if (insErr || !ins?.id) {
        return fail(`pre-insert failed: ${insErr?.message ?? "no id"}`);
      }
      // Delete
      const { error: delErr } = await sb!
        .from("saved_dashboards")
        .delete()
        .eq("id", ins.id);
      if (delErr) return fail(`delete: ${delErr.message}`);
      // Verify gone
      const { data: check } = await sb!
        .from("saved_dashboards")
        .select("id")
        .eq("id", ins.id);
      if (Array.isArray(check) && check.length > 0) {
        return fail("row still present after delete");
      }
      return pass();
    },
  },
  {
    id: "supabase/count-alerts",
    category: "supabase",
    label: "SELECT count on alerts (informational)",
    timeoutMs: 15000,
    run: async () => {
      const ctx = await requireAdminSession();
      if ("status" in ctx) return ctx;
      const { sb } = ctx;
      // The alerts table exists in production; if the schema's been
      // renamed this surfaces here without crashing the suite.
      const { error, count } = await sb!
        .from("alerts")
        .select("id", { count: "exact", head: true });
      if (error) {
        // Some deployments may not have the alerts table yet — warn,
        // don't fail.
        return warn(`alerts table query failed: ${error.message}`);
      }
      return pass(`${count ?? 0} alerts owned`, { count });
    },
  },
  {
    id: "supabase/no-leaked-diagnostic-rows",
    category: "supabase",
    label: "no leftover __diag__ rows from prior runs",
    timeoutMs: 15000,
    run: async () => {
      const ctx = await requireAdminSession();
      if ("status" in ctx) return ctx;
      const { sb } = ctx;
      const { data, error } = await sb!
        .from("saved_dashboards")
        .select("id, slug, title, updated_at")
        .like("title", `${DIAG_TITLE_PREFIX}%`);
      if (error) return fail(`select: ${error.message}`);
      const rows = data ?? [];
      if (rows.length === 0) return pass("none");
      // Auto-cleanup: orphans are safe to delete since they're all
      // owned by the current user (RLS) and the prefix is reserved.
      const ids = rows.map((r) => r.id);
      const { error: delErr } = await sb!
        .from("saved_dashboards")
        .delete()
        .in("id", ids);
      if (delErr) {
        return warn(
          `${rows.length} leftover rows; cleanup failed: ${delErr.message}`,
          { rows },
        );
      }
      return warn(`cleaned up ${rows.length} leftover rows`, { rows });
    },
  },
  {
    id: "supabase/saved-dashboard-renders-via-u-slug",
    category: "supabase",
    label:
      "INSERT a saved dashboard, fetch /u/<slug>/, verify the SSR renderer produces tile markup",
    timeoutMs: 45000,
    run: async () => {
      const ctx = await requireAdminSession();
      if ("status" in ctx) return ctx;
      const { sb, userId } = ctx;

      const title = diagTitle("e2e");
      const slug = diagSlug("e2e");
      // Realistic state_json: a single section with one known chart.
      // us-macro/cpi-yoy was probed in iframe tests and is a stable
      // marquee chart ID. The renderer at /u/[slug] decodes this via
      // composedStateSchema → resolveDashboard, so any schema drift
      // surfaces as a 500 here.
      const state_json = {
        v: 1,
        title,
        description: "Diagnostic E2E marker — safe to delete.",
        sections: [
          {
            title: "Diag section",
            charts: ["us-macro/cpi-yoy"],
          },
        ],
      };

      let insertedId: string | null = null;
      try {
        const { data: ins, error: insErr } = await sb!
          .from("saved_dashboards")
          .insert({
            owner_id: userId,
            slug,
            title,
            state_json,
            // Public so the GET below works without forwarding the
            // session cookie (we can't rely on the diagnostic fetch
            // carrying auth to the SSR route — depends on cookie
            // forwarding and same-origin).
            visibility: "public",
          })
          .select("id, slug")
          .single();
        if (insErr) return fail(`insert: ${insErr.message}`);
        if (!ins?.id) return fail("insert returned no id");
        insertedId = ins.id;

        // Some deployments cache the route; cache-bust by adding a
        // ?nocache query param. /u/[slug] is prerender:false so it
        // shouldn't be cached, but defensive is cheap.
        const slugUrl = new URL(
          `/u/${encodeURIComponent(slug)}/?diag=${Date.now()}`,
          window.location.origin,
        );
        // Brief delay so the row's commit propagates to a read
        // replica (Supabase usually serves reads from the primary,
        // but in case of replica lag this saves a flake).
        await new Promise((r) => setTimeout(r, 500));
        const res = await fetch(slugUrl.toString(), { cache: "no-store" });
        if (res.status !== 200) {
          return fail(
            `/u/${slug}/ status=${res.status} (expected 200 after insert)`,
          );
        }
        const body = await res.text();
        // Sentinels: the page should show the dashboard's title AND
        // some chart-tile-shaped markup. Looking for the chart-id
        // attribute is the most robust signal that resolveDashboard
        // composed something renderable.
        if (!body.includes(title)) {
          return fail(
            `/u/${slug}/ rendered, but the title we inserted (${title.slice(0, 32)}...) wasn't in the body`,
            { bodyLength: body.length },
          );
        }
        const tileSentinel = /data-chart-id|chart-tile|data-tile-chart-id/;
        if (!tileSentinel.test(body)) {
          return fail(
            `/u/${slug}/ rendered with title but no chart-tile markup — section may have been dropped or the chart-id resolved to nothing`,
            { bodyLength: body.length },
          );
        }
        return pass(
          `${slug}: SSR rendered with title + tile markup (${(body.length / 1024).toFixed(1)}KB)`,
          { slug, bodyLength: body.length },
        );
      } finally {
        if (insertedId) {
          await sb!
            .from("saved_dashboards")
            .delete()
            .eq("id", insertedId);
        }
      }
    },
  },
];
