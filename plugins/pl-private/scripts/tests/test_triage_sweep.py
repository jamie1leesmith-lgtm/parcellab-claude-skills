import unittest

import triage_sweep


def row(**kw):
    base = {"Run ID": "r", "Outcome": "Verified", "Reached": "Beat 2",
            "Comms expected": 12, "Comms fired": 12, "Lanes failed": [],
            "Deviations": [], "Largest gap": 1.0, "Total elapsed": 60.0}
    base.update(kw)
    return base


class MultiSelectTests(unittest.TestCase):
    """The connector's SQL mode returns multi-select columns as JSON strings.

    Found on the first live sweep, 2026-08-12: `len()` on the string counted
    characters, so a 2-deviation row scored 38 and a 4-deviation row 86 —
    ranking by string length, with the order inverted and the numbers still
    looking plausible.
    """

    def test_json_string_counts_items_not_characters(self):
        value = '["comm_missing","workaround_invented"]'
        self.assertEqual(triage_sweep.multi_select(value),
                         ["comm_missing", "workaround_invented"])
        self.assertEqual(len(triage_sweep.multi_select(value)), 2)

    def test_real_list_passes_through(self):
        self.assertEqual(triage_sweep.multi_select(["scrape"]), ["scrape"])

    def test_none_is_no_items(self):
        self.assertEqual(triage_sweep.multi_select(None), [])

    def test_empty_json_array_string_is_no_items(self):
        self.assertEqual(triage_sweep.multi_select("[]"), [])

    def test_malformed_string_is_no_items_not_a_crash(self):
        """A malformed cell must not decide the ranking, or raise."""
        self.assertEqual(triage_sweep.multi_select("not json"), [])

    def test_non_list_json_is_no_items(self):
        self.assertEqual(triage_sweep.multi_select('"comm_missing"'), [])


class SeverityTests(unittest.TestCase):
    def test_clean_run_scores_zero(self):
        self.assertEqual(triage_sweep.severity(row()), 0)

    def test_deviations_as_a_json_string_score_per_item(self):
        """The live-data shape: two deviations must score 2, not 38."""
        scored = triage_sweep.severity(
            row(Deviations='["comm_missing","workaround_invented"]'))
        self.assertEqual(scored, 2)

    def test_failed_lanes_as_a_json_string_score_two_each(self):
        scored = triage_sweep.severity(
            row(**{"Lanes failed": '["orders","cdc"]'}))
        self.assertEqual(scored, 4)

    def test_the_two_real_rows_keep_their_order(self):
        """Regression guard for the inversion.

        Before the fix Currys scored ~88 to Kapten's ~45 on deviation-string
        length alone, putting a completed run above a stalled one that mailed
        nobody.
        """
        kapten = triage_sweep.severity(row(
            Outcome="Stalled", Reached="Beat 2",
            Deviations='["comm_missing","workaround_invented"]',
            **{"Comms expected": 12, "Comms fired": 0}))
        currys = triage_sweep.severity(row(
            Outcome="Built", Reached="Beat 1",
            Deviations='["manual_intervention","instruction_unfollowable",'
                       '"workaround_invented","gate_reasked"]',
            **{"Comms expected": None, "Comms fired": None}))
        self.assertEqual(kapten, 9)
        self.assertEqual(currys, 6)
        self.assertGreater(kapten, currys)

    def test_stalled_outcome_scores(self):
        self.assertEqual(triage_sweep.severity(row(Outcome="Stalled")), 4)

    def test_missing_comms_score(self):
        self.assertEqual(triage_sweep.severity(row(**{"Comms fired": 0})), 3)

    def test_kapten_row(self):
        """Stalled, 0 of 12 comms, two deviations, no failed lane."""
        scored = triage_sweep.severity(row(
            Outcome="Stalled", Deviations=["comm_missing",
                                           "workaround_invented"],
            **{"Comms fired": 0}))
        self.assertEqual(scored, 9)

    def test_a_run_that_never_reached_beat_2_scores(self):
        """No Beat 2 is a stall signal, not missing data.

        The 2026-08-11 Currys run stopped at Beat 1 with Outcome "Built", which
        no other rule catches.
        """
        self.assertEqual(triage_sweep.severity(row(Reached="Beat 1")), 2)

    def test_failed_lanes_score_two_each(self):
        self.assertEqual(
            triage_sweep.severity(row(**{"Lanes failed": ["orders", "cdc"]})),
            4)

    def test_zero_expected_comms_is_not_a_shortfall(self):
        """A zero-planned run is not treated as having missed any comms."""
        self.assertEqual(
            triage_sweep.severity(row(**{"Comms expected": 0,
                                         "Comms fired": 0})), 0)

    def test_null_counts_are_not_a_shortfall(self):
        """A row with null comms counts is not treated as a comms shortfall."""
        self.assertEqual(
            triage_sweep.severity(row(**{"Comms expected": None,
                                         "Comms fired": None})), 0)

    def test_a_row_with_no_reached_key_scores_as_unverified(self):
        """Absent is not neutral here, deliberately.

        Every other field defaults to neutral when missing; this one scores,
        because a row with no `Reached` did not reach Beat 2. `build_telemetry_row`
        writes `Reached` at every stage, so an absent key means the row came from
        somewhere else — which is itself worth surfacing.
        """
        r = row()
        del r["Reached"]
        self.assertEqual(triage_sweep.severity(r), 2)


class RankTests(unittest.TestCase):
    def test_severity_outranks_time(self):
        mild = row(**{"Run ID": "mild", "Largest gap": 40.0})
        severe = row(**{"Run ID": "severe", "Outcome": "Failed",
                        "Largest gap": 1.0})
        self.assertEqual([r["Run ID"] for r in triage_sweep.rank([mild,
                                                                  severe])],
                         ["severe", "mild"])

    def test_time_breaks_a_severity_tie(self):
        slow = row(**{"Run ID": "slow", "Largest gap": 18.5})
        quick = row(**{"Run ID": "quick", "Largest gap": 2.0})
        self.assertEqual([r["Run ID"] for r in triage_sweep.rank([quick,
                                                                  slow])],
                         ["slow", "quick"])

    def test_missing_largest_gap_sorts_last_not_first(self):
        """A null gap is unmeasured, and must not outrank a measured one."""
        unmeasured = row(**{"Run ID": "unmeasured", "Largest gap": None})
        measured = row(**{"Run ID": "measured", "Largest gap": 5.0})
        self.assertEqual(
            [r["Run ID"] for r in triage_sweep.rank([unmeasured, measured])],
            ["measured", "unmeasured"])


if __name__ == "__main__":
    unittest.main()
