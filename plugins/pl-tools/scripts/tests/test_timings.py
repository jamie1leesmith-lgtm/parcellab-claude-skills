"""Unit tests for timings. Stdlib unittest — no pytest."""
import datetime
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import timings  # noqa: E402


def dt(hh, mm, ss=0):
    return datetime.datetime(2026, 8, 11, hh, mm, ss)


class TestParseTs(unittest.TestCase):
    def test_parses_second_precision(self):
        self.assertEqual(timings.parse_ts("2026-08-11T21:35:56Z"), dt(21, 35, 56))

    def test_parses_millisecond_precision(self):
        # events.jsonl stamps carry .000Z; the timeline does not.
        self.assertEqual(timings.parse_ts("2026-08-11T21:38:56.000Z"),
                         dt(21, 38, 56))

    def test_none_passes_through(self):
        self.assertIsNone(timings.parse_ts(None))

    def test_unparseable_raises(self):
        with self.assertRaises(ValueError):
            timings.parse_ts("yesterday")


class TestPairIntervals(unittest.TestCase):
    def test_pairs_start_and_end_by_name(self):
        timeline = [
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:52:00Z"},
            {"kind": "lane", "name": "scrape", "phase": "end",
             "at": "2026-08-11T21:01:00Z"},
        ]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "scrape")
        self.assertEqual(spans[0]["start"], dt(20, 52))
        self.assertEqual(spans[0]["end"], dt(21, 1))

    def test_unclosed_interval_has_no_end(self):
        # An agent that died mid-run. Must not report zero, and must not be
        # silently stretched to the end of the run.
        timeline = [{"kind": "agent", "name": "seed", "phase": "start",
                     "at": "2026-08-11T21:00:00Z"}]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(len(spans), 1)
        self.assertIsNone(spans[0]["end"])

    def test_gate_asked_answered_pairs(self):
        timeline = [
            {"kind": "gate", "name": "plan", "phase": "asked",
             "at": "2026-08-11T21:20:00Z"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T21:23:00Z"},
        ]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(spans[0]["start"], dt(21, 20))
        self.assertEqual(spans[0]["end"], dt(21, 23))

    def test_repeated_marks_make_one_span_each(self):
        # A re-asked gate is an enumerated deviation. Keeping the first open
        # and the last close would report 65 minutes of waiting against a
        # truth of 10.
        timeline = [
            {"kind": "gate", "name": "plan", "phase": "asked",
             "at": "2026-08-11T20:00:00Z"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T20:05:00Z"},
            {"kind": "gate", "name": "plan", "phase": "asked",
             "at": "2026-08-11T21:00:00Z"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T21:05:00Z"},
        ]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(len(spans), 2)
        self.assertEqual((spans[0]["start"], spans[0]["end"]),
                         (dt(20, 0), dt(20, 5)))
        self.assertEqual((spans[1]["start"], spans[1]["end"]),
                         (dt(21, 0), dt(21, 5)))

    def test_reopen_before_close_leaves_the_first_span_unclosed(self):
        timeline = [
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:00:00Z"},
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:10:00Z"},
            {"kind": "agent", "name": "scrape", "phase": "end",
             "at": "2026-08-11T20:20:00Z"},
        ]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(len(spans), 2)
        self.assertIsNone(spans[0]["end"])
        self.assertEqual(spans[1]["end"], dt(20, 20))

    def test_same_name_in_different_kinds_does_not_cross_pair(self):
        timeline = [
            {"kind": "lane", "name": "seed", "phase": "start",
             "at": "2026-08-11T21:00:00Z"},
            {"kind": "agent", "name": "seed", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "agent", "name": "seed", "phase": "end",
             "at": "2026-08-11T21:07:00Z"},
            {"kind": "lane", "name": "seed", "phase": "end",
             "at": "2026-08-11T21:10:00Z"},
        ]
        spans = {(s["kind"], s["name"]): s for s in timings.pair_intervals(timeline)}
        self.assertEqual(spans[("lane", "seed")]["end"], dt(21, 10))
        self.assertEqual(spans[("agent", "seed")]["end"], dt(21, 7))


class TestUnionSeconds(unittest.TestCase):
    def test_disjoint_spans_add_up(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 5)),
                                   (dt(11, 0), dt(11, 5))]), 600)

    def test_overlapping_spans_are_not_double_counted(self):
        # The whole reason union exists: the scrape agent runs during the
        # intake interview, so summing would count the same minutes twice.
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 10)),
                                   (dt(10, 5), dt(10, 15))]), 900)

    def test_fully_contained_span_adds_nothing(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 30)),
                                   (dt(10, 5), dt(10, 10))]), 1800)

    def test_unclosed_spans_are_ignored(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 5)),
                                   (dt(11, 0), None)]), 300)

    def test_no_spans_is_zero(self):
        self.assertEqual(timings.union_seconds([]), 0)

    def test_touching_spans_merge(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 5)),
                                   (dt(10, 5), dt(10, 10))]), 600)

    def test_reversed_span_raises(self):
        # An impossible union must raise rather than return -600, which would
        # make `covered` negative and inflate `unattributed` above the total.
        with self.assertRaises(ValueError):
            timings.union_seconds([(dt(10, 0), dt(9, 50))])



import json  # noqa: E402
import tempfile  # noqa: E402


def a_run_dir(timeline=None, logs=None):
    """A run dir with a timeline and optional per-order run.log files."""
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "orders").mkdir()
    (d / "run-state.json").write_text(json.dumps(
        {"run_id": "currys-1", "timeline": timeline or []}))
    for name, lines in (logs or {}).items():
        (d / "orders" / name).mkdir(parents=True, exist_ok=True)
        (d / "orders" / name / "run.log").write_text("\n".join(lines) + "\n")
    return str(d)


def start_line(stamp, events, dryrun=0):
    """A START line in exactly the shape `run-lifecycle.sh:72` emits.

    Fixtures that drop the `dryrun=` token do not exercise the live path,
    so a regression in the guard would leave the suite green.
    """
    return (f"{stamp} START sequence: {events} events, gap=180s, "
            f"dryrun={dryrun}, endpoint=/v4/track/events/, account=1626718")


DRIVER_LOGS = {
    # Concurrent: 3, 5 and 4 events, all launched together. The window is the
    # longest order, not the total — this is the 2026-08-11 miscalculation.
    "01-clean-low": [start_line("2026-08-11T21:35:56Z", 3),
                     "2026-08-11T21:45:00Z DONE sequence complete"],
    "02-split-medium": [start_line("2026-08-11T21:36:01Z", 5),
                        "2026-08-11T21:51:06Z DONE sequence complete"],
    "03-recovered-high": [start_line("2026-08-11T21:36:06Z", 4),
                          "2026-08-11T21:48:09Z DONE sequence complete"],
}


class TestDriverIntervals(unittest.TestCase):
    def test_reads_start_and_end_from_run_log(self):
        spans = timings.driver_intervals(a_run_dir(logs=DRIVER_LOGS))
        by_name = {s["name"]: s for s in spans}
        self.assertEqual(by_name["01-clean-low"]["start"], dt(21, 35, 56))
        self.assertEqual(by_name["01-clean-low"]["end"], dt(21, 45, 0))

    def test_unfinished_driver_has_no_end(self):
        logs = {"01-clean-low": [start_line("2026-08-11T21:35:56Z", 3),
                                 "2026-08-11T21:38:56Z EVENT 1/3"]}
        spans = timings.driver_intervals(a_run_dir(logs=logs))
        self.assertIsNone(spans[0]["end"])

    def test_no_orders_gives_no_intervals(self):
        self.assertEqual(timings.driver_intervals(a_run_dir()), [])

    def test_dry_run_pass_is_not_counted_as_the_driver_start(self):
        # Both SKILL.mds mandate a DRYRUN=1 pass into the same run.log
        # immediately before the live launch. Anchoring on lines[0] made a
        # 3.0-minute order read as 6.7.
        logs = {"01-fraud-low-happy": [
            "2026-08-11T17:39:29Z START sequence: 3 events, gap=180s, "
            "dryrun=1, endpoint=/v4/track/events/, account=1626718",
            "2026-08-11T17:39:29Z DONE sequence complete",
            "2026-08-11T17:43:12Z START sequence: 3 events, gap=180s, "
            "dryrun=0, endpoint=/v4/track/events/, account=1626718",
            "2026-08-11T17:46:13Z DONE sequence complete",
        ]}
        spans = timings.driver_intervals(a_run_dir(logs=logs))
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["start"], dt(17, 43, 12))
        self.assertEqual(spans[0]["end"], dt(17, 46, 13))

    def test_dry_run_only_log_has_no_driver_interval(self):
        logs = {"01-fraud-low-happy": [
            "2026-08-11T17:39:29Z START sequence: 3 events, gap=180s, "
            "dryrun=1, endpoint=/v4/track/events/, account=1626718",
            "2026-08-11T17:39:29Z DONE sequence complete",
        ]}
        self.assertEqual(timings.driver_intervals(a_run_dir(logs=logs)), [])

    def test_malformed_done_line_leaves_the_driver_unfinished(self):
        logs = {"01-clean-low": [
            start_line("2026-08-11T21:35:56Z", 3),
            "not-a-timestamp DONE sequence complete",
        ]}
        spans = timings.driver_intervals(a_run_dir(logs=logs))
        self.assertEqual(spans[0]["start"], dt(21, 35, 56))
        self.assertIsNone(spans[0]["end"])

    def test_malformed_first_line_skips_that_driver_only(self):
        # A partial write or truncated flush in one order's log must not take
        # down the whole report — only that driver is skipped.
        logs = {
            "01-garbled": [start_line("not-a-timestamp", 1)],
            "02-clean-low": DRIVER_LOGS["01-clean-low"],
        }
        spans = timings.driver_intervals(a_run_dir(logs=logs))
        names = {s["name"] for s in spans}
        self.assertNotIn("01-garbled", names)
        self.assertIn("02-clean-low", names)

    def test_log_with_no_dryrun_token_has_no_driver_interval(self):
        # The guard must fail CLOSED. If the driver's START line is ever
        # reworded or loses the flag, there is no way to tell a dry-run pass
        # from the live one — and a dry run's stamp inflates the window.
        # A missing mark yields a null, never a wrong number.
        logs = {"01-clean-low": [
            "2026-08-11T21:35:56Z START sequence: 3 events",
            "2026-08-11T21:45:00Z DONE sequence complete",
        ]}
        self.assertEqual(timings.driver_intervals(a_run_dir(logs=logs)), [])


class TestDriverLogFormatContract(unittest.TestCase):
    """`timings` parses a line another file emits. Pin the coupling."""

    SCRIPT = (pathlib.Path(__file__).resolve().parent.parent.parent
              / "skills" / "order-lifecycle" / "references" / "run-lifecycle.sh")

    def test_run_lifecycle_start_line_still_emits_a_dryrun_token(self):
        # _live_start_index anchors on `dryrun=0`. Reword this line without
        # the flag and every driver interval silently disappears.
        self.assertTrue(self.SCRIPT.exists(), f"missing {self.SCRIPT}")
        starts = [ln for ln in self.SCRIPT.read_text().splitlines()
                  if ln.lstrip().startswith("log ") and "START sequence" in ln]
        self.assertEqual(len(starts), 1, "expected exactly one START log line")
        self.assertIn("dryrun=", starts[0])


class TestSummarise(unittest.TestCase):
    def test_event_window_is_the_longest_order_not_the_total(self):
        # 12 events x 180s sequential would be 36 min. Concurrent: 15.2.
        out = timings.summarise(a_run_dir(logs=DRIVER_LOGS))
        self.assertEqual(out["event_window_min"], 15.2)

    def test_gate_overlapping_an_agent_keeps_unattributed_non_negative(self):
        # The four headline metrics are NOT additive. total - measured -
        # waiting would go negative here; a single union must not.
        timeline = [
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:50:00Z"},
            {"kind": "agent", "name": "scrape", "phase": "end",
             "at": "2026-08-11T21:00:00Z"},
            {"kind": "gate", "name": "plan", "phase": "asked",
             "at": "2026-08-11T20:52:00Z"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T20:58:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertEqual(out["total_elapsed_min"], 10.0)
        self.assertEqual(out["measured_min"], 10.0)
        self.assertEqual(out["waiting_on_user_min"], 6.0)
        self.assertGreaterEqual(out["unattributed_min"], 0)
        self.assertEqual(out["unattributed_min"], 0.0)

    def test_unattributed_counts_time_nothing_covered(self):
        timeline = [
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:50:00Z"},
            {"kind": "agent", "name": "scrape", "phase": "end",
             "at": "2026-08-11T20:55:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "end",
             "at": "2026-08-11T21:10:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertEqual(out["total_elapsed_min"], 20.0)
        self.assertEqual(out["measured_min"], 10.0)
        self.assertEqual(out["unattributed_min"], 10.0)

    def test_no_gate_marks_gives_null_waiting(self):
        timeline = [
            {"kind": "lane", "name": "cdc", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "end",
             "at": "2026-08-11T21:10:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertIsNone(out["waiting_on_user_min"])

    def test_slowest_lane_is_named(self):
        timeline = [
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:50:00Z"},
            {"kind": "lane", "name": "scrape", "phase": "end",
             "at": "2026-08-11T21:00:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "end",
             "at": "2026-08-11T21:06:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertEqual(out["slowest_lane"], "scrape")
        self.assertEqual(out["per_lane"]["scrape"], 10.0)
        self.assertEqual(out["per_lane"]["cdc"], 1.0)

    def test_empty_run_reports_nulls_not_zeros(self):
        out = timings.summarise(a_run_dir())
        self.assertIsNone(out["total_elapsed_min"])
        self.assertIsNone(out["event_window_min"])
        self.assertIsNone(out["slowest_lane"])

    def test_unclosed_gate_gives_null_waiting_not_zero(self):
        # A gate that was asked but never answered is a real, ongoing wait —
        # not "the user was never asked anything". A missing mark yields a
        # null, never a wrong number.
        timeline = [
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:50:00Z"},
            {"kind": "agent", "name": "scrape", "phase": "end",
             "at": "2026-08-11T21:00:00Z"},
            {"kind": "gate", "name": "plan", "phase": "asked",
             "at": "2026-08-11T20:52:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertIsNone(out["waiting_on_user_min"])

    def test_unclosed_work_gives_null_measured_not_zero(self):
        # An agent or lane that started but never ended must not read as
        # zero measured work.
        timeline = [
            {"kind": "lane", "name": "cdc", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertIsNone(out["measured_min"])

    def test_malformed_driver_log_does_not_break_summarise(self):
        # A garbled run.log in one order must degrade to skipping that
        # driver, not raise out of summarise() and kill the whole report.
        logs = dict(DRIVER_LOGS)
        logs["04-garbled"] = [start_line("not-a-timestamp", 1)]
        out = timings.summarise(a_run_dir(logs=logs))
        self.assertEqual(out["event_window_min"], 15.2)

        # A garbled DONE line is the same class of corruption and was
        # unguarded: it raised out of summarise and killed the whole row.
        # The driver is simply unfinished, so the window is not yet known.
        logs = dict(DRIVER_LOGS)
        logs["04-garbled-done"] = [
            start_line("2026-08-11T21:36:00Z", 1),
            "not-a-timestamp DONE sequence complete",
        ]
        out = timings.summarise(a_run_dir(logs=logs))
        self.assertIsNone(out["event_window_min"])

    def test_unfinished_driver_makes_the_window_null(self):
        # Falling back to the other drivers' stamps silently shortens the
        # window; it genuinely is not known until every driver finishes.
        logs = dict(DRIVER_LOGS)
        logs["04-still-running"] = [start_line("2026-08-11T21:36:00Z", 2)]
        out = timings.summarise(a_run_dir(logs=logs))
        self.assertIsNone(out["event_window_min"])

    def test_single_mark_reports_null_total_not_zero(self):
        # "Total elapsed 0.0, Unattributed 0.0" reads as fully instrumented
        # with nothing unexplained — the most misleading output available.
        timeline = [{"kind": "lane", "name": "cdc", "phase": "start",
                     "at": "2026-08-11T21:05:00Z"}]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertIsNone(out["total_elapsed_min"])
        self.assertIsNone(out["unattributed_min"])

    def test_two_marks_at_the_same_instant_are_not_a_total(self):
        timeline = [
            {"kind": "lane", "name": "cdc", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "end",
             "at": "2026-08-11T21:05:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertIsNone(out["total_elapsed_min"])
        self.assertIsNone(out["unattributed_min"])

    def test_missing_run_state_returns_nulls_not_an_exception(self):
        # Telemetry is an observer that never fails a run.
        d = pathlib.Path(a_run_dir(logs=DRIVER_LOGS))
        (d / "run-state.json").unlink()
        out = timings.summarise(d)
        self.assertEqual(out["timeline"], [])
        self.assertIsNone(out["waiting_on_user_min"])
        # The drivers still stamped their own logs, so what was recorded is
        # still reported.
        self.assertEqual(out["event_window_min"], 15.2)

    def test_unreadable_run_state_returns_nulls_not_an_exception(self):
        d = pathlib.Path(a_run_dir())
        (d / "run-state.json").write_text("{not json")
        out = timings.summarise(d)
        self.assertIsNone(out["total_elapsed_min"])
        self.assertEqual(out["timeline"], [])


class TestDurationToBuild(unittest.TestCase):
    def test_plan_answered_to_beat1_end(self):
        timeline = [
            {"kind": "gate", "name": "plan", "phase": "asked",
             "at": "2026-08-11T20:00:00Z"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T20:05:00Z"},
            {"kind": "gate", "name": "beat1", "phase": "end",
             "at": "2026-08-11T20:35:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertEqual(out["duration_to_build_min"], 30.0)

    def test_missing_beat1_gives_null(self):
        timeline = [
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T20:05:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertIsNone(out["duration_to_build_min"])

    def test_missing_plan_answer_gives_null(self):
        timeline = [
            {"kind": "gate", "name": "beat1", "phase": "end",
             "at": "2026-08-11T20:35:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertIsNone(out["duration_to_build_min"])

    def test_reasked_plan_gate_measures_from_the_final_answer(self):
        timeline = [
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T20:05:00Z"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "gate", "name": "beat1", "phase": "end",
             "at": "2026-08-11T21:35:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertEqual(out["duration_to_build_min"], 30.0)

    def test_beat1_before_the_plan_answer_gives_null_not_a_negative(self):
        timeline = [
            {"kind": "gate", "name": "beat1", "phase": "end",
             "at": "2026-08-11T20:05:00Z"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T20:35:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertIsNone(out["duration_to_build_min"])


if __name__ == "__main__":
    unittest.main()
