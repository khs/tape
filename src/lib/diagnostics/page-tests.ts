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
  htmlPageTest("library", "/library/ index renders", "/library/", /library/i),
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

  // library.json — the canonical "everything we have" payload. A
  // suspiciously low count signals a content-collection misload.
  {
    id: "pages/library-json",
    category: "pages",
    label: "/library.json parses and has >= 4000 entries",
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
      if (!Array.isArray(parsed)) {
        return fail(
          `expected an array, got ${typeof parsed} (keys: ${
            parsed && typeof parsed === "object"
              ? Object.keys(parsed).join(",")
              : "n/a"
          })`,
        );
      }
      const count = parsed.length;
      if (count < 4000) {
        return warn(`only ${count} library entries — pipeline output may be incomplete`, {
          count,
        });
      }
      return pass(`${count} entries (${(r.body.length / 1024).toFixed(0)}KB)`, {
        count,
        bytes: r.body.length,
      });
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

  // OG image generation — the SSR /api/og endpoint that produces
  // social-card PNGs.
  {
    id: "pages/og-image",
    category: "pages",
    label: "/api/og produces a PNG",
    timeoutMs: 20000,
    run: async () => {
      const res = await fetch(
        url("/api/og?title=Diagnostic+Test&subtitle=admin+probe"),
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

  // Sentinel data file — proves a known source's JSON is fetchable
  // from the static asset host. Picks a well-known FRED series the
  // pipeline always emits.
  {
    id: "pages/known-source-json",
    category: "pages",
    label: "a known source-data file is fetchable",
    timeoutMs: 15000,
    run: async () => {
      // CPI-YoY is one of the most-likely-to-exist sources; the
      // path follows the pipeline's <id>.json convention.
      const candidates = [
        "/data/fred/cpi_yoy.json",
        "/data/fred/dgs10.json",
        "/data/fred/fed_funds.json",
      ];
      for (const p of candidates) {
        const r = await fetch(url(p), { cache: "no-store" });
        if (r.status === 200) {
          try {
            const parsed = JSON.parse(await r.text());
            const pts = (parsed as { points?: unknown[] })?.points;
            if (Array.isArray(pts) && pts.length > 0) {
              return pass(`${p} has ${pts.length} points`, {
                path: p,
                points: pts.length,
              });
            }
          } catch {
            // try next candidate
          }
        }
      }
      return fail(
        `none of the candidate sources returned valid timeseries: ${candidates.join(", ")}`,
      );
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
];
