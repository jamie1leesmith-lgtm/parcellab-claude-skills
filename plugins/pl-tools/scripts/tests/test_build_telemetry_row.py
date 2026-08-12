"""Unit tests for build_telemetry_row. Stdlib unittest — no pytest, no network."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import build_telemetry_row as btr  # noqa: E402
import run_state  # noqa: E402
import timings  # noqa: E402

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

    def _kapten_run_dir(self):
        """A run with a measurable gap extending to the horizon mark.

        The largest gap is 18.5 minutes (1110 seconds) after orders:end.
        This scenario tests the horizon-extension branch in largest_gap():
        Beat 2 records only an `end` mark with no matching `start`, which
        extends the measurement horizon beyond closed spans.
        """
        d = pathlib.Path(self._run_dir())
        state = json.loads((d / "run-state.json").read_text())
        state["timeline"] = [
            {"kind": "lane", "name": "orders", "phase": "start",
             "at": "2026-08-12T10:53:22Z"},
            {"kind": "lane", "name": "orders", "phase": "end",
             "at": "2026-08-12T11:09:34Z"},
            {"kind": "gate", "name": "beat2", "phase": "end",
             "at": "2026-08-12T11:28:06Z"},
        ]
        (d / "run-state.json").write_text(json.dumps(state))
        return str(d)

    def _single_stamp_run_dir(self):
        """A run with only one timestamp entry (cannot measure a gap)."""
        d = pathlib.Path(self._run_dir())
        state = json.loads((d / "run-state.json").read_text())
        state["timeline"] = [
            {"kind": "lane", "name": "orders", "phase": "start",
             "at": "2026-08-12T20:00:00Z"},
        ]
        (d / "run-state.json").write_text(json.dumps(state))
        return str(d)

    def _corrupt_run_dir(self):
        """A run whose lane marks are reversed — an impossible duration."""
        import json
        import pathlib
        d = pathlib.Path(self._run_dir())
        state = json.loads((d / "run-state.json").read_text())
        state["timeline"] = [
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-11T21:00:00Z"},
            {"kind": "lane", "name": "scrape", "phase": "end",
             "at": "2026-08-11T20:50:00Z"},
        ]
        (d / "run-state.json").write_text(json.dumps(state))
        return str(d)

    def test_a_corrupt_span_costs_its_durations_not_the_whole_row(self):
        # Telemetry is an observer, never a dependency: one reversed pair of
        # marks must not take out the ~20 columns that are not durations.
        row = btr.build_row(self._corrupt_run_dir(), "beat1")
        self.assertEqual(row["Run ID"], "currys-1")
        self.assertEqual(row["Brand"], "Currys")
        self.assertIsNone(row["Total elapsed"])
        self.assertIsNone(row["Measured working time"])

    def test_a_corrupt_span_is_named_in_error_detail(self):
        # Silently nulling five columns would hide the corruption; the row
        # must say why the numbers are missing.
        row = btr.build_row(self._corrupt_run_dir(), "beat1")
        self.assertIn("timing", row["Error detail"])
        self.assertIn("before it starts", row["Error detail"])

    def test_a_clean_run_leaves_error_detail_alone(self):
        self.assertEqual(btr.build_row(self._run_dir(), "beat1")["Error detail"],
                         "")

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

    def test_row_carries_the_largest_gap_columns(self):
        row = btr.build_row(self._kapten_run_dir(), "beat2", skill_version="abc1234")
        self.assertEqual(row["Largest gap"], 18.5)
        self.assertEqual(row["Largest gap after"], "orders:end")

    def test_largest_gap_is_null_when_unmeasurable(self):
        """A one-stamp run is unmeasured, not instantaneous."""
        row = btr.build_row(
            self._single_stamp_run_dir(), "committed", skill_version="abc1234")
        self.assertIsNone(row["Largest gap"])
        self.assertIsNone(row["Largest gap after"])



class TestPageColumns(unittest.TestCase):
    def test_timeline_json_passes_short_timelines_through(self):
        timeline = [{"kind": "gate", "name": "plan", "phase": "asked",
                     "at": "2026-08-12T10:00:00Z"}]
        self.assertEqual(json.loads(btr.timeline_json(timeline)), timeline)

    def test_timeline_json_truncates_oldest_and_marks_the_loss(self):
        timeline = [{"kind": "lane", "name": f"lane{i}", "phase": "start",
                     "at": "2026-08-12T10:00:00Z"} for i in range(200)]
        text = btr.timeline_json(timeline)
        self.assertLessEqual(len(text), 1900)
        payload = json.loads(text)
        self.assertIn("truncated", payload[0])
        self.assertGreater(payload[0]["truncated"], 0)
        self.assertEqual(payload[-1]["name"], "lane199")

    def test_agent_entries_duplicating_a_lane_are_dropped(self):
        timeline = [
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:47:05"},
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:47:05"},
        ]
        payload = json.loads(btr.timeline_json(timeline))
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["kind"], "lane")

    def test_agent_entry_with_its_own_timestamp_is_kept(self):
        """Only exact duplicates go. A distinct stamp is real information."""
        timeline = [
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:47:05"},
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:48:30"},
        ]
        payload = json.loads(btr.timeline_json(timeline))
        self.assertEqual(len(payload), 2)

    def test_compact_separators(self):
        timeline = [{"kind": "lane", "name": "seed", "phase": "start",
                     "at": "2026-08-12T10:36:26"}]
        self.assertNotIn(", ", btr.timeline_json(timeline))

    def test_truncation_marker_still_applies(self):
        timeline = [{"kind": "lane", "name": f"lane{i}", "phase": "start",
                     "at": "2026-08-12T10:36:26"} for i in range(200)]
        payload = json.loads(btr.timeline_json(timeline))
        self.assertIn("truncated", payload[0])
        self.assertLessEqual(len(btr.timeline_json(timeline)), 1900)

    def test_page_counts_and_url_stability(self):
        page = {"renders": [{"at": "2026-08-12T10:00:00Z"}] * 3,
                "publishes": [
                    {"at": "2026-08-12T10:00:01Z", "url": "https://x.test/a"},
                    {"at": "2026-08-12T10:00:02Z", "url": "https://x.test/a"}]}
        cols = btr.page_columns(page, [])
        self.assertEqual(cols["Page renders"], 3)
        self.assertEqual(cols["Page publishes"], 2)
        self.assertEqual(cols["Page URL changes"], 0)

    def test_page_url_change_is_counted(self):
        page = {"renders": [], "publishes": [
            {"at": "2026-08-12T10:00:01Z", "url": "https://x.test/a"},
            {"at": "2026-08-12T10:00:02Z", "url": "https://x.test/b"}]}
        self.assertEqual(btr.page_columns(page, [])["Page URL changes"], 1)

    def test_page_columns_are_null_without_publishes(self):
        cols = btr.page_columns(
            {"renders": [{"at": "2026-08-12T10:00:00Z"}], "publishes": []}, [])
        self.assertEqual(cols["Page renders"], 1)
        self.assertEqual(cols["Page publishes"], 0)
        self.assertIsNone(cols["Page URL changes"])
        self.assertIsNone(cols["Page cadence"])
        self.assertIsNone(cols["Max page gap"])

    def test_page_cadence_counts_seconds_from_the_first_render(self):
        page = {"renders": [{"at": "2026-08-12T10:00:00Z"}],
                "publishes": [{"at": "2026-08-12T10:00:05Z", "url": "u"},
                              {"at": "2026-08-12T10:01:00Z", "url": "u"}]}
        self.assertEqual(btr.page_columns(page, [])["Page cadence"], "5,60")

    def test_max_page_gap_uses_only_publishes_inside_the_driver_window(self):
        page = {"renders": [], "publishes": [
            {"at": "2026-08-12T10:00:00Z", "url": "u"},
            {"at": "2026-08-12T10:10:00Z", "url": "u"},
            {"at": "2026-08-12T10:14:00Z", "url": "u"},
            {"at": "2026-08-12T10:15:00Z", "url": "u"},
            {"at": "2026-08-12T11:00:00Z", "url": "u"}]}
        drivers = [{"kind": "driver", "name": "01",
                    "start": timings.parse_ts("2026-08-12T10:05:00Z"),
                    "end": timings.parse_ts("2026-08-12T10:20:00Z")}]
        self.assertEqual(btr.page_columns(page, drivers)["Max page gap"], 4.0)

    def test_max_page_gap_is_null_while_a_driver_is_unfinished(self):
        page = {"renders": [], "publishes": [
            {"at": "2026-08-12T10:10:00Z", "url": "u"},
            {"at": "2026-08-12T10:14:00Z", "url": "u"}]}
        drivers = [{"kind": "driver", "name": "01",
                    "start": timings.parse_ts("2026-08-12T10:05:00Z"),
                    "end": None}]
        self.assertIsNone(btr.page_columns(page, drivers)["Max page gap"])

    def test_page_columns_tolerate_a_missing_page_section(self):
        cols = btr.page_columns(None, [])
        self.assertEqual(cols["Page renders"], 0)
        self.assertEqual(cols["Page publishes"], 0)
        self.assertIsNone(cols["Page cadence"])


if __name__ == "__main__":
    unittest.main()
