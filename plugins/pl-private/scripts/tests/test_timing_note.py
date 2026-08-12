import unittest

import timing_note


def timing_row(**kw):
    base = {"Total elapsed": 101.0, "Largest gap": 18.5,
            "Largest gap after": "orders:end", "Unattributed": 41.6}
    base.update(kw)
    return base


class FormatNoteTests(unittest.TestCase):
    def test_kapten_row_produces_the_exact_note(self):
        expected = ("Total 101.0 min. Largest gap 18.5 min after orders:end "
                    "(18% of total). Unattributed 41.6 min (41% of total) — "
                    "size and location only, not a diagnosis.")
        self.assertEqual(timing_note.format_note(timing_row()), expected)

    def test_no_timing_data_returns_none(self):
        """Currys' shape: everything null because it predates instrumentation.

        None here means silence, not a zero — the same rule `largest_gap()`
        already follows for an unmeasured run.
        """
        row = {"Total elapsed": None, "Largest gap": None,
               "Largest gap after": None, "Unattributed": None}
        self.assertIsNone(timing_note.format_note(row))

    def test_missing_gap_omits_the_gap_sentence(self):
        row = timing_row(**{"Largest gap": None, "Largest gap after": None})
        note = timing_note.format_note(row)
        self.assertNotIn("Largest gap", note)
        self.assertIn("Total 101.0 min.", note)
        self.assertIn("Unattributed 41.6 min", note)

    def test_missing_unattributed_omits_that_sentence(self):
        row = timing_row(**{"Unattributed": None})
        note = timing_note.format_note(row)
        self.assertNotIn("Unattributed", note)
        self.assertIn("Largest gap 18.5 min", note)

    def test_gap_without_a_label_is_omitted_defensively(self):
        """`largest_gap()` always returns the pair together in current code,
        but a gap with no label would otherwise render an incomplete
        sentence — omit rather than guess at wording.
        """
        row = timing_row(**{"Largest gap after": None})
        note = timing_note.format_note(row)
        self.assertNotIn("Largest gap", note)

    def test_percentages_round_to_whole_numbers(self):
        row = timing_row(**{"Total elapsed": 60.0, "Largest gap": 10.0,
                            "Largest gap after": "beat2:end",
                            "Unattributed": 20.0})
        note = timing_note.format_note(row)
        self.assertIn("(17% of total)", note)
        self.assertIn("(33% of total)", note)

    def test_never_claims_a_cause(self):
        """The load-bearing rule from the design doc: report, don't diagnose."""
        note = timing_note.format_note(timing_row())
        for banned in ("because", "caused by", "bottleneck", "the reason"):
            self.assertNotIn(banned, note.lower())


if __name__ == "__main__":
    unittest.main()
