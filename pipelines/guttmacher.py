"""Guttmacher Institute — US abortion incidence (count, rate, ratio).

National abortion statistics from the Guttmacher Institute's Abortion Provider
Census (APC), a periodic survey of every known US abortion provider conducted
roughly every three years since 1973. Unlike CDC Abortion Surveillance (which is
voluntary and excludes several states that do not report — notably California,
Maryland, New Hampshire, and New Jersey), the APC covers all 50 states and DC,
so it is the more complete national count. The CDC series understates the
national total by ~40-50%; this is why the Guttmacher figures are used here.

Series: count, rate (per 1,000 women 15-44), and ratio (per 1,000 live births),
national, annual 1973-2020. Hand-entered from the published appendix tables of
"Pregnancies, Births and Abortions in the United States, 1973-2020: National and
State Trends by Age" (Chiu, Maddow-Zimet & Kost) — Appendix Table 4 (number),
Table 3 (rate), Table 5 (ratio, per 1,000 births), the "15-44" all-ages column.
There is no API; the same hand-entered pattern as the CDC NVSS series in
cdc_health.py. Counts are rounded to the nearest 10 by Guttmacher.

Spliced onto the APC census: the post-Dobbs Monthly Abortion Provision Study
(MAPS), national annual totals for 2023-2025 (count + rate). MAPS is a DIFFERENT
methodology (a modeled monthly provider sample, not a full census) and leaves a
2021-2022 gap, so a methodology-break annotation marks the transition on the
charts. MAPS does not publish a per-1,000-births ratio, so for 2023-2024 the
ratio is computed as MAPS abortions / CDC NCHS live births; the 2025 ratio
awaits final 2025 birth totals, so the ratio series runs one year behind count
and rate. All three sources (Guttmacher APC, Guttmacher MAPS, CDC NCHS natality)
are cited in each series description.

Compliance / ToS
----------------
Guttmacher's published data are free to use without registration or permission;
they ask only for citation, which we provide via provenance. The full dataset is
also archived on OSF (https://osf.io/kthnf). We serve only national annual
aggregates — no micro-data.

Usage:
    python pipelines/guttmacher.py            # build everything
    python pipelines/guttmacher.py abortion   # one builder
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import write_timeseries  # noqa: E402

PIPELINE = "guttmacher"
REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_DIR = REPO_ROOT / "src" / "content" / "sources" / PIPELINE

APC_URL = (
    "https://www.guttmacher.org/report/"
    "pregnancies-births-abortions-in-united-states-1973-2020"
)

# Guttmacher Abortion Provider Census, national totals (the "15-44" all-ages
# column), 1973-2020. Tuple = (number of abortions, rate per 1,000 women 15-44,
# ratio per 1,000 live births). From the report's appendix tables 4 / 3 / 5.
# Counts rounded to nearest 10 (as published); ratio rounded to a whole number
# to match the CDC ratio's formatting.
ABORTION_APC = {
    "1973": (744610, 16.3, 237), "1974": (898570, 19.3, 284), "1975": (1034170, 21.7, 329), "1976": (1179300, 24.2, 372),
    "1977": (1316700, 26.4, 396), "1978": (1409600, 27.7, 423), "1979": (1497670, 28.8, 429), "1980": (1553890, 29.3, 430),
    "1981": (1577340, 29.3, 435), "1982": (1573920, 28.8, 428), "1983": (1575000, 28.5, 433), "1984": (1577180, 28.1, 430),
    "1985": (1588550, 28.0, 422), "1986": (1574000, 27.4, 419), "1987": (1559110, 26.9, 409), "1988": (1590750, 27.4, 407),
    "1989": (1566870, 26.8, 388), "1990": (1608620, 27.4, 387), "1991": (1556510, 26.2, 379), "1992": (1528930, 25.7, 376),
    "1993": (1495000, 25.0, 374), "1994": (1423000, 23.7, 360), "1995": (1359440, 22.5, 349), "1996": (1360160, 22.4, 350),
    "1997": (1335000, 21.9, 344), "1998": (1319000, 21.5, 335), "1999": (1314790, 21.4, 332), "2000": (1312990, 21.3, 324),
    "2001": (1291000, 20.9, 321), "2002": (1269000, 20.5, 316), "2003": (1250000, 20.2, 306), "2004": (1222100, 19.7, 297),
    "2005": (1206200, 19.4, 292), "2006": (1242000, 20.0, 291), "2007": (1209640, 19.4, 280), "2008": (1212350, 19.4, 285),
    "2009": (1151600, 18.5, 279), "2010": (1102670, 17.7, 276), "2011": (1058490, 16.9, 268), "2012": (1011070, 16.1, 256),
    "2013": (958700, 15.2, 244), "2014": (926190, 14.6, 232), "2015": (899270, 14.2, 226), "2016": (874080, 13.7, 222),
    "2017": (862320, 13.5, 224), "2018": (885800, 13.8, 234), "2019": (916460, 14.2, 244), "2020": (930160, 14.4, 257),
}

# Guttmacher Monthly Abortion Provision Study (MAPS) — national annual totals,
# (number of clinician-provided abortions, rate per 1,000 women 15-44). A modeled
# monthly provider sample launched after Dobbs; covers all states (figures
# include medication abortions via telehealth under shield laws). Different
# methodology from the APC census above, and 2021-2022 are not covered.
#   2023: https://www.guttmacher.org/2024/03/despite-bans-number-abortions-united-states-increased-2023
#   2024: https://www.guttmacher.org/news-release/2025/guttmacher-institute-releases-full-year-us-abortion-data-2024
#   2025: https://www.guttmacher.org/news-release/2026/guttmacher-releases-full-year-2025-abortion-incidence-and-travel-data
MAPS = {
    "2023": (1037000, 15.9),
    "2024": (1124000, 16.7),
    "2025": (1126000, 16.7),
}

# CDC NCHS live births (final), used to compute the MAPS-era ratio (Guttmacher
# does not publish a per-1,000-births ratio for MAPS years). 2025 births are not
# yet released, so the ratio series stops at 2024 while count/rate run to 2025.
#   https://www.cdc.gov/nchs/products/databriefs/db535.htm (2024 final)
CDC_BIRTHS = {"2023": 3596017, "2024": 3628934}


def _yaml_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def write_yaml(
    sid: str, name: str, short_name: str, description: str,
    supported: list[str], unit: str, decimals: int, suffix: str,
    series_note: str, unit_class: str,
) -> None:
    YAML_DIR.mkdir(parents=True, exist_ok=True)
    tags = ["health", "gender", "us"]
    deltas = ", ".join(f'"{d}"' for d in supported)
    lines = [
        f"name: {_yaml_str(name)}",
        f"shortName: {_yaml_str(short_name)}",
        f"description: {_yaml_str(description)}",
        "kind: timeseries",
        f"pipeline: {PIPELINE}",
        f"dataFile: data/{PIPELINE}/{sid}.json",
        f"supportedDeltas: [{deltas}]",
        f'unit: "{unit}"',
        "emphasis: change",
        "formatting:",
        "  style: number",
        f"  decimals: {decimals}",
        f'  suffix: "{suffix}"',
        "provenance:",
        "  provider: Guttmacher Institute",
        f"  series: {_yaml_str(series_note)}",
        f"  url: {APC_URL}",
        "  license: Free to use with citation (Guttmacher Institute)",
        "tags:",
        *[f"  - {t}" for t in tags],
        f"unitClass: {unit_class}",
        "",
    ]
    (YAML_DIR / f"{sid}.yaml").write_text("\n".join(lines), encoding="utf-8")


# Per-series descriptions, each citing all three sources. No em-dashes in this
# user-facing prose (project style rule); name fields keep the structured
# "— United States" separator, which is exempt.
_DESC_COUNT = (
    "Total number of abortions in the United States, by year. Two Guttmacher "
    "Institute series, spliced: the Abortion Provider Census (a survey of all "
    "known providers in all 50 states and DC) for 1973 to 2020, and the Monthly "
    "Abortion Provision Study for 2023 to 2025. Both count nationally, unlike "
    "CDC Abortion Surveillance, which is voluntary and excludes several states "
    "including California. The two Guttmacher series use different methods (a "
    "full provider census versus a modeled monthly sample) and 2021 to 2022 are "
    "not covered, so the recent points are not strictly comparable with the "
    "earlier census; recent figures include medication abortions via telehealth "
    "under shield laws."
)
_DESC_RATE = (
    "Abortions per 1,000 women aged 15 to 44 in the United States, by year. "
    "Guttmacher Institute Abortion Provider Census for 1973 to 2020, spliced "
    "with the Guttmacher Monthly Abortion Provision Study for 2023 to 2025. Both "
    "count nationally, unlike CDC Abortion Surveillance, which excludes several "
    "states including California. The two Guttmacher series use different methods "
    "and 2021 to 2022 are not covered, so the recent points are not strictly "
    "comparable with the earlier census."
)
_DESC_RATIO = (
    "Abortions per 1,000 live births in the United States, by year. The "
    "Guttmacher Institute Abortion Provider Census reports this ratio directly "
    "for 1973 to 2020. For 2023 and 2024 it is computed as Guttmacher Monthly "
    "Abortion Provision Study abortions divided by CDC NCHS live births; 2025 "
    "abortions are available but the 2025 ratio awaits final 2025 birth totals. "
    "Because Guttmacher counts nationally (all 50 states and DC, unlike CDC "
    "Abortion Surveillance, which excludes California and others), this ratio "
    "runs well above the CDC abortion-surveillance figure."
)


def build_abortion() -> int:
    """National abortion count, rate, and ratio: the Guttmacher APC census
    (1973-2020) spliced with the MAPS study (2023+); the ratio for MAPS years is
    computed against CDC NCHS births. Each series cites all three sources."""
    apc = sorted(ABORTION_APC)
    maps = sorted(MAPS)
    count_pts = [(y, ABORTION_APC[y][0]) for y in apc] + [(y, MAPS[y][0]) for y in maps]
    rate_pts = [(y, ABORTION_APC[y][1]) for y in apc] + [(y, MAPS[y][1]) for y in maps]
    ratio_pts = [(y, ABORTION_APC[y][2]) for y in apc] + [
        (y, round(MAPS[y][0] / CDC_BIRTHS[y] * 1000)) for y in maps if y in CDC_BIRTHS
    ]
    deltas = ["1y", "5y", "10y", "30y"]
    specs = [
        ("abortion_count_us", "Abortions — United States", "US abortions",
         count_pts, "abortions", 0, "", "count", _DESC_COUNT,
         "Guttmacher APC (1973-2020) + MAPS (2023-2025); national; number"),
        ("abortion_rate_us", "Abortion rate — United States", "US abortion rate",
         rate_pts, "per 1,000 women 15-44", 1, " per 1k", "rate", _DESC_RATE,
         "Guttmacher APC (1973-2020) + MAPS (2023-2025); national; rate"),
        ("abortion_ratio_us", "Abortion ratio — United States",
         "US abortion ratio", ratio_pts, "per 1,000 live births", 0,
         " per 1k births", "ratio", _DESC_RATIO,
         "Guttmacher APC (1973-2020) + MAPS abortions / CDC NCHS births "
         "(2023-2024); national; ratio per 1,000 births"),
    ]
    n = 0
    for sid, name, short, pairs, unit, dec, suf, ucls, desc, note in specs:
        pts = [{"t": f"{y}-12-31", "v": v} for y, v in pairs]
        write_timeseries(PIPELINE, sid, name, pts, unit=unit, merge=False)
        write_yaml(sid, name, short, desc, deltas, unit, dec, suf, note, ucls)
        n += 1
    return n


BUILDERS = {"abortion": build_abortion}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    which = argv or list(BUILDERS)
    total = 0
    for key in which:
        if key not in BUILDERS:
            print(f"unknown builder: {key} (have: {', '.join(BUILDERS)})")
            return 2
        total += BUILDERS[key]()
    print(f"guttmacher: wrote {total} sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
