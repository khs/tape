/**
 * Tests for the walkthrough-as-live-board seeder.
 *
 * Every signed-in user gets exactly one saved_dashboards row pointing
 * at the walkthrough preset on their first sign-in. This module runs
 * on every BaseLayout mount with a signed-in session — getting any
 * branch wrong silently breaks new-user onboarding OR doubles-up rows
 * for existing users, neither of which surfaces in production until a
 * support ticket. These tests lock down each branch.
 *
 * Strategy: mock global fetch + the `./supabase` exports, run
 * maybeSeedTutorial against synthetic StoredSession objects, and
 * assert on the fetch calls + localStorage state.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { StoredSession } from "./supabase";

// Mock ./supabase BEFORE importing the SUT so seed-tutorial picks up
// the test config values. The non-empty URL + key enable the seeder's
// network path (without them it short-circuits to no-op).
vi.mock("./supabase", () => ({
  SUPABASE_REST_URL: "https://test.supabase.co",
  SUPABASE_REST_ANON_KEY: "anon-test-key",
}));

// nanoid is non-deterministic by design; we don't care about slug
// content in tests, only that an INSERT call was made. The real
// nanoid keeps working in production.
vi.mock("nanoid", () => ({
  nanoid: vi.fn(() => "test-slug-abc"),
}));

import { maybeSeedTutorial } from "./seed-tutorial";

/** Minimal session shape the seeder expects. */
function fakeSession(userId = "user-uuid-1"): StoredSession {
  return {
    access_token: "test-jwt-abc",
    user: { id: userId, email: "test@example.com" },
  };
}

/** In-memory localStorage stub. Vitest's jsdom env provides one by
 *  default but resetting it between tests keeps state isolated. */
function freshLocalStorage(): void {
  const store = new Map<string, string>();
  const ls: Storage = {
    getItem: (k) => store.get(k) ?? null,
    setItem: (k, v) => {
      store.set(k, v);
    },
    removeItem: (k) => {
      store.delete(k);
    },
    clear: () => {
      store.clear();
    },
    get length() {
      return store.size;
    },
    key: (i) => Array.from(store.keys())[i] ?? null,
  };
  vi.stubGlobal("localStorage", ls);
}

/** A fetch mock that responds based on a route table. The table is
 *  keyed by the substring matched in the request URL. */
function makeFetchMock(
  routes: Record<string, { ok: boolean; status?: number; body?: unknown }>,
): ReturnType<typeof vi.fn> {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : (input as URL).toString();
    for (const [key, response] of Object.entries(routes)) {
      if (url.includes(key)) {
        return {
          ok: response.ok,
          status: response.status ?? (response.ok ? 200 : 500),
          json: async () => response.body ?? null,
          text: async () => JSON.stringify(response.body ?? ""),
        } as Response;
      }
    }
    throw new Error(`unmocked fetch url: ${url}`);
  });
}

beforeEach(() => {
  freshLocalStorage();
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("maybeSeedTutorial — fast-path short-circuits", () => {
  it("does nothing when the localStorage flag is already set", async () => {
    const fetchMock = makeFetchMock({});
    vi.stubGlobal("fetch", fetchMock);
    // Pre-set the flag for this user.
    localStorage.setItem(
      "tape:seeded-walkthrough-ref-v2:user-uuid-1",
      "seeded",
    );
    await maybeSeedTutorial(fakeSession());
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does nothing when localStorage is undefined (SSR-style env)", async () => {
    const fetchMock = makeFetchMock({});
    vi.stubGlobal("fetch", fetchMock);
    // Simulate a no-localStorage env. The fast-path check `typeof
    // localStorage === "undefined"` exits before any network.
    vi.stubGlobal("localStorage", undefined);
    await maybeSeedTutorial(fakeSession());
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("maybeSeedTutorial — first sign-in (no existing row)", () => {
  it("POSTs a new public row with the seed state_json", async () => {
    const fetchMock = makeFetchMock({
      // Initial existence check returns empty array.
      "?owner_id=eq.": { ok: true, body: [] },
      // INSERT response.
      "/rest/v1/saved_dashboards": { ok: true, body: null },
    });
    vi.stubGlobal("fetch", fetchMock);
    await maybeSeedTutorial(fakeSession());

    // First call: existence check (GET, no body).
    // Second call: INSERT (POST). Find by method.
    const insertCall = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "POST",
    );
    expect(insertCall).toBeDefined();
    const insertBody = JSON.parse(
      (insertCall![1] as RequestInit).body as string,
    );
    expect(insertBody.title).toContain("Walkthrough");
    expect(insertBody.visibility).toBe("public");
    expect(insertBody.owner_id).toBe("user-uuid-1");
    expect(insertBody.slug).toBeTruthy();
    expect(insertBody.state_json.presetRef).toBe("walkthrough");
    expect(insertBody.state_json.v).toBe(1);
  });

  it("sets the localStorage flag after a successful insert", async () => {
    const fetchMock = makeFetchMock({
      "?owner_id=eq.": { ok: true, body: [] },
      "/rest/v1/saved_dashboards": { ok: true, body: null },
    });
    vi.stubGlobal("fetch", fetchMock);
    await maybeSeedTutorial(fakeSession());
    expect(
      localStorage.getItem("tape:seeded-walkthrough-ref-v2:user-uuid-1"),
    ).toBe("seeded");
  });

  it("does NOT set the flag if the insert fails", async () => {
    const fetchMock = makeFetchMock({
      "?owner_id=eq.": { ok: true, body: [] },
      "/rest/v1/saved_dashboards": { ok: false, status: 500, body: null },
    });
    vi.stubGlobal("fetch", fetchMock);
    await maybeSeedTutorial(fakeSession());
    expect(
      localStorage.getItem("tape:seeded-walkthrough-ref-v2:user-uuid-1"),
    ).toBeNull();
  });

  it("forwards the user's access_token as a Bearer header", async () => {
    const fetchMock = makeFetchMock({
      "?owner_id=eq.": { ok: true, body: [] },
      "/rest/v1/saved_dashboards": { ok: true, body: null },
    });
    vi.stubGlobal("fetch", fetchMock);
    await maybeSeedTutorial(fakeSession());
    // Every fetch should include the Bearer token.
    for (const [, init] of fetchMock.mock.calls) {
      const headers = (init as RequestInit)?.headers as Record<
        string,
        string
      >;
      expect(headers?.Authorization).toBe("Bearer test-jwt-abc");
      expect(headers?.apikey).toBe("anon-test-key");
    }
  });
});

describe("maybeSeedTutorial — already-seeded row exists", () => {
  it("does NOT insert when a row with the seed title already exists", async () => {
    const fetchMock = makeFetchMock({
      "?owner_id=eq.": {
        ok: true,
        body: [{ id: "existing-row-1", visibility: "public" }],
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    await maybeSeedTutorial(fakeSession());

    // No POST should have happened.
    const insertCall = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "POST",
    );
    expect(insertCall).toBeUndefined();
  });

  it("sets the localStorage flag to short-circuit the next call", async () => {
    const fetchMock = makeFetchMock({
      "?owner_id=eq.": {
        ok: true,
        body: [{ id: "existing-row-1", visibility: "public" }],
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    await maybeSeedTutorial(fakeSession());
    expect(
      localStorage.getItem("tape:seeded-walkthrough-ref-v2:user-uuid-1"),
    ).toBe("exists");
  });
});

describe("maybeSeedTutorial — v1 repair path (private → public)", () => {
  it("PATCHes a private existing row to visibility=public", async () => {
    const fetchMock = makeFetchMock({
      "?owner_id=eq.": {
        ok: true,
        body: [{ id: "v1-row-id", visibility: "private" }],
      },
      "?id=eq.v1-row-id": { ok: true, body: null },
    });
    vi.stubGlobal("fetch", fetchMock);
    await maybeSeedTutorial(fakeSession());

    const patchCall = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "PATCH",
    );
    expect(patchCall).toBeDefined();
    const patchBody = JSON.parse(
      (patchCall![1] as RequestInit).body as string,
    );
    expect(patchBody.visibility).toBe("public");
  });

  it("does NOT PATCH when the existing row is already public", async () => {
    const fetchMock = makeFetchMock({
      "?owner_id=eq.": {
        ok: true,
        body: [{ id: "v2-row-id", visibility: "public" }],
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    await maybeSeedTutorial(fakeSession());

    const patchCall = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "PATCH",
    );
    expect(patchCall).toBeUndefined();
  });

  it("sets the flag after a successful PATCH (avoids re-checking forever)", async () => {
    const fetchMock = makeFetchMock({
      "?owner_id=eq.": {
        ok: true,
        body: [{ id: "v1-row-id", visibility: "private" }],
      },
      "?id=eq.v1-row-id": { ok: true, body: null },
    });
    vi.stubGlobal("fetch", fetchMock);
    await maybeSeedTutorial(fakeSession());
    expect(
      localStorage.getItem("tape:seeded-walkthrough-ref-v2:user-uuid-1"),
    ).toBe("exists");
  });
});

describe("maybeSeedTutorial — error-handling defensives", () => {
  it("returns silently when the existence-check fetch throws", async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error("network down");
    });
    vi.stubGlobal("fetch", fetchMock);
    // Should not throw and should not set the flag (so the next
    // sign-in re-tries).
    await expect(maybeSeedTutorial(fakeSession())).resolves.toBeUndefined();
    expect(
      localStorage.getItem("tape:seeded-walkthrough-ref-v2:user-uuid-1"),
    ).toBeNull();
  });

  it("returns silently when the existence-check fetch returns non-ok", async () => {
    const fetchMock = makeFetchMock({
      "?owner_id=eq.": { ok: false, status: 500, body: null },
    });
    vi.stubGlobal("fetch", fetchMock);
    await maybeSeedTutorial(fakeSession());
    // No insert attempted.
    const insertCall = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "POST",
    );
    expect(insertCall).toBeUndefined();
  });

  it("isolates the flag per-user", async () => {
    const fetchMock = makeFetchMock({
      "?owner_id=eq.": { ok: true, body: [] },
      "/rest/v1/saved_dashboards": { ok: true, body: null },
    });
    vi.stubGlobal("fetch", fetchMock);
    // Seed for user A.
    await maybeSeedTutorial(fakeSession("user-a"));
    expect(
      localStorage.getItem("tape:seeded-walkthrough-ref-v2:user-a"),
    ).toBe("seeded");
    // User B's flag should NOT be set — different account, different
    // browser sign-in flow.
    expect(
      localStorage.getItem("tape:seeded-walkthrough-ref-v2:user-b"),
    ).toBeNull();
  });
});
