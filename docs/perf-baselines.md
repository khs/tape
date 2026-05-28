# Performance baselines

Synthetic measurements against prod, recorded at the boundary of each
performance-affecting change so we have a fixed reference point to
compare against later. Captured with:

```bash
for path in / /us-macro/ /tech/ /stocks/ /countries/ /va-08/; do
  curl -sS --max-time 30 -o /tmp/page.html \
    -w "%{time_total},%{size_download}\n" \
    "https://legible-markets.vercel.app$path"
done
```

## 2026-05-14 — before Phase 2 (tile-payload refactor)

| Path | Total HTML | `data-chart-payload` text | Tiles | Per-tile avg |
|---|---:|---:|---:|---:|
| `/` | 2.86 MB | 2.69 MB | 32 | ~84 KB |
| `/us-macro/` | 2.86 MB | 2.69 MB | 32 | ~84 KB |
| `/stocks/` | 3.42 MB | 3.27 MB | 30 | ~109 KB |
| `/tech/` | 999 KB | 944 KB | 8 | ~118 KB |
| `/countries/` | 2.42 MB | 2.33 MB | 10 | ~233 KB |
| `/va-08/` | 185 KB | 94 KB | 10 | ~9 KB |

94–96% of the HTML on the busiest dashboards is the inline
`data-chart-payload` script blocks (full timeseries shipped per tile).
Per-tile cost ranges from ~9 KB (sparse ACS) to ~233 KB (long-history
country ETF time series), depending on how many points the source's
longest supportedDelta covers.

`/va-08/` is the only existing dashboard that doesn't ship full data
inline today — its sources are ACS demographics with very few points
per series. Useful as a control case.

Median first-byte time across three measurements ranged from ~0.13s
(/va-08/) to ~0.9s (/countries/). HTML parse cost on the client
scales with payload size; LCP isn't captured here yet (would need
client-side Navigation Timing telemetry).

## 2026-05-14 — after Phase 2 (tile-payload refactor, commit 99edf50e)

| Path | Total HTML | `data-chart-payload` text | Tiles | Δ total | Δ payload |
|---|---:|---:|---:|---:|---:|
| `/` | 346 KB | 183 KB | 32 | **8.3× smaller** | **14.7× smaller** |
| `/us-macro/` | 352 KB | 183 KB | 32 | **8.1×** | **14.7×** |
| `/stocks/` | 440 KB | 289 KB | 30 | **7.8×** | **11.3×** |
| `/tech/` | 151 KB | 95 KB | 8 | **6.6×** | **9.9×** |
| `/countries/` | 358 KB | 270 KB | 10 | **6.8×** | **8.6×** |
| `/va-08/` | 173 KB | 82 KB | 10 | **1.1×** | **1.1×** |

Total across all six dashboards: 12.74 MB → 1.82 MB (~**7× aggregate
reduction** in delivered HTML).

Median first-byte time fell roughly proportionally: 0.5–0.9s → 0.13–0.30s
on the busiest dashboards. Server-side render is faster too because the
function reads ~5KB summaries instead of ~50KB full series per source.

`/va-08/` barely moved because (a) its data series are small to begin
with and (b) it leans on derived `acs_cd/*` sources that don't have
.summary.json siblings, so they still ship via the full-data inline
path. Expected behavior.

The lazy-fetch on dialog open hydrates the full `<id>.json` from the
static-asset origin. Telemetry events `chart_expanded.lazy_fetch_ms`
and `dashboard_perf_loaded.payload_bytes` carry the real-user numbers
to PostHog for ongoing visibility.
