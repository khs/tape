"""
Unit tests for ``audit_source_scales.classify()`` — the heuristic
plausibility check for (value, unit, formatting-style) tuples.

These lock down the refinements from commit fa1c4bc542, which fixed:

  - Unicode crash on Windows (cp1252 can't encode →; switched to ASCII)
  - 189 false positives from over-aggressive heuristics:
      * raw counts in the billions (bushels, people, gallons/day) were
        being flagged "HUGE >= 1B" even though count units stored RAW
        legitimately reach the billions for large aggregates
      * currency with non-billion units ("thousands USD" for state tax
        revenue, "USD" for Zillow home prices) was flagged because the
        audit didn't read the unit text before classifying
      * indices below 1 (St. Louis Fed Stress Index z-score) and above
        10k (Nasdaq) were flagged with a fixed band
      * empty-data series (projection-only / queued metro) were dragged
        into the "Flagged for review" tail

The audit's purpose remains: catch the original "raw dollars stored
as if billions" class of bug (currency-unit ÷ count-unit derivations
producing absurd magnitudes — the bug that triggered the audit's
creation in the first place). These tests check that real-bug shapes
still flag while legitimate values pass.

Run locally with::

    python -m unittest pipelines.test_audit_source_scales

CI runs the file via ``python -m unittest`` so the heuristic stays
locked down across future edits.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "audit_source_scales.py"
spec = importlib.util.spec_from_file_location("audit_source_scales", MODULE_PATH)
assert spec and spec.loader
audit_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_mod)


class ClassifyTest(unittest.TestCase):
    # --- No-data path ----------------------------------------------------

    def test_none_returns_ok_no_data(self) -> None:
        """Projection-only / queued-metro series have JSON files with no
        points — they're not regressions and shouldn't pull into the
        Flagged-for-review tail."""
        self.assertEqual(audit_mod.classify(None, "billions USD", "currency"), "ok-no-data")

    # --- Percent --------------------------------------------------------

    def test_percent_normal_range(self) -> None:
        for value in [0, 0.5, 5.0, 50, 99.9]:
            with self.subTest(value=value):
                self.assertEqual(audit_mod.classify(value, "%", "percent"), "ok")

    def test_percent_unusual_but_possible(self) -> None:
        """China's broad-money/GDP runs above 200%; that's real, not a bug."""
        verdict = audit_mod.classify(227.5, "%", "percent")
        self.assertTrue(verdict.startswith("ok"), f"expected ok, got {verdict!r}")

    def test_percent_implausibly_high_is_flagged(self) -> None:
        verdict = audit_mod.classify(5000, "%", "percent")
        self.assertIn("CHECK", verdict)

    def test_percent_recognized_by_unit_text_when_style_isnt_percent(self) -> None:
        """The classifier should also key on '%' in unit, not just fmt_style."""
        self.assertEqual(audit_mod.classify(50, "% of GDP", "number"), "ok")

    # --- Index ----------------------------------------------------------

    def test_index_z_score_negative(self) -> None:
        """STLFSI z-score can be sub-1 or negative; both fine."""
        verdict = audit_mod.classify(-0.76, "index (z-score)", "number")
        self.assertEqual(verdict, "ok")

    def test_index_market_index_large(self) -> None:
        """Nasdaq-style indices reach 20k; still fine."""
        verdict = audit_mod.classify(20000, "index", "index")
        self.assertEqual(verdict, "ok")

    def test_index_implausibly_high(self) -> None:
        verdict = audit_mod.classify(2e6, "index", "index")
        self.assertIn("CHECK", verdict)

    # --- Currency: unit-text normalization ------------------------------

    def test_currency_billions_typical_us_gdp(self) -> None:
        """US real GDP ~$24T stored as 24000 in 'billions USD'."""
        verdict = audit_mod.classify(24000.0, "billions USD", "currency")
        self.assertEqual(verdict, "ok")

    def test_currency_billions_huge_at_quadrillion(self) -> None:
        """A regression that stored raw dollars (1e16) as if billions."""
        verdict = audit_mod.classify(1e7, "billions USD", "currency")
        self.assertIn("HUGE", verdict)

    def test_currency_thousands_usd_state_tax_revenue(self) -> None:
        """FRED state tax-revenue series ships in 'thousands USD' — a
        4-million value (= $4B) should not be flagged."""
        verdict = audit_mod.classify(4_000_000, "thousands USD", "currency")
        self.assertEqual(verdict, "ok")

    def test_currency_millions_usd(self) -> None:
        verdict = audit_mod.classify(500_000.0, "millions USD", "currency")
        self.assertEqual(verdict, "ok")  # $500B, fine

    def test_currency_raw_usd_zillow_home_price(self) -> None:
        """Zillow ZHVI ships in raw USD; an SF home at $1.1M is real."""
        verdict = audit_mod.classify(1_145_540.0, "USD", "currency")
        self.assertEqual(verdict, "ok")

    def test_currency_sub_cent_memecoin(self) -> None:
        """Shiba Inu trades around $5.6e-6; legitimate."""
        verdict = audit_mod.classify(5.6e-6, "USD", "currency")
        self.assertEqual(verdict, "ok")

    def test_currency_scale_regression_at_quadrillion(self) -> None:
        """The original bug class: raw dollars stored where billions were
        expected. 5e11 raw dollars stored as if billions = $500 sextillion."""
        verdict = audit_mod.classify(5e11, "billions USD", "currency")
        self.assertIn("HUGE", verdict)

    # --- Counts (raw) ----------------------------------------------------

    def test_count_raw_people_china_population(self) -> None:
        """1.4B people stored raw — legitimate."""
        verdict = audit_mod.classify(1.4e9, "people", "number")
        self.assertEqual(verdict, "ok")

    def test_count_raw_bushels_us_corn(self) -> None:
        """US corn harvest ~17B bushels — legitimate raw count."""
        verdict = audit_mod.classify(17e9, "BU", "number")
        self.assertEqual(verdict, "ok")

    def test_count_raw_huge_above_ten_trillion(self) -> None:
        """At 10T+ raw a count is genuinely suspicious — bigger than
        any natural aggregate we ship."""
        verdict = audit_mod.classify(1e13, "people", "number")
        self.assertIn("HUGE", verdict)

    def test_count_zero_for_aggregator_state(self) -> None:
        """DC has no farms, OT='Other states' is a residual — zeros are
        legitimate, not flagged."""
        verdict = audit_mod.classify(0.0, "BU", "number")
        self.assertEqual(verdict, "ok")


if __name__ == "__main__":
    unittest.main()
