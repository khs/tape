# URL migration checklist

When the production URL changes — whether that's renaming the Vercel
project (`legible-markets` → `tape`), buying a custom domain (`tape.io`
or anything else), or both — these are the places that need to flip
in lockstep. Forgetting any of them will silently break post-deploy
diagnostics, search-engine indexing, or test fixtures.

## Current state (as of 2026-05-28)

| Surface | Current value | Owns the canonical URL string? |
| --- | --- | --- |
| GitHub repo | `khs/tape` | n/a — name only |
| Folder on Keller's machine | `FinanceForDC/` | n/a — load-bearing in scripts, do NOT rename |
| Brand display name | "Tape" (via `SITE_BRAND_NAME` in `src/lib/brand.ts`) | n/a — display only |
| Brand display URL | "tape.io" (via `SITE_BRAND_URL` in `src/lib/brand.ts`) | **Aspirational** — tape.io not registered |
| Vercel project name | `legible-markets` | n/a — name only |
| Vercel public domain | `legible-markets.vercel.app` | **Yes — this is the live URL** |

The cross-cutting decision: changing the Vercel project name flips
the public domain to `tape.vercel.app`, which is independent of
whether you buy `tape.io`. Don't do the project rename until you
know which public URL you actually want as the deploy target — if
you're going to buy `tape.io`, the project rename matters less
because the custom domain wins anyway.

## Load-bearing — must flip together

These 5 files contain hardcoded production-URL strings that the CI
or crawlers read at runtime. Bad value here = silent failure mode.

1. **`.github/workflows/post-deploy-diagnostic.yml`** — `workflow_dispatch.inputs.url.default` (around line 38) AND `PROD_URL=` in the "Resolve URL to diagnose" step.

2. **`.github/workflows/post-deploy-smoke.yml`** — `workflow_dispatch.inputs.url.default` AND `PROD_URL=` in the "Resolve URL to test" step.

3. **`public/robots.txt`** — `Sitemap: https://<url>/sitemap-index.xml`. Pointing this at a wrong domain misdirects search crawlers; pointing at one that 404s `/sitemap-index.xml` causes zero indexing.

4. **`src/lib/brand.ts`** — `SITE_BRAND_URL`. The string that renders in chart watermarks + OG cards + the about page. Changing the deploy URL is independent of this, but they should usually move together.

5. **Vercel project itself** — the canonical thing. If renamed in the Vercel dashboard, the new `*.vercel.app` URL becomes the live one and the old one starts 404'ing (Vercel doesn't preserve old project URLs).

## Non-load-bearing — update for cleanliness but no runtime impact

These contain stale URL strings in comments / examples / test
fixtures. Safe to leave behind on a single coordinated change;
clean up next time you're touching the file anyway.

- `astro.config.mjs` — comment on line 16 about `VERCEL_URL`.
- `docs/perf-baselines.md` — historical curl example.
- `scripts/run-deploy-diagnostic.mjs` — `Usage:` comment example.
- `src/lib/load-data.test.ts` — `VERCEL_PROJECT_PRODUCTION_URL` test fixture (2 occurrences).

## Verification after a URL change

1. Run the smoke test against the new URL via `workflow_dispatch` from the Actions tab. Should pass.
2. Run the diagnostic the same way. Should be 16/16.
3. Submit the new `/sitemap-index.xml` to Google Search Console.
4. Visit `https://<old-url>/` and confirm it either redirects or returns a graceful message — don't leave stale-domain links circulating.

## History

- **2026-05-28**: Discovered the diagnostic + smoke + robots.txt were prematurely flipped to `tape.vercel.app` in anticipation of a Vercel project rename that never landed. The site was actually serving from `legible-markets.vercel.app`, so the diagnostic failed 15/16 (only `/` passed because `tape.vercel.app` returns a Vercel "domain not configured" placeholder for the root). Reverted all three to `legible-markets.vercel.app` and documented this checklist.
