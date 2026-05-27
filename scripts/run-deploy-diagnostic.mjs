#!/usr/bin/env node
/**
 * Server-side subset of the diagnostic suite — runnable from Node
 * (or GitHub Actions). The browser-based tests (iframe, dialog
 * interactions, localStorage probes) can't run here, but the
 * HTTP-fetch tests are trivially Node-compatible and form the
 * majority of the actionable signal.
 *
 * Usage:
 *   node scripts/run-deploy-diagnostic.mjs https://tape.vercel.app
 *
 * Outputs a Markdown-formatted report on stdout. The CI workflow
 * (.github/workflows/post-deploy-diagnostic.yml) captures stdout
 * and posts as a comment on the Diagnostics GitHub issue.
 *
 * Exit code: 0 if all checks pass, 1 if any check fails. The post-
 * deploy workflow always posts regardless of exit code so failures
 * are visible.
 */

const targetUrl = (process.argv[2] || "").replace(/\/$/, "");
if (!targetUrl) {
  console.error("Usage: run-deploy-diagnostic.mjs <url>");
  process.exit(2);
}

const checks = [];
let exitCode = 0;

function record({ name, status, detail, durationMs }) {
  checks.push({ name, status, detail, durationMs });
  if (status === "fail") exitCode = 1;
}

async function timed(name, fn) {
  const t0 = Date.now();
  try {
    const result = await fn();
    const dur = Date.now() - t0;
    if (result.status) {
      record({ name, ...result, durationMs: dur });
    } else {
      record({ name, status: "pass", detail: result.detail ?? "", durationMs: dur });
    }
  } catch (e) {
    record({
      name,
      status: "fail",
      detail: `threw: ${e.message ?? String(e)}`,
      durationMs: Date.now() - t0,
    });
  }
}

async function fetchText(path) {
  const url = path.startsWith("http") ? path : `${targetUrl}${path}`;
  const res = await fetch(url, {
    method: "GET",
    redirect: "follow",
  });
  const body = await res.text();
  return { status: res.status, headers: res.headers, body };
}

async function fetchBuffer(path) {
  const url = path.startsWith("http") ? path : `${targetUrl}${path}`;
  const res = await fetch(url, { method: "GET" });
  const buf = await res.arrayBuffer();
  return { status: res.status, headers: res.headers, bytes: buf.byteLength };
}

// ---------- Checks ----------

async function checkRoute(path, sentinel, minBodyLength = 1024) {
  return timed(`page ${path} renders`, async () => {
    const r = await fetchText(path);
    if (r.status !== 200) {
      return { status: "fail", detail: `status=${r.status}` };
    }
    if (r.body.length < minBodyLength) {
      return {
        status: "warn",
        detail: `body=${r.body.length} bytes (< ${minBodyLength})`,
      };
    }
    if (sentinel && !sentinel.test(r.body)) {
      return {
        status: "fail",
        detail: `body missing sentinel ${sentinel}`,
      };
    }
    return {
      status: "pass",
      detail: `${(r.body.length / 1024).toFixed(1)}KB`,
    };
  });
}

await checkRoute("/", /<title>/);
await checkRoute("/us-macro/", /chart/i);
await checkRoute("/walkthrough/", /chart/i);
await checkRoute("/privacy/", /Privacy/);
await checkRoute("/terms/", /Terms/);
await checkRoute("/about/", /tape/i);
await checkRoute("/me/", /dashboards|sign in/i);
await checkRoute("/compose/", /compose/i);
await checkRoute("/alerts/", /alert/i);

await timed("/library.json parses + has source dict", async () => {
  const r = await fetchText("/library.json");
  if (r.status !== 200)
    return { status: "fail", detail: `status=${r.status}` };
  let parsed;
  try {
    parsed = JSON.parse(r.body);
  } catch (e) {
    return { status: "fail", detail: `parse: ${e.message}` };
  }
  const charts = parsed?.charts;
  const sources = parsed?.sources;
  if (!Array.isArray(charts))
    return { status: "fail", detail: ".charts not an array" };
  if (!sources || typeof sources !== "object")
    return { status: "fail", detail: ".sources not an object" };
  const sourceCount = Object.keys(sources).length;
  if (sourceCount < 1000)
    return {
      status: "warn",
      detail: `only ${sourceCount} sources`,
    };
  return {
    status: "pass",
    detail: `${sourceCount} sources, ${charts.length} charts (${(r.body.length / 1024).toFixed(0)}KB)`,
  };
});

await timed("/og.png produces a PNG", async () => {
  const r = await fetchBuffer("/og.png?title=CI+probe");
  if (r.status !== 200)
    return { status: "fail", detail: `status=${r.status}` };
  const ct = r.headers.get("content-type") ?? "";
  if (!ct.includes("image/png"))
    return { status: "fail", detail: `content-type=${ct}` };
  if (r.bytes < 1024)
    return { status: "fail", detail: `${r.bytes} bytes (< 1KB)` };
  return {
    status: "pass",
    detail: `${(r.bytes / 1024).toFixed(1)}KB PNG`,
  };
});

await timed("/og.png personalizes by params", async () => {
  const a = await fetchBuffer("/og.png?title=A");
  const b = await fetchBuffer(
    "/og.png?title=A+much+longer+social+card+title+for+a+CI+probe",
  );
  if (a.status !== 200 || b.status !== 200)
    return { status: "fail", detail: `statuses=${a.status},${b.status}` };
  if (a.bytes === b.bytes)
    return {
      status: "fail",
      detail: `both PNGs same size (${a.bytes}B) — title param may be ignored`,
    };
  return { status: "pass", detail: `${a.bytes}B vs ${b.bytes}B` };
});

await timed("/sitemap-index.xml has child sitemaps", async () => {
  const r = await fetchText("/sitemap-index.xml");
  if (r.status !== 200)
    return { status: "fail", detail: `status=${r.status}` };
  const childCount = (r.body.match(/<sitemap>/g) ?? []).length;
  if (childCount === 0)
    return { status: "fail", detail: "no <sitemap> entries" };
  return { status: "pass", detail: `${childCount} child sitemap(s)` };
});

await timed("/robots.txt has Sitemap directive", async () => {
  const r = await fetchText("/robots.txt");
  if (r.status !== 200)
    return { status: "fail", detail: `status=${r.status}` };
  if (!r.body.includes("Sitemap"))
    return { status: "warn", detail: "no Sitemap directive" };
  return { status: "pass", detail: `${r.body.length} bytes` };
});

await timed("CSS bundle ships with immutable cache-control", async () => {
  const home = await fetchText("/");
  const match = home.body.match(
    /<link[^>]*rel=["']stylesheet["'][^>]*href=["']([^"']+)["'][^>]*>/,
  );
  if (!match)
    return {
      status: "fail",
      detail: "no <link rel='stylesheet'> on home page",
    };
  const href = match[1];
  const css = await fetchText(href);
  if (css.status !== 200)
    return { status: "fail", detail: `${href} status=${css.status}` };
  const cc = css.headers.get("cache-control") ?? "";
  const looksImmutable =
    /immutable/i.test(cc) || /max-age=\s*[0-9]{6,}/i.test(cc);
  if (!looksImmutable)
    return {
      status: "warn",
      detail: `cache-control=${cc || "(none)"} — fingerprinted asset should be immutable`,
    };
  return { status: "pass", detail: `${href} (${cc})` };
});

await timed("404 path returns a styled 404 page", async () => {
  const r = await fetchText(`/__doesnt_exist_${Date.now()}__/`);
  if (r.status !== 404)
    return {
      status: r.status >= 300 && r.status < 400 ? "warn" : "fail",
      detail: `status=${r.status}`,
    };
  const hasBrand = /Tape/.test(r.body);
  const hasNotFound = /not found|404/i.test(r.body);
  if (!hasBrand || !hasNotFound)
    return {
      status: "fail",
      detail: `body missing brand=${hasBrand}, 404-copy=${hasNotFound}`,
    };
  return { status: "pass", detail: `${(r.body.length / 1024).toFixed(1)}KB` };
});

// ---------- Report ----------

const passCount = checks.filter((c) => c.status === "pass").length;
const warnCount = checks.filter((c) => c.status === "warn").length;
const failCount = checks.filter((c) => c.status === "fail").length;
const totalMs = checks.reduce((s, c) => s + c.durationMs, 0);

const lines = [];
lines.push("## Post-deploy diagnostic");
lines.push("");
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
console.log(lines.join("\n"));

process.exit(exitCode);
