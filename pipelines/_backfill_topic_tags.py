"""
Backfill topical tags (inflation / housing / us) onto hand-maintained source
YAMLs that were missing them. fred_series.py and bls.py write data + nothing
else, so these source YAMLs are authored by hand; this script is the record of
which series belong to which topical category.

Idempotent: only adds a tag that isn't already present; preserves file
formatting (line-based insert, not a yaml round-trip).

Run:  python pipelines/_backfill_topic_tags.py
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "content" / "sources"

# id -> tags to ensure. Built additively so a series in two categories
# (e.g. CPI shelter is both inflation and housing) gets the union.
PLAN: dict[str, set[str]] = {}


def add(provider: str, names: list[str], tags: set[str]) -> None:
    for n in names:
        PLAN.setdefault(f"{provider}/{n}", set()).update(tags)


# --- Inflation: price-level + inflation-expectation measures -----------------
# CPI families, PPI (producer prices — "leading inflation" per the user's
# unit-labor-costs note), PCE, the GDP deflator, unit labor costs, and the
# 5y5y forward breakeven. These are all US national, so ensure `us` too.
add("fred", [
    "us_cpi", "core_cpi", "cpi_yoy", "cpi_food", "cpi_food_at_home",
    "cpi_food_away", "cpi_energy", "cpi_medical", "cpi_rent", "cpi_shelter",
    "sticky_cpi", "median_cpi", "dc_cpi",
    "ppi_all_commodities", "ppi_final_demand", "ppi_farm_products",
    "ppi_fertilizer", "ppi_semiconductor", "ppi_data_processing_hosting",
    "core_pce", "headline_pce", "gdp_deflator", "forward_inflation_5y5y",
], {"inflation", "us"})
# unit_labor_costs ships with NO tags — a leading measure of producer-side
# inflation. us_population also ships tagless and is plainly US.
add("fred", ["unit_labor_costs"], {"macro", "us", "inflation"})
add("fred", ["us_population"], {"macro", "us"})
# BLS CPI category series ship tagless.
add("bls", [
    "cpi_medical", "cpi_new_vehicles", "cpi_shelter",
    "cpi_used_vehicles", "cpi_washington_metro",
], {"macro", "us", "inflation"})

# --- Housing: the macro housing indicators (extends the existing `housing` ---
# tag that zillow already uses). real-estate stays as-is (it is dominated by
# ACS owner/renter-occupancy micro-data).
add("fred", [
    "housing_starts", "building_permits", "new_home_sales",
    "median_home_price", "median_listing_price", "mortgage_15y",
    "mortgage_30y", "mortgage_delinquency", "rental_vacancy",
    "homeowner_vacancy", "fhfa_dc_hpi", "fhfa_purchase_only_hpi",
    "fhfa_us_hpi", "cpi_rent", "cpi_shelter",
], {"housing", "us"})
add("bls", ["cpi_shelter"], {"housing"})
# Per-state building permits (51) are housing too.
for _f in glob.glob(str(SRC / "fred" / "state_building_permits_*.yaml")):
    PLAN.setdefault(f"fred/{Path(_f).stem}", set()).add("housing")

# --- Labor: BLS employment series that shipped with NO tags at all ----------
# National JOLTS hires/quits rates.
add("bls", ["jolts_hires_rate", "jolts_quits_rate"], {"macro", "us", "labor"})
# State payrolls, state + county unemployment: geo tags already supply us/state;
# add the topical `labor` tag so they surface under the labor chip (+ geo).
for _pat in ("state_payrolls_*", "state_unemployment_*", "county_unemployment_*"):
    for _f in glob.glob(str(SRC / "bls" / _pat)):
        PLAN.setdefault(f"bls/{Path(_f).stem}", set()).add("labor")


# --- Topical tags for hand-written providers that shipped fully untagged ----
# Each rule matches the topical tags the provider's already-tagged siblings use
# (or, for country/geo-hidden providers, the obvious topic), so this only fills
# gaps, never invents a taxonomy. ensure_tags is idempotent.
# usaspending: federal spending (tagged siblings carry government+macro).
for _f in glob.glob(str(SRC / "usaspending" / "*.yaml")):
    PLAN.setdefault(f"usaspending/{Path(_f).stem}", set()).update({"government", "macro"})
# OECD foreign indicators, by metric suffix (country tag already hides them).
for _f in glob.glob(str(SRC / "oecd" / "*.yaml")):
    _s = Path(_f).stem
    if _s.endswith("_gov_debt_pct_gdp") or _s.endswith("_gov_deficit_pct_gdp"):
        PLAN.setdefault(f"oecd/{_s}", set()).update({"macro", "government"})
    elif _s.endswith("_health_spending_pct_gdp"):
        PLAN.setdefault(f"oecd/{_s}", set()).update({"health", "macro"})
    elif _s.endswith("_life_expectancy"):
        PLAN.setdefault(f"oecd/{_s}", set()).add("health")
# fred per-state population (matches us_population -> macro; geo supplies us/state).
for _f in glob.glob(str(SRC / "fred" / "state_population_*.yaml")):
    PLAN.setdefault(f"fred/{Path(_f).stem}", set()).add("macro")
# treasury_tic foreign holders of US treasuries (matches siblings).
for _f in glob.glob(str(SRC / "treasury_tic" / "*.yaml")):
    PLAN.setdefault(f"treasury_tic/{Path(_f).stem}", set()).update({"government", "macro"})
# country GDP-share + worldbank US GDP -> macro; country equity-vs-world -> equity-index.
for _f in glob.glob(str(SRC / "countries_gdp" / "*.yaml")):
    PLAN.setdefault(f"countries_gdp/{Path(_f).stem}", set()).add("macro")
PLAN.setdefault("worldbank_gdp_raw/usa", set()).add("macro")
for _f in glob.glob(str(SRC / "countries" / "*.yaml")):
    PLAN.setdefault(f"countries/{Path(_f).stem}", set()).add("equity-index")
# yahoo: only the UNTAGGED set (mega-cap stocks vs a few crypto); never re-tag
# the existing ETF/commodity/fx/crypto entries.
_CRYPTO_YAHOO = {"dot_usd", "shib_usd", "trx_usd", "etha"}
for _f in glob.glob(str(SRC / "yahoo" / "*.yaml")):
    _txt = open(_f, encoding="utf-8").read()
    if "\ntags:" in _txt or _txt.startswith("tags:"):
        continue  # already tagged
    _s = Path(_f).stem
    PLAN.setdefault(f"yahoo/{_s}", set()).add(
        "crypto" if _s in _CRYPTO_YAHOO else "large-stocks")


def ensure_tags(path: Path, needed: set[str]) -> list[str]:
    """Return the tags actually added (empty if none)."""
    lines = path.read_text(encoding="utf-8").split("\n")
    # Locate a tags: line.
    idx = next(
        (i for i, l in enumerate(lines) if l == "tags:" or l.startswith("tags:")),
        None,
    )
    if idx is not None and lines[idx].strip() == "tags:":
        # Block style. Collect existing list items.
        j = idx + 1
        existing = set()
        while j < len(lines) and lines[j].lstrip().startswith("- "):
            existing.add(lines[j].split("- ", 1)[1].strip())
            j += 1
        added = [t for t in sorted(needed) if t not in existing]
        if added:
            lines[j:j] = [f"  - {t}" for t in added]
            path.write_text("\n".join(lines), encoding="utf-8")
        return added
    if idx is not None and "[" in lines[idx]:
        # Inline style: tags: [a, b]
        inner = lines[idx][lines[idx].index("[") + 1 : lines[idx].rindex("]")]
        existing = [x.strip() for x in inner.split(",") if x.strip()]
        added = [t for t in sorted(needed) if t not in existing]
        if added:
            lines[idx] = "tags: [" + ", ".join(existing + added) + "]"
            path.write_text("\n".join(lines), encoding="utf-8")
        return added
    # No tags block — insert one before `kind:` (or append).
    block = ["tags:"] + [f"  - {t}" for t in sorted(needed)]
    ki = next((i for i, l in enumerate(lines) if l.startswith("kind:")), None)
    if ki is not None:
        lines[ki:ki] = block
    else:
        lines += block
    path.write_text("\n".join(lines), encoding="utf-8")
    return sorted(needed)


def main() -> None:
    changed = 0
    missing = 0
    for sid, tags in sorted(PLAN.items()):
        path = SRC / (sid + ".yaml")
        if not path.exists():
            print(f"  ?? missing file: {sid}")
            missing += 1
            continue
        added = ensure_tags(path, tags)
        if added:
            print(f"  + {sid}: {added}")
            changed += 1
    print(f"\nupdated {changed} files; {missing} missing; {len(PLAN)} planned")


if __name__ == "__main__":
    main()
