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

1. **Full `script-src` Content-Security-Policy** (medium) — **ENFORCED + live
   (verified 2026-06-11).** `vercel.json` ships an *enforcing*
   `Content-Security-Policy` header globally (not Report-Only): `default-src
   'self'; script-src 'self' 'unsafe-inline' https://us.i.posthog.com; …
   object-src 'none'; base-uri 'self'`. The connect/img/object/base
   restrictions (exfil containment) are fully enforced. **Remaining upgrade
   (optional, lower-value):** drop `'unsafe-inline'` from `script-src` by
   hashing/nonce-ing inline scripts — the only way CSP would actually block
   inline-script injection. It's defense-in-depth only (the XSS sinks are
   already fixed), and the clean path is Astro's experimental CSP
   auto-hashing — but that needs a *verifiable* build (this 7.4GB laptop
   can't `astro build`), so it's a deliberate, CI-gated follow-up rather than
   a blind flip. Historical note: a `Content-Security-Policy-Report-Only`
   header shipped first (commit 86f5a6e04b) and was later promoted to
   enforcing with `'unsafe-inline'`.
   ```
   default-src 'self'; script-src 'self' 'unsafe-inline' https://us.i.posthog.com;
   style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:;
   connect-src 'self' https://*.supabase.co wss://*.supabase.co https://us.i.posthog.com https://us-assets.i.posthog.com;
   object-src 'none'; base-uri 'self'
   ```
   Report-Only NEVER blocks (safe on prod); it surfaces violations in the
   browser console. **To enforce:** read the live console violations across the
   key pages (home / compose / custom / alerts / a dashboard / source / me) —
   they reveal which `is:inline` scripts need hashing (`chart/[...id].astro:76,
   206`; `index.astro:232` `define:vars`; `me/index.astro:46`;
   `me/diagnostics.astro:24`) and any origin beyond the inventoried PostHog/
   Supabase. Then either enable Astro's experimental CSP (auto-hashes inline
   scripts — the clean path) or enforce with `script-src … 'unsafe-inline'`
   (pragmatic, weaker — defense-in-depth only, the XSS sinks are already fixed),
   flip the header name to `Content-Security-Policy`, and remove the RO one.
   (The browser console read was blocked this session by an unstable Chrome
   extension freezing on the heavy /compose page — retry when it's stable.)
2. **Focus trap + focus restoration in the composer modals** (medium, a11y) —
   **SHIPPED 2026-06-10 (commit 1ef08b2011); keyboard re-verify pending.**
   `wireModalFocusTraps()` in `compose.astro`: a stateless installer that
   observes each `.cc-modal-backdrop`'s `hidden` toggle (save/restore trigger
   focus) + one document Tab handler that wraps focus at the modal's
   first/last focusable. astro check 0/0/0; the post-deploy diagnostic (which
   boots the composer) passed, so it runs without error — but the keyboard
   BEHAVIOR (Tab-wrap + focus-restore) wasn't runtime-verified because the
   Chrome extension froze on /compose this session. Re-verify with a keyboard
   walkthrough (or the synthetic-Tab eval in the transcript) when the browser
   is stable. Design is additive/can't-break-modals, so it's low-risk shipped.
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
4. **Lazy-load Plot/d3** (low, perf) — **DISSOLVED on inspection 2026-06-10
   (no change made).** The finding's premise didn't survive the code: (a)
   `ChartMap` already uses *named* d3 imports (`import { select, zoom,
   zoomIdentity } from "d3"`) which Vite/Rollup tree-shake — there is no
   `import * as d3` umbrella to narrow (the lone `d3.geoAlbers` is in a code
   comment); (b) `@observablehq/plot` is needed AT LOAD for the tile
   sparklines (not just dialog-open), so deferring it via dynamic `import()`
   would break the tiles — the naive fix is a regression; (c) Astro already
   ships each component's `<script>` only on pages that render it, so map-free
   pages don't pay the topojson/d3 cost. Net: already handled; nothing safe to
   change. (Same lesson as the BLS finding — read for the real shape first.)

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

**Shipped from this follow-up (2026-06-10):**
- A05 email-header hardening — `dispatch_alert_emails.py` `_one_line()` strips
  CR/LF + control chars from `source_label` before the Subject/bodies (commit
  86f5a6e04b; +2 tests). Belt-and-suspenders over Resend/Postmark validation.
- A02 CSP Report-Only probe — see deferred item 1 (now Report-Only-live;
  enforce pending a stable browser read).

**Still optional / not confirmed findings:** tighten any non-wildcard CORS if
one is ever introduced. The CSP *enforce* step is the only remaining
OWASP-adjacent item of substance.
