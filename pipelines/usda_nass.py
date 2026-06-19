"""USDA NASS QuickStats — state + national crop yield, quantity, and price.

QuickStats (https://quickstats.nass.usda.gov/api) is USDA's survey
agricultural database. We pull the major field crops (corn, soybeans, wheat)
at NATIONAL + STATE level. (County-level is deliberately out of scope — it's
~11k series and NASS has been discontinuing county estimates, e.g. county
wheat ended ~2008.)

Three series per (crop, geography):
  - YIELD          BU / ACRE   (per HARVESTED acre; rate)
  - PRODUCTION     BU          (physical quantity; count, raw)
  - PRICE RECEIVED USD / bu    (marketing-year average price; unitClass unset)

We deliberately DON'T store production VALUE ($) — it's price × quantity, so
the composer derives it on demand via the multiply op (and divide recovers
quantity). Storing price + quantity instead of value + quantity removes the
redundancy while keeping value one combine away. Verified the identity holds:
NASS's own "PRODUCTION, MEASURED IN $" = marketing-year price × quantity
(corn 2023: $4.55/bu × 15.34e9 bu ≈ $70e9).

Why price has no unitClass: the composer's multiply treats unitClass "rate"
as a percent (×100, so it applies a 0.01 factor) and "currency" as
billions-denominated — both wrong for a $/bu price. Leaving it unset routes
price × quantity through the general-multiply path (raw product), which is
the correct value. See src/lib/derive.ts combineOpFormatting.

New-data-source checklist (docs/new-data-source-checklist.md)
-------------------------------------------------------------
1. Authoritative label: each row's ``short_desc`` (stored verbatim in
   ``provenance.series``), e.g. "CORN, GRAIN - PRICE RECEIVED, MEASURED IN
   $ / BU".
2. Identifier: synthesized ``<commodity>_<seriestype>_<geo>`` (geo = "us" or
   state alpha); ambiguous dims pinned in _FIXED.
3. Auth: NASS_API_KEY (.env + GitHub Secrets; free at the API page). api_GET
   caps at 50,000 rows; state+national queries are well under, no chunking.
4. License: public domain (US government work). Product-level NASS disclaimer
   lives once on the About page (not per chart).

Reference periods differ by statistic: YIELD/PRODUCTION use "YEAR" (final
annual), PRICE RECEIVED uses "MARKETING YEAR" (the season-average price that
reconciles with value). Suppressed values "(D)"/"(Z)"/... are skipped.

Run:
  python pipelines/usda_nass.py --counts   # get_counts preflight
  python pipelines/usda_nass.py            # fetch + write data + YAMLs
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import _env  # noqa: F401  (loads .env → NASS_API_KEY)

from common import cached_get, write_timeseries

PIPELINE = "usda_nass"
REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_DIR = REPO_ROOT / "src" / "content" / "sources" / PIPELINE

API_BASE = "https://quickstats.nass.usda.gov/api"
API_KEY = os.environ.get("NASS_API_KEY", "")
START_YEAR = 1950
AGG_LEVELS = ["NATIONAL", "STATE"]

# Pin the ambiguous dimensions so a (commodity, stat, geo, year, unit) maps to
# one row. reference_period_desc is NOT pinned here — it varies by statistic
# (see STATS).
_FIXED = {
    "source_desc": "SURVEY",
    "prodn_practice_desc": "ALL PRODUCTION PRACTICES",
    "util_practice_desc": "ALL UTILIZATION PRACTICES",
    "class_desc": "ALL CLASSES",
    "domain_desc": "TOTAL",
    "freq_desc": "ANNUAL",
}


@dataclass
class Stat:
    statisticcat: str       # QuickStats statisticcat_desc
    reference_period: str   # "YEAR" | "MARKETING YEAR"


STATS = [
    Stat("YIELD", "YEAR"),
    Stat("PRODUCTION", "YEAR"),
    Stat("PRICE RECEIVED", "MARKETING YEAR"),
]


@dataclass
class Commodity:
    commodity: str       # QuickStats commodity_desc
    label: str           # display, e.g. "Corn"
    extra_params: dict   # per-commodity dimension overrides


CATALOG: list[Commodity] = [
    # Corn yield/production/price split GRAIN vs SILAGE with no ALL-UTIL
    # rollup — pin GRAIN (the preflight returns 0 rows otherwise).
    Commodity("CORN", "Corn", {"util_practice_desc": "GRAIN"}),
    Commodity("SOYBEANS", "Soybeans", {}),
    Commodity("WHEAT", "Wheat", {}),
]


@dataclass
class SeriesType:
    key: str
    label: str
    unit_class: str      # "" → omit unitClass (e.g. price; see module docstring)
    unit_out: str
    decimals: int
    notation: str | None
    style: str


def classify(statisticcat: str, unit_desc: str) -> SeriesType | None:
    """Route a row to an output series type by (statistic, unit), or None to
    skip. PRODUCTION's "$" (value) variant is intentionally dropped — value is
    derived as price × quantity in the composer."""
    u = (unit_desc or "").strip()
    if statisticcat == "YIELD":
        # Keep the per-HARVESTED-acre standard ("BU / ACRE"); skip the
        # "BU / NET PLANTED ACRE" variant and any $-denominated yield so one
        # yield series isn't a silent mix of bases.
        if "$" in u or "PLANTED" in u.upper():
            return None
        return SeriesType("yield", "yield", "rate", u, 1, None, "number")
    if statisticcat == "PRODUCTION":
        if u == "$":
            return None  # value = price × quantity, derived (not stored)
        return SeriesType("production", "production", "count", u, 0, "compact", "number")
    if statisticcat == "PRICE RECEIVED":
        if "/" not in u:
            return None
        denom = u.split("/")[-1].strip().lower()  # "$ / BU" → "bu"
        # unitClass "price" = currency-per-unit, stored raw. Lets the
        # composer's multiply render price × quantity as a $-value (see
        # src/lib/derive.ts combineOpFormatting) without the billions
        # invariant or the rate×count 0.01 factor.
        return SeriesType("price", "price", "price", f"USD / {denom}", 2, None, "currency")
    return None


def _num(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s.startswith("("):  # (D),(Z),(NA),(X),(S)
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _slug(s: str) -> str:
    out = "".join(ch if ch.isalnum() else "_" for ch in s.lower())
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


def _api(endpoint: str, params: dict) -> dict:
    q = {"key": API_KEY, "format": "JSON", **params}
    body = cached_get(f"{API_BASE}/{endpoint}", ttl_seconds=14 * 24 * 3600, params=q)
    return json.loads(body)


def _query(commodity: Commodity, stat: Stat, agg: str) -> dict:
    return {"commodity_desc": commodity.commodity, "statisticcat_desc": stat.statisticcat,
            "agg_level_desc": agg, "reference_period_desc": stat.reference_period,
            "year__GE": str(START_YEAR), **_FIXED, **commodity.extra_params}


def get_count(commodity: Commodity, stat: Stat, agg: str) -> int:
    try:
        return int(_api("get_counts", _query(commodity, stat, agg)).get("count", 0))
    except Exception as e:  # noqa: BLE001
        print(f"  count failed {commodity.commodity}/{stat.statisticcat}/{agg}: {e}",
              file=sys.stderr)
        return -1


def preflight() -> None:
    if not API_KEY:
        print("NASS_API_KEY not set — add to .env.", file=sys.stderr)
        return
    total = 0
    print(f"{'commodity':10}{'stat':16}{'natl':>6}{'state':>7}")
    for c in CATALOG:
        for s in STATS:
            n_, st = get_count(c, s, "NATIONAL"), get_count(c, s, "STATE")
            total += max(n_, 0) + max(st, 0)
            print(f"{c.commodity:10}{s.statisticcat:16}{n_:>6}{st:>7}")
    print(f"\nTOTAL rows (>= {START_YEAR}): {total:,}")


def fetch_rows(commodity: Commodity, stat: Stat, agg: str) -> list[dict]:
    return _api("api_GET", _query(commodity, stat, agg)).get("data", [])


def _yaml_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def write_yaml(sid: str, name: str, short_name: str, description: str,
               geo_key: str, st: SeriesType, short_desc: str,
               combine: dict | None = None) -> None:
    YAML_DIR.mkdir(parents=True, exist_ok=True)
    tags = ["agriculture"]
    if geo_key != "us":
        tags.append("us-state")
    tags.append("us")
    lines = [
        f"name: {_yaml_str(name)}",
        f"shortName: {_yaml_str(short_name)}",
        f"description: {_yaml_str(description)}",
        "kind: timeseries",
        f"pipeline: {PIPELINE}",
        f"dataFile: data/{PIPELINE}/{sid}.json",
        'supportedDeltas: ["1y", "5y", "10y", "30y", "50y"]',
        f'unit: "{st.unit_out}"',
        "emphasis: change",
        "formatting:",
        f"  style: {st.style}",
        f"  decimals: {st.decimals}",
    ]
    if st.notation:
        lines.append(f"  notation: {st.notation}")
    lines += [
        "provenance:",
        "  provider: USDA National Agricultural Statistics Service (NASS)",
        f"  series: {_yaml_str(short_desc)}",
        "  url: https://quickstats.nass.usda.gov/",
        "  license: Public domain (US government data)",
        "tags:",
        *[f"  - {t}" for t in tags],
    ]
    if st.unit_class:
        lines.append(f"unitClass: {st.unit_class}")
    if combine:
        lines += [
            "combineHint:",
            f"  partner: {combine['partner']}",
            f"  op: {combine['op']}",
            f"  resultLabel: {_yaml_str(combine['resultLabel'])}",
        ]
    lines.append("")
    (YAML_DIR / f"{sid}.yaml").write_text("\n".join(lines), encoding="utf-8")


def build() -> int:
    series: dict[str, dict] = {}
    dups = 0
    for c in CATALOG:
        for stat in STATS:
            for agg in AGG_LEVELS:
                for r in fetch_rows(c, stat, agg):
                    st = classify(stat.statisticcat, r.get("unit_desc", ""))
                    if st is None:
                        continue
                    val = _num(r.get("Value"))
                    yr = str(r.get("year") or "").strip()
                    if val is None or not yr.isdigit():
                        continue
                    if agg == "NATIONAL":
                        geo_key, geo_name = "us", "United States"
                    else:
                        alpha = (r.get("state_alpha") or "").strip().lower()
                        geo_name = (r.get("state_name") or "").strip().title()
                        if not alpha or not geo_name:
                            continue
                        geo_key = alpha
                    sid = f"{_slug(c.label)}_{st.key}_{geo_key}"
                    rec = series.setdefault(sid, {
                        "commodity": c, "st": st, "geo_key": geo_key,
                        "geo_name": geo_name, "short_desc": r.get("short_desc", ""),
                        "points": {},
                    })
                    y = int(yr)
                    if y in rec["points"]:
                        dups += 1
                    rec["points"][y] = round(val, 2 if st.key == "price" else 1)

    n = 0
    for sid, rec in series.items():
        pts = [{"t": f"{y}-12-31", "v": v} for y, v in sorted(rec["points"].items())]
        if len(pts) < 2:
            continue
        c, st, geo_name = rec["commodity"], rec["st"], rec["geo_name"]
        name = f"{c.label} {st.label} — {geo_name}"
        short_name = f"{geo_name} {c.label.lower()} {st.label}"
        if st.key == "price":
            desc = (f"{c.label} price received for {geo_name} ({st.unit_out}, "
                    f"marketing-year average), annual. USDA National Agricultural "
                    f"Statistics Service (QuickStats survey).")
        else:
            desc = (f"{c.label} {st.label} for {geo_name} (in {st.unit_out}), annual. "
                    f"USDA National Agricultural Statistics Service (QuickStats survey).")
        # "Other States" (geo_key "ot") is NASS's residual aggregate for states
        # it doesn't publish individually — it isn't one state, so it can't be
        # placed under the state picker chip (it lands in the library manifest's
        # `misc` bucket, allowlisted). Note WHICH states ARE reported separately
        # for this crop+stat so the aggregate is interpretable + it's clear what
        # "Other" excludes. Derived from the sibling series we just built.
        if rec["geo_key"] == "ot":
            prefix = f"{_slug(c.label)}_{st.key}_"
            indiv = sorted(
                series[k]["geo_key"].upper()
                for k in series
                if k.startswith(prefix) and series[k]["geo_key"] not in ("ot", "us")
            )
            if indiv:
                desc += (
                    " Other States is the USDA NASS residual for states not "
                    f"published individually; the {len(indiv)} reported separately "
                    f"in this dataset are " + ", ".join(indiv) + "."
                )
        # combineHint: link price <-> production for the same crop+geo so
        # the composer can offer "price × quantity → production value" (and
        # vice-versa) as a one-click chip. Only when the partner exists with
        # enough history to plot.
        combine = None
        if st.key in ("price", "production"):
            other = "production" if st.key == "price" else "price"
            partner = sid.replace(f"_{st.key}_", f"_{other}_", 1)
            pr = series.get(partner)
            if pr and len(pr["points"]) >= 2:
                combine = {
                    "partner": f"{PIPELINE}/{partner}",
                    "op": "multiply",
                    "resultLabel": f"{c.label} production value — {geo_name}",
                }
        write_timeseries(PIPELINE, sid, name, pts, unit=st.unit_out, merge=False)
        write_yaml(sid, name, short_name, desc, rec["geo_key"], st,
                   rec["short_desc"], combine=combine)
        n += 1
    print(f"[usda_nass] wrote {n} series (+ YAMLs); {dups} duplicate "
          f"(geo,year) rows collapsed.")
    if n == 0:
        print("  nothing written — check NASS_API_KEY / network.", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = (argv or [])[1:]
    if "--counts" in args:
        preflight()
        return 0
    if not API_KEY:
        print("NASS_API_KEY not set — add to .env, then re-run.", file=sys.stderr)
        return 1
    return build()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
