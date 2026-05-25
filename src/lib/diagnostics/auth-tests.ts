/**
 * Auth-state diagnostic tests.
 *
 * Run against the live Supabase session — verifies the session is
 * actually present, the user is the expected admin, and the JWT isn't
 * about to expire. Doesn't try to sign in or out (OAuth redirects
 * can't be tested from a same-page suite).
 */
import {
  createSupabase,
  isSupabaseConfigured,
  readStoredSession,
} from "../supabase";
import {
  fail,
  pass,
  skip,
  warn,
  type DiagnosticTest,
} from "../diagnostic-runner";
import { isAdmin } from "../admin";

/** Threshold for "near expiry" warning. JWTs are 1-hour by default;
 *  if we're within 5 minutes the next refresh roundtrip might race
 *  another operation. */
const NEAR_EXPIRY_SECONDS = 5 * 60;

export const authTests: DiagnosticTest[] = [
  {
    id: "auth/supabase-configured",
    category: "auth",
    label: "Supabase client can be created",
    run: () => {
      if (!isSupabaseConfigured) {
        return fail("isSupabaseConfigured is false");
      }
      const sb = createSupabase();
      if (!sb) return fail("createSupabase() returned null");
      return pass();
    },
  },
  {
    id: "auth/session-present",
    category: "auth",
    label: "active session present",
    timeoutMs: 10000,
    run: async () => {
      if (!isSupabaseConfigured) {
        return skip("Supabase not configured");
      }
      const sb = createSupabase()!;
      const { data, error } = await sb.auth.getSession();
      if (error) return fail(`getSession error: ${error.message}`);
      if (!data.session) {
        return fail("no session — sign in first, then re-run diagnostics");
      }
      return pass(`user=${data.session.user.email ?? "(no email)"}`);
    },
  },
  {
    id: "auth/user-is-admin",
    category: "auth",
    label: "current user is admin",
    timeoutMs: 10000,
    run: async () => {
      if (!isSupabaseConfigured) return skip("Supabase not configured");
      const sb = createSupabase()!;
      const { data } = await sb.auth.getSession();
      const email = data.session?.user.email;
      if (!email) return fail("no user email on session");
      if (!isAdmin(email)) {
        // This page shouldn't be reachable to non-admins — but if
        // someone is here and not admin, that's a surface that needs
        // the gate fixed.
        return fail(
          `${email} is not in ADMIN_EMAILS — diagnostic page gate is broken`,
        );
      }
      return pass(email);
    },
  },
  {
    id: "auth/jwt-not-near-expiry",
    category: "auth",
    label: "JWT not about to expire",
    timeoutMs: 10000,
    run: async () => {
      if (!isSupabaseConfigured) return skip("Supabase not configured");
      const sb = createSupabase()!;
      const { data } = await sb.auth.getSession();
      const exp = data.session?.expires_at;
      if (exp == null) return warn("session has no expires_at");
      const secondsToExpiry = exp - Math.floor(Date.now() / 1000);
      if (secondsToExpiry < 0) {
        return fail(`JWT expired ${-secondsToExpiry}s ago`);
      }
      if (secondsToExpiry < NEAR_EXPIRY_SECONDS) {
        return warn(`JWT expires in ${secondsToExpiry}s`, { secondsToExpiry });
      }
      return pass(
        `${Math.floor(secondsToExpiry / 60)}m to expiry`,
        { secondsToExpiry },
      );
    },
  },
  {
    id: "auth/stored-session-matches-runtime",
    category: "auth",
    label: "localStorage session matches getSession()",
    timeoutMs: 10000,
    run: async () => {
      // The /me/ page has a synchronous localStorage read that gates
      // the "Loading…" → "Sign in" pre-paint. If the localStorage
      // session and the async getSession() disagree, that pre-paint
      // is lying to the user.
      if (!isSupabaseConfigured) return skip("Supabase not configured");
      const stored = readStoredSession();
      const sb = createSupabase()!;
      const { data } = await sb.auth.getSession();
      const live = data.session;
      if (!stored && !live) return pass("both empty (signed out)");
      if (!stored && live) {
        return fail("getSession returned a session but localStorage is empty");
      }
      if (stored && !live) {
        return fail(
          "localStorage has a session but getSession returned null — likely stale token",
        );
      }
      // Both populated — confirm same user.
      if (stored!.user.id !== live!.user.id) {
        return fail(
          `mismatch: stored.user.id=${stored!.user.id} vs live.user.id=${live!.user.id}`,
        );
      }
      return pass();
    },
  },
  {
    id: "auth/refresh-roundtrip",
    category: "auth",
    label: "sb.auth.refreshSession() returns a fresh token",
    timeoutMs: 15000,
    run: async () => {
      if (!isSupabaseConfigured) return skip("Supabase not configured");
      const sb = createSupabase()!;
      const { data: before } = await sb.auth.getSession();
      if (!before.session) return skip("no active session to refresh");
      const beforeExp = before.session.expires_at;
      const { data: refreshed, error } = await sb.auth.refreshSession();
      if (error) return fail(`refreshSession error: ${error.message}`);
      if (!refreshed.session) return fail("refreshSession returned no session");
      const afterExp = refreshed.session.expires_at;
      if (
        beforeExp != null &&
        afterExp != null &&
        afterExp < beforeExp
      ) {
        return fail(
          `refresh produced an EARLIER expiry (before=${beforeExp}, after=${afterExp})`,
        );
      }
      return pass(
        afterExp != null
          ? `new exp=${afterExp} (Δ=${
              beforeExp != null ? afterExp - beforeExp : "?"
            }s)`
          : "refreshed (no expiry returned)",
      );
    },
  },
];
