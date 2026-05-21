/**
 * Walkthrough-as-live-board seeder.
 *
 * On sign-in, ensures every user has a saved-dashboard row that is
 * a thin reference to the canonical /walkthrough/ preset. The row
 * appears in /me/ alongside the user's own boards, and when opened
 * renders the LIVE walkthrough content (not a snapshot) — updates
 * to walkthrough.mdx propagate to every user automatically.
 *
 * History: this used to copy walkthrough.mdx into a materialized
 * "Tutorial" snapshot, only for users with zero saves. The snapshot
 * drifted (each new walkthrough section had to be backfilled by
 * hand) and existing users never saw the tour. The presetRef row
 * fixes both: every user gets it, and it stays in sync.
 *
 * Guarantees:
 *   1. Never creates a second walkthrough-ref. The check looks for
 *      "any saved row owned by this user with state_json.presetRef =
 *      walkthrough", not "any row at all".
 *   2. Idempotent across browsers. The DB-side check is the source
 *      of truth; the localStorage flag is a perf optimization to
 *      skip the network round-trip on repeat sign-ins, NOT a
 *      correctness mechanism.
 *   3. Respects user deletions. If a user explicitly deletes the
 *      walkthrough row, the localStorage flag stays set on THIS
 *      browser — we don't re-create on every refresh. (Sign-in
 *      from a fresh browser will re-seed; rare and acceptable.)
 *   4. Old "Tutorial" snapshots (pre-presetRef) are left alone.
 *      They're a user-owned row at this point; we don't touch
 *      them. New users only see the new walkthrough-ref.
 */
import { nanoid } from "nanoid";
import {
  SUPABASE_REST_URL,
  SUPABASE_REST_ANON_KEY,
  type StoredSession,
} from "./supabase";
import { WALKTHROUGH_DASHBOARD_SLUG } from "./brand";
import type { ComposedState } from "./composer-state";

const FLAG_PREFIX = "tape:seeded-walkthrough-ref:";

/**
 * Title for the seeded row, shown in /me/ and the home-page list.
 * Kept in sync with the walkthrough preset's title on seed; if the
 * preset title later changes, this stale display title remains until
 * the next sign-in seeds a NEW row for a NEW user. Existing users see
 * the (slightly stale) row title in /me/ but the live preset title at
 * /u/<slug>/. Acceptable for the level of churn we expect.
 */
const SEED_TITLE = "Walkthrough — a tour of every Tape feature";

/**
 * The state_json blob we write. Note the deliberate sparseness — no
 * sections, no charts, no chartOverrides. The /u/[slug].astro
 * renderer detects presetRef and pulls all content from the preset
 * dashboard at render time. Anything we put in sections/charts
 * here would be IGNORED, so keep the row minimal.
 */
const SEED_STATE: ComposedState = {
  v: 1,
  title: SEED_TITLE,
  presetRef: WALKTHROUGH_DASHBOARD_SLUG,
};

/**
 * Idempotent. Called from BaseLayout's auth handler on every refresh
 * that detects a signed-in session. Cheap fast-path: per-browser
 * localStorage flag short-circuits before any network call.
 *
 * (Function name preserved from the prior tutorial-snapshot
 * implementation so existing imports in BaseLayout.astro keep
 * compiling; the contract changed but the call site didn't.)
 */
export async function maybeSeedTutorial(
  stored: StoredSession,
): Promise<void> {
  if (!SUPABASE_REST_URL || !SUPABASE_REST_ANON_KEY) return;
  if (typeof localStorage === "undefined") return;

  const flagKey = `${FLAG_PREFIX}${stored.user.id}`;
  if (localStorage.getItem(flagKey)) return;

  // Does this user already have a walkthrough-ref row? PostgREST
  // doesn't natively index into JSON columns from the URL query
  // string, so we ask for any saved_dashboards row owned by the user
  // with the title we seed under — cheap proxy that catches the seed
  // row without listing the user's other boards.
  //
  // False positives: a user who happens to rename one of their own
  // dashboards to exactly "Walkthrough — a tour of every Tape
  // feature" will be considered "already seeded" and not get the
  // canonical ref. Acceptable — that's an extremely deliberate
  // collision.
  let hasRef: boolean;
  try {
    const url =
      `${SUPABASE_REST_URL}/rest/v1/saved_dashboards` +
      `?owner_id=eq.${encodeURIComponent(stored.user.id)}` +
      `&title=eq.${encodeURIComponent(SEED_TITLE)}` +
      `&select=id&limit=1`;
    const res = await fetch(url, {
      headers: {
        apikey: SUPABASE_REST_ANON_KEY,
        Authorization: `Bearer ${stored.access_token}`,
      },
    });
    if (!res.ok) return;
    const rows = await res.json().catch(() => []);
    hasRef = Array.isArray(rows) && rows.length > 0;
  } catch {
    return;
  }

  if (hasRef) {
    // Already present (this browser or another). Set the local flag
    // so we skip the round-trip on subsequent loads.
    try {
      localStorage.setItem(flagKey, "exists");
    } catch {
      /* localStorage quota or disabled — best-effort flag, swallow */
    }
    return;
  }

  // Seed.
  try {
    const insertRes = await fetch(
      `${SUPABASE_REST_URL}/rest/v1/saved_dashboards`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          apikey: SUPABASE_REST_ANON_KEY,
          Authorization: `Bearer ${stored.access_token}`,
          Prefer: "return=minimal",
        },
        body: JSON.stringify({
          slug: nanoid(10),
          owner_id: stored.user.id,
          title: SEED_TITLE,
          state_json: SEED_STATE,
          // Private by default — the user can flip to public from /me/
          // if they want a shareable link. The canonical walkthrough
          // already lives at /walkthrough/ for sharing; this row is
          // the per-user "I want it in my list" affordance.
          visibility: "private",
        }),
      },
    );
    if (insertRes.ok) {
      try {
        localStorage.setItem(flagKey, "seeded");
      } catch {
        /* swallow */
      }
    }
  } catch {
    // Swallow; next sign-in retries.
  }
}
