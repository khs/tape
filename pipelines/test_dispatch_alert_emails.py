"""Unit tests for the alert-email dispatcher.

The full dispatcher talks to Supabase + a third-party email provider;
end-to-end testing requires both. These tests cover the pieces that
are pure functions or trivially fakeable — message rendering, the
condition phrase, HTML escaping, and the auto-pause decision logic.

Run from repo root:
  python -m unittest pipelines.test_dispatch_alert_emails

Or from this directory:
  python -m unittest test_dispatch_alert_emails
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the in-directory module importable from either pipelines/ or
# the repo root, mirroring the pattern in test_check_alerts.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dispatch_alert_emails as dae  # noqa: E402


class ConditionPhraseTests(unittest.TestCase):
    """condition_phrase renders the prose used in subjects + bullet
    lines. The seven canonical conditions each have a specific
    rendering; anything else falls back to a generic '<cond> <thresh>'
    so the email still ships, just less polished."""

    def test_gt(self) -> None:
        self.assertEqual(dae.condition_phrase("gt", 4.0), "> 4.0")

    def test_gte(self) -> None:
        self.assertEqual(dae.condition_phrase("gte", 4.0), "≥ 4.0")

    def test_lt(self) -> None:
        self.assertEqual(dae.condition_phrase("lt", 4.0), "< 4.0")

    def test_lte(self) -> None:
        self.assertEqual(dae.condition_phrase("lte", 4.0), "≤ 4.0")

    def test_crosses_above(self) -> None:
        self.assertEqual(
            dae.condition_phrase("crosses_above", 0.0),
            "crossed above 0.0",
        )

    def test_crosses_below(self) -> None:
        self.assertEqual(
            dae.condition_phrase("crosses_below", 0.0),
            "crossed below 0.0",
        )

    def test_change_above(self) -> None:
        self.assertEqual(
            dae.condition_phrase("change_above", 0.5),
            "|Δ| > 0.5",
        )

    def test_unknown_falls_back(self) -> None:
        # An unrecognized condition keeps the email shippable instead
        # of crashing the whole dispatch.
        self.assertEqual(
            dae.condition_phrase("not_a_condition", 7.0),
            "not_a_condition 7.0",
        )

    def test_threshold_can_be_int_like(self) -> None:
        # Float inputs come from JSON as floats. 0 renders as 0.0 —
        # confirm we don't accidentally call int().
        self.assertEqual(dae.condition_phrase("gte", 0.0), "≥ 0.0")


class EscapeHtmlTests(unittest.TestCase):
    """The dispatcher injects user-controlled source labels (and
    pause_reason) into HTML email bodies. escape_html is the only
    defense against an attacker setting a source_label like
    `<script>alert(1)</script>` — verify it covers all five entities."""

    def test_ampersand(self) -> None:
        self.assertEqual(dae.escape_html("a & b"), "a &amp; b")

    def test_lt_gt(self) -> None:
        self.assertEqual(
            dae.escape_html("<script>"),
            "&lt;script&gt;",
        )

    def test_quotes(self) -> None:
        self.assertEqual(
            dae.escape_html("she said \"hi\""),
            "she said &quot;hi&quot;",
        )

    def test_single_quote(self) -> None:
        self.assertEqual(dae.escape_html("don't"), "don&#39;t")

    def test_plain_string_untouched(self) -> None:
        self.assertEqual(dae.escape_html("plain text"), "plain text")

    def test_ampersand_first_avoids_double_encoding(self) -> None:
        # If we replaced < then &, the &amp; from < would become
        # &amp;amp;. Encoding & FIRST is the standard order — verify
        # we have it right.
        self.assertEqual(
            dae.escape_html("<a&b>"),
            "&lt;a&amp;b&gt;",
        )


class BuildBatchMessageTests(unittest.TestCase):
    """build_batch_message takes a list of trigger rows and produces
    (subject, text, html). The same body shape is reused for 1 vs N
    triggers — only the subject and headline differ. Verify the
    branch boundaries (0 → ValueError; 1 → singular subject; 2+ →
    'N alerts: <first>, and N-1 more' subject)."""

    @staticmethod
    def _trigger(**kw: object) -> dict[str, object]:
        # Tiny helper that builds a trigger row with sensible defaults
        # so each test can override just the fields it cares about.
        base: dict[str, object] = {
            "id": "00000000-0000-0000-0000-000000000001",
            "source_id": "fred/cpi_yoy",
            "source_label": "CPI YoY",
            "condition": "gte",
            "threshold": 4.0,
            "observed_value": 4.1,
            "observed_t": "2026-05-01",
            "triggered_at": "2026-05-21T00:00:00Z",
        }
        base.update(kw)
        return base

    def test_empty_list_raises(self) -> None:
        # An empty batch is a programming error in the dispatcher —
        # the caller should have skipped sending. We raise rather
        # than emit a blank email.
        with self.assertRaises(ValueError):
            dae.build_batch_message([])

    def test_single_trigger_subject(self) -> None:
        t = self._trigger()
        subject, _text, _html = dae.build_batch_message([t])
        self.assertEqual(subject, "[Tape] CPI YoY ≥ 4.0")

    def test_one_line_flattens_control_chars(self) -> None:
        # The _one_line helper underpins the header-injection guard.
        self.assertEqual(dae._one_line("a\r\nb"), "a b")
        self.assertEqual(dae._one_line("a\tb\x00c"), "a b c")
        self.assertEqual(dae._one_line("  plain  text  "), "plain text")

    def test_source_label_crlf_cannot_inject_header_or_body(self) -> None:
        # Defense in depth (OWASP A05): a CR/LF in a label must never
        # reach the Subject header or split a body line. Labels are
        # catalog-derived today, but neutralize a newline regardless.
        t = self._trigger(source_label="CPI\r\nBcc: evil@example.com")
        subject, text, html = dae.build_batch_message([t])
        self.assertNotIn("\r", subject)
        self.assertNotIn("\n", subject)
        self.assertIn("CPI Bcc: evil@example.com", subject)
        # Bodies: the label is flattened (the raw CRLF sequence is gone).
        self.assertNotIn("CPI\r\nBcc", text)
        self.assertNotIn("CPI\r\nBcc", html)
        self.assertIn("CPI Bcc: evil@example.com", text)

    def test_single_trigger_text_body(self) -> None:
        t = self._trigger()
        _subject, text, _html = dae.build_batch_message([t])
        # "a pending Tape alert" (singular form) for n==1.
        self.assertIn("a pending Tape alert", text)
        self.assertNotIn("alerts.", text)
        self.assertIn("CPI YoY", text)
        self.assertIn("≥ 4.0", text)
        self.assertIn("2026-05-01", text)
        self.assertIn("observed 4.1", text)

    def test_single_trigger_html_body(self) -> None:
        t = self._trigger()
        _subject, _text, html = dae.build_batch_message([t])
        self.assertIn("<strong>CPI YoY</strong>", html)
        self.assertIn("a pending Tape alert", html)
        self.assertIn("Manage your alerts", html)

    def test_two_trigger_subject(self) -> None:
        t1 = self._trigger(source_label="CPI YoY")
        t2 = self._trigger(
            id="00000000-0000-0000-0000-000000000002",
            source_label="Unemployment",
            condition="gte",
            threshold=5.0,
        )
        subject, _text, _html = dae.build_batch_message([t1, t2])
        # Subject names the FIRST trigger and the count of others.
        self.assertEqual(
            subject,
            "[Tape] 2 alerts: CPI YoY ≥ 4.0, and 1 more",
        )

    def test_many_trigger_subject(self) -> None:
        triggers = [
            self._trigger(
                id=f"00000000-0000-0000-0000-00000000000{i}",
                source_label=f"Series {i}",
            )
            for i in range(5)
        ]
        subject, _text, _html = dae.build_batch_message(triggers)
        self.assertTrue(subject.startswith("[Tape] 5 alerts:"))
        self.assertIn("and 4 more", subject)

    def test_two_trigger_text_lists_both(self) -> None:
        t1 = self._trigger(source_label="CPI YoY", observed_value=4.1)
        t2 = self._trigger(
            id="00000000-0000-0000-0000-000000000002",
            source_label="Unemployment",
            observed_value=5.2,
        )
        _subject, text, _html = dae.build_batch_message([t1, t2])
        self.assertIn("CPI YoY", text)
        self.assertIn("Unemployment", text)
        # Plural form when n != 1.
        self.assertIn("2 pending Tape alerts", text)
        # Both observed values appear.
        self.assertIn("4.1", text)
        self.assertIn("5.2", text)

    def test_html_escapes_source_label(self) -> None:
        # User-controlled label injection — verify XSS payload gets
        # escaped before it lands in the email HTML.
        t = self._trigger(source_label="<script>alert(1)</script>")
        _subject, _text, html = dae.build_batch_message([t])
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_manage_url_overrideable(self) -> None:
        t = self._trigger()
        subject, text, html = dae.build_batch_message(
            [t],
            manage_url="https://example.com/x",
        )
        del subject  # subject doesn't include the manage URL
        self.assertIn("https://example.com/x", text)
        self.assertIn("https://example.com/x", html)

    def test_missing_source_label_falls_back_to_id(self) -> None:
        # If source_label is missing (shouldn't happen at the schema
        # level but defensive code), fall back to source_id rather
        # than crashing.
        t = self._trigger()
        del t["source_label"]
        subject, _text, _html = dae.build_batch_message([t])
        self.assertIn("fred/cpi_yoy", subject)


class ShouldAutoPauseRuleTests(unittest.TestCase):
    """should_auto_pause_rule is a pure function used to decide
    whether enough of a rule's recent triggers permanently failed
    delivery (sentinel-stamped) to warrant auto-pausing the rule.

    Threshold defaults to AUTOPAUSE_THRESHOLD (3 of last 5). Tests
    cover boundaries on both sides + the sentinel detection + the
    parallel-arrays consistency guard.
    """

    def test_no_failures_no_pause(self) -> None:
        # All recent triggers delivered successfully — never pause.
        attempts = [1, 1, 1, 1, 1]
        notified = [
            "2026-05-21T00:00:00Z",
            "2026-05-14T00:00:00Z",
            "2026-05-07T00:00:00Z",
            "2026-04-30T00:00:00Z",
            "2026-04-23T00:00:00Z",
        ]
        self.assertFalse(
            dae.should_auto_pause_rule(attempts, notified, threshold=3)
        )

    def test_two_failures_below_threshold_no_pause(self) -> None:
        attempts = [5, 5, 1, 1, 1]
        notified = [
            dae.SENTINEL_DROPPED,
            dae.SENTINEL_DROPPED,
            "2026-05-07T00:00:00Z",
            "2026-04-30T00:00:00Z",
            "2026-04-23T00:00:00Z",
        ]
        self.assertFalse(
            dae.should_auto_pause_rule(attempts, notified, threshold=3)
        )

    def test_three_failures_at_threshold_triggers_pause(self) -> None:
        # Exactly threshold sentinels → pause. The decision is
        # >=, not strict >.
        attempts = [5, 5, 5, 1, 1]
        notified = [
            dae.SENTINEL_DROPPED,
            dae.SENTINEL_DROPPED,
            dae.SENTINEL_DROPPED,
            "2026-04-30T00:00:00Z",
            "2026-04-23T00:00:00Z",
        ]
        self.assertTrue(
            dae.should_auto_pause_rule(attempts, notified, threshold=3)
        )

    def test_all_failures_triggers_pause(self) -> None:
        attempts = [5, 5, 5, 5, 5]
        notified = [dae.SENTINEL_DROPPED] * 5
        self.assertTrue(
            dae.should_auto_pause_rule(attempts, notified, threshold=3)
        )

    def test_pending_triggers_dont_count(self) -> None:
        # notified_at IS NULL = still pending (queued). NULL is NOT
        # a sentinel match — these should NOT contribute to the
        # auto-pause count. Otherwise the very FIRST run with a
        # batch of fresh triggers would auto-pause.
        attempts = [0, 0, 0, 1, 1]
        notified = [None, None, None, "2026-04-30T00:00:00Z", "2026-04-23T00:00:00Z"]
        self.assertFalse(
            dae.should_auto_pause_rule(attempts, notified, threshold=3)
        )

    def test_mismatched_array_lengths_returns_false(self) -> None:
        # Defensive: the caller should always pass parallel arrays
        # of the same length. If they don't, don't auto-pause (let
        # a human notice the bug rather than silently locking out
        # the user's rule).
        self.assertFalse(
            dae.should_auto_pause_rule([1, 2, 3], [None], threshold=1)
        )

    def test_empty_history_no_pause(self) -> None:
        # Rule with no triggers yet → nothing to compare → no pause.
        self.assertFalse(
            dae.should_auto_pause_rule([], [], threshold=3)
        )

    def test_custom_sentinel(self) -> None:
        # The sentinel is configurable via kwarg; verify the function
        # uses the passed value rather than hardcoding SENTINEL_DROPPED.
        custom = "9999-12-31T23:59:59Z"
        attempts = [5, 5, 5]
        notified = [custom, custom, custom]
        # Default sentinel — no match → no pause.
        self.assertFalse(
            dae.should_auto_pause_rule(attempts, notified, threshold=3)
        )
        # Custom sentinel — match → pause.
        self.assertTrue(
            dae.should_auto_pause_rule(
                attempts, notified, threshold=3, sentinel=custom
            )
        )

    def test_threshold_one_pauses_on_first_failure(self) -> None:
        # An aggressive user setting threshold=1 should pause as
        # soon as a single sentinel is in the window.
        attempts = [5, 1, 1, 1, 1]
        notified = [
            dae.SENTINEL_DROPPED,
            "2026-05-14T00:00:00Z",
            "2026-05-07T00:00:00Z",
            "2026-04-30T00:00:00Z",
            "2026-04-23T00:00:00Z",
        ]
        self.assertTrue(
            dae.should_auto_pause_rule(attempts, notified, threshold=1)
        )


class EnvIntTests(unittest.TestCase):
    """env_int is a small wrapper that reads an int env var with a
    fallback. Trivial but the dispatcher's tunables depend on it so
    a broken parse would silently change behavior."""

    def setUp(self) -> None:
        # Clean the test env vars so we control them per-test.
        import os

        for k in (
            "DAE_TEST_INT",
            "DAE_TEST_BAD",
            "DAE_TEST_EMPTY",
        ):
            os.environ.pop(k, None)

    def test_unset_returns_default(self) -> None:
        self.assertEqual(dae.env_int("DAE_TEST_INT", 7), 7)

    def test_set_returns_parsed(self) -> None:
        import os

        os.environ["DAE_TEST_INT"] = "42"
        self.assertEqual(dae.env_int("DAE_TEST_INT", 7), 42)

    def test_empty_returns_default(self) -> None:
        import os

        os.environ["DAE_TEST_EMPTY"] = ""
        self.assertEqual(dae.env_int("DAE_TEST_EMPTY", 5), 5)

    def test_unparseable_returns_default(self) -> None:
        # A malformed env var must NOT crash the dispatcher at module
        # import time — the default keeps things working.
        import os

        os.environ["DAE_TEST_BAD"] = "not-an-int"
        self.assertEqual(dae.env_int("DAE_TEST_BAD", 99), 99)


if __name__ == "__main__":
    unittest.main()
