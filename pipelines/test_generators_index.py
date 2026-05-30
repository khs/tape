"""
Unit tests for the country-label + slug-parsing logic in
``_generate_generators_index.py``.

These guard the pre-shipped regressions:
  - "Uk" / "Uae" (single-letter-capitalized acronyms — slug.title())
  - "kong", "rica", "zealand", "eu" (multi-word country slugs sliced
    by the old greedy regex)
  - Template-label leaks like "Total population" rendering as
    "Sub-Saharan Africa" (because the entity-name stripper didn't
    know "africa_ssf"'s canonical label)
  - Description leaks ("for the Abilene metropolitan statistical
    area" reading as the description of a 387-MSA template)

Run locally with::

    python -m unittest pipelines.test_generators_index

The CI workflow (`.github/workflows/ci.yml`) runs the file via
``python -m unittest`` so the audit is enforced before merge.

Why unittest and not pytest: the rest of the repo doesn't ship a
Python test dep, and unittest is in stdlib. Keeps `pip install` in
CI snappy and the new test file self-contained.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

# Load the module under test by file path. The pipeline file starts
# with an underscore, which is allowed but a bit awkward for
# `from pipelines._generate_generators_index import ...` — load it
# explicitly to avoid an import-path dance in CI.
HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "_generate_generators_index.py"
spec = importlib.util.spec_from_file_location("gen_idx", MODULE_PATH)
assert spec is not None and spec.loader is not None, MODULE_PATH
gen_idx = importlib.util.module_from_spec(spec)
sys.modules["gen_idx"] = gen_idx
spec.loader.exec_module(gen_idx)


class MatchCountryWbExtTests(unittest.TestCase):
    """The matcher is the heart of the multi-word-slug fix. Pre-fix
    code returned ``(co2_per_capita_hong, kong)`` because the regex
    greedily ate everything before the last underscore."""

    def test_two_word_country_keeps_underscore(self) -> None:
        r = gen_idx._match_country_wb_ext(
            "worldbank_extended/co2_per_capita_hong_kong"
        )
        self.assertEqual(
            r,
            ("country", "worldbank_extended_co2_per_capita", "hong_kong"),
        )

    def test_south_korea_not_split_to_korea(self) -> None:
        r = gen_idx._match_country_wb_ext(
            "worldbank_extended/population_south_korea"
        )
        self.assertEqual(
            r,
            ("country", "worldbank_extended_population", "south_korea"),
        )

    def test_costa_rica(self) -> None:
        r = gen_idx._match_country_wb_ext(
            "worldbank_extended/agriculture_pct_gdp_costa_rica"
        )
        self.assertEqual(
            r,
            ("country", "worldbank_extended_agriculture_pct_gdp", "costa_rica"),
        )

    def test_europe_eu_not_split_to_eu(self) -> None:
        # Pre-fix the regex captured just "eu" and called it a country.
        r = gen_idx._match_country_wb_ext(
            "worldbank_extended/population_europe_eu"
        )
        self.assertEqual(
            r,
            ("country", "worldbank_extended_population", "europe_eu"),
        )

    def test_africa_ssf_not_split_to_ssf(self) -> None:
        r = gen_idx._match_country_wb_ext(
            "worldbank_extended/population_africa_ssf"
        )
        self.assertEqual(
            r,
            ("country", "worldbank_extended_population", "africa_ssf"),
        )

    def test_single_word_country_still_works(self) -> None:
        r = gen_idx._match_country_wb_ext(
            "worldbank_extended/population_australia"
        )
        self.assertEqual(
            r,
            ("country", "worldbank_extended_population", "australia"),
        )

    def test_three_letter_slug_uae(self) -> None:
        # UAE is a short slug; pre-fix the slug.title() produced "Uae".
        # The matcher should still resolve the right country here —
        # the label cleanup is a separate function.
        r = gen_idx._match_country_wb_ext(
            "worldbank_extended/population_uae"
        )
        self.assertEqual(
            r,
            ("country", "worldbank_extended_population", "uae"),
        )

    def test_two_letter_slug_uk(self) -> None:
        r = gen_idx._match_country_wb_ext(
            "worldbank_extended/population_uk"
        )
        self.assertEqual(
            r,
            ("country", "worldbank_extended_population", "uk"),
        )

    def test_non_worldbank_ext_id_returns_none(self) -> None:
        self.assertIsNone(
            gen_idx._match_country_wb_ext("worldbank_gdp_raw/usa")
        )
        self.assertIsNone(
            gen_idx._match_country_wb_ext("bls/metro_unemployment_35620")
        )

    def test_unknown_country_slug_returns_none(self) -> None:
        # A source ID whose tail isn't in COUNTRY_SLUGS_BY_LEN doesn't
        # match. We'd rather silently drop than mis-attribute.
        self.assertIsNone(
            gen_idx._match_country_wb_ext(
                "worldbank_extended/population_atlantis"
            )
        )


class CountryLabelOverridesTests(unittest.TestCase):
    """The hand-maintained override table. Failures here mean a future
    refactor accidentally dropped a needed entry."""

    def test_us_uk_uae_overrides(self) -> None:
        ov = gen_idx.COUNTRY_LABEL_OVERRIDES
        self.assertEqual(ov["usa"]["short"], "United States")
        self.assertEqual(ov["uk"]["short"], "United Kingdom")
        self.assertEqual(ov["uae"]["short"], "United Arab Emirates")

    def test_aggregate_overrides_use_proper_capitalization(self) -> None:
        ov = gen_idx.COUNTRY_LABEL_OVERRIDES
        self.assertEqual(ov["eu"]["short"], "European Union")
        self.assertEqual(ov["mena"]["short"], "MENA")
        self.assertEqual(ov["latam"]["short"], "Latin America & Caribbean")
        self.assertEqual(ov["ssf"]["short"], "Sub-Saharan Africa")

    def test_no_override_lowercased_or_titlecased_acronyms(self) -> None:
        # Sanity: make sure nobody accidentally checks in "Uae" / "Uk"
        # / "Eu" as the override value (which would be the worst case
        # — looks intentional, but wrong).
        for slug, labels in gen_idx.COUNTRY_LABEL_OVERRIDES.items():
            for field in ("short", "name"):
                val = labels[field]
                # A label should not be a single title-cased word that's
                # actually an acronym ("Uk", "Uae", "Eu", "Mena", "Ssf").
                if val in {"Uk", "Uae", "Eu", "Mena", "Ssf", "Usa", "Latam"}:
                    self.fail(
                        f"override for {slug!r}.{field} is {val!r}, "
                        f"which is the wrong-capitalization bug we just fixed",
                    )


class CountryLabelsFromYamlTests(unittest.TestCase):
    """``load_country_labels`` reads population_*.yaml at import time.
    These tests check that the parser correctly extracted the
    canonical label out of the YAML's ``name`` and ``shortName`` fields.
    """

    def test_known_canonical_labels_present(self) -> None:
        labels = gen_idx.COUNTRY_LABELS
        # These slugs must resolve to their proper human label — the
        # YAMLs already contain the right spelling, so this confirms
        # we're plumbing it through (and not just title-casing the slug).
        expected = {
            "uae": "United Arab Emirates",
            "uk": "United Kingdom",
            "hong_kong": "Hong Kong",
            "costa_rica": "Costa Rica",
            "el_salvador": "El Salvador",
            "new_zealand": "New Zealand",
            "saudi_arabia": "Saudi Arabia",
            "south_africa": "South Africa",
            "south_korea": "South Korea",
            "cayman_islands": "Cayman Islands",
            "europe_eu": "European Union",
            "africa_ssf": "Sub-Saharan Africa",
            "turkiye": "Türkiye",  # diacritic preserved from YAML
        }
        for slug, want in expected.items():
            self.assertEqual(
                labels.get(slug, {}).get("short"),
                want,
                msg=f"slug {slug!r} should resolve to {want!r}",
            )

    def test_no_acronym_title_cased(self) -> None:
        # Nothing in the discovered set should look like "Uk", "Uae", etc.
        for slug, e in gen_idx.COUNTRY_LABELS.items():
            self.assertNotIn(
                e["short"],
                {"Uk", "Uae", "Eu", "Mena", "Ssf", "Usa", "Latam"},
                msg=f"{slug!r} resolved to acronym-looks-wrong {e['short']!r}",
            )

    def test_country_slugs_by_len_is_longest_first(self) -> None:
        # The matcher relies on this ordering to pick "south_korea"
        # before "korea". Any shuffle here would silently regress the
        # multi-word-slug parsing.
        prev = 9999
        for slug in gen_idx.COUNTRY_SLUGS_BY_LEN:
            self.assertLessEqual(
                len(slug), prev,
                msg=f"slug {slug!r} ({len(slug)}) followed a shorter one ({prev})",
            )
            prev = len(slug)


class EntityLabelCandidatesTests(unittest.TestCase):
    """``_entity_label_candidates`` feeds the label/description
    stripper. For countries it needs to know the canonical spelling
    OR the stripper won't recognize "Sub-Saharan Africa" in a name
    like "Total population — Sub-Saharan Africa"."""

    def test_country_includes_canonical_label(self) -> None:
        cands = gen_idx._entity_label_candidates("country", "africa_ssf")
        self.assertIn("Sub-Saharan Africa", cands)
        cands = gen_idx._entity_label_candidates("country", "europe_eu")
        self.assertIn("European Union", cands)
        cands = gen_idx._entity_label_candidates("country", "uae")
        self.assertIn("United Arab Emirates", cands)

    def test_country_includes_titlecased_slug_as_fallback(self) -> None:
        # For countries without a canonical override, the title-cased
        # slug is the right candidate ("australia" -> "Australia").
        cands = gen_idx._entity_label_candidates("country", "australia")
        self.assertIn("Australia", cands)

    def test_state_two_letter_present(self) -> None:
        cands = gen_idx._entity_label_candidates("state", "VA")
        self.assertIn("Virginia", cands)
        self.assertIn("VA", cands)


class CleanTemplateLabelTests(unittest.TestCase):
    """The label cleanup turns one sibling's ``name`` field into a
    template name. The hard cases:
      - Em-dash split: pick the half that ISN'T the entity name
      - Sub-Saharan Africa was leaking because the candidate list
        didn't include the canonical label."""

    def test_strips_canonical_country_label(self) -> None:
        # Pre-fix this returned "Sub-Saharan Africa" because the longer
        # half was returned when neither half matched.
        out = gen_idx.clean_template_label(
            "Total population — Sub-Saharan Africa",
            "country",
            "africa_ssf",
        )
        self.assertEqual(out, "Total population")

    def test_strips_european_union(self) -> None:
        out = gen_idx.clean_template_label(
            "Total population — European Union",
            "country",
            "europe_eu",
        )
        self.assertEqual(out, "Total population")

    def test_strips_uae(self) -> None:
        out = gen_idx.clean_template_label(
            "Total population — United Arab Emirates",
            "country",
            "uae",
        )
        self.assertEqual(out, "Total population")

    def test_state_label_with_em_dash(self) -> None:
        out = gen_idx.clean_template_label(
            "Total households (vehicle-table denominator) — AL",
            "state", "AL",
        )
        # The "al" substring leaked through and made the tail look
        # like the entity. Fixed via word-boundary matching.
        self.assertEqual(out, "Total households (vehicle-table denominator)")


class CleanTemplateDescriptionTests(unittest.TestCase):
    """Description scrubbing — strip entity-specific phrases like
    "Abilene metropolitan statistical area" or "for AK (statewide)"."""

    def test_metro_strips_cbsa_phrase(self) -> None:
        raw = (
            "Total federal outlays where the recipient location is "
            "in the Abilene metropolitan statistical area "
            "(CBSA 10180, OMB-defined). Aggregated up from USAspending.gov."
        )
        out = gen_idx.clean_template_description(raw, "metro", "10180")
        self.assertIn("the selected metro", out)
        self.assertNotIn("Abilene", out)
        self.assertNotIn("CBSA 10180", out)

    def test_state_strips_statewide_phrase(self) -> None:
        raw = (
            "Median household income for AK (statewide). From the "
            "American Community Survey 5-year estimates."
        )
        out = gen_idx.clean_template_description(raw, "state", "AK")
        self.assertIn("the selected state (statewide)", out)
        self.assertNotIn("for AK", out)

    def test_country_strips_country_name(self) -> None:
        raw = (
            "Total population for Australia, annual. From World Bank "
            "World Development Indicators."
        )
        out = gen_idx.clean_template_description(raw, "country", "australia")
        self.assertIn("the selected country", out)
        self.assertNotIn("Australia", out)

    def test_country_with_canonical_label_stripped(self) -> None:
        raw = (
            "Total population for United Arab Emirates, annual. From "
            "World Bank World Development Indicators."
        )
        out = gen_idx.clean_template_description(raw, "country", "uae")
        self.assertIn("the selected country", out)
        self.assertNotIn("United Arab Emirates", out)

    def test_state_drops_district_count_aside(self) -> None:
        raw = (
            "Median household income for the selected state (statewide). "
            "AK has a single congressional district, so values match the "
            "underlying CD series exactly."
        )
        out = gen_idx.clean_template_description(raw, "state", "AK")
        # The "AK has a single congressional district..." sentence is
        # entity-specific and must be dropped — it can't generalize
        # to a template that covers 51 states.
        self.assertNotIn("AK has", out)
        self.assertNotIn("congressional district", out)


class GeneratedIndexAuditTests(unittest.TestCase):
    """Top-level audit of the generated JSON. Catches regressions
    where the per-function tests pass but the wiring drops the ball
    somewhere downstream (e.g. build_country_entities didn't merge
    the override map)."""

    @classmethod
    def setUpClass(cls) -> None:
        idx_path = HERE.parent / "public" / "generators-index.json"
        if not idx_path.exists():
            raise unittest.SkipTest(
                f"{idx_path.relative_to(HERE.parent)} missing — run "
                f"`python pipelines/_generate_generators_index.py` first.",
            )
        cls.idx = json.loads(idx_path.read_text(encoding="utf-8"))

    def test_no_phantom_truncated_country_slugs(self) -> None:
        # If the regex regressed, we'd see entities like "kong", "rica",
        # "salvador", "zealand", "eu", "ssf", "arabia", "korea" (the
        # one we DIDN'T want — south_korea exists too).
        entities = self.idx["geoTypes"]["country"]["entities"]
        for forbidden in ("kong", "rica", "salvador", "zealand", "eu", "ssf",
                          "arabia", "kingdom", "states", "america", "islands"):
            self.assertNotIn(
                forbidden, entities,
                msg=f"phantom truncated slug {forbidden!r} is back; "
                f"_match_country_wb_ext regressed",
            )

    def test_no_acronym_title_cased_in_entities(self) -> None:
        entities = self.idx["geoTypes"]["country"]["entities"]
        for code, e in entities.items():
            self.assertNotIn(
                e["short"],
                {"Uk", "Uae", "Eu", "Mena", "Ssf", "Usa", "Latam"},
                msg=f"entity {code!r}.short = {e['short']!r} — "
                f"label override regressed",
            )

    def test_specific_canonical_labels(self) -> None:
        entities = self.idx["geoTypes"]["country"]["entities"]
        expected = {
            "uae": "United Arab Emirates",
            "uk": "United Kingdom",
            "usa": "United States",
            "hong_kong": "Hong Kong",
            "costa_rica": "Costa Rica",
            "south_korea": "South Korea",
            "saudi_arabia": "Saudi Arabia",
            "europe_eu": "European Union",
            "africa_ssf": "Sub-Saharan Africa",
        }
        for slug, want in expected.items():
            self.assertIn(slug, entities, msg=f"missing entity {slug!r}")
            self.assertEqual(
                entities[slug]["short"], want,
                msg=f"entity {slug!r}.short should be {want!r}, "
                f"got {entities[slug]['short']!r}",
            )

    def test_populations_attached_for_known_entities(self) -> None:
        # At least the big metros, states, and countries should have a
        # `pop` field — the sort-by-population control depends on it.
        m = self.idx["geoTypes"]["metro"]["entities"]
        self.assertIsNotNone(m.get("35620", {}).get("pop"),
                             msg="NY-Newark MSA should have a population")
        self.assertIsNotNone(m.get("31080", {}).get("pop"),
                             msg="LA MSA should have a population")
        s = self.idx["geoTypes"]["state"]["entities"]
        self.assertIsNotNone(s.get("CA", {}).get("pop"),
                             msg="California should have a population")
        c = self.idx["geoTypes"]["country"]["entities"]
        self.assertIsNotNone(c.get("china", {}).get("pop"),
                             msg="China should have a population")
        self.assertIsNotNone(c.get("usa", {}).get("pop"),
                             msg="USA should have a population (acs_national fallback)")

    def test_no_description_entity_leaks(self) -> None:
        leaks: list[tuple[str, str, str]] = []
        # Phrases that would indicate the cleaner missed a leak.
        suspect_substrings = [
            "Abilene",          # alphabetically-first metro
            "(CBSA ",           # raw CBSA code
            " AK (statewide)",  # alphabetically-first state phrase
            " Australia, annual",  # alphabetically-first country phrase
            " AL has",          # entity-specific aside
        ]
        for geo in ("metro", "state", "country"):
            for t in self.idx["geoTypes"][geo]["templates"]:
                for s in suspect_substrings:
                    if s in t["description"]:
                        leaks.append((geo, t["id"], s))
        self.assertEqual(leaks, [], msg=f"description leaks: {leaks!r}")

    def test_no_empty_template_label_or_description(self) -> None:
        for geo in ("metro", "state", "country"):
            for t in self.idx["geoTypes"][geo]["templates"]:
                self.assertTrue(
                    t["label"],
                    msg=f"{geo} template {t['id']} has empty label",
                )
                self.assertTrue(
                    t["description"],
                    msg=f"{geo} template {t['id']} has empty description",
                )

    def test_state_labels_not_two_letter_codes(self) -> None:
        # Before the word-boundary fix in `matches_entity`, some state
        # templates ended up labeled "AL" because the matcher thought
        # "al" was inside "total" or similar.
        for t in self.idx["geoTypes"]["state"]["templates"]:
            self.assertNotIn(
                t["label"], {"AL", "AK", "AR", "AZ", "CA"},
                msg=f"state template {t['id']} has 2-letter abbreviation "
                f"as label — the substring-match bug regressed",
            )


class BuildCountryPresetsTests(unittest.TestCase):
    """build_country_presets() filters COUNTRY_PRESET_DEFS down to the
    slugs actually in the entity index and tags every emitted entry
    with a `total` = canonical group size from the def. Both behaviors
    matter:

      - filter: ensures a preset with zero overlap doesn't ship as
        "(0/N)" garbage that the renderer would have to filter out
        again.
      - total: preserves the conceptual group size when partial data
        is ingested (e.g. Russia missing from index → BRICS shows
        codes=4, total=5 → renderer displays "BRICS (4/5)" not the
        misleading "BRICS (4/4)").
    """

    def test_filters_unknown_slugs(self) -> None:
        # entities has only USA + JPN — every other G7 slug should
        # be dropped from `codes` but `total` stays at 7.
        entities = {"usa": {}, "japan": {}}
        result = gen_idx.build_country_presets(entities)
        g7 = result.get("g7")
        self.assertIsNotNone(g7, "g7 preset should still ship even at partial coverage")
        self.assertEqual(set(g7["codes"]), {"usa", "japan"})
        self.assertEqual(g7["total"], 7,
                         "total must be the canonical G7 size (7), "
                         "not the filtered codes length (2)")

    def test_drops_groups_with_zero_overlap(self) -> None:
        # No BRICS country in entities → group disappears entirely.
        entities = {"usa": {}, "japan": {}, "germany": {}}
        result = gen_idx.build_country_presets(entities)
        self.assertNotIn("brics", result)

    def test_total_uses_intent_count_not_codes_length(self) -> None:
        # Every emitted preset's `total` should equal the length of
        # its source slug list in COUNTRY_PRESET_DEFS. This is the
        # property the renderer leans on for the "X/Y" label format
        # — drifting `total` would make the count meaningless.
        intent: dict[str, int] = {
            key: len(slugs) for key, _label, slugs in gen_idx.COUNTRY_PRESET_DEFS
        }
        # Build with every slug present so every preset emits.
        all_slugs = {s for _, _, slugs in gen_idx.COUNTRY_PRESET_DEFS for s in slugs}
        entities = {s: {} for s in all_slugs}
        result = gen_idx.build_country_presets(entities)
        for key, expected_total in intent.items():
            self.assertIn(key, result, f"preset {key} missing under full coverage")
            self.assertEqual(
                result[key]["total"], expected_total,
                f"preset {key} total mismatch: got {result[key]['total']}, "
                f"expected {expected_total}",
            )

    def test_preset_order_preserved(self) -> None:
        # COUNTRY_PRESET_DEFS is ordered by reader-intuition priority
        # (G7 → BRICS → G20 → ...). The renderer's dropdown ordering
        # leans on Python dict insertion order, so a build that
        # accidentally re-sorted would change every reader's dropdown.
        all_slugs = {s for _, _, slugs in gen_idx.COUNTRY_PRESET_DEFS for s in slugs}
        entities = {s: {} for s in all_slugs}
        result = gen_idx.build_country_presets(entities)
        expected_order = [key for key, _label, _slugs in gen_idx.COUNTRY_PRESET_DEFS]
        self.assertEqual(list(result.keys()), expected_order)

    def test_canonical_groups_match_external_definitions(self) -> None:
        # Lockdown on the EXACT membership of the canonical groups —
        # G7 has 7 countries, BRICS has 5, Anglosphere has 5, Nordics
        # has 5, North America (3-country) has 3. If someone tweaks
        # these without thinking, the test fails loudly. (G20 / Top GDP
        # / Top Pop are partial subsets of canonical groups due to
        # data-availability constraints, so they're not locked here.)
        canonical = {
            "g7": {"usa", "japan", "germany", "uk", "france", "italy", "canada"},
            "brics": {"china", "india", "brazil", "russia", "south_africa"},
            "anglosphere": {"usa", "uk", "canada", "australia", "new_zealand"},
            "nordics": {"norway", "sweden", "finland", "denmark", "iceland"},
            "north_america_n3": {"usa", "canada", "mexico"},
        }
        defs_by_key = {k: set(slugs) for k, _l, slugs in gen_idx.COUNTRY_PRESET_DEFS}
        for key, expected_members in canonical.items():
            self.assertIn(key, defs_by_key, f"canonical preset {key} missing")
            self.assertEqual(
                defs_by_key[key], expected_members,
                f"canonical preset {key} membership drifted: "
                f"got {defs_by_key[key]}, expected {expected_members}",
            )


class MatcherCoverageTest(unittest.TestCase):
    """Catches the class of bug where a new provider ships per-entity
    sources following one of the standard conventions but nobody added a
    matcher to MATCHERS — so the Generators tab silently loses the
    templates. Hit in May 2026 with 9 state-level providers (usgs_water,
    usda_nass, cdc_health, acs_labor, census_govfin, edu_spending,
    eia_state_energy, naep, usaspending) and treasury_tic at the country
    tier — all had been sitting un-templated on the shelf since they
    shipped.

    Strategy: walk every source YAML, group by (provider, series_prefix)
    where series_prefix = filename minus the entity-suffix. For each
    group with WIDE coverage of the geo's entities, assert
    classify_source returns a non-None result for at least one. The
    wide-coverage threshold rules out the obvious false positives —
    e.g. BLS county-unemployment ends in ``_<state>`` too
    (``county_unemployment_alexandria_va``) but each county shows up
    once, so its group has 1 entry and stays below the threshold.

    Geo-specific detectors live as nested closures: state = trailing
    ``_<lower-2>`` matching a known abbr; metro = trailing
    ``_<5-digit>`` matching a known CBSA; country = longest-suffix
    match against the canonical slug list (handles ``hong_kong``,
    ``costa_rica``)."""

    def _find_orphans(
        self,
        suffix_detector,
        wide_threshold: int,
        geo_label: str,
    ) -> list[tuple[tuple[str, str], dict]]:
        """Walk source YAMLs, group by (provider, series_prefix) using
        the geo-specific detector, return groups that are wide-coverage
        but have zero classified sources. Each group dict carries
        ``suffixes`` (set), ``classified`` (int), ``example`` (str|None).
        """
        from collections import defaultdict
        sources_dir = HERE.parent / "src" / "content" / "sources"
        groups: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"suffixes": set(), "classified": 0, "example": None},
        )
        for path in sources_dir.rglob("*.yaml"):
            rel = path.relative_to(sources_dir).with_suffix("").as_posix()
            parts = rel.split("/")
            if len(parts) < 2:
                continue
            provider, fname = parts[0], parts[-1]
            detected = suffix_detector(fname)
            if detected is None:
                continue
            prefix, suffix = detected
            g = groups[(provider, prefix)]
            g["suffixes"].add(suffix)
            if gen_idx.classify_source(rel) is not None:
                g["classified"] += 1
            else:
                g["example"] = rel
        return sorted(
            (key, g)
            for key, g in groups.items()
            if len(g["suffixes"]) >= wide_threshold and g["classified"] == 0
        )

    def _fail_with_orphans(
        self,
        orphans: list[tuple[tuple[str, str], dict]],
        geo_label: str,
    ) -> None:
        msg = [
            f"{len(orphans)} per-{geo_label} series have wide {geo_label} "
            "coverage but no matcher in MATCHERS — Generators tab silently "
            "drops them:",
        ]
        for (provider, prefix), g in orphans:
            display = f"{provider}/{prefix}_*" if prefix else f"{provider}/*"
            msg.append(
                f"  {display}  ({len(g['suffixes'])} {geo_label}s, "
                f"e.g. {g['example']})"
            )
        msg.append(
            "Add a matcher per provider in "
            "pipelines/_generate_generators_index.py and register it in MATCHERS."
        )
        self.fail("\n".join(msg))

    def test_no_orphan_state_template(self) -> None:
        state_lower = {a.lower() for a in gen_idx.STATE_ABBR_TO_NAME}

        def detect(fname: str):
            if "_" not in fname:
                return None
            prefix, suffix = fname.rsplit("_", 1)
            if suffix not in state_lower:
                return None
            return (prefix, suffix)

        orphans = self._find_orphans(detect, wide_threshold=25, geo_label="state")
        if orphans:
            self._fail_with_orphans(orphans, "state")

    def test_no_orphan_metro_template(self) -> None:
        # 5-digit CBSA codes only — known via the same crosswalk the
        # matchers use, so a 5-digit non-CBSA suffix (rare; usually a
        # year-vintage) doesn't false-positive.
        import re as _re
        metro_pat = _re.compile(r"^(.+)_(\d{5})$")
        cbsa_set = set(gen_idx.CBSA_LABELS)

        def detect(fname: str):
            m = metro_pat.match(fname)
            if not m:
                return None
            prefix, cbsa = m.group(1), m.group(2)
            if cbsa not in cbsa_set:
                return None
            return (prefix, cbsa)

        # ~390 CBSAs total; 50 is a clear "fanned out across most metros".
        orphans = self._find_orphans(detect, wide_threshold=50, geo_label="metro")
        if orphans:
            self._fail_with_orphans(orphans, "metro")

    def test_no_orphan_country_template(self) -> None:
        # Country slugs are variable-length ("us", "hong_kong"); use the
        # canonical slug list with longest-suffix matching to avoid
        # slicing a multi-word slug at the wrong underscore. Empty
        # prefix is fine — some providers ship singleton-per-country
        # (treasury_tic/<country>) with no per-series prefix.
        slugs_by_len = sorted(gen_idx.COUNTRY_SLUGS_BY_LEN, key=len, reverse=True)

        def detect(fname: str):
            for slug in slugs_by_len:
                if fname == slug:
                    return ("", slug)
                if fname.endswith("_" + slug):
                    return (fname[: -len(slug) - 1], slug)
            return None

        # ~250 worldbank slugs total (sovereigns + regional aggregates);
        # 30 is comfortably above the noise floor.
        orphans = self._find_orphans(detect, wide_threshold=30, geo_label="country")
        if orphans:
            self._fail_with_orphans(orphans, "country")


if __name__ == "__main__":
    unittest.main()
