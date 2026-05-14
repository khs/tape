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
