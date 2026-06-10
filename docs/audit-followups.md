# Codebase audit — follow-ups (2026-06-10)

A full adversarially-verified audit ran on 2026-06-10 (10 dimensions, every
finding refuted-or-confirmed by an independent skeptic; one dimension
re-run after a tooling drop). ~32 raw findings were refuted; 15 confirmed.
This file tracks what shipped and what's deliberately deferred.

## Shipped + verified (CI + post-deploy green)
- **XSS — two classes** (`6076a5842d`): user `blurb` rendered via raw
  `set:html` (→ `renderMarkdown()`), and the `JSON.stringify`-into-`<script>`
  breakout via `</script>` in user titles/blurbs/state (→ `jsonForScript()`
  on all 8 data islands). Both reachable unauth via `/custom?d=`. The 2nd
  class was missed by the audit finders and caught while implementing.
- **Security headers** (`9918c40f3f`, live-verified): global `nosniff` +
  `Referrer-Policy`; `X-Frame-Options: SAMEORIGIN` + CSP `frame-ancestors
  'self'` scoped to `/me /compose /custom /alerts /u` (NOT global — `/embed`
  must stay externally framable; confirmed exempt on prod).
- **Ops/SEO/a11y/tests** (`9918c40f3f`): `/sitemap.xml`→`-index` redirect;
  `/custom` soft-404 (404/400 instead of 200); `aria-hidden` on decorative
  chart SVGs; encode/decode round-trip tests for inlineSources/inlineMaps/
  fixedRange. README naep.py→naep_scores.py (`ac5b718ff0`).
- **BLS metro parity-gate** (`f8ad76bfbb`): `bls_metro.py` now emits a source
  YAML only when its data file exists; deleted 137 data-less orphans that
  rendered blank in the composer. (Was intentional "surface every metro"
  behavior — reversed per the parity philosophy.)

## Deferred — each needs something not available offline
Ordered by value. The blocker is real in every case (this is a 7.4GB laptop:
no `astro build`, no `astro dev`; Chrome MCP currently disconnected).

1. **Full `script-src` Content-Security-Policy** (medium). Only
   `frame-ancestors` shipped. A real CSP must allow the app's inline scripts
   + the data islands + PostHog + Vercel Analytics + Observable Plot, so it
   needs a **preview deploy** to validate without white-screening prod.
   Approach: enable Astro's experimental CSP (auto-hashes hoisted +
   `is:inline` scripts) — needed because there ARE executable inline scripts
   (`chart/[...id].astro:76,206`; `index.astro:232` `define:vars`;
   `me/index.astro:46`; `me/diagnostics.astro:24`) that a bare `'self'` would
   block. Start in `Content-Security-Policy-Report-Only`, watch reports on a
   preview, then enforce. The JSON islands (`type="application/json"` /
   `ld+json`) are NOT script-src concerns (not executed).
   **Candidate policy to deploy-test (origins already inventoried):**
   ```
   default-src 'self';
   script-src 'self' https://us.i.posthog.com 'unsafe-inline';   # replace 'unsafe-inline' with Astro-generated hashes before enforce
   connect-src 'self' https://*.supabase.co wss://*.supabase.co https://us.i.posthog.com;
   style-src 'self' 'unsafe-inline';   # dynamic inline style attributes (banners, ChartMap, Plot)
   img-src 'self' data:;
   font-src 'self';   # @fontsource is bundled
   object-src 'none'; base-uri 'self';
   ```
   (Vercel Analytics serves its script same-origin at `/_vercel/insights/`, so
   `'self'` covers it.)
2. **Focus trap + focus restoration in the composer modals** (medium, a11y).
   cc-modal / ds-modal / signin-prompt in `compose.astro` are `.hidden`-
   toggled `<div role="dialog">` with no Tab-trap and no return-focus on
   close. Pattern to copy: `welcome.astro`'s `popoutLastFocus` save/restore.
   Additive JS, but only truly verifiable with a **keyboard walkthrough** —
   do it when a browser is connected.
3. **`library.json` payload size** (low, perf) — **MEASURED + partly
   addressed 2026-06-10.** Reality: **38.9 MB uncompressed but only ~1.6 MB
   gzip / ~1.1 MB brotli over the wire** — the audit's ">10 MB" was the
   uncompressed figure; real-browser transfer is modest. It's `prerender=true`
   (static), so Vercel ignored the endpoint's own `max-age=300` and served
   `max-age=0, must-revalidate` (revalidated every visit). **Shipped:** a
   `vercel.json` rule edge-caches `/library.json` (`s-maxage=86400` +
   `stale-while-revalidate`); deploys purge it and it's immutable between data
   refreshes, so this is safe and cuts cross-user/repeat origin hits.
   **Residual (not worth the risk):** the real cost is the client `JSON.parse`
   of 38.9 MB. `searchText` duplicates name/description but is ENRICHED
   (hint-level series names, linked-chart source names), so dropping it would
   degrade search — NOT a safe blind trim. A real reduction would mean a
   leaner picker-only manifest (id/name/shortName/tags) with descriptions
   fetched on demand — a bigger redesign, deferred.
4. **Lazy-load Plot/d3** (low, perf). `ChartController`/`ChartMap` import
   `@observablehq/plot` + `d3` (umbrella) at top-of-script on chart-bearing
   pages. Defer via dynamic `import()` on dialog-open; narrow
   `import * as d3 from "d3"` to the 3 symbols used. Needs a **build** to
   confirm no render regression.

## Skipped by choice (info-tier)
- Pipeline `fetch_*` helpers swallow malformed-JSON/empty-200 without a stderr
  WARN — low value (real HTTP 500s already crash loud; the headline was
  refuted), and noisy given legitimate BLS suppression.
- No `aria-live` announcement when a chart silently falls back to its low-fi
  preview — the value/trend is already in the announced descriptor.
- No `/compose` prefetch hint on the welcome page — micro-opt; a blanket
  `library.json` preload would actually regress the welcome page.

## Notes
- The audit's adversarial layer mattered: it refuted a claimed "critical"
  pipeline idempotency bug, downgraded several severities, and caught
  fabricated line citations. Treat raw finder output as a lead, not a fact.
- The BLS "orphan" finding was **intentional** behavior, not a bug — always
  read for an explicit design rationale before acting on an audit finding.

## OWASP Top 10:2025 check (2026-06-10)

Mapped the codebase against https://owasp.org/Top10/2025/ (adversarially
verified, 10 categories). Result: **7 pass, 3 concern, 0 fail** — highest
confirmed severity *low*; 12 findings refuted.

| Category | Posture |
|---|---|
| A01 Broken Access Control | pass (RLS enforces ownership everywhere) |
| A02 Security Misconfiguration | concern (CORS-wildcard + localStorage-token findings were **refuted**; full CSP still deferred) |
| A03 Software Supply Chain | pass |
| A04 Cryptographic Failures | pass |
| A05 Injection | pass (XSS classes fixed; email-CRLF finding refuted) |
| A06 Insecure Design | pass (RLS + rate limits + owner-bound alerts) |
| A07 Authentication Failures | pass |
| A08 Software/Data Integrity | pass |
| A09 Logging & Alerting | concern → **partly fixed** |
| A10 Exceptional Conditions | concern → **partly fixed** |

**Key insight:** security rests almost entirely on Supabase RLS as the one
load-bearing control — sound, but with no compensating *visibility*. If RLS
or the single admin account were compromised, nothing would surface it.

**Shipped from this check:**
- A09 — `/api/diagnostic` now logs all auth/authz refusals + the authorized
  admin action server-side (Vercel function logs), closing the audit blind
  spot on the app's one privileged endpoint.
- A10 — `alerts.astro` init now uses `Promise.allSettled` + an error banner
  so a failed data load can't leave the form rendered-but-dead.

**Remaining OWASP-adjacent (folded into the deferred list above):** full
`script-src` CSP (the A02 defense-in-depth gap; needs a preview deploy).
Optional hardening, not confirmed findings: tighten any non-wildcard CORS if
introduced later; sanitize `source_label` newlines before email interpolation
(belt-and-suspenders over Resend/Postmark's own validation).
