/**
 * Tests for src/lib/supabase.ts — readStoredSession (raw localStorage
 * peek), the createSupabase singleton, and the isSupabaseConfigured
 * flag.
 *
 * Vitest's `node` env doesn't provide window/localStorage, and jsdom
 * isn't installed. We stub both globals manually — same approach as
 * seed-tutorial.test.ts. Env vars are stubbed via vi.stubEnv before
 * the SUT module loads (supabase.ts reads import.meta.env at import
 * time).
 */
import { vi } from "vitest";
// vi.hoisted is the only way to mutate state BEFORE the test file's
// import statements run (Vite hoists all imports to the top of the
// module regardless of source order). supabase.ts reads
// import.meta.env.PUBLIC_SUPABASE_URL at module-init time — if we
// stub it after the import, the module already snapshotted "".
vi.hoisted(() => {
  process.env.PUBLIC_SUPABASE_URL = "https://test-ref.supabase.co";
  process.env.PUBLIC_SUPABASE_ANON_KEY = "anon-test-key";
});

// Stub @supabase/supabase-js so createSupabase doesn't try real
// network. createClient returns an opaque sentinel.
const fakeClient = { __fake: true };
vi.mock("@supabase/supabase-js", () => ({
  createClient: vi.fn(() => fakeClient),
}));

import { describe, it, expect, beforeEach, afterEach } from "vitest";

/**
 * Build a minimal window + localStorage shim for one test. Mutating
 * `(window as any).__legibleMarketsSupabase` works as long as the
 * stub exposes a writable property.
 */
function setupBrowserStubs(): {
  win: Record<string, unknown>;
  ls: Storage;
} {
  const lsStore = new Map<string, string>();
  const ls: Storage = {
    getItem: (k) => lsStore.get(k) ?? null,
    setItem: (k, v) => {
      lsStore.set(k, v);
    },
    removeItem: (k) => {
      lsStore.delete(k);
    },
    clear: () => lsStore.clear(),
    get length() {
      return lsStore.size;
    },
    key: (i) => Array.from(lsStore.keys())[i] ?? null,
  };
  // `window` needs to be a real object the SUT can stash a property on.
  const win: Record<string, unknown> = {};
  vi.stubGlobal("window", win);
  vi.stubGlobal("localStorage", ls);
  return { win, ls };
}

import {
  createSupabase,
  readStoredSession,
  isSupabaseConfigured,
  SUPABASE_REST_URL,
  SUPABASE_REST_ANON_KEY,
} from "./supabase";

let browserCtx: ReturnType<typeof setupBrowserStubs>;

beforeEach(() => {
  browserCtx = setupBrowserStubs();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("isSupabaseConfigured", () => {
  it("is true when both URL + anon key are set at module init", () => {
    expect(isSupabaseConfigured).toBe(true);
  });

  it("exposes the URL + key via SUPABASE_REST_* exports", () => {
    // Used by seed-tutorial.ts to issue direct PostgREST calls
    // bypassing supabase-js (so the auth lock can't deadlock).
    expect(SUPABASE_REST_URL).toBe("https://test-ref.supabase.co");
    expect(SUPABASE_REST_ANON_KEY).toBe("anon-test-key");
  });
});

describe("createSupabase — browser-side caching", () => {
  it("returns a client the first time it's called", () => {
    const c = createSupabase();
    expect(c).toBe(fakeClient);
  });

  it("caches the client on window so subsequent calls return the same reference", () => {
    // The whole point of the cache: nav bundle + composer bundle +
    // tile bundle all share one GoTrueClient instead of fighting
    // over the NavigatorLock.
    const first = createSupabase();
    const second = createSupabase();
    expect(first).toBe(second);
    expect(first).toBe(browserCtx.win.__legibleMarketsSupabase);
  });

  it("only calls createClient once across multiple createSupabase() invocations", async () => {
    const { createClient } = await import("@supabase/supabase-js");
    const callsBefore = (
      createClient as unknown as { mock: { calls: unknown[] } }
    ).mock.calls.length;
    createSupabase();
    createSupabase();
    createSupabase();
    const callsAfter = (
      createClient as unknown as { mock: { calls: unknown[] } }
    ).mock.calls.length;
    expect(callsAfter - callsBefore).toBe(1);
  });

  it("re-creates after the window cache is cleared (simulates fresh page)", async () => {
    const { createClient } = await import("@supabase/supabase-js");
    const callsBefore = (
      createClient as unknown as { mock: { calls: unknown[] } }
    ).mock.calls.length;
    createSupabase();
    delete browserCtx.win.__legibleMarketsSupabase;
    createSupabase();
    const callsAfter = (
      createClient as unknown as { mock: { calls: unknown[] } }
    ).mock.calls.length;
    // Two creates because the cache was wiped between them.
    expect(callsAfter - callsBefore).toBe(2);
  });
});

describe("readStoredSession", () => {
  // supabase-js's auth-token localStorage key format:
  // sb-<projectRef>-auth-token  → JSON-stringified session
  const KEY = "sb-test-ref-auth-token";

  it("returns null when no session is stored", () => {
    expect(readStoredSession()).toBeNull();
  });

  it("returns the access_token + user when a valid session is stored", () => {
    const session = {
      access_token: "jwt-abc",
      refresh_token: "rt-abc",
      user: { id: "uuid-1", email: "test@example.com" },
      expires_at: 1779799999,
    };
    browserCtx.ls.setItem(KEY, JSON.stringify(session));
    const result = readStoredSession();
    expect(result).not.toBeNull();
    expect(result?.access_token).toBe("jwt-abc");
    expect(result?.refresh_token).toBe("rt-abc");
    expect(result?.user.id).toBe("uuid-1");
    expect(result?.user.email).toBe("test@example.com");
    expect(result?.expires_at).toBe(1779799999);
  });

  it("handles the wrapped currentSession shape too (legacy supabase-js)", () => {
    const session = {
      access_token: "jwt-wrapped",
      user: { id: "uuid-2" },
    };
    browserCtx.ls.setItem(KEY, JSON.stringify({ currentSession: session }));
    const result = readStoredSession();
    expect(result?.access_token).toBe("jwt-wrapped");
    expect(result?.user.id).toBe("uuid-2");
  });

  it("returns null when the stored JSON is malformed", () => {
    browserCtx.ls.setItem(KEY, "{not json");
    expect(readStoredSession()).toBeNull();
  });

  it("returns null when the session has no access_token", () => {
    // Half-populated session = treat as signed out.
    browserCtx.ls.setItem(
      KEY,
      JSON.stringify({ user: { id: "uuid-3" } }),
    );
    expect(readStoredSession()).toBeNull();
  });

  it("returns null when the session has no user.id", () => {
    browserCtx.ls.setItem(
      KEY,
      JSON.stringify({ access_token: "jwt-xyz", user: {} }),
    );
    expect(readStoredSession()).toBeNull();
  });

  it("returns null when window is undefined (SSR / Node)", () => {
    vi.stubGlobal("window", undefined);
    expect(readStoredSession()).toBeNull();
  });

  it("uses the URL's project-ref to derive the localStorage key", () => {
    // Lock the contract: the key format is sb-<ref>-auth-token where
    // <ref> is the projectId from the URL.
    // Our test URL is https://test-ref.supabase.co — ref = "test-ref".
    // Putting the session under a DIFFERENT ref's key should not be
    // found by readStoredSession.
    browserCtx.ls.setItem(
      "sb-different-ref-auth-token",
      JSON.stringify({
        access_token: "jwt",
        user: { id: "uuid" },
      }),
    );
    expect(readStoredSession()).toBeNull();
  });
});
