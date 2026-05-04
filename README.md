# Legible Markets

A free, link-shareable financial-markets dashboard built for policy folks,
journalists, and curious generalists — not for traders. The premise is that
"levels alone" and "changes alone" each leave half the picture out, so every
chart shows both, with curator notes explaining what to look at.

Live: TBD (Vercel)

<!--
Drop screenshots here when ready. Suggested:
- ![Homepage](docs/screenshots/home.png)
- ![Composer](docs/screenshots/compose.png)
- ![Saved dashboard](docs/screenshots/saved.png)
- ![Expanded chart](docs/screenshots/chart-detail.png)
-->

## What's distinctive

- **Level + change, side by side.** Pick a window (1W / 1M / 1Y / 5Y / 10Y);
  every chart shows current value and the move over that window.
- **Composable dashboards.** Six curated preset dashboards (US macro, oil &
  energy, tech, markets, countries, commodities) plus a drag-to-reorder
  composer where any visitor can pick from 130+ charts (or assemble new ones
  from raw sources), add section commentary, and share via URL.
- **Curator notes layer.** Each chart can carry a plain-language blurb
  explaining what to notice — that's the "legible" part.
- **Auth + saves.** Optional Google sign-in unlocks save-to-account, custom
  URL slugs (`/u/<your-slug>/`), and in-place editing.

## Stack

| Layer | Choice |
| --- | --- |
| Framework | [Astro 5](https://astro.build/) (hybrid: prerender by default, SSR for `/custom/` and `/u/[slug]/`) |
| Charts | [Observable Plot](https://observablehq.com/plot/) + D3 |
| Styling | Tailwind v4 (via `@tailwindcss/vite`) + a small editorial token set |
| Auth + DB | [Supabase](https://supabase.com/) (Postgres + Google OAuth, RLS-gated) |
| Hosting | [Vercel](https://vercel.com/) (`@astrojs/vercel`) |
| Data pipelines | Python (`yfinance`, FRED API, World Bank API) |
| Refresh | GitHub Actions, weekly cron |

## Data lineage

| Source | Used for | Pipeline |
| --- | --- | --- |
| [FRED](https://fred.stlouisfed.org/) (St. Louis Fed) | Rates, inflation, employment, GDP, most US macro | `pipelines/fred_series.py` |
| [Yahoo Finance](https://finance.yahoo.com/) (via `yfinance`) | Equity tickers, ETFs, futures | `pipelines/yahoo_quotes.py`, `pipelines/yahoo_marketcap.py` |
| [World Bank Open Data](https://data.worldbank.org/) | Country GDP shares | `pipelines/worldbank_gdp.py` |
| EIA | Retail fuel prices (selected) | (within `fred_series.py`) |

Every series writes to `public/data/<provider>/<id>.json`, gets committed back
into the repo by the weekly GitHub Actions job, and is served from Vercel's
CDN. **Visitors never call upstream sources** — one IP per provider per week,
not one per visitor per request.

## Repo layout

```
.github/workflows/refresh-data.yml    weekly data refresh
pipelines/                            python data fetchers
public/data/<provider>/<id>.json      cached time series
src/
  components/
    Chart.astro                       chart card + expanded modal
    ChartController.astro             window-pill controller
  content/
    config.ts                         Zod schemas for sources / charts / dashboards
    sources/<provider>/<id>.yaml      data-source manifests
    charts/<topic>/<id>.yaml          chart manifests (1+ sources)
    dashboards/<slug>.mdx             preset dashboard layouts
  layouts/BaseLayout.astro
  lib/
    composer-state.ts                 URL-state schema + base64url codec
    resolve-dashboard.ts              chart/source resolution + supported-window logic
    deltas.ts                         window helpers
    supabase.ts                       client factory + readStoredSession()
    load-data.ts                      filesystem read of cached JSON
  pages/
    index.astro                       landing
    [...slug].astro                   preset dashboards
    compose.astro                     composer (Preact-free vanilla TS)
    custom.astro                      ?d=<state> URL-state viewer (SSR)
    u/[slug].astro                    saved-dashboard viewer (SSR)
    me/index.astro                    profile / saved-dashboard list
    about.astro                       what + who + where
    library.json.ts                   composer's chart manifest
supabase/
  migrations/0001_init.sql            saved_dashboards table + RLS
```

The hierarchy is **Source → Chart → Dashboard.** A *Source* is a single time
series with provider attribution. A *Chart* names one or more sources and
specifies a render mode. A *Dashboard* arranges charts into sections.
Composer-built dashboards are the same shape; saved dashboards live in
Supabase as `state_json`.

## Local development

Requirements: Node 22+ (Vercel pins this), Python 3.13+ for pipelines.

```sh
npm install
npm run dev         # http://localhost:4321/
```

To pull a fresh data snapshot locally:

```sh
python -m pip install yfinance pandas
python pipelines/fred_series.py
python pipelines/yahoo_quotes.py
python pipelines/yahoo_marketcap.py
python pipelines/countries_relative.py
python pipelines/worldbank_gdp.py
```

Pipelines are idempotent and only rewrite their own `public/data/<provider>/`
subdirectory. The Actions workflow runs each step with `continue-on-error` so
one provider rate-limiting us doesn't block the others.

## Environment

For local Supabase-backed features (saves, `/me/`, custom URLs):

```
PUBLIC_SUPABASE_URL=...
PUBLIC_SUPABASE_ANON_KEY=...
```

Both are *publishable* keys — safe in the browser. RLS on `saved_dashboards`
gates writes to owners and reads to public-or-own. The service-role key is
**never** used by this codebase.

## Adding a chart

1. If the data source isn't already cached, add a YAML manifest in
   `src/content/sources/<provider>/<id>.yaml` and extend the relevant pipeline
   to fetch it.
2. Add a chart manifest in `src/content/charts/<topic>/<id>.yaml` referencing
   that source.
3. Add the chart ID to one or more dashboards in
   `src/content/dashboards/<slug>.mdx` (or just leave it in the library — the
   composer will pick it up automatically via `library.json`).

Chart YAML shape:

```yaml
title: Federal funds rate
sources: ["fred/fed_funds"]
render: line          # line | curve | smallMultiples | sparkDelta | deltaGrid | relativeReturns
defaultDelta: 1y      # default time window
tags: [rates, macro]  # used by composer's library filter
blurb: |              # optional curator note shown in the expanded view
  The effective overnight rate the Fed targets through OMO. ...
```

## Saved dashboards

`saved_dashboards` row: `(id, owner_id, slug, title, state_json,
visibility, created_at, updated_at)`. State JSON shape mirrors a strict
subset of the Dashboard content-collection schema, so the same renderer
handles preset, URL-state, and saved dashboards.

Custom URLs: owners can rename their slug from `/me/`. No alias / redirect on
rename — old slugs are freed for re-use, by design.

## License

MIT (TBD — confirm before public). Data carries upstream provider terms;
attribution links live on every chart's expanded view.

## Contact

Built by [Keller Scholl](https://khs.github.io). Notes, corrections, requests:
[keller.scholl@gmail.com](mailto:keller.scholl@gmail.com).
