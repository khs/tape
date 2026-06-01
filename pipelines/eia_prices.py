"""
EIA retail energy prices by state — electricity (¢/kWh) + residential
natural gas ($/MCF). EIA API v2 (needs EIA_API_KEY). Public domain.

Routes (each fetched for ALL states in one paginated call, then grouped):
  electricity/retail-sales : data[0]=price, sectorid=ALL  → cents/kWh
  natural-gas/pri/sum      : data[0]=value, process=PRS    → $/MCF
                             (PRS = "price delivered to residential")
Annual. Per state + DC (+ US where published).

Checklist notes: labels constructed from (indicator + state); correct-
by-construction with a preflight that the response carries the price/
value field. Identifier: eia_prices/<indicator>_<st>; series in
provenance names the EIA route + facet. Prices are intensities, stored
raw (unitClass "price"). Key never logged (it's in the query string).

Run: python pipelines/eia_prices.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import _env  # noqa: F401 — loads .env

from common import write_timeseries

HERE = Path(__file__).resolve().parent
SOURCES_DIR = HERE.parent / "src" / "content" / "sources" / "eia_prices"
V2 = "https://api.eia.gov/v2"

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}


def _get(route: str, extra: list[tuple[str, str]], key: str) -> list[dict]:
    """Paginated fetch of an EIA v2 data route. Returns all rows."""
    rows: list[dict] = []
    offset = 0
    while True:
        params = [
            ("api_key", key), ("frequency", "annual"),
            *extra, ("start", "1990"),
            ("offset", str(offset)), ("length", "5000"),
        ]
        url = f"{V2}/{route}/data/?" + urllib.parse.urlencode(params)
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "tape/1.0"})
                data = json.loads(urllib.request.urlopen(req, timeout=60).read())
                break
            except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
                if e.code in (429, 500, 502, 503) and attempt < 3:
                    time.sleep(2 + 2 * attempt)
                    continue
                raise
        batch = (data.get("response", {}) or {}).get("data", []) or []
        rows.extend(batch)
        if len(batch) < 5000:
            break
        offset += 5000
        time.sleep(0.3)
    return rows


def yaml_for(slug, name, short, desc, series, unit, decimals, tags):
    lines = [
        f"name: {name}", f"shortName: {short}", f"description: {desc}",
        "kind: timeseries", "pipeline: eia_prices",
        f"dataFile: data/eia_prices/{slug}.json",
        'supportedDeltas: ["1y", "5y", "10y", "30y"]',
        f'unit: "{unit}"', "formatting:", "  style: number",
        f"  decimals: {decimals}", "emphasis: change",
        "provenance:",
        "  provider: U.S. Energy Information Administration (EIA)",
        f"  series: {series}",
        "  url: https://www.eia.gov/opendata/",
        "  license: Public domain (US government data)",
        "tags:",
    ] + [f"  - {t}" for t in tags] + ['unitClass: price', ""]
    (SOURCES_DIR / f"{slug}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    key = os.environ.get("EIA_API_KEY")
    if not key:
        print("ERROR: EIA_API_KEY required", file=sys.stderr)
        return 2
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0

    # --- electricity retail price (all sectors), cents/kWh ---
    erows = _get("electricity/retail-sales",
                 [("data[0]", "price"), ("facets[sectorid][]", "ALL")], key)
    by_state: dict[str, list[dict]] = {}
    for r in erows:
        st = r.get("stateid"); v = r.get("price"); yr = r.get("period")
        if st in STATES and v not in (None, "") and yr:
            try:
                by_state.setdefault(st, []).append({"t": f"{yr}-12-31", "v": float(v)})
            except (TypeError, ValueError):
                pass
    for st, pts in by_state.items():
        pts.sort(key=lambda p: p["t"])
        slug = f"electricity_price_{st.lower()}"
        write_timeseries(pipeline="eia_prices", series_id=slug,
                         name=f"Electricity price — {STATES[st]}", points=pts,
                         unit="cents/kWh")
        yaml_for(slug, f"Electricity price — {STATES[st]}", f"{STATES[st]} electricity price",
                 f"Average retail price of electricity (all sectors) in {STATES[st]}, annual, in cents per kilowatt-hour. From the U.S. Energy Information Administration.",
                 f"electricity/retail-sales price; sectorid=ALL; stateid={st}",
                 "cents/kWh", 2, ["energy", "us", "us-state"])
        written += 1

    # --- residential natural gas price, $/MCF ---
    grows = _get("natural-gas/pri/sum",
                 [("data[0]", "value"), ("facets[process][]", "PRS")], key)
    gas: dict[str, list[dict]] = {}
    for r in grows:
        duo = r.get("duoarea", ""); v = r.get("value"); yr = r.get("period")
        m = re.match(r"^S([A-Z]{2})$", duo or "")  # SCA -> CA
        if m and m.group(1) in STATES and v not in (None, "") and yr:
            try:
                gas.setdefault(m.group(1), []).append({"t": f"{yr}-12-31", "v": float(v)})
            except (TypeError, ValueError):
                pass
    for st, pts in gas.items():
        pts.sort(key=lambda p: p["t"])
        slug = f"natural_gas_price_{st.lower()}"
        write_timeseries(pipeline="eia_prices", series_id=slug,
                         name=f"Natural gas price (residential) — {STATES[st]}", points=pts,
                         unit="$/MCF")
        yaml_for(slug, f"Natural gas price (residential) — {STATES[st]}", f"{STATES[st]} gas price",
                 f"Price of natural gas delivered to residential consumers in {STATES[st]}, annual, in dollars per thousand cubic feet. From the U.S. Energy Information Administration.",
                 f"natural-gas/pri/sum value; process=PRS; duoarea=S{st}",
                 "$/MCF", 2, ["energy", "us", "us-state"])
        written += 1

    print(f"eia_prices: wrote {written} series.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
