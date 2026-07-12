/**
 * Shared page-fetch diagnostic checks — the SINGLE source of truth for both:
 *
 *   1. the in-app admin diagnostics page (src/lib/diagnostics/page-tests.ts,
 *      runs in the browser, base = window.location.origin), and
 *   2. the post-deploy CI runner (scripts/run-deploy-diagnostic.mjs, runs in
 *      Node, base = the target URL passed on the command line).
 *
 * Before this module the two duplicated every check inline and drifted — most
 * visibly the /library.json source-count floor, which the browser test lowered
 * to 500 after the lean/geo split while the Node runner kept the stale 1000 and
 * warned on every healthy deploy. Now each check lives here ONCE; both consumers
 * are thin wrappers. Change a check here and both get it.
 *
 * Framework-agnostic on purpose: plain ESM, NO browser globals and NO imports,
 * so the dependency-free Node runner can `import` it directly (the CI workflow
 * runs `node scripts/run-deploy-diagnostic.mjs` with no `npm ci`). Types live in
 * the sibling page-checks.d.mts so the TypeScript wrapper stays type-safe.
 *
 * Each check is `{ id, label, category, timeoutMs, run(ctx) }` and returns a
 * `{ status, message?, data? }` (the DiagnosticResult shape). The host supplies
 * `ctx`:
 *   ctx.get(pathOrUrl)       -> { status, contentType, cacheControl, body }
 *   ctx.getBuffer(pathOrUrl) -> { status, contentType, bytes }
 * so the check bodies never touch `window` or a hard-coded origin.
 */

const pass = (message, data) => ({ status: "pass", message, data });
const fail = (message, data) => ({ status: "fail", message, data });
const warn = (message, data) => ({ status: "warn", message, data });

/**
 * A "fetch this path, expect 200 + text/html + a sentinel in the body" check.
 * Most routes get one of these.
 */
function routeCheck(id, label, path, sentinel) {
  return {
    id: `pages/${id}`,
    category: "pages",
    label,
    timeoutMs: 15000,
    run: async (ctx) => {
      const r = await ctx.get(path);
      if (r.status !== 200) {
        return fail(`status=${r.status} for ${path}`, { status: r.status });
      }
      if (!r.contentType || !r.contentType.startsWith("text/html")) {
        return fail(
          `unexpected content-type ${r.contentType ?? "(none)"} for ${path}`,
        );
      }
      const matches =
        typeof sentinel === "string"
          ? r.body.includes(sentinel)
          : sentinel.test(r.body);
      if (!matches) {
        return fail(
          `body did not contain sentinel ${
            typeof sentinel === "string" ? JSON.stringify(sentinel) : sentinel.toString()
          }`,
          { bodyLength: r.body.length },
        );
      }
      return pass(`${(r.body.length / 1024).toFixed(1)}KB`, {
        status: r.status,
        contentType: r.contentType,
        cacheControl: r.cacheControl,
        bodyLength: r.body.length,
      });
    },
  };
}

/** @type {import("./page-checks.d.mts").PageCheck[]} */
export const pageChecks = [
  // Static-prerendered marquee routes. If any 404 or 500, the build is broken.
  routeCheck("home", "/ home page renders", "/", /<title>/),
  routeCheck("us-macro", "/us-macro/ dashboard renders", "/us-macro/", /chart/i),
  routeCheck("walkthrough", "/walkthrough/ renders", "/walkthrough/", /chart/i),
  routeCheck("privacy", "/privacy/ renders", "/privacy/", /Privacy/),
  routeCheck("terms", "/terms/ renders", "/terms/", /Terms/),
  routeCheck("about", "/about/ renders", "/about/", /Tape|tape/),

  // SSR routes — must actually respond from a function, not just serve a
  // static prerender.
  routeCheck("me", "/me/ SSR route responds", "/me/", /dashboards|sign in/i),
  routeCheck("compose", "/compose/ composer route responds", "/compose/", /compose/i),
  routeCheck("alerts", "/alerts/ alerts route responds", "/alerts/", /alert/i),

  // library.json — the canonical "everything we have" payload. Shape is
  // { charts: [], sources: {id->meta}, metros: [], countries: [], ... }
  // (see src/pages/library.json.ts). Verify it parses + has a sensible
  // quantity in each of the two big sections (charts + sources).
  {
    id: "pages/library-json",
    category: "pages",
    label: "/library.json parses with charts + sources sections",
    timeoutMs: 30000,
    run: async (ctx) => {
      const r = await ctx.get("/library.json");
      if (r.status !== 200) return fail(`status=${r.status}`);
      let parsed;
      try {
        parsed = JSON.parse(r.body);
      } catch (e) {
        return fail(`invalid JSON: ${e.message}`);
      }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        return fail(
          `expected an object, got ${Array.isArray(parsed) ? "array" : typeof parsed}`,
        );
      }
      const charts = parsed.charts;
      const sources = parsed.sources;
      if (!Array.isArray(charts)) {
        return fail(`.charts not an array (got ${typeof charts})`);
      }
      if (!sources || typeof sources !== "object" || Array.isArray(sources)) {
        return fail(`.sources not an object (got ${typeof sources})`);
      }
      const chartCount = charts.length;
      const sourceCount = Object.keys(sources).length;
      // Floor for the LEAN /library.json. Since the lean/geo split, the ~96% of
      // sources that are geographic (per-CD / metro / state / country) are
      // lazy-loaded behind /library-geo and are deliberately NOT in this
      // payload — it carries only the visible-by-default non-geo catalog (~685
      // today). The old 1000 floor predated the split and fired a permanent
      // false "unusually low" warning. 500 still catches a real collapse of the
      // lean catalog without flagging its normal size.
      if (sourceCount < 500) {
        return warn(
          `only ${sourceCount} sources, ${chartCount} charts (lean catalog; geo sources are in /library-geo)`,
          { chartCount, sourceCount },
        );
      }
      if (chartCount < 50) {
        return warn(
          `${sourceCount} sources, ${chartCount} charts — charts unusually low`,
          { chartCount, sourceCount },
        );
      }
      return pass(
        `${sourceCount} sources, ${chartCount} charts (${(r.body.length / 1024).toFixed(0)}KB)`,
        {
          chartCount,
          sourceCount,
          metroCount: Array.isArray(parsed.metros) ? parsed.metros.length : null,
          countryCount: Array.isArray(parsed.countries) ? parsed.countries.length : null,
          bytes: r.body.length,
        },
      );
    },
  },

  // /robots.txt + /sitemap-index.xml — search-engine sanity. These must exist
  // or the site goes dark in search.
  {
    id: "pages/robots-txt",
    category: "pages",
    label: "/robots.txt is served with a Sitemap directive",
    timeoutMs: 10000,
    run: async (ctx) => {
      const r = await ctx.get("/robots.txt");
      if (r.status !== 200) return fail(`status=${r.status}`);
      if (!r.body.includes("Sitemap")) {
        return warn("robots.txt missing Sitemap directive");
      }
      return pass(`${r.body.length} bytes`);
    },
  },
  {
    id: "pages/sitemap-index",
    category: "pages",
    label: "/sitemap-index.xml has child sitemaps",
    timeoutMs: 10000,
    run: async (ctx) => {
      const r = await ctx.get("/sitemap-index.xml");
      if (r.status !== 200) return fail(`status=${r.status}`);
      const childCount = (r.body.match(/<sitemap>/g) ?? []).length;
      if (childCount === 0) return fail("no <sitemap> entries");
      return pass(`${childCount} child sitemap(s)`);
    },
  },

  // OG image generation — the /og.png SSR endpoint that produces social-card
  // PNGs (route file src/pages/og.png.ts, NOT /api/og).
  {
    id: "pages/og-image",
    category: "pages",
    label: "/og.png produces a PNG",
    timeoutMs: 20000,
    run: async (ctx) => {
      const r = await ctx.getBuffer("/og.png?title=Diagnostic+probe");
      if (r.status !== 200) return fail(`status=${r.status}`);
      if (!r.contentType || !r.contentType.includes("image/png")) {
        return fail(`content-type=${r.contentType ?? "(none)"} (expected image/png)`);
      }
      if (r.bytes < 1024) return fail(`PNG suspiciously small (${r.bytes} bytes)`);
      return pass(`${(r.bytes / 1024).toFixed(1)}KB PNG`, { bytes: r.bytes });
    },
  },
  {
    id: "pages/og-personalizes",
    category: "pages",
    label: "/og.png personalizes by title param",
    timeoutMs: 30000,
    run: async (ctx) => {
      const a = await ctx.getBuffer("/og.png?title=A");
      const b = await ctx.getBuffer(
        "/og.png?title=A+much+longer+social+card+title+for+a+probe",
      );
      if (a.status !== 200 || b.status !== 200) {
        return fail(`statuses=${a.status},${b.status}`);
      }
      if (a.bytes === b.bytes) {
        return fail(
          `both PNGs same size (${a.bytes}B) — title param may be ignored`,
        );
      }
      return pass(`${a.bytes}B vs ${b.bytes}B`);
    },
  },

  // The fingerprinted CSS bundle must ship with a long/immutable cache-control
  // so returning visitors don't re-download it.
  {
    id: "pages/css-immutable",
    category: "pages",
    label: "CSS bundle ships with immutable cache-control",
    timeoutMs: 15000,
    run: async (ctx) => {
      const home = await ctx.get("/");
      const match = home.body.match(
        /<link[^>]*rel=["']stylesheet["'][^>]*href=["']([^"']+)["'][^>]*>/,
      );
      if (!match) return fail("no <link rel='stylesheet'> on home page");
      const href = match[1];
      const css = await ctx.get(href);
      if (css.status !== 200) return fail(`${href} status=${css.status}`);
      const cc = css.cacheControl ?? "";
      const looksImmutable =
        /immutable/i.test(cc) || /max-age=\s*[0-9]{6,}/i.test(cc);
      if (!looksImmutable) {
        return warn(
          `cache-control=${cc || "(none)"} — fingerprinted asset should be immutable`,
        );
      }
      return pass(`${href} (${cc})`);
    },
  },

  // Sentinel data file — discovers a REAL source's dataFile via library.json
  // (rather than hard-coding a guess), then probes that file. Resilient to
  // source-id renames.
  {
    id: "pages/known-source-json",
    category: "pages",
    label: "a real source-data file (discovered via library.json) is fetchable",
    timeoutMs: 30000,
    run: async (ctx) => {
      const libRes = await ctx.get("/library.json");
      if (libRes.status !== 200) {
        return fail(`couldn't fetch library.json: status=${libRes.status}`);
      }
      let lib;
      try {
        lib = JSON.parse(libRes.body);
      } catch (e) {
        return fail(`library.json parse failed: ${e.message}`);
      }
      const sources = lib?.sources;
      if (!sources || typeof sources !== "object") {
        return fail("library.json had no sources dict");
      }
      let chosenDataFile = null;
      let chosenId = null;
      for (const [id, meta] of Object.entries(sources)) {
        if (meta?.dataFile) {
          chosenDataFile = meta.dataFile;
          chosenId = id;
          break;
        }
      }
      if (!chosenDataFile) return fail("no source in library.json had a dataFile");
      const dataPath = chosenDataFile.startsWith("/") ? chosenDataFile : `/${chosenDataFile}`;
      const dataRes = await ctx.get(dataPath);
      if (dataRes.status !== 200) {
        return fail(
          `fetched library.json OK but its first source (${chosenId}) → ${dataPath} returned ${dataRes.status}`,
        );
      }
      let parsed;
      try {
        parsed = JSON.parse(dataRes.body);
      } catch (e) {
        return fail(`${dataPath} parse failed: ${e.message}`);
      }
      const kind = parsed?.kind;
      if (kind === "timeseries") {
        const pts = parsed?.points;
        if (Array.isArray(pts) && pts.length > 0) {
          return pass(`${chosenId} → ${dataPath} (${pts.length} points)`, {
            sourceId: chosenId,
            dataPath,
            points: pts.length,
          });
        }
        return fail(`${chosenId} → ${dataPath} parsed but had no points`);
      }
      if (kind === "curve") {
        const snaps = parsed?.snapshots;
        if (Array.isArray(snaps) && snaps.length > 0) {
          return pass(`${chosenId} → ${dataPath} (curve, ${snaps.length} snapshots)`, {
            sourceId: chosenId,
            dataPath,
            snapshots: snaps.length,
          });
        }
      }
      return warn(
        `${chosenId} → ${dataPath} parsed but kind=${kind}, payload shape unrecognized`,
        { sourceId: chosenId, dataPath, kind },
      );
    },
  },

  // A made-up route should 404 cleanly AND return user-facing copy — a 404 with
  // an empty / unstyled / "Internal Server Error" body still ships a broken
  // experience even though the status code is correct.
  {
    id: "pages/404-on-bogus",
    category: "pages",
    label: "bogus path returns a 404 with user-facing copy",
    timeoutMs: 10000,
    // Cache-buster in the path keeps a CDN from serving a warm 404; the
    // timestamp is injected by the host so this module stays pure.
    run: async (ctx) => {
      const r = await ctx.get(`/__diagnostic_404_probe_${ctx.nonce}__/`);
      if (r.status !== 404) {
        if (r.status >= 300 && r.status < 400) {
          return warn(`got ${r.status} (redirect) instead of 404`);
        }
        return fail(`expected 404, got ${r.status}`);
      }
      const hasBrand = /Tape/.test(r.body);
      const has404Copy = /not found|404/i.test(r.body);
      if (!hasBrand || !has404Copy) {
        return fail(
          `404 body missing sentinel(s): brand=${hasBrand}, 404-copy=${has404Copy}`,
          { bodyLength: r.body.length },
        );
      }
      if (r.body.length < 2048) {
        return warn(
          `404 body suspiciously small (${r.body.length} bytes) — platform fallback?`,
        );
      }
      return pass(`${(r.body.length / 1024).toFixed(1)}KB`);
    },
  },
];
