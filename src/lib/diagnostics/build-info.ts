/**
 * Build / environment diagnostic tests.
 *
 * These all run synchronously from the browser, reading values baked
 * into the client bundle at build time (PUBLIC_* env vars set in
 * astro.config.mjs) and a couple of constants from src/lib/brand.ts.
 *
 * Purpose: when the admin pastes back a diagnostic, the first thing
 * I need to know is "which build of which deployment am I looking
 * at?" — these tests put that at the top of the report so I don't
 * have to play guess-the-commit.
 */
import { SITE_BRAND_NAME, SITE_BRAND_URL } from "../brand";
import {
  fail,
  pass,
  warn,
  type DiagnosticTest,
} from "../diagnostic-runner";

/**
 * Snapshot of the build constants exposed to client code. Pulled
 * once at module init so every test below uses a consistent view
 * (otherwise a test that mutated process.env mid-suite would skew
 * subsequent reads).
 */
function buildInfo(): {
  sha: string;
  env: string;
  buildTime: string;
} {
  return {
    sha: import.meta.env.PUBLIC_BUILD_SHA ?? "unknown",
    env: import.meta.env.PUBLIC_BUILD_ENV ?? "unknown",
    buildTime: import.meta.env.PUBLIC_BUILD_TIME ?? "unknown",
  };
}

export const buildInfoTests: DiagnosticTest[] = [
  {
    id: "build/sha-present",
    category: "build",
    label: "build SHA was baked into bundle",
    run: () => {
      const { sha } = buildInfo();
      if (sha === "unknown") {
        return warn(
          "PUBLIC_BUILD_SHA not set — diagnostic report will show 'unknown' for the commit. Set VERCEL_GIT_COMMIT_SHA in Vercel env (auto-populated in production).",
        );
      }
      if (sha === "dev") {
        return warn("running a local dev build (sha='dev')");
      }
      // Vercel ships full-length SHAs; sanity check the shape.
      if (!/^[0-9a-f]{7,40}$/.test(sha)) {
        return fail(`PUBLIC_BUILD_SHA doesn't look like a git SHA: ${sha}`);
      }
      return pass(`sha=${sha.slice(0, 7)}`, { sha });
    },
  },
  {
    id: "build/env-present",
    category: "build",
    label: "VERCEL_ENV captured",
    run: () => {
      const { env } = buildInfo();
      if (env === "production") return pass("production");
      if (env === "preview" || env === "development") {
        return warn(`env=${env} (not production)`, { env });
      }
      return warn("VERCEL_ENV not set");
    },
  },
  {
    id: "build/time-recent",
    category: "build",
    label: "build timestamp recent",
    run: () => {
      const { buildTime } = buildInfo();
      if (buildTime === "unknown") return warn("no build time recorded");
      const t = Date.parse(buildTime);
      if (Number.isNaN(t)) return fail(`unparseable build time: ${buildTime}`);
      const ageDays = (Date.now() - t) / (1000 * 60 * 60 * 24);
      if (ageDays > 30) {
        return warn(`build is ${ageDays.toFixed(1)} days old`, {
          buildTime,
          ageDays,
        });
      }
      return pass(`${ageDays.toFixed(1)}d old`, { buildTime, ageDays });
    },
  },
  {
    id: "build/host-matches-known-deployment",
    category: "build",
    label: "host is a known Tape deployment",
    run: () => {
      if (typeof window === "undefined") return warn("no window");
      const host = window.location.host;
      const known = [
        "legible-markets.vercel.app",
        "tape.io",
        "localhost",
        "127.0.0.1",
      ];
      const isKnown = known.some((k) => host === k || host.startsWith(k));
      if (!isKnown) {
        return warn(`unrecognized host: ${host}`, { host });
      }
      return pass(host, { host });
    },
  },
  {
    id: "build/brand-constants-defined",
    category: "build",
    label: "brand constants are populated",
    run: () => {
      if (!SITE_BRAND_NAME) return fail("SITE_BRAND_NAME is empty");
      if (!SITE_BRAND_URL) return fail("SITE_BRAND_URL is empty");
      return pass(`${SITE_BRAND_NAME} / ${SITE_BRAND_URL}`, {
        name: SITE_BRAND_NAME,
        url: SITE_BRAND_URL,
      });
    },
  },
  {
    id: "build/supabase-configured",
    category: "build",
    label: "Supabase public env vars present",
    run: () => {
      const hasUrl = !!import.meta.env.PUBLIC_SUPABASE_URL;
      const hasKey = !!import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
      if (!hasUrl || !hasKey) {
        return fail(
          `Supabase env missing (url=${hasUrl}, anonKey=${hasKey}). /me/ and saved-dashboard features will be disabled.`,
        );
      }
      return pass("URL + anon key both present");
    },
  },
];
