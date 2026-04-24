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

/** Publicly-consumable flag so UI can hide auth/save features in dev without creds. */
export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

/** Expose URL + anon key for direct-fetch REST calls (used when we want to
 *  bypass supabase-js's auth lock, which has been observed to deadlock on
 *  getSession() during token refresh). */
export const SUPABASE_REST_URL = SUPABASE_URL ?? "";
export const SUPABASE_REST_ANON_KEY = SUPABASE_ANON_KEY ?? "";

export type StoredSession = {
  access_token: string;
  refresh_token?: string;
  user: { id: string; email?: string };
  expires_at?: number;
};

/** Reads the active session straight from localStorage, bypassing supabase-js
 *  entirely. Useful when getSession() is deadlocked and for first-paint auth
 *  checks that don't want to wait for async hydration. */
export function readStoredSession(): StoredSession | null {
  if (typeof window === "undefined" || !SUPABASE_URL) return null;
  try {
    const m = SUPABASE_URL.match(/https:\/\/([^.]+)\.supabase\.co/);
    if (!m) return null;
    const ref = m[1];
    const raw = localStorage.getItem(`sb-${ref}-auth-token`);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const s = parsed?.currentSession ?? parsed;
    if (!s?.access_token || !s?.user?.id) return null;
    return {
      access_token: s.access_token,
      refresh_token: s.refresh_token,
      user: { id: s.user.id, email: s.user.email },
      expires_at: s.expires_at,
    };
  } catch {
    return null;
  }
}
