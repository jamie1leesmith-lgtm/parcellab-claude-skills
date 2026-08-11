"""Unit tests for build_telemetry_row. Stdlib unittest — no pytest, no network."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import build_telemetry_row as btr  # noqa: E402
import run_state  # noqa: E402

MANIFEST = {
    "run": {"id": "uniqlo-20260811-1913", "pace": "standard"},
    "path": "engage",
    "brand": {"name": "UNIQLO", "url": "https://www.uniqlo.com/uk/en/",
              "region": "UK", "category": "Fashion"},
    "account": {"id": 1626718, "name": "Demo - Jamie Lee-Smith"},
    "orders": [
        {"label": "Clean delivery", "shipments": [
            {"label": "A", "events": ["InTransit", "OutForDelivery",
                                      "Delivered"]}]},
        {"label": "Split", "shipments": [
            {"label": "A", "events": ["InTransit", "Delivered"]},
            {"label": "B", "events": ["InTransit", "WarehouseDelay"]}]},
    ],
}


def a_run(finished=True, with_failure=False):
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "results").mkdir()
    (d / "demo-manifest.json").write_text(json.dumps(MANIFEST))
    run_state.init(d, "uniqlo-20260811-1913", "engage", "Demo - JLS")
    run_state.set_lane(d, "scrape", "ok")
    run_state.set_lane(d, "template", "published", layout_id=20701)
    run_state.set_lane(d, "seed", "skipped")
    run_state.set_lane(d, "orders", "ok")
    run_state.set_lane(d, "cdc", "failed" if with_failure else "ok")
    run_state.add_order(d, "Clean delivery", "UNQ-1", [
        {"label": "A", "tracking_number": "TN1", "courier": "dpd-uk",
         "planned": ["InTransit", "OutForDelivery", "Delivered"]}])
    for status in ("InTransit", "OutForDelivery", "Delivered"):
        run_state.confirm_event(d, "TN1", status, "2026-08-11T18:43:27Z", 204)
    if with_failure:
        run_state.add_failure(d, "cdc", "500 from API")
    if finished:
        run_state.finish(d)
    return d


class TestBuildTelemetryRow(unittest.TestCase):
    def test_identity_fields_come_from_the_manifest(self):
        row = btr.build_row(a_run(), "beat2", skill_version="f0ee309")
        self.assertEqual(row["Run ID"], "uniqlo-20260811-1913")
        self.assertEqual(row["Brand"], "UNIQLO")
        self.assertEqual(row["Path"], "engage")
        self.assertEqual(row["Account"], 1626718)
        self.assertEqual(row["Skill version"], "f0ee309")

    def test_stage_sets_outcome_and_reached(self):
        self.assertEqual(btr.build_row(a_run(), "committed")["Outcome"],
                         "Committed")
        self.assertEqual(btr.build_row(a_run(), "beat2")["Outcome"], "Verified")

    def test_counts_events_pushed_and_confirmed(self):
        row = btr.build_row(a_run(), "beat2")
        self.assertEqual(row["Events pushed"], 3)

    def test_failed_lane_appears_in_lanes_failed(self):
        row = btr.build_row(a_run(with_failure=True), "beat2")
        self.assertIn("cdc", row["Lanes failed"])

    def test_clean_run_has_no_lanes_failed(self):
        self.assertEqual(btr.build_row(a_run(), "beat2")["Lanes failed"], [])

    def test_skipped_lane_is_not_a_failure(self):
        self.assertNotIn("seed", btr.build_row(a_run(), "beat2")["Lanes failed"])

    def test_api_error_deviation_is_derived_mechanically(self):
        d = a_run(with_failure=True)
        deviations = btr.derive_deviations(run_state.load(d), {})
        self.assertIn("api_error", deviations)

    def test_no_deviations_on_a_clean_run(self):
        d = a_run()
        self.assertEqual(btr.derive_deviations(run_state.load(d), {}), [])

    def test_every_derived_deviation_is_in_the_taxonomy(self):
        d = a_run(with_failure=True)
        for dev in btr.derive_deviations(run_state.load(d), {}):
            self.assertIn(dev, btr.DEVIATIONS)

    def test_row_contains_no_triage_columns(self):
        # Triage is written by review, never by a run — a run must not be able
        # to clobber it. Triage status is the one permitted exception: it is
        # always set to Untriaged on creation so unreviewed rows are
        # findable by value.
        row = btr.build_row(a_run(), "beat2")
        for column in ("Reviewed at", "Action taken",
                       "Fix commit", "Verified in run", "Reviewed by"):
            self.assertNotIn(column, row)

    def test_row_carries_no_customer_pii(self):
        blob = json.dumps(btr.build_row(a_run(), "beat2"))
        self.assertNotIn("@", blob.replace("https://", ""))

    def test_unfinished_run_reports_stalled(self):
        row = btr.build_row(a_run(finished=False), "beat2")
        self.assertEqual(row["Outcome"], "Stalled")


class TestTimingColumns(unittest.TestCase):
    def _run_dir(self):
        import json
        import pathlib
        import tempfile
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "orders").mkdir()
        (d / "results").mkdir()
        (d / "run-state.json").write_text(json.dumps({
            "run_id": "currys-1",
            "lanes": {},
            "orders": [],
            "failures": [],
            "timeline": [
                {"kind": "lane", "name": "scrape", "phase": "start",
                 "at": "2026-08-11T20:50:00Z"},
                {"kind": "lane", "name": "scrape", "phase": "end",
                 "at": "2026-08-11T21:00:00Z"},
                {"kind": "gate", "name": "plan", "phase": "asked",
                 "at": "2026-08-11T21:02:00Z"},
                {"kind": "gate", "name": "plan", "phase": "answered",
                 "at": "2026-08-11T21:05:00Z"},
            ],
        }))
        (d / "demo-manifest.json").write_text(json.dumps(
            {"brand": {"name": "Currys"}, "orders": []}))
        return str(d)

    def test_timing_columns_are_present_and_derived(self):
        row = btr.build_row(self._run_dir(), "beat1")
        self.assertEqual(row["Total elapsed"], 15.0)
        self.assertEqual(row["Measured working time"], 10.0)
        self.assertEqual(row["Waiting on user"], 3.0)
        self.assertEqual(row["Slowest lane"], "scrape")
        self.assertGreaterEqual(row["Unattributed"], 0)

    def test_timeline_is_serialised_as_json_text(self):
        import json
        row = btr.build_row(self._run_dir(), "beat1")
        self.assertIsInstance(row["Timeline"], str)
        self.assertEqual(len(json.loads(row["Timeline"])), 4)

    def test_triage_status_starts_untriaged(self):
        # Blank makes unreviewed rows findable only by querying for empty.
        row = btr.build_row(self._run_dir(), "committed")
        self.assertEqual(row["Triage status"], "Untriaged")

    def test_triage_status_is_written_only_at_row_creation(self):
        # Emitting it at beat1/beat2 resets whatever a reviewer set.
        for stage in ("beat1", "beat2"):
            self.assertNotIn("Triage status", btr.build_row(self._run_dir(),
                                                            stage))

    def test_duration_to_build_is_derived_not_a_duplicate_of_total(self):
        d = pathlib.Path(self._run_dir())
        state = json.loads((d / "run-state.json").read_text())
        state["timeline"].append({"kind": "gate", "name": "beat1",
                                  "phase": "end", "at": "2026-08-11T21:35:00Z"})
        (d / "run-state.json").write_text(json.dumps(state))
        row = btr.build_row(d, "beat1")
        self.assertEqual(row["Duration to build"], 30.0)
        self.assertNotEqual(row["Duration to build"], row["Total elapsed"])

    def test_duration_to_build_is_null_without_a_beat1_mark(self):
        row = btr.build_row(self._run_dir(), "beat1")
        self.assertIsNone(row["Duration to build"])

    def test_missing_run_state_still_builds_a_partial_row(self):
        # Telemetry is an observer, never a dependency: a run dir with no
        # run-state.json must yield nulls, not a FileNotFoundError.
        d = pathlib.Path(self._run_dir())
        (d / "run-state.json").unlink()
        row = btr.build_row(d, "beat1")
        self.assertIsNone(row["Total elapsed"])
        self.assertEqual(row["Brand"], "Currys")

    def test_no_other_triage_column_is_written(self):
        row = btr.build_row(self._run_dir(), "beat1")
        for column in ("Issue key", "Reviewed at", "Reviewed by",
                       "Action taken", "Fix commit", "Verified in run"):
            self.assertNotIn(column, row)


if __name__ == "__main__":
    unittest.main()
