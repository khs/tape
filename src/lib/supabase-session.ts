/**
 * Zero-dependency session helpers — split out from supabase.ts so that
 * code which only needs the lightweight "is there a stored session?"
 * check (nav auth state, the chart "click to save" hint, the
 * add-to-dashboard REST calls) does NOT statically pull in
 * @supabase/supabase-js (~52KB). The heavy client lives in supabase.ts
 * and is dynamic-imported only when an actual auth action runs.
 *
 * Everything here reads env + localStorage only.
 */
const SUPABASE_URL = import.meta.env.PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

/** True when Supabase creds are present (UI hides auth/save features without them). */
export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

/** URL + anon key for direct REST fetches (bypassing supabase-js's auth lock). */
export const SUPABASE_REST_URL = SUPABASE_URL ?? "";
export const SUPABASE_REST_ANON_KEY = SUPABASE_ANON_KEY ?? "";

export type StoredSession = {
  access_token: string;
  refresh_token?: string;
  user: { id: string; email?: string };
  expires_at?: number;
};

/** Reads the active session straight from localStorage, bypassing
 *  supabase-js entirely — for first-paint auth checks that don't want
 *  to wait for (or pay the bytes of) async client hydration. */
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
