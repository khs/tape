"""
Compute country-ETF performance relative to a global benchmark (VT).

For each country ETF, produce an indexed timeseries: (country_close / VT_close)
normalized so the value is 100 at the first overlapping date. The *delta* over any
window then reads directly as "country outperformed (or underperformed) VT by X%".

Run AFTER ``yahoo_quotes.py`` has populated ``public/data/yahoo/``.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from common import write_timeseries, DATA_ROOT


BENCHMARK_ID = "VT"
BENCHMARK_NAME = "Vanguard Total World Stock ETF"


@dataclass
class CountrySpec:
    etf_id: str  # yahoo series id (e.g. "EWJ")
    country: str  # human-readable country name


COUNTRIES: list[CountrySpec] = [
    CountrySpec("EWJ", "Japan"),
    CountrySpec("EWG", "Germany"),
    CountrySpec("EWU", "United Kingdom"),
    CountrySpec("EWZ", "Brazil"),
    CountrySpec("FXI", "China"),
    CountrySpec("INDA", "India"),
    CountrySpec("EWC", "Canada"),
    CountrySpec("EWA", "Australia"),
    CountrySpec("EWW", "Mexico"),
    CountrySpec("EWY", "South Korea"),
]


def load_series(pipeline: str, series_id: str) -> dict:
    path = DATA_ROOT / pipeline / f"{series_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    try:
        vt = load_series("yahoo", BENCHMARK_ID)
    except FileNotFoundError:
        print(
            f"Benchmark {BENCHMARK_ID} not found. Run yahoo_quotes.py first.",
            file=sys.stderr,
        )
        return 2

    vt_by_date = {p["t"]: p["v"] for p in vt["points"]}

    for spec in COUNTRIES:
        try:
            etf = load_series("yahoo", spec.etf_id)
        except FileNotFoundError:
            print(f"Missing {spec.etf_id}; skipping.")
            continue

        pairs: list[tuple[str, float]] = []
        for p in etf["points"]:
            vt_v = vt_by_date.get(p["t"])
            if vt_v is None or vt_v <= 0:
                continue
            pairs.append((p["t"], p["v"] / vt_v))

        if not pairs:
            print(f"No overlap between {spec.etf_id} and {BENCHMARK_ID}; skipping.")
            continue

        base = pairs[0][1]
        points = [{"t": t, "v": (v / base) * 100} for t, v in pairs]

        out = write_timeseries(
            pipeline="countries_relative",
            series_id=spec.etf_id,
            name=f"{spec.country} (vs. world)",
            points=points,
            unit="index",
        )
        print(f"  {spec.etf_id} ({spec.country}): {len(points):>6} pts -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
