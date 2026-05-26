/**
 * Page-fetch diagnostic tests.
 *
 * Hits the live deployed pages over HTTP and checks: status code,
 * content-type, payload length, response headers, sentinel body
 * strings. This catches a class of bugs that vitest can't reach:
 *
 *   - SSR-only routes (e.g. /me/, /api/og) actually responding
 *   - Static routes correctly prerendered (e.g. /us-macro/)
 *   - /library.json valid JSON with the expected entry count
 *   - cache headers in the right shape on prerendered vs SSR routes
 *   - 404s on routes that shouldn't 404
 *
 * Each test is independent — failures don't cascade. The fetches use
 * the current document.origin so the suite always probes the
 * deployment it's actually running on (preview, prod, or localhost).
 */
import {
  fail,
  pass,
  warn,
  type DiagnosticTest,
  type DiagnosticResult,
} from "../diagnostic-runner";

/**
 * Build the absolute URL for a same-origin path. Used because relative
 * URLs from inside fetch() inside an Astro SSR page can resolve oddly
 * if the page itself is at a nested path.
 */
function url(pathOrUrl: string): string {
  if (/^https?:/i.test(pathOrUrl)) return pathOrUrl;
  return new URL(pathOrUrl, window.location.origin).toString();
}

/**
 * Common GET helper: returns {status, headers, body} after reading
 * the full body. Bounded by the caller's outer timeout via the runner.
 */
async function get(
  pathOrUrl: string,
): Promise<{
  status: number;
  contentType: string | null;
  cacheControl: string | null;
  body: string;
}> {
  const res = await fetch(url(pathOrUrl), {
    method: "GET",
    redirect: "follow",
    cache: "no-store",
  });
  const body = await res.text();
  return {
    status: res.status,
    contentType: res.headers.get("content-type"),
    cacheControl: res.headers.get("cache-control"),
    body,
  };
}

/**
 * Build a "fetch this path and check that it 200s and contains the
 * sentinel" test. Most pages get one of these.
 */
function htmlPageTest(
  id: string,
  label: string,
  path: string,
  sentinel: string | RegExp,
): DiagnosticTest {
  return {
    id: `pages/${id}`,
    category: "pages",
    label,
    timeoutMs: 15000,
    run: async () => {
      const r = await get(path);
      if (r.status !== 200) {
        return fail(`status=${r.status} for ${path}`, {
          status: r.status,
        });
      }
      if (!r.contentType?.startsWith("text/html")) {
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
          `body did not contain sentinel ${typeof sentinel === "string" ? JSON.stringify(sentinel) : sentinel.toString()}`,
          { bodyLength: r.body.length },
        );
      }
      return pass(
        `${(r.body.length / 1024).toFixed(1)}KB`,
        {
          status: r.status,
          contentType: r.contentType,
          cacheControl: r.cacheControl,
          bodyLength: r.body.length,
        },
      );
    },
  };
}

export const pageTests: DiagnosticTest[] = [
  // Static-prerendered marquee routes. If any of these 404 or 500,
  // the build is fundamentally broken.
  htmlPageTest("home", "/ home page renders", "/", /<title>/),
  htmlPageTest(
    "us-macro",
    "/us-macro/ dashboard renders",
    "/us-macro/",
    /chart/i,
  ),
  // /library.json is the canonical "everything" endpoint — there's no
  // /library/ HTML index; that's by design. The composer's
  // Sources/Pregenerated/Maps/Generators tabs ARE the library UI.
  htmlPageTest("walkthrough", "/walkthrough/ renders", "/walkthrough/", /chart/i),
  htmlPageTest("privacy", "/privacy/ renders", "/privacy/", /Privacy/),
  htmlPageTest("terms", "/terms/ renders", "/terms/", /Terms/),
  htmlPageTest("about", "/about/ renders", "/about/", /Tape|tape/),

  // SSR routes — must actually respond from a function, not just
  // serve a static prerender.
  htmlPageTest("me", "/me/ SSR route responds", "/me/", /dashboards|sign in/i),
  htmlPageTest(
    "compose",
    "/compose/ composer route responds",
    "/compose/",
    /compose/i,
  ),
  htmlPageTest("alerts", "/alerts/ alerts route responds", "/alerts/", /alert/i),

  // library.json — the canonical "everything we have" payload. Shape
  // is { charts: [], sources: {id->meta}, metros: [], metroTag,
  // countries: [], countryTag } (see src/pages/library.json.ts). Test
  // verifies the response parses + has a sensible quantity in each of
  // the two big sections (charts + sources).
  {
    id: "pages/library-json",
    category: "pages",
    label: "/library.json parses with charts + sources sections",
    timeoutMs: 30000,
    run: async (): Promise<DiagnosticResult> => {
      const r = await get("/library.json");
      if (r.status !== 200) {
        return fail(`status=${r.status}`);
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(r.body);
      } catch (e) {
        return fail(`invalid JSON: ${(e as Error).message}`);
      }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        return fail(
          `expected an object, got ${Array.isArray(parsed) ? "array" : typeof parsed}`,
        );
      }
      const obj = parsed as Record<string, unknown>;
      const charts = obj.charts;
      const sources = obj.sources;
      if (!Array.isArray(charts)) {
        return fail(`.charts not an array (got ${typeof charts})`);
      }
      if (!sources || typeof sources !== "object" || Array.isArray(sources)) {
        return fail(`.sources not an object (got ${typeof sources})`);
      }
      const chartCount = charts.length;
      const sourceCount = Object.keys(sources).length;
      // 100 + 1000 are conservative floors — the pipeline emits
      // ~thousands of sources and at least dozens of curated charts.
      if (sourceCount < 1000) {
        return warn(
          `${sourceCount} sources, ${chartCount} charts — sources unusually low`,
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
          metroCount: Array.isArray(obj.metros) ? obj.metros.length : null,
          countryCount: Array.isArray(obj.countries)
            ? obj.countries.length
            : null,
          bytes: r.body.length,
        },
      );
    },
  },

  // /robots.txt + /sitemap-index.xml — search engine sanity. These
  // must exist or the site goes dark in search.
  {
    id: "pages/robots-txt",
    category: "pages",
    label: "/robots.txt is served",
    timeoutMs: 10000,
    run: async () => {
      const r = await get("/robots.txt");
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
    label: "/sitemap-index.xml is served",
    timeoutMs: 10000,
    run: async () => {
      const r = await get("/sitemap-index.xml");
      if (r.status !== 200) return fail(`status=${r.status}`);
      if (!r.body.includes("<sitemap>")) {
        return fail("sitemap-index.xml missing <sitemap> entries");
      }
      return pass();
    },
  },

  // OG image generation — the /og.png SSR endpoint that produces
  // social-card PNGs (NOT /api/og; the route file is at
  // src/pages/og.png.ts).
  {
    id: "pages/og-image",
    category: "pages",
    label: "/og.png produces a PNG",
    timeoutMs: 20000,
    run: async () => {
      const res = await fetch(
        url("/og.png?title=Diagnostic+Test&subtitle=admin+probe"),
        { cache: "no-store" },
      );
      if (res.status !== 200) {
        return fail(`status=${res.status}`);
      }
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.includes("image/png")) {
        return fail(`content-type=${ct} (expected image/png)`);
      }
      const buf = await res.arrayBuffer();
      if (buf.byteLength < 1024) {
        return fail(`PNG suspiciously small (${buf.byteLength} bytes)`);
      }
      return pass(`${(buf.byteLength / 1024).toFixed(1)}KB PNG`, {
        bytes: buf.byteLength,
      });
    },
  },

  // Sentinel data file — fetches /library.json first to discover a
  // REAL source's dataFile path (rather than hardcoding guesses),
  // then probes that file. Resilient to source-id renames.
  {
    id: "pages/known-source-json",
    category: "pages",
    label: "a real source-data file (discovered via library.json) is fetchable",
    timeoutMs: 30000,
    run: async () => {
      // Discover via library.json's sources dict so we don't have to
      // hardcode any specific source ID.
      const libRes = await fetch(url("/library.json"), { cache: "no-store" });
      if (libRes.status !== 200) {
        return fail(`couldn't fetch library.json: status=${libRes.status}`);
      }
      let lib: unknown;
      try {
        lib = JSON.parse(await libRes.text());
      } catch (e) {
        return fail(`library.json parse failed: ${(e as Error).message}`);
      }
      const sources = (lib as { sources?: Record<string, unknown> })?.sources;
      if (!sources || typeof sources !== "object") {
        return fail("library.json had no sources dict");
      }
      // Pick the first source with a dataFile and a kind we can
      // probe (timeseries).
      let chosenDataFile: string | null = null;
      let chosenId: string | null = null;
      for (const [id, meta] of Object.entries(sources)) {
        const m = meta as { dataFile?: string; kind?: string };
        if (m?.dataFile) {
          chosenDataFile = m.dataFile;
          chosenId = id;
          break;
        }
      }
      if (!chosenDataFile) {
        return fail("no source in library.json had a dataFile");
      }
      const dataPath = chosenDataFile.startsWith("/")
        ? chosenDataFile
        : `/${chosenDataFile}`;
      const dataRes = await fetch(url(dataPath), { cache: "no-store" });
      if (dataRes.status !== 200) {
        return fail(
          `fetched library.json OK but its first source (${chosenId}) → ${dataPath} returned ${dataRes.status}`,
        );
      }
      try {
        const parsed = JSON.parse(await dataRes.text());
        const kind = (parsed as { kind?: string })?.kind;
        if (kind === "timeseries") {
          const pts = (parsed as { points?: unknown[] })?.points;
          if (Array.isArray(pts) && pts.length > 0) {
            return pass(`${chosenId} → ${dataPath} (${pts.length} points)`, {
              sourceId: chosenId,
              dataPath,
              points: pts.length,
            });
          }
          return fail(
            `${chosenId} → ${dataPath} parsed but had no points`,
          );
        }
        if (kind === "curve") {
          const snaps = (parsed as { snapshots?: unknown[] })?.snapshots;
          if (Array.isArray(snaps) && snaps.length > 0) {
            return pass(
              `${chosenId} → ${dataPath} (curve, ${snaps.length} snapshots)`,
              { sourceId: chosenId, dataPath, snapshots: snaps.length },
            );
          }
        }
        return warn(
          `${chosenId} → ${dataPath} parsed but kind=${kind}, payload shape unrecognized`,
          { sourceId: chosenId, dataPath, kind },
        );
      } catch (e) {
        return fail(`${dataPath} parse failed: ${(e as Error).message}`);
      }
    },
  },

  // A made-up route that should 404 cleanly. Confirms the 404 path
  // works at all (some misconfigurations make every 404 hang).
  {
    id: "pages/404-on-bogus",
    category: "pages",
    label: "bogus path returns a 404",
    timeoutMs: 10000,
    run: async () => {
      const r = await get(
        "/__definitely_does_not_exist_" + Date.now() + "__/",
      );
      if (r.status === 404) return pass();
      if (r.status >= 300 && r.status < 400) {
        return warn(`got ${r.status} (redirect) instead of 404`);
      }
      return fail(`expected 404, got ${r.status}`);
    },
  },
  // Tile-summary invariant: every timeseries source ships a sibling
  // `<dataFile>.summary.json` (cheap latest+priors+sparks). The Phase 2
  // tile-payload work depends on these being kept in sync with the full
  // data file. If the pipeline drifts and a summary is stale (or
  // missing), tiles render wrong values without crashing — silent and
  // bad. This test discovers a source via library.json, fetches both
  // files, and confirms `latest` matches.
  {
    id: "pages/tile-summary-matches-full",
    category: "pages",
    label: "<id>.summary.json's latest matches the full file's last point",
    timeoutMs: 30000,
    run: async () => {
      const libRes = await fetch(url("/library.json"), { cache: "no-store" });
      if (libRes.status !== 200) {
        return fail(`library.json status=${libRes.status}`);
      }
      const lib = JSON.parse(await libRes.text()) as {
        sources?: Record<string, { dataFile?: string; kind?: string }>;
      };
      if (!lib.sources) return fail("library.json has no sources");
      // Find the first TIMESERIES source with a dataFile. Curve
      // sources don't ship .summary.json, so skip them.
      let dataFile: string | null = null;
      let sourceId: string | null = null;
      for (const [id, m] of Object.entries(lib.sources)) {
        if (m?.dataFile && m?.kind === "timeseries") {
          dataFile = m.dataFile;
          sourceId = id;
          break;
        }
      }
      if (!dataFile) {
        return fail("no timeseries source in library.json had a dataFile");
      }
      const fullPath = dataFile.startsWith("/") ? dataFile : `/${dataFile}`;
      // Replace .json suffix with .summary.json. Anything else and
      // the pipeline doesn't ship a sibling.
      if (!fullPath.endsWith(".json")) {
        return fail(`dataFile doesn't end with .json: ${fullPath}`);
      }
      const summaryPath = fullPath.replace(/\.json$/, ".summary.json");
      const [fullRes, summaryRes] = await Promise.all([
        fetch(url(fullPath), { cache: "no-store" }),
        fetch(url(summaryPath), { cache: "no-store" }),
      ]);
      if (fullRes.status !== 200) {
        return fail(`full data fetch ${fullPath}: status=${fullRes.status}`);
      }
      if (summaryRes.status !== 200) {
        return fail(
          `summary fetch ${summaryPath}: status=${summaryRes.status}`,
        );
      }
      const full = JSON.parse(await fullRes.text()) as {
        points?: Array<{ t: string; v: number }>;
      };
      const summary = JSON.parse(await summaryRes.text()) as {
        latest?: { t: string; v: number };
      };
      const lastFull = full.points?.[full.points.length - 1];
      if (!lastFull) return fail(`full file has no points: ${fullPath}`);
      if (!summary.latest) {
        return fail(`summary has no .latest field: ${summaryPath}`);
      }
      // The summary's latest should be byte-equal to the full file's
      // last point. Drift means build_summaries.py and the full-data
      // pipeline disagree about what "latest" is.
      if (
        summary.latest.t !== lastFull.t ||
        summary.latest.v !== lastFull.v
      ) {
        return fail(
          `summary.latest drifted from full.points[-1] for ${sourceId}: full=(${lastFull.t}, ${lastFull.v}) vs summary=(${summary.latest.t}, ${summary.latest.v})`,
        );
      }
      // Sanity: the summary should be substantially smaller (Phase 2
      // bandwidth-reduction motivation). >50% smaller is normal.
      const fullSize = (await (await fetch(url(fullPath))).text()).length;
      const summarySize = (await (await fetch(url(summaryPath))).text()).length;
      const sizeRatio = summarySize / fullSize;
      if (sizeRatio > 0.9) {
        return warn(
          `summary not much smaller than full (${(sizeRatio * 100).toFixed(0)}%) — Phase 2 benefit lost`,
          { fullSize, summarySize, sizeRatio },
        );
      }
      return pass(
        `${sourceId}: ${(summarySize / 1024).toFixed(1)}KB summary vs ${(fullSize / 1024).toFixed(1)}KB full (${(sizeRatio * 100).toFixed(0)}%)`,
        { sourceId, lastT: lastFull.t, sizeRatio },
      );
    },
  },
];
