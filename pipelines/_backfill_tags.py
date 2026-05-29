"""
Backfill `tags:` lines on every chart YAML so the composer library filter has
something to work with. Tag assignment is rule-based on file path + filename.
Idempotent: if a `tags:` line already exists, skip that file.

Run once:  python pipelines/_backfill_tags.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHARTS = ROOT / "src" / "content" / "charts"


def tags_for(rel_path: str) -> list[str]:
    """rel_path is e.g. 'us-macro/ten_year.yaml' (posix)."""
    parts = rel_path.split("/")
    dir_name = parts[0]
    stem = parts[-1].removesuffix(".yaml")

    # Fast dir-based fallthrough
    if dir_name == "commodities":
        return ["commodities"]
    if dir_name == "stocks":
        return ["large-stocks"]
    if dir_name == "countries":
        return ["world", "equity-index"]

    if dir_name == "us-macro":
        # Rates
        rates_names = {
            "ten_year", "two_year", "us_3mo", "us_5y", "us_30y",
            "curve_spread", "fed_funds", "mortgage_30y",
        }
        if stem in rates_names:
            return ["rates", "macro"]
        # Credit
        if stem in {"hy_spread", "ig_spread"}:
            return ["credit", "macro"]
        # Equity indices in macro section
        if stem in {"sp500", "nasdaq"}:
            return ["equity-index", "macro"]
        # Everything else macro-ish
        return ["macro"]

    if dir_name == "markets":
        sector_set = {
            "xlk", "xlf", "xlv", "xli", "xlp", "xly", "xlb", "xlc",
            "xlre", "xlu", "xle",
        }
        international_set = {"efa", "vea", "eem", "vwo"}
        if stem in sector_set:
            return ["sectors", "equity-index"]
        if stem in international_set:
            return ["world", "equity-index"]
        # dia, iwm, iwb, vti, sp500, nasdaq
        return ["equity-index"]

    if dir_name == "tech":
        if stem == "hy_tmt_bonds":
            return ["credit"]
        if stem in {"indices"}:
            return ["equity-index"]
        # Mega-cap tech stocks
        return ["large-stocks"]

    if dir_name == "oil":
        if stem in {"xle", "transition"}:
            return ["sectors", "equity-index"]
        return ["commodities"]

    # Fallback
    return []


def patch_file(path: Path, tags: list[str]) -> bool:
    text = path.read_text(encoding="utf-8")
    if "\ntags:" in text or text.startswith("tags:"):
        return False
    if not tags:
        return False
    tags_line = "tags: [" + ", ".join(tags) + "]\n"
    # Insert tags right after the "sources:" block (end of its list) and before
    # "render:" line, for readability. Pragmatic: append to the end of the file.
    if not text.endswith("\n"):
        text += "\n"
    text += tags_line
    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    count = 0
    skipped = 0
    for yaml_path in sorted(CHARTS.rglob("*.yaml")):
        rel = yaml_path.relative_to(CHARTS).as_posix()
        tags = tags_for(rel)
        if patch_file(yaml_path, tags):
            print(f"  + {rel}  -> {tags}")
            count += 1
        else:
            skipped += 1
    print(f"\ntagged {count} files; skipped {skipped}")


if __name__ == "__main__":
    main()
