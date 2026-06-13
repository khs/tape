import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Typed Supabase client. Uses the public (publishable/anon) key — safe to ship
 * to the browser. Row-Level Security on the server enforces write permissions;
 * reads against `saved_dashboards` follow the `public | private` visibility
 * flag plus ownership.
 *
 * Both server-rendered pages (like /u/[slug].astro) and the composer island
 * import from here.
 */
// Cheap session helpers live in a zero-dependency module so importing
// THEM doesn't drag in @supabase/supabase-js. Re-exported here so the
// many existing importers of supabase.ts keep working unchanged; code
// on the anonymous-content critical path should import from
// ./supabase-session directly to stay client-free.
export {
  isSupabaseConfigured,
  SUPABASE_REST_URL,
  SUPABASE_REST_ANON_KEY,
  readStoredSession,
  type StoredSession,
} from "./supabase-session";

const SUPABASE_URL = import.meta.env.PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  // eslint-disable-next-line no-console
  console.warn(
    "Supabase env vars missing; /me, /u/:slug, and saved-dashboard features will be disabled.",
  );
}

export type DashboardRow = {
  id: string;
  slug: string;
  owner_id: string;
  title: string;
  state_json: unknown;
  visibility: "public" | "private";
  created_at: string;
  updated_at: string;
};

declare global {
  interface Window {
    __legibleMarketsSupabase?: SupabaseClient;
  }
}

/**
 * Returns a Supabase client. In the browser, caches a single instance on
 * `window` so every `<script>` bundle (nav, composer, home, /me/) shares one
 * auth state instead of each spinning up a GoTrueClient and fighting over the
 * `sb-...-auth-token` NavigatorLock.
 */
export function createSupabase(): SupabaseClient | null {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return null;
  if (typeof window !== "undefined") {
    if (window.__legibleMarketsSupabase) {
      return window.__legibleMarketsSupabase;
    }
    const client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        // Bypass the NavigatorLock entirely. Stuck locks from prior versions
        // of this page (where multiple clients contended) caused getSession()
        // to hang indefinitely. Single-tab usage doesn't need cross-tab
        // serialization; worst case on multi-tab is one tab retries a refresh.
        lock: async (_name, _acquireTimeout, fn) => fn(),
      },
    });
    window.__legibleMarketsSupabase = client;
    return client;
  }
  // Server-side (e.g. /u/[slug] with prerender:false): fresh per-request,
  // no shared-state concern.
  return createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  });
}

