/**
 * Tests for the diagnostic-runner framework.
 *
 * The runner is the spine of the admin Test Functionality flow — if
 * its summarization or report formatting drifts, every diagnostic
 * pasted back is harder to read. These tests lock down:
 *
 *   - Test results are captured correctly (pass/fail/warn/skip)
 *   - A test that throws becomes a fail record (suite doesn't abort)
 *   - A test that hangs past its timeout becomes a fail record
 *   - Timing is measured + included
 *   - summarize() counts each status
 *   - formatReport() produces a paste-friendly report with the
 *     summary line at the top and a JSON appendix
 */
import { describe, it, expect, vi } from "vitest";
import {
  runOneTest,
  runSuite,
  summarize,
  formatReport,
  pass,
  fail,
  warn,
  skip,
  type DiagnosticTest,
  type DiagnosticRecord,
} from "./diagnostic-runner";

describe("runOneTest", () => {
  it("captures a passing test as status='pass' with timing", async () => {
    const t: DiagnosticTest = {
      id: "ok",
      label: "trivial pass",
      category: "smoke",
      run: () => pass("everything fine"),
    };
    const rec = await runOneTest(t);
    expect(rec.status).toBe("pass");
    expect(rec.message).toBe("everything fine");
    expect(rec.durationMs).toBeGreaterThanOrEqual(0);
  });

  it("captures an async test that returns a fail result", async () => {
    const t: DiagnosticTest = {
      id: "nope",
      label: "intentional fail",
      category: "smoke",
      run: async () => fail("nope"),
    };
    const rec = await runOneTest(t);
    expect(rec.status).toBe("fail");
    expect(rec.message).toBe("nope");
  });

  it("captures a thrown error as status='fail' (suite must keep going)", async () => {
    // The runner's whole purpose is to keep the suite running even
    // when one test crashes. A throw must NOT escape runOneTest.
    const t: DiagnosticTest = {
      id: "throws",
      label: "throws something",
      category: "smoke",
      run: () => {
        throw new Error("boom");
      },
    };
    const rec = await runOneTest(t);
    expect(rec.status).toBe("fail");
    expect(rec.message).toBe("boom");
    expect(rec.errorName).toBe("Error");
    expect(rec.errorStack).toBeDefined();
  });

  it("captures a rejected promise as a fail with the rejection reason", async () => {
    const t: DiagnosticTest = {
      id: "rejects",
      label: "rejects async",
      category: "smoke",
      run: () => Promise.reject(new Error("async boom")),
    };
    const rec = await runOneTest(t);
    expect(rec.status).toBe("fail");
    expect(rec.message).toBe("async boom");
  });

  it("times out a hanging test (default + custom timeout)", async () => {
    const t: DiagnosticTest = {
      id: "hang",
      label: "hangs forever",
      category: "smoke",
      timeoutMs: 50, // fast for the test suite
      run: () => new Promise(() => {}), // never resolves
    };
    const rec = await runOneTest(t);
    expect(rec.status).toBe("fail");
    expect(rec.message).toContain("Timed out after 50ms");
  });

  it("records the warn status with a message", async () => {
    const t: DiagnosticTest = {
      id: "wt",
      label: "warn-only",
      category: "smoke",
      run: () => warn("looks suspicious but not broken"),
    };
    const rec = await runOneTest(t);
    expect(rec.status).toBe("warn");
    expect(rec.message).toBe("looks suspicious but not broken");
  });

  it("records the skip status with a reason", async () => {
    const t: DiagnosticTest = {
      id: "sk",
      label: "skipped",
      category: "smoke",
      run: () => skip("not configured in this env"),
    };
    const rec = await runOneTest(t);
    expect(rec.status).toBe("skip");
    expect(rec.message).toBe("not configured in this env");
  });

  it("carries through the test's data field for the JSON appendix", async () => {
    const t: DiagnosticTest = {
      id: "data",
      label: "with data",
      category: "smoke",
      run: () => pass("ok", { rows: 12, byKind: { line: 8, bar: 4 } }),
    };
    const rec = await runOneTest(t);
    expect(rec.data).toEqual({ rows: 12, byKind: { line: 8, bar: 4 } });
  });
});

describe("runSuite", () => {
  it("runs every test even when some fail", async () => {
    const tests: DiagnosticTest[] = [
      { id: "a", label: "a", category: "x", run: () => pass() },
      { id: "b", label: "b", category: "x", run: () => fail("nope") },
      { id: "c", label: "c", category: "x", run: () => pass() },
    ];
    const records = await runSuite(tests);
    expect(records).toHaveLength(3);
    expect(records.map((r) => r.id)).toEqual(["a", "b", "c"]);
    expect(records.map((r) => r.status)).toEqual(["pass", "fail", "pass"]);
  });

  it("fires onProgress once per test with running index/total", async () => {
    const tests: DiagnosticTest[] = [
      { id: "a", label: "a", category: "x", run: () => pass() },
      { id: "b", label: "b", category: "x", run: () => pass() },
    ];
    const spy = vi.fn();
    await runSuite(tests, spy);
    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy.mock.calls[0][1]).toBe(1); // index after first completes
    expect(spy.mock.calls[0][2]).toBe(2); // total
    expect(spy.mock.calls[1][1]).toBe(2);
  });

  it("returns an empty array for an empty test list", async () => {
    expect(await runSuite([])).toEqual([]);
  });

  it("runs tests sequentially (no overlap)", async () => {
    // The supabase round-trip tests depend on sequential execution
    // (insert then read then delete on the same row id). Lock that
    // contract — concurrent runs would break attribution.
    const order: string[] = [];
    const tests: DiagnosticTest[] = [
      {
        id: "a",
        label: "a",
        category: "x",
        run: async () => {
          order.push("a-start");
          await new Promise((r) => setTimeout(r, 10));
          order.push("a-end");
          return pass();
        },
      },
      {
        id: "b",
        label: "b",
        category: "x",
        run: async () => {
          order.push("b-start");
          return pass();
        },
      },
    ];
    await runSuite(tests);
    // a must fully complete before b starts.
    expect(order).toEqual(["a-start", "a-end", "b-start"]);
  });
});

describe("summarize", () => {
  function rec(status: DiagnosticRecord["status"]): DiagnosticRecord {
    return {
      id: status,
      label: status,
      category: "x",
      status,
      durationMs: 10,
    };
  }

  it("counts each status independently", () => {
    const records = [
      rec("pass"),
      rec("pass"),
      rec("pass"),
      rec("fail"),
      rec("warn"),
      rec("skip"),
    ];
    const s = summarize(records);
    expect(s).toEqual({
      total: 6,
      pass: 3,
      fail: 1,
      warn: 1,
      skip: 1,
      durationMs: 60,
    });
  });

  it("zero-counts an empty run", () => {
    expect(summarize([])).toEqual({
      total: 0,
      pass: 0,
      fail: 0,
      warn: 0,
      skip: 0,
      durationMs: 0,
    });
  });
});

describe("formatReport", () => {
  const baseRecords: DiagnosticRecord[] = [
    {
      id: "a",
      label: "first test",
      category: "smoke",
      status: "pass",
      durationMs: 24,
    },
    {
      id: "b",
      label: "second test",
      category: "smoke",
      status: "fail",
      message: "X didn't equal Y",
      durationMs: 412,
      errorName: "AssertionError",
      errorStack: "Error: bad\n  at f (foo.ts:1)\n  at g (bar.ts:2)",
    },
    {
      id: "c",
      label: "another category test",
      category: "network",
      status: "warn",
      message: "slow but not broken (3.2s)",
      durationMs: 3200,
    },
  ];

  const header = {
    startedAt: "2026-05-25T14:32:11Z",
    build: { sha: "abc1234", env: "production" },
    user: { id: "uuid-1", email: "keller.scholl@gmail.com" },
    browser: { userAgent: "Mozilla/5.0 …", viewport: "1920x1080" },
  };

  it("includes the banner and summary line", () => {
    const out = formatReport(header, baseRecords);
    expect(out).toContain("=== Tape Diagnostic ===");
    expect(out).toContain("Started: 2026-05-25T14:32:11Z");
    expect(out).toContain("1/3 pass");
    expect(out).toContain("1 warn");
    expect(out).toContain("1 fail");
  });

  it("includes the context block (build / user / browser)", () => {
    const out = formatReport(header, baseRecords);
    expect(out).toContain("Build: abc1234 (production)");
    expect(out).toContain("keller.scholl@gmail.com");
    expect(out).toContain("Mozilla/5.0");
    expect(out).toContain("1920x1080");
  });

  it("groups records by category in first-seen order", () => {
    const out = formatReport(header, baseRecords);
    const smokeIdx = out.indexOf("== SMOKE");
    const networkIdx = out.indexOf("== NETWORK");
    expect(smokeIdx).toBeGreaterThan(-1);
    expect(networkIdx).toBeGreaterThan(-1);
    expect(smokeIdx).toBeLessThan(networkIdx);
  });

  it("emits per-category pass count", () => {
    const out = formatReport(header, baseRecords);
    expect(out).toContain("== SMOKE (1/2 pass) ==");
    expect(out).toContain("== NETWORK (0/1 pass) ==");
  });

  it("renders status glyphs the formatter docs promise", () => {
    const out = formatReport(header, baseRecords);
    expect(out).toContain("[OK]");
    expect(out).toContain("[FAIL]");
    expect(out).toContain("[WARN]");
  });

  it("includes the fail message inline and an indented stack snippet", () => {
    const out = formatReport(header, baseRecords);
    expect(out).toContain("X didn't equal Y");
    // First few stack frames should appear under the fail line.
    expect(out).toContain("foo.ts:1");
  });

  it("appends a fenced JSON appendix with the full records", () => {
    const out = formatReport(header, baseRecords);
    expect(out).toContain("--- raw json appendix ---");
    expect(out).toContain("```json");
    expect(out).toContain('"id": "a"');
    expect(out).toContain('"category": "smoke"');
    expect(out).toContain("```");
  });

  it("truncates absurdly long strings in the JSON appendix", () => {
    const huge: DiagnosticRecord = {
      id: "huge",
      label: "huge",
      category: "x",
      status: "pass",
      message: "x".repeat(10000),
      durationMs: 1,
    };
    const out = formatReport(header, [huge]);
    expect(out).toContain("…[truncated");
    expect(out).not.toContain("x".repeat(5000));
  });
});

describe("result factories", () => {
  it("pass()/fail()/warn()/skip() set the right status", () => {
    expect(pass().status).toBe("pass");
    expect(fail("x").status).toBe("fail");
    expect(warn("x").status).toBe("warn");
    expect(skip("x").status).toBe("skip");
  });

  it("carry message and data through unchanged", () => {
    const p = pass("ok", { k: 1 });
    expect(p.message).toBe("ok");
    expect(p.data).toEqual({ k: 1 });
  });
});
