/**
 * Collected diagnostic suite.
 *
 * Exports the master test list in the order the runner should execute
 * them. Order matters for two reasons:
 *   1. Cheap-first: sync browser-capability tests finish in <50ms so
 *      the progress bar tracks past them quickly and the admin gets
 *      visible progress while the slower network tests start.
 *   2. Cleanup-friendly: the supabase tests come before the iframe
 *      tests, so iframe failures (which take longer) don't delay
 *      garbage-collection of leaked __diag__ rows by 30+ seconds.
 *
 * To add a new category, write its tests in a sibling file under
 * src/lib/diagnostics/ and import + spread the list here. Keep
 * individual test files under ~300 LOC so they stay reviewable.
 */
import { buildInfoTests } from "./build-info";
import { browserTests } from "./browser-tests";
import { authTests } from "./auth-tests";
import { pageTests } from "./page-tests";
import { supabaseTests } from "./supabase-tests";
import { iframeTests } from "./iframe-tests";
import type { DiagnosticTest } from "../diagnostic-runner";

export const ALL_DIAGNOSTIC_TESTS: ReadonlyArray<DiagnosticTest> = [
  ...buildInfoTests,
  ...browserTests,
  ...authTests,
  ...pageTests,
  ...supabaseTests,
  ...iframeTests,
];

/** Tests grouped by category name, preserving in-list order. Useful
 *  for the UI to render a per-category enable/disable checkbox list. */
export function testsByCategory(): Map<string, DiagnosticTest[]> {
  const out = new Map<string, DiagnosticTest[]>();
  for (const t of ALL_DIAGNOSTIC_TESTS) {
    const bucket = out.get(t.category);
    if (bucket) bucket.push(t);
    else out.set(t.category, [t]);
  }
  return out;
}
