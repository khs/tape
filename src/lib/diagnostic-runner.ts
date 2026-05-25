/**
 * Diagnostic test framework for the admin-only Test Functionality page.
 *
 * The page (/me/diagnostics) loads a battery of tests that exercise the
 * things vitest can't reach from Node: live Supabase RLS round-trips,
 * real-browser DOM rendering of charts, HTTP-fetch behavior of the
 * deployed pages, and the things-that-only-happen-in-a-real-browser
 * environment.
 *
 * Each test is a tiny self-contained async function returning a
 * DiagnosticResult. The runner threads them through with a per-test
 * timeout (so a hanging fetch can't lock up the whole suite), captures
 * timing, and accumulates results. A separate formatter renders the
 * Map of results as a paste-friendly text report (the report ends up
 * downloaded as a .txt the admin shares back).
 *
 * Why a framework instead of just inline async/await: when a test fails
 * mid-suite we want to keep going (vs throwing out the whole report),
 * and the report needs to attribute every error to its specific test
 * with timing. Doing this inline gets messy fast.
 */

/**
 * One diagnostic test. Pure shape — the test functions live in
 * sibling files under src/lib/diagnostics/.
 */
export interface DiagnosticTest {
  /** Stable identifier — used as the dict key in results. */
  id: string;
  /** Short human label shown in the report. */
  label: string;
  /** Group heading the result appears under in the report. */
  category: string;
  /** Per-test timeout in ms. Defaults to 5000 if omitted. */
  timeoutMs?: number;
  /** The actual check. Resolves with a result; rejecting is treated
   *  as a fail with the rejection reason captured. */
  run: () => Promise<DiagnosticResult> | DiagnosticResult;
}

/** Outcome of one test run. */
export interface DiagnosticResult {
  status: "pass" | "fail" | "skip" | "warn";
  /** Short message. For fails, the failure reason; for passes, an
   *  optional confirmation detail like "12 rows visible". */
  message?: string;
  /** Structured data to dump in the JSON appendix at the bottom of
   *  the report. Use sparingly — large blobs bloat the .txt. */
  data?: unknown;
  /** Timing — set by the runner, callers don't fill this in. */
  durationMs?: number;
  /** Set by the runner when the test threw. */
  errorName?: string;
  errorStack?: string;
}

/**
 * Final per-test record stored in the report. Combines the test
 * metadata with its run result so the formatter doesn't need to look
 * back at the original test list.
 */
export interface DiagnosticRecord {
  id: string;
  label: string;
  category: string;
  status: DiagnosticResult["status"];
  message?: string;
  data?: unknown;
  durationMs: number;
  errorName?: string;
  errorStack?: string;
}

/** Default per-test timeout when the test doesn't set its own. */
export const DEFAULT_TIMEOUT_MS = 5000;

/** Cap for the inline message in the human-readable report. Anything
 *  longer is truncated with a marker; the full value still lives in
 *  the JSON appendix. Keeps single-line test entries from blowing up
 *  the .txt when a test accidentally dumps a giant string. */
const INLINE_MESSAGE_MAX_CHARS = 300;

function truncateInline(s: string): string {
  if (s.length <= INLINE_MESSAGE_MAX_CHARS) return s;
  return (
    s.slice(0, INLINE_MESSAGE_MAX_CHARS) +
    `…[truncated, ${s.length} chars total]`
  );
}

/**
 * Race a promise against a timeout. Returns the resolved value or a
 * synthetic timeout rejection. The runner uses this so a hung fetch
 * doesn't block the rest of the suite.
 */
function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`Timed out after ${ms}ms: ${label}`));
    }, ms);
    p.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      },
    );
  });
}

/**
 * Run one test, capturing timing and any throw. Never rejects —
 * throws turn into fail records so the runner can keep going.
 */
export async function runOneTest(t: DiagnosticTest): Promise<DiagnosticRecord> {
  const start =
    typeof performance !== "undefined" && performance.now
      ? performance.now()
      : Date.now();
  const timeout = t.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  try {
    const result = await withTimeout(
      Promise.resolve(t.run()),
      timeout,
      t.label,
    );
    const end =
      typeof performance !== "undefined" && performance.now
        ? performance.now()
        : Date.now();
    return {
      id: t.id,
      label: t.label,
      category: t.category,
      status: result.status,
      message: result.message,
      data: result.data,
      durationMs: Math.round(end - start),
    };
  } catch (e) {
    const end =
      typeof performance !== "undefined" && performance.now
        ? performance.now()
        : Date.now();
    const err = e as Error;
    return {
      id: t.id,
      label: t.label,
      category: t.category,
      status: "fail",
      message: err?.message ?? String(e),
      durationMs: Math.round(end - start),
      errorName: err?.name,
      errorStack: err?.stack,
    };
  }
}

/**
 * Run a suite sequentially. Sequential (not parallel) on purpose —
 * the supabase round-trip tests insert + read + delete, and running
 * those concurrently with other supabase calls makes failures harder
 * to attribute. Also keeps the progress UI sensible.
 *
 * `onProgress` fires after each test completes — UI uses it to tick
 * a progress bar without waiting for the whole suite.
 */
export async function runSuite(
  tests: ReadonlyArray<DiagnosticTest>,
  onProgress?: (
    record: DiagnosticRecord,
    index: number,
    total: number,
  ) => void,
): Promise<DiagnosticRecord[]> {
  const out: DiagnosticRecord[] = [];
  for (let i = 0; i < tests.length; i++) {
    const record = await runOneTest(tests[i]);
    out.push(record);
    onProgress?.(record, i + 1, tests.length);
  }
  return out;
}

/**
 * Aggregate counts by status. Used in the report header line.
 */
export interface SuiteSummary {
  total: number;
  pass: number;
  fail: number;
  warn: number;
  skip: number;
  durationMs: number;
}

export function summarize(records: ReadonlyArray<DiagnosticRecord>): SuiteSummary {
  const summary: SuiteSummary = {
    total: records.length,
    pass: 0,
    fail: 0,
    warn: 0,
    skip: 0,
    durationMs: 0,
  };
  for (const r of records) {
    summary[r.status]++;
    summary.durationMs += r.durationMs;
  }
  return summary;
}

/**
 * Render the suite results as a paste-friendly text report. The
 * format is roughly:
 *
 *   === Tape Diagnostic — <iso> ===
 *   Summary: 38/42 pass (1 warn, 3 fail, 0 skip) in 8.2s
 *
 *   Build: <sha> (<env>)
 *   User:  <email> (<uuid>)
 *   UA:    <ua>
 *   ...header metadata...
 *
 *   == CATEGORY (12/14 pass) ==
 *     ✓ test label (24ms)
 *     ✓ another test (1ms) — optional pass detail
 *     ⚠ a warning (52ms)
 *         message goes here, wrapped at 80 chars
 *     ✗ a failure (412ms)
 *         message
 *         (data dump truncated for readability)
 *   ...
 *
 *   --- raw json appendix ---
 *   { full JSON dump of every record's data field }
 *
 * The appendix is what lets me reconstruct exact values when the
 * pass/fail headline isn't enough.
 */
export interface ReportHeader {
  /** ISO timestamp the suite started. */
  startedAt: string;
  /** Build SHA + environment, if known. */
  build?: { sha?: string; env?: string };
  /** Auth context. */
  user?: { id?: string; email?: string };
  /** Browser context. */
  browser?: { userAgent?: string; viewport?: string; language?: string };
  /** Anything else worth noting at the top of the report. */
  extra?: Record<string, string | number | boolean>;
}

const STATUS_GLYPH: Record<DiagnosticResult["status"], string> = {
  pass: "[OK]  ",
  warn: "[WARN]",
  fail: "[FAIL]",
  skip: "[SKIP]",
};

/**
 * Wrap a multi-line message with a leading indent. Used for the
 * detail block under a fail.
 */
function indentLines(text: string, prefix: string): string {
  return text
    .split("\n")
    .map((l) => prefix + l)
    .join("\n");
}

export function formatReport(
  header: ReportHeader,
  records: ReadonlyArray<DiagnosticRecord>,
): string {
  const summary = summarize(records);
  const lines: string[] = [];

  // Top banner — easy to spot when scanning a paste-back.
  lines.push("=== Tape Diagnostic ===");
  lines.push(`Started: ${header.startedAt}`);
  lines.push(
    `Summary: ${summary.pass}/${summary.total} pass` +
      ` (${summary.warn} warn, ${summary.fail} fail, ${summary.skip} skip)` +
      ` in ${(summary.durationMs / 1000).toFixed(2)}s`,
  );
  lines.push("");

  // Context block — everything that helps debug "where was this run?"
  if (header.build) {
    const { sha, env } = header.build;
    lines.push(`Build: ${sha ?? "unknown"} (${env ?? "unknown"})`);
  }
  if (header.user) {
    lines.push(`User:  ${header.user.email ?? "anonymous"} (${header.user.id ?? "no-id"})`);
  }
  if (header.browser) {
    const { userAgent, viewport, language } = header.browser;
    if (userAgent) lines.push(`UA:    ${userAgent}`);
    if (viewport) lines.push(`View:  ${viewport}`);
    if (language) lines.push(`Lang:  ${language}`);
  }
  if (header.extra) {
    for (const [k, v] of Object.entries(header.extra)) {
      lines.push(`${k.padEnd(6)} ${v}`);
    }
  }
  lines.push("");

  // Group records by category, preserving first-seen order.
  const byCategory = new Map<string, DiagnosticRecord[]>();
  for (const r of records) {
    const bucket = byCategory.get(r.category);
    if (bucket) bucket.push(r);
    else byCategory.set(r.category, [r]);
  }

  for (const [category, group] of byCategory) {
    const passCount = group.filter((r) => r.status === "pass").length;
    lines.push(`== ${category.toUpperCase()} (${passCount}/${group.length} pass) ==`);
    for (const r of group) {
      const glyph = STATUS_GLYPH[r.status];
      const head = `  ${glyph} ${r.label} (${r.durationMs}ms)`;
      const tail = r.message ? ` — ${truncateInline(r.message)}` : "";
      // For pass: single-line entry. For fail/warn: include the
      // message inline (already done via tail), plus indented stack
      // if there is one.
      lines.push(head + tail);
      if (r.status === "fail" && r.errorStack) {
        // Truncate stack to keep the human report readable; full
        // stack lives in the JSON appendix.
        const stack = r.errorStack
          .split("\n")
          .slice(0, 3)
          .join("\n");
        lines.push(indentLines(stack, "      "));
      }
    }
    lines.push("");
  }

  // JSON appendix — full record dump including any `data` fields.
  // Fenced code block so paste-back into a markdown editor renders
  // it cleanly.
  lines.push("--- raw json appendix ---");
  lines.push("```json");
  lines.push(
    JSON.stringify(
      { header, summary, records },
      // Replacer: trim absurdly long string fields to keep the
      // appendix manageable. 4KB per field is plenty for any
      // diagnostic value.
      (_k, v) => {
        if (typeof v === "string" && v.length > 4000) {
          return v.slice(0, 4000) + `…[truncated, ${v.length} chars total]`;
        }
        return v;
      },
      2,
    ),
  );
  lines.push("```");

  return lines.join("\n");
}

/**
 * Convenience: pass / fail / warn / skip result factories. Lets test
 * functions read like:
 *
 *   return pass("found 12 rows");
 *   return fail("RLS allowed access to another user's row");
 *
 * rather than the verbose object literal every time.
 */
export const pass = (message?: string, data?: unknown): DiagnosticResult => ({
  status: "pass",
  message,
  data,
});
export const fail = (message: string, data?: unknown): DiagnosticResult => ({
  status: "fail",
  message,
  data,
});
export const warn = (message: string, data?: unknown): DiagnosticResult => ({
  status: "warn",
  message,
  data,
});
export const skip = (message: string, data?: unknown): DiagnosticResult => ({
  status: "skip",
  message,
  data,
});
