#!/usr/bin/env node
/**
 * Post-deploy diagnostic runner (Node / GitHub Actions).
 *
 * Runs the shared page-fetch checks against a live deployment and prints a
 * Markdown report on stdout. The check DEFINITIONS live in
 * src/lib/diagnostics/page-checks.mjs — the SAME module the in-app admin
 * diagnostics page (src/lib/diagnostics/page-tests.ts) runs in the browser — so
 * the two can't drift (they used to duplicate every check inline, and the
 * /library.json source-count floor drifted: this runner kept a stale 1000 while
 * the browser test lowered it to 500, warning on every healthy deploy).
 *
 * This runner stays DEPENDENCY-FREE on purpose (the CI workflow runs it with
 * `node scripts/run-deploy-diagnostic.mjs <url>` and NO `npm ci`): the shared
 * core is plain ESM with no imports, so a bare `node` can load it. All it adds
 * here is a Node fetch context (resolving paths against the target URL) plus the
 * timing/timeout harness and the Markdown report the CI workflow posts.
 *
 * Usage:
 *   node scripts/run-deploy-diagnostic.mjs https://legible-markets.vercel.app
 *
 * Exit code: 0 if all checks pass (warns don't fail), 1 if any check fails. The
 * post-deploy workflow always posts stdout regardless of exit code.
 */
import { pageChecks } from "../src/lib/diagnostics/page-checks.mjs";

const targetUrl = (process.argv[2] || "").replace(/\/$/, "");
if (!targetUrl) {
  console.error("Usage: run-deploy-diagnostic.mjs <url>");
  process.exit(2);
}

/** Node fetch context handed to every shared check. Resolves relative paths
 *  against the target URL; passes absolute URLs through unchanged. */
const nodeCtx = {
  // Per-run cache-buster token for the 404 probe (mirrors the browser wrapper's
  // Date.now()); keeps the shared core pure.
  nonce: Date.now(),
  async get(pathOrUrl) {
    const u = pathOrUrl.startsWith("http") ? pathOrUrl : `${targetUrl}${pathOrUrl}`;
    const res = await fetch(u, { method: "GET", redirect: "follow" });
    const body = await res.text();
    return {
      status: res.status,
      contentType: res.headers.get("content-type"),
      cacheControl: res.headers.get("cache-control"),
      body,
    };
  },
  async getBuffer(pathOrUrl) {
    const u = pathOrUrl.startsWith("http") ? pathOrUrl : `${targetUrl}${pathOrUrl}`;
    const res = await fetch(u, { method: "GET" });
    const buf = await res.arrayBuffer();
    return {
      status: res.status,
      contentType: res.headers.get("content-type"),
      bytes: buf.byteLength,
    };
  },
};

/** Race a check against its declared timeout so a hung fetch can't lock up the
 *  whole suite (mirrors src/lib/diagnostic-runner.ts's withTimeout). */
function withTimeout(p, ms, label) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error(`Timed out after ${ms}ms: ${label}`)),
      ms,
    );
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

const checks = [];
let exitCode = 0;

for (const check of pageChecks) {
  const t0 = Date.now();
  let status, detail;
  try {
    const result = await withTimeout(
      Promise.resolve(check.run(nodeCtx)),
      check.timeoutMs ?? 15000,
      check.label,
    );
    status = result?.status ?? "pass";
    detail = result?.message ?? "";
  } catch (e) {
    status = "fail";
    detail = `threw: ${e?.message ?? String(e)}`;
  }
  const durationMs = Date.now() - t0;
  checks.push({ name: check.label, status, detail, durationMs });
  if (status === "fail") exitCode = 1;
}

// ---------- Report ----------

const passCount = checks.filter((c) => c.status === "pass").length;
const warnCount = checks.filter((c) => c.status === "warn").length;
const failCount = checks.filter((c) => c.status === "fail").length;
const totalMs = checks.reduce((s, c) => s + c.durationMs, 0);

// Two report shapes — concise when every check is green, full table when
// there's anything to act on. The Diagnostics issue accrues a comment per
// deploy; showing the per-check breakdown on every healthy deploy creates
// attention fatigue, so green deploys collapse to a one-line "all pass" and the
// heading carries a ✅/⚠️/❌ glyph so the comment list is scannable at a glance.
const allGreen = failCount === 0 && warnCount === 0;
const headingGlyph = failCount > 0 ? "❌" : warnCount > 0 ? "⚠️" : "✅";
const lines = [];
lines.push(`## Post-deploy diagnostic ${headingGlyph}`);
lines.push("");
if (allGreen) {
  lines.push(
    `**Result:** All ${checks.length} checks pass in ${(totalMs / 1000).toFixed(2)}s.`,
  );
  lines.push("");
  lines.push(`**Target:** ${targetUrl}`);
  lines.push(`**Timestamp:** ${new Date().toISOString()}`);
  lines.push(`**Commit:** ${process.env.GITHUB_SHA || "(unset)"}`);
} else {
  lines.push(`**Target:** ${targetUrl}`);
  lines.push(
    `**Result:** ${passCount}/${checks.length} pass · ${warnCount} warn · ${failCount} fail · ${(totalMs / 1000).toFixed(2)}s`,
  );
  lines.push(`**Timestamp:** ${new Date().toISOString()}`);
  lines.push(`**Commit:** ${process.env.GITHUB_SHA || "(unset)"}`);
  lines.push("");
  lines.push("| Status | Test | Detail | Time |");
  lines.push("|---|---|---|---|");
  for (const c of checks) {
    const glyph =
      c.status === "pass"
        ? "✅"
        : c.status === "warn"
          ? "⚠️"
          : c.status === "fail"
            ? "❌"
            : c.status;
    // Escape pipes in detail so the markdown table doesn't break.
    const detail = (c.detail ?? "").replace(/\|/g, "\\|");
    lines.push(`| ${glyph} | ${c.name} | ${detail} | ${c.durationMs}ms |`);
  }
}
console.log(lines.join("\n"));

process.exit(exitCode);
