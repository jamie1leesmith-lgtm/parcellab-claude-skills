"""Unit tests for run_state. Stdlib unittest — no pytest."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import run_state  # noqa: E402


class TestRunState(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        run_state.init(self.dir, "uniqlo-20260811-1913", "engage", "Demo - JLS")

    def test_init_creates_all_lanes_pending(self):
        state = run_state.load(self.dir)
        self.assertEqual(state["run_id"], "uniqlo-20260811-1913")
        self.assertFalse(state["finished"])
        for lane in ("scrape", "template", "seed", "orders", "cdc"):
            self.assertEqual(state["lanes"][lane]["status"], "pending")

    def test_set_lane_records_status_and_extras(self):
        run_state.set_lane(self.dir, "template", "published", layout_id=20701)
        lane = run_state.load(self.dir)["lanes"]["template"]
        self.assertEqual(lane["status"], "published")
        self.assertEqual(lane["layout_id"], 20701)
        self.assertTrue(lane["at"])

    def test_set_lane_rejects_unknown_lane(self):
        with self.assertRaises(ValueError):
            run_state.set_lane(self.dir, "nonsense", "ok")

    def test_set_lane_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            run_state.set_lane(self.dir, "orders", "finished-ish")

    def test_confirm_event_appends_to_the_right_shipment(self):
        run_state.add_order(self.dir, "Clean delivery", "UNQ-1", [
            {"label": "A", "tracking_number": "15221962690914",
             "courier": "dpd-uk",
             "planned": ["InTransit", "OutForDelivery", "Delivered"]},
        ])
        run_state.confirm_event(self.dir, "15221962690914", "InTransit",
                                "2026-08-11T18:43:27Z", 204)
        ship = run_state.load(self.dir)["orders"][0]["shipments"][0]
        self.assertEqual(len(ship["confirmed"]), 1)
        self.assertEqual(ship["confirmed"][0]["status"], "InTransit")
        self.assertEqual(ship["confirmed"][0]["http"], 204)

    def test_confirm_event_is_idempotent(self):
        # The watcher may re-read the same line; a replay must not duplicate.
        run_state.add_order(self.dir, "Clean", "UNQ-1", [
            {"label": "A", "tracking_number": "TN1", "courier": "dpd-uk",
             "planned": ["InTransit"]},
        ])
        for _ in range(3):
            run_state.confirm_event(self.dir, "TN1", "InTransit",
                                    "2026-08-11T18:43:27Z", 204)
        ship = run_state.load(self.dir)["orders"][0]["shipments"][0]
        self.assertEqual(len(ship["confirmed"]), 1)

    def test_confirm_event_unknown_tracking_raises(self):
        with self.assertRaises(KeyError):
            run_state.confirm_event(self.dir, "NOPE", "InTransit",
                                    "2026-08-11T18:43:27Z", 204)

    def test_finish_sets_flag(self):
        run_state.finish(self.dir)
        self.assertTrue(run_state.load(self.dir)["finished"])

    def test_add_failure_accumulates(self):
        run_state.add_failure(self.dir, "cdc", "500 from API")
        run_state.add_failure(self.dir, "seed", "no store")
        self.assertEqual(len(run_state.load(self.dir)["failures"]), 2)

    def test_writes_are_valid_json_on_disk(self):
        run_state.set_lane(self.dir, "scrape", "ok")
        raw = (pathlib.Path(self.dir) / "run-state.json").read_text()
        json.loads(raw)


if __name__ == "__main__":
    unittest.main()


class TestSetMeta(unittest.TestCase):
    """The run page promises path and account name 'fill in at the next
    republish' — which needs an API to fill them in with."""

    def test_set_meta_fills_in_account_and_path(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        run_state.set_meta(d, path="retain-shopify",
                           account_name="Demo - JLS")
        state = run_state.load(d)
        self.assertEqual(state["account_name"], "Demo - JLS")
        self.assertEqual(state["path"], "retain-shopify")

    def test_set_meta_leaves_omitted_fields_alone(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", "retain-shopify", "Demo - JLS")
        run_state.set_meta(d, account_name="Renamed")
        state = run_state.load(d)
        self.assertEqual(state["path"], "retain-shopify")
        self.assertEqual(state["account_name"], "Renamed")


class TestTimeline(unittest.TestCase):
    """Durations were unrecoverable because set_lane overwrites: template and
    seed both read 21:31:05 on the live Currys run, the moment each was marked
    done. The timeline is append-only so this cannot recur."""

    def test_init_creates_an_empty_timeline(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        self.assertEqual(run_state.load(d)["timeline"], [])

    def test_mark_appends_without_replacing(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        run_state.mark(d, "lane", "scrape", "start")
        run_state.mark(d, "lane", "scrape", "end")
        timeline = run_state.load(d)["timeline"]
        self.assertEqual(len(timeline), 2)
        self.assertEqual([e["phase"] for e in timeline], ["start", "end"])
        self.assertEqual(timeline[0]["kind"], "lane")
        self.assertEqual(timeline[0]["name"], "scrape")
        self.assertTrue(timeline[0]["at"].endswith("Z"))

    def test_mark_rejects_an_unknown_kind(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        with self.assertRaises(ValueError):
            run_state.mark(d, "sandwich", "scrape", "start")

    def test_mark_rejects_an_unknown_phase(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        with self.assertRaises(ValueError):
            run_state.mark(d, "lane", "scrape", "middle")

    def test_mark_works_on_a_state_predating_the_timeline(self):
        # Runs already on disk have no timeline key.
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        state = run_state.load(d)
        del state["timeline"]
        run_state._write(d, state)
        run_state.mark(d, "gate", "plan", "asked")
        self.assertEqual(len(run_state.load(d)["timeline"]), 1)


class TestMarkDrivesTheLanePills(unittest.TestCase):
    """A lane mark must also move the pill the run page renders.

    SKILL.md tells the conductor to call `mark(d, "lane", <name>, …)` at every
    lane boundary and never mentions `set_lane` — it has never appeared in the
    skill in any commit. The page renders `state["lanes"]`, which only
    `set_lane` wrote, so a conductor following the skill exactly left all five
    lanes on `init()`'s "pending" for the whole run (thenorthface 2026-08-12).
    Earlier runs show the mirror image: Currys and UNIQLO have correct pills
    and an empty timeline, because those conductors called `set_lane` and never
    marked. No run has ever produced both halves.

    These tests are why the defect survived: every existing render test seeds
    its state with `set_lane` directly, so the renderer was only ever checked
    against a state the documented workflow cannot produce.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        run_state.init(self.dir, "currys-1", "engage", "Demo - JLS")

    def test_lane_start_marks_the_lane_running(self):
        run_state.mark(self.dir, "lane", "scrape", "start")
        self.assertEqual(
            run_state.load(self.dir)["lanes"]["scrape"]["status"], "running")

    def test_lane_end_marks_the_lane_ok(self):
        run_state.mark(self.dir, "lane", "scrape", "start")
        run_state.mark(self.dir, "lane", "scrape", "end")
        self.assertEqual(
            run_state.load(self.dir)["lanes"]["scrape"]["status"], "ok")

    def test_lane_end_never_downgrades_a_failed_lane(self):
        # A lane can fail and still reach its "end" boundary. Reporting that as
        # ok would erase the failure the run page exists to surface.
        run_state.set_lane(self.dir, "cdc", "failed")
        run_state.mark(self.dir, "lane", "cdc", "end")
        self.assertEqual(
            run_state.load(self.dir)["lanes"]["cdc"]["status"], "failed")

    def test_lane_end_never_downgrades_a_richer_status(self):
        # The template lane ends "published"; seed can end "skipped". Neither
        # is improved by being flattened to plain ok.
        run_state.set_lane(self.dir, "template", "published", layout_id=20701)
        run_state.mark(self.dir, "lane", "template", "end")
        lane = run_state.load(self.dir)["lanes"]["template"]
        self.assertEqual(lane["status"], "published")
        self.assertEqual(lane["layout_id"], 20701)

    def test_marking_still_records_the_timeline_entry(self):
        # The durations half must survive the pills fix.
        run_state.mark(self.dir, "lane", "scrape", "start")
        run_state.mark(self.dir, "lane", "scrape", "end")
        lane_marks = [e for e in run_state.load(self.dir)["timeline"]
                      if e["kind"] == "lane"]
        self.assertEqual([e["phase"] for e in lane_marks], ["start", "end"])

    def test_agent_and_gate_marks_do_not_touch_lanes(self):
        # "scrape" is both an agent name and a lane name; only the lane kind
        # may move a pill.
        run_state.mark(self.dir, "agent", "scrape", "start")
        run_state.mark(self.dir, "gate", "plan", "asked")
        self.assertEqual(
            run_state.load(self.dir)["lanes"]["scrape"]["status"], "pending")

    def test_a_lane_mark_outside_the_known_lanes_is_ignored_not_fatal(self):
        # `mark` accepts any name by design (it is a free-text timeline label);
        # only the five real lanes have pills.
        run_state.mark(self.dir, "lane", "not-a-lane", "start")
        self.assertNotIn("not-a-lane", run_state.load(self.dir)["lanes"])


class TestPageTelemetry(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        run_state.init(self.dir, "uniqlo-20260811-1913", "engage", "Demo - JLS")

    def test_init_seeds_an_empty_page_section(self):
        state = run_state.load(self.dir)
        self.assertEqual(state["page"], {"renders": [], "publishes": []})

    def test_record_render_appends_a_stamp(self):
        state = run_state.record_render(self.dir)
        self.assertEqual(len(state["page"]["renders"]), 1)
        self.assertRegex(state["page"]["renders"][0]["at"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_record_publish_keeps_the_url(self):
        state = run_state.record_publish(self.dir, "https://x.test/a")
        self.assertEqual(state["page"]["publishes"][0]["url"],
                         "https://x.test/a")

    def test_recorders_append_never_replace(self):
        run_state.record_render(self.dir)
        run_state.record_render(self.dir)
        run_state.record_publish(self.dir, "https://x.test/a")
        state = run_state.record_publish(self.dir, "https://x.test/b")
        self.assertEqual(len(state["page"]["renders"]), 2)
        self.assertEqual([p["url"] for p in state["page"]["publishes"]],
                         ["https://x.test/a", "https://x.test/b"])

    def test_recorders_survive_a_state_written_before_page_existed(self):
        state = run_state.load(self.dir)
        del state["page"]
        run_state._write(self.dir, state)
        state = run_state.record_render(self.dir)
        self.assertEqual(len(state["page"]["renders"]), 1)
        state = run_state.record_publish(self.dir, "https://x.test/a")
        self.assertEqual(len(state["page"]["publishes"]), 1)
