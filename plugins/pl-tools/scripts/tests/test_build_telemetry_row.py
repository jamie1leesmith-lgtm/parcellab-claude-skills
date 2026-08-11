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
        # to clobber it.
        row = btr.build_row(a_run(), "beat2")
        for column in ("Triage status", "Reviewed at", "Action taken",
                       "Fix commit", "Verified in run", "Reviewed by"):
            self.assertNotIn(column, row)

    def test_row_carries_no_customer_pii(self):
        blob = json.dumps(btr.build_row(a_run(), "beat2"))
        self.assertNotIn("@", blob.replace("https://", ""))

    def test_unfinished_run_reports_stalled(self):
        row = btr.build_row(a_run(finished=False), "beat2")
        self.assertEqual(row["Outcome"], "Stalled")


if __name__ == "__main__":
    unittest.main()
