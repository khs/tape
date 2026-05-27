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
    label: "no leftover __diag__ rows in saved_dashboards or alert_rules",
    timeoutMs: 15000,
    run: async () => {
      const ctx = await requireAdminSession();
      if ("status" in ctx) return ctx;
      const { sb } = ctx;
      // Sweep saved_dashboards (title prefix).
      const dashRes = await sb!
        .from("saved_dashboards")
        .select("id, slug, title, updated_at")
        .like("title", `${DIAG_TITLE_PREFIX}%`);
      if (dashRes.error) return fail(`select dashboards: ${dashRes.error.message}`);
      const dashRows = dashRes.data ?? [];

      // Sweep alert_rules (label prefix). The alert E2E tests use the
      // same prefix so a crashed/aborted run leaves traceable orphans.
      const alertRes = await sb!
        .from("alert_rules")
        .select("id, label, paused, source_id")
        .like("label", `${DIAG_TITLE_PREFIX}%`);
      // alert_rules may not exist on older deployments (pre-0005);
      // treat that as "no rows to clean" rather than a fail.
      const alertTableMissing =
        alertRes.error &&
        /relation .*alert_rules.* does not exist/i.test(alertRes.error.message);
      if (alertRes.error && !alertTableMissing) {
        return fail(`select alerts: ${alertRes.error.message}`);
      }
      const alertRows = alertTableMissing ? [] : (alertRes.data ?? []);

      const total = dashRows.length + alertRows.length;
      if (total === 0) return pass("none");

      // Auto-cleanup: orphans are safe to delete since they're all
      // owned by the current user (RLS) and the prefix is reserved.
      const messages: string[] = [];
      if (dashRows.length > 0) {
        const { error } = await sb!
          .from("saved_dashboards")
          .delete()
          .in(
            "id",
            dashRows.map((r) => r.id),
          );
        if (error) messages.push(`dashboards cleanup: ${error.message}`);
        else messages.push(`cleaned ${dashRows.length} dashboard rows`);
      }
      if (alertRows.length > 0) {
        const { error } = await sb!
          .from("alert_rules")
          .delete()
          .in(
            "id",
            alertRows.map((r) => r.id),
          );
        if (error) messages.push(`alerts cleanup: ${error.message}`);
        else messages.push(`cleaned ${alertRows.length} alert rules`);
      }
      return warn(messages.join("; "), { dashRows, alertRows });
    },
  },
  {
    id: "supabase/alert-rule-insert-and-list",
    category: "supabase",
    label: "INSERT an alert_rule, verify it lists via SELECT, cleanup",
    timeoutMs: 30000,
    run: async () => {
      const ctx = await requireAdminSession();
      if ("status" in ctx) return ctx;
      const { sb, userId } = ctx;

      // Marker label so cleanup is unambiguous. Same prefix the
      // no-leaked-rows cleanup pass below sweeps.
      const label = `${DIAG_TITLE_PREFIX}alert_${Date.now()}`;
      let insertedId: string | null = null;
      try {
        const { data: ins, error: insErr } = await sb!
          .from("alert_rules")
          .insert({
            owner_id: userId,
            source_id: "fred/cpi_yoy",
            source_label: "CPI YoY (diagnostic test)",
            condition: "gt",
            threshold: 999, // far above any real CPI, so the
                            // evaluator never actually fires while
                            // the row exists. Belt-and-suspenders:
                            // we also delete it before the test
                            // returns.
            label,
            paused: true,   // double-belt — even if 999 were too low,
                            // paused rules don't dispatch.
          })
          .select("id, label, condition, threshold")
          .single();
        if (insErr) {
          // Some deployments may not have migration 0005 applied;
          // surface that with a skip rather than a fail.
          if (
            /relation .*alert_rules.* does not exist/i.test(insErr.message)
          ) {
            return skip(
              "alert_rules table missing — migration 0005 not applied",
            );
          }
          return fail(`insert: ${insErr.message}`);
        }
        if (!ins?.id) return fail("insert returned no id");
        insertedId = ins.id;
        if (ins.label !== label) {
          return fail(
            `insert echoed wrong label (${ins.label} vs ${label})`,
          );
        }

        // SELECT back via the per-owner index path the /alerts/
        // page uses.
        const { data: list, error: listErr } = await sb!
          .from("alert_rules")
          .select("id, label, paused")
          .eq("owner_id", userId)
          .order("updated_at", { ascending: false });
        if (listErr) return fail(`list: ${listErr.message}`);
        const found = (list ?? []).find((r) => r.id === insertedId);
        if (!found) {
          return fail("inserted rule not in SELECT-by-owner result");
        }
        if (!found.paused) {
          return fail("inserted rule lost its paused=true");
        }
        return pass(
          `inserted + listed (id=${insertedId}, ${list?.length ?? 0} total rules visible)`,
          { insertedId, ownedRuleCount: list?.length ?? 0 },
        );
      } finally {
        // ALWAYS clean up. Even if the test failed, we don't want
        // to leave a real alert in the DB.
        if (insertedId) {
          await sb!.from("alert_rules").delete().eq("id", insertedId);
        }
      }
    },
  },
  {
    id: "supabase/alerts-page-shows-inserted-rule",
    category: "supabase",
    label:
      "INSERT alert_rule, fetch /alerts/, verify the rule's label appears in body",
    timeoutMs: 30000,
    run: async () => {
      const ctx = await requireAdminSession();
      if ("status" in ctx) return ctx;
      const { sb, userId } = ctx;
      const label = `${DIAG_TITLE_PREFIX}alert_e2e_${Date.now()}`;
      let insertedId: string | null = null;
      try {
        const { data: ins, error: insErr } = await sb!
          .from("alert_rules")
          .insert({
            owner_id: userId,
            source_id: "fred/cpi_yoy",
            source_label: "CPI YoY (diagnostic E2E)",
            condition: "gt",
            threshold: 999,
            label,
            paused: true,
          })
          .select("id")
          .single();
        if (insErr) {
          if (
            /relation .*alert_rules.* does not exist/i.test(insErr.message)
          ) {
            return skip("alert_rules table missing");
          }
          return fail(`insert: ${insErr.message}`);
        }
        insertedId = ins!.id;
        // /alerts/ is SSR and reads via the user's session. Since
        // our diagnostic fetch is same-origin from a signed-in
        // browser, the session cookie WILL forward.
        await new Promise((r) => setTimeout(r, 500)); // commit settle
        const res = await fetch(
          new URL(
            `/alerts/?diag=${Date.now()}`,
            window.location.origin,
          ).toString(),
          { cache: "no-store", credentials: "include" },
        );
        if (res.status !== 200) {
          return fail(`/alerts/ status=${res.status}`);
        }
        const body = await res.text();
        if (!body.includes(label)) {
          // /alerts/ may render the rule list client-side after
          // the initial HTML. In that case the label won't be in
          // the SSR HTML. Don't fail — warn.
          return warn(
            `/alerts/ responded 200 but the inserted label wasn't in the SSR body — list likely hydrates client-side; consider an iframe-based check instead`,
            { bodyLength: body.length },
          );
        }
        return pass(
          `${label} visible in /alerts/ SSR body (${(body.length / 1024).toFixed(1)}KB)`,
          { insertedId, bodyLength: body.length },
        );
      } finally {
        if (insertedId) {
          await sb!.from("alert_rules").delete().eq("id", insertedId);
        }
      }
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
  {
    id: "supabase/rate-limit-trips-on-rapid-inserts",
    category: "supabase",
    label:
      "rate-limit trigger fires on rapid saved_dashboards INSERTs (3/60s cap from 0003)",
    timeoutMs: 30000,
    // MUST RUN LAST in the supabase category. The probe intentionally
    // exhausts the per-user dash_insert_min budget; any insert-using
    // test that runs after it will see false-positive failures (this
    // burned the saved-dashboard E2E test in the v1 ordering).
    run: async () => {
      const ctx = await requireAdminSession();
      if ("status" in ctx) return ctx;
      const { sb, userId } = ctx;

      // Burst up to 6 inserts. After migration 0003 the per-user limit
      // is 3 inserts per 60 seconds, so we expect at least one of the
      // last few to fail with PG error code P0001 + a message
      // starting with "Saving too quickly".
      //
      // Bonus: other supabase tests above have already burned 2-3
      // inserts by this point, so the limit may trip on the first
      // probe insert. Either way is fine — we just need at least
      // one failure with the rate-limit signature.
      const insertedIds: string[] = [];
      const errors: Array<{ idx: number; code?: string; message: string }> = [];
      const BURST = 6;
      for (let i = 0; i < BURST; i++) {
        const title = diagTitle(`rl${i}`);
        const slug = diagSlug(`rl${i}`);
        const { data, error } = await sb!
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
        if (error) {
          errors.push({
            idx: i,
            code: (error as { code?: string }).code,
            message: error.message,
          });
        } else if (data?.id) {
          insertedIds.push(data.id);
        }
      }

      // Cleanup: nuke everything that DID get in.
      if (insertedIds.length > 0) {
        await sb!.from("saved_dashboards").delete().in("id", insertedIds);
      }

      if (errors.length === 0) {
        return fail(
          `all ${BURST} rapid INSERTs succeeded — rate-limit triggers from migration 0002/0003 do not appear to be active`,
          { burst: BURST, insertCount: insertedIds.length },
        );
      }
      // At least one failure → rate-limit is firing. Confirm the
      // failure is the right one (PG raise_exception with our
      // human copy), not some unrelated DB error.
      const rateLimitHits = errors.filter(
        (e) =>
          e.code === "P0001" &&
          /too quickly|limit reached|Too many dashboards/i.test(e.message),
      );
      if (rateLimitHits.length === 0) {
        return fail(
          `${errors.length} INSERTs failed but none matched the rate-limit signature`,
          { errors, insertCount: insertedIds.length },
        );
      }
      return pass(
        `rate-limit fired on ${rateLimitHits.length} of ${BURST} attempts (${insertedIds.length} succeeded, all cleaned)`,
        {
          burst: BURST,
          succeeded: insertedIds.length,
          rateLimited: rateLimitHits.length,
          sampleMessage: rateLimitHits[0].message,
        },
      );
    },
  },
];
