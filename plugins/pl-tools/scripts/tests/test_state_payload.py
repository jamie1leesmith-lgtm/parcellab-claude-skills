"""Unit tests for state_payload. Stdlib unittest — no pytest."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import run_state  # noqa: E402
import state_payload  # noqa: E402


class TestStatePayload(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        (self.dir / "scrape").mkdir()
        (self.dir / "results").mkdir()
        run_state.init(str(self.dir), "pccomponentes-20260819-1546",
                       "retain-shopify", "Demo - JLS")

    def test_phase_is_intake_until_intake_json_exists(self):
        self.assertEqual(state_payload.build(self.dir)["phase"], "intake")

    def test_phase_is_building_once_intake_json_exists(self):
        (self.dir / "intake.json").write_text("{}")
        self.assertEqual(state_payload.build(self.dir)["phase"], "building")

    def test_phase_is_live_once_the_run_is_finished(self):
        """The stepper's third step can only light if the payload says so.

        Beat 2 calls run_state.finish(); before this the payload only ever
        emitted intake|building, so a completed run sat on "Building"
        forever.
        """
        (self.dir / "intake.json").write_text("{}")
        run_state.finish(str(self.dir))
        payload = state_payload.build(self.dir)
        self.assertEqual(payload["phase"], "live")
        self.assertTrue(payload["finished"])

    def test_finished_run_without_intake_json_is_not_live(self):
        """Guard the ordering: live means finished AND past intake."""
        run_state.finish(str(self.dir))
        self.assertEqual(state_payload.build(self.dir)["phase"], "intake")

    def test_carries_run_state_basics(self):
        payload = state_payload.build(self.dir)
        self.assertEqual(payload["run_id"], "pccomponentes-20260819-1546")
        self.assertEqual(payload["account_name"], "Demo - JLS")
        self.assertEqual(payload["path"], "retain-shopify")
        self.assertFalse(payload["finished"])
        self.assertEqual(payload["lanes"]["scrape"]["status"], "pending")

    def test_detail_keys_are_present_even_when_empty(self):
        detail = state_payload.build(self.dir)["detail"]
        for key in ("scrape", "template", "seed", "cdc"):
            self.assertIn(key, detail)

    def test_scrape_detail_comes_from_assets(self):
        (self.dir / "scrape" / "assets.json").write_text(json.dumps({
            "tokens": {"primary": "#e2001a", "text": "#1a1a1a",
                       "font": "Inter"},
            "logo_data_uri": "data:image/svg+xml;base64,AAA",
            "products": {
                "SKU1": {"name": "RTX 4070", "product_type": "graphics card",
                         "price": "649.00", "data_uri": "data:image/png;base64,BBB"},
            },
        }))
        scrape = state_payload.build(self.dir)["detail"]["scrape"]
        self.assertEqual(scrape["swatches"], ["#e2001a", "#1a1a1a"])
        self.assertEqual(scrape["logo"], "data:image/svg+xml;base64,AAA")
        self.assertEqual(len(scrape["products"]), 1)
        self.assertEqual(scrape["products"][0]["name"], "RTX 4070")

    def test_scrape_detail_skips_non_colour_tokens(self):
        (self.dir / "scrape" / "assets.json").write_text(json.dumps({
            "tokens": {"font": "Inter", "primary": "#abc"}, "products": {}}))
        scrape = state_payload.build(self.dir)["detail"]["scrape"]
        self.assertEqual(scrape["swatches"], ["#abc"])

    def test_seed_detail_carries_products_and_demos(self):
        (self.dir / "results" / "shopify-seed.json").write_text(json.dumps({
            "status": "ok",
            "products": [{"title": "RTX 4070", "seeded_price": "299.00",
                          "adjusted": True,
                          "variants": [{"id": "gid://1"}, {"id": "gid://2"}]}],
            "demos": {"in_product_even": {"product": "RTX 4070",
                                          "option": "Memory",
                                          "swap": "12GB → 16GB"},
                      "cross_product_even": ["Mouse", "RAM"],
                      "uneven_upward": {"from": "Mouse", "to": "RTX 4070",
                                        "balance": "170.00"},
                      "uneven_downward": None},
            "warnings": [],
            "error": None,
        }))
        seed = state_payload.build(self.dir)["detail"]["seed"]
        self.assertEqual(seed["status"], "ok")
        self.assertEqual(seed["products"][0]["variant_count"], 2)
        self.assertEqual(seed["demos"]["cross_product_even"], ["Mouse", "RAM"])

    def test_cdc_detail_reports_generate_orders_from_manifest(self):
        (self.dir / "demo-manifest.json").write_text(json.dumps({
            "cdc": {"generate_orders": False, "orders": []}}))
        cdc = state_payload.build(self.dir)["detail"]["cdc"]
        self.assertFalse(cdc["generate_orders"])

    def test_template_detail_reports_path_and_lane_status(self):
        run_state.set_lane(str(self.dir), "template", "published",
                           layout_id=20701)
        template = state_payload.build(self.dir)["detail"]["template"]
        self.assertEqual(template["status"], "published")
        self.assertEqual(template["layout_id"], 20701)
        self.assertEqual(template["path"], "retain-shopify")

    def test_orders_carry_shipment_progress(self):
        run_state.add_order(str(self.dir), "01-fraud-low", "pl-1041", [
            {"label": "A", "tracking_number": "TN1", "courier": "dhl-germany",
             "planned": ["InTransit", "Delivered"]}])
        run_state.confirm_event(str(self.dir), "TN1", "InTransit",
                                "2026-08-19T15:31:05Z", 204)
        orders = state_payload.build(self.dir)["orders"]
        self.assertEqual(orders[0]["order_number"], "pl-1041")
        self.assertEqual(orders[0]["shipments"][0]["confirmed"][0]["status"],
                         "InTransit")

    def test_cdc_detail_surfaces_demo_request_on_success(self):
        (self.dir / "results" / "demo-request.json").write_text(json.dumps({
            "id": "cdc-req-1",
            "request_status": "ok",
            "request_url": "https://app.parcellab.com/demo-requests/cdc-req-1",
            "linked_submitted": ["pl-1041", "pl-1042"],
        }))
        cdc = state_payload.build(self.dir)["detail"]["cdc"]
        self.assertEqual(cdc["id"], "cdc-req-1")
        self.assertEqual(cdc["url"],
                         "https://app.parcellab.com/demo-requests/cdc-req-1")
        self.assertEqual(cdc["request_status"], "ok")
        self.assertEqual(cdc["linked_count"], 2)

    def test_cdc_detail_surfaces_demo_request_on_failure(self):
        (self.dir / "results" / "demo-request.json").write_text(json.dumps({
            "id": "cdc-req-2",
            "request_status": "failed",
            "request_url": "https://app.parcellab.com/demo-requests/cdc-req-2",
            "linked_submitted": [],
        }))
        cdc = state_payload.build(self.dir)["detail"]["cdc"]
        self.assertEqual(cdc["id"], "cdc-req-2")
        self.assertEqual(cdc["request_status"], "failed")
        self.assertEqual(cdc["linked_count"], 0)

    def test_malformed_side_file_does_not_break_the_payload(self):
        (self.dir / "scrape" / "assets.json").write_text("{ broken")
        payload = state_payload.build(self.dir)
        self.assertIsNone(payload["detail"]["scrape"])
        self.assertEqual(payload["run_id"], "pccomponentes-20260819-1546")

    def test_order_fraud_level_comes_from_the_manifest_when_labels_match(self):
        run_state.add_order(str(self.dir), "01-fraud-low", "pl-1041", [
            {"label": "A", "tracking_number": "TN1", "courier": "dhl-germany",
             "planned": ["InTransit", "Delivered"]}])
        (self.dir / "demo-manifest.json").write_text(json.dumps({
            "orders": [{"label": "01-fraud-low", "fraud_level": "low"}],
        }))
        orders = state_payload.build(self.dir)["orders"]
        self.assertEqual(orders[0]["fraud_level"], "low")

    def test_order_with_no_manifest_match_degrades_to_fraud_level_none(self):
        run_state.add_order(str(self.dir), "01-fraud-low", "pl-1041", [
            {"label": "A", "tracking_number": "TN1", "courier": "dhl-germany",
             "planned": ["InTransit", "Delivered"]}])
        (self.dir / "demo-manifest.json").write_text(json.dumps({
            "orders": [{"label": "some-other-order", "fraud_level": "high"}],
        }))
        orders = state_payload.build(self.dir)["orders"]
        self.assertIsNone(orders[0]["fraud_level"])

    def test_missing_manifest_still_produces_orders_with_fraud_level_none(self):
        run_state.add_order(str(self.dir), "01-fraud-low", "pl-1041", [
            {"label": "A", "tracking_number": "TN1", "courier": "dhl-germany",
             "planned": ["InTransit", "Delivered"]}])
        # No demo-manifest.json written at all.
        orders = state_payload.build(self.dir)["orders"]
        self.assertIsNone(orders[0]["fraud_level"])

    def test_malformed_manifest_still_produces_a_usable_payload(self):
        run_state.add_order(str(self.dir), "01-fraud-low", "pl-1041", [
            {"label": "A", "tracking_number": "TN1", "courier": "dhl-germany",
             "planned": ["InTransit", "Delivered"]}])
        (self.dir / "demo-manifest.json").write_text("{ broken")
        payload = state_payload.build(self.dir)
        self.assertIsNone(payload["orders"][0]["fraud_level"])
        self.assertEqual(payload["run_id"], "pccomponentes-20260819-1546")

    def test_gate_states_default_to_pending(self):
        gates = state_payload.gate_states(
            json.loads((self.dir / "run-state.json").read_text()))
        self.assertEqual(gates, {"template": "pending", "plan": "pending"})

    def test_asked_without_answered_is_open(self):
        run_state.mark(str(self.dir), "gate", "template", "asked")
        state = json.loads((self.dir / "run-state.json").read_text())
        self.assertEqual(state_payload.gate_states(state)["template"], "open")
        self.assertEqual(state_payload.gate_states(state)["plan"], "pending")

    def test_asked_then_answered_is_answered(self):
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        run_state.mark(str(self.dir), "gate", "plan", "answered")
        state = json.loads((self.dir / "run-state.json").read_text())
        self.assertEqual(state_payload.gate_states(state)["plan"], "answered")

    def test_re_asking_after_an_answer_reopens_the_gate(self):
        """A rejected gate is re-asked: last mark wins, so it is open again."""
        for phase in ("asked", "answered", "asked"):
            run_state.mark(str(self.dir), "gate", "template", phase)
        state = json.loads((self.dir / "run-state.json").read_text())
        self.assertEqual(state_payload.gate_states(state)["template"], "open")

    def test_gate_marks_returns_the_latest_asked_timestamp(self):
        run_state.mark(str(self.dir), "gate", "template", "asked")
        state = json.loads((self.dir / "run-state.json").read_text())
        marks = state_payload.gate_marks(state)
        self.assertEqual(set(marks), {"template"})
        self.assertTrue(marks["template"])

    def test_gate_marks_tolerates_a_missing_timeline(self):
        self.assertEqual(state_payload.gate_marks({}), {})

    def test_a_fresh_ask_after_a_rejection_produces_a_new_mark(self):
        """A rejected gate is re-asked under the SAME name — gate_states
        already makes that free ("last mark wins"), which is exactly why
        the page's re-render guard needs a second signal: `gate_marks`
        must expose that the re-ask is a genuinely new timeline entry, not
        just the same status recurring.

        `run_state.mark`'s timestamps have whole-second resolution, so two
        marks made back-to-back in a fast test run can legitimately share
        an `at` string. Assert on the count of recorded entries (proof a
        fresh one was appended) and on which entry `gate_marks` reports,
        rather than on the strings being unequal — so this cannot flake.
        """
        path = self.dir / "run-state.json"
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        first_state = json.loads(path.read_text())
        first_gate_entries = sum(1 for e in first_state["timeline"]
                                  if e.get("kind") == "gate")

        run_state.mark(str(self.dir), "gate", "plan", "answered")
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        second_state = json.loads(path.read_text())
        second_gate_entries = sum(1 for e in second_state["timeline"]
                                   if e.get("kind") == "gate")

        self.assertGreater(second_gate_entries, first_gate_entries)
        self.assertEqual(state_payload.gate_states(second_state)["plan"],
                         "open")

        asked_ats = [e["at"] for e in second_state["timeline"]
                    if e.get("kind") == "gate" and e.get("name") == "plan"
                    and e.get("phase") == "asked"]
        self.assertEqual(len(asked_ats), 2)
        # The mark handed to the page must track the LATEST ask, not the
        # first one it ever saw.
        self.assertEqual(state_payload.gate_marks(second_state)["plan"],
                         asked_ats[-1])

    def test_build_payload_carries_gates_at(self):
        run_state.mark(str(self.dir), "gate", "template", "asked")
        gates_at = state_payload.build(self.dir)["gates_at"]
        self.assertIn("template", gates_at)
        self.assertTrue(gates_at["template"])

    def test_lane_and_agent_marks_never_affect_gates(self):
        run_state.mark(str(self.dir), "lane", "template", "start")
        run_state.mark(str(self.dir), "agent", "scrape", "start")
        gates = state_payload.gate_states(
            json.loads((self.dir / "run-state.json").read_text()))
        self.assertEqual(gates, {"template": "pending", "plan": "pending"})

    def test_build_payload_carries_gates(self):
        run_state.mark(str(self.dir), "gate", "template", "asked")
        self.assertEqual(state_payload.build(self.dir)["gates"]["template"],
                         "open")

    def test_gate_states_tolerates_a_missing_timeline(self):
        self.assertEqual(state_payload.gate_states({}),
                         {"template": "pending", "plan": "pending"})

    def test_plan_gate_stays_pending_when_only_the_manifest_exists(self):
        """The manifest exists from Phase 0 step 7 — before the plan gate.

        Keying the plan card on the manifest would leak the whole plan while
        the operator is still being asked about the template.
        """
        (self.dir / "demo-manifest.json").write_text(json.dumps(
            {"brand": {"name": "Brand"}}))
        self.assertEqual(state_payload.build(self.dir)["gates"]["plan"],
                         "pending")

    MANIFEST = {
        "brand": {"region": "UK", "category": "Electronics"},
        "account": {"id": 1626718, "name": "Demo - JLS"},
        "cdc": {"config_source": "none", "generate_orders": False,
                "orders": []},
        "products": [
            {"id": "h100", "name": "Beoplay H100",
             "product_type": "Over-Ear Headphones", "price": "1500.00"},
            {"id": "a5", "name": "Beosound A5",
             "product_type": "Portable Home Speaker", "price": "1400.00"},
            {"id": "ex", "name": "Beosound Explore",
             "product_type": "Outdoor Speaker", "price": "219.00"},
            {"id": "el", "name": "Beoplay Eleven",
             "product_type": "Wireless Earbuds", "price": "429.00"},
        ],
        "selection": {"core4": ["h100", "a5", "ex", "el"],
                      "shopify_extra": []},
        "orders": [{
            "label": "fraud-low", "fraud_level": "low",
            "cdc_slot": "fraud_low",
            "customer": {"name": "James Wilson",
                         "email": "james@example.com"},
            "products": ["el"],
            "shipments": [{"label": "A", "scenario": "happy",
                           "courier": "dpd-uk",
                           "events": ["InTransit", "Delivered"]}],
        }],
        "gates": {"order_lifecycle": {
            "gate_c": "extras",
            "extras": {"article_weights": {
                "el": {"weight": 0.4, "weight_unit": "kg"}}}}},
    }

    def write_manifest(self):
        (self.dir / "demo-manifest.json").write_text(
            json.dumps(self.MANIFEST))

    def test_plan_detail_is_none_before_the_gate_opens(self):
        self.write_manifest()
        self.assertIsNone(state_payload.build(self.dir)["detail"]["plan"])

    def test_plan_detail_appears_when_the_gate_is_open(self):
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        plan = state_payload.build(self.dir)["detail"]["plan"]
        self.assertIsNotNone(plan)
        self.assertEqual(plan["account"], "Demo - JLS")

    def test_plan_core4_resolves_ids_to_products(self):
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        core4 = state_payload.build(self.dir)["detail"]["plan"]["core4"]
        self.assertEqual([p["name"] for p in core4],
                         ["Beoplay H100", "Beosound A5",
                          "Beosound Explore", "Beoplay Eleven"])
        self.assertEqual(core4[0]["product_type"], "Over-Ear Headphones")

    def test_plan_orders_carry_shipments_and_product_names(self):
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        orders = state_payload.build(self.dir)["detail"]["plan"]["orders"]
        self.assertEqual(orders[0]["products"], ["Beoplay Eleven"])
        self.assertEqual(orders[0]["shipments"][0]["scenario"], "happy")
        self.assertEqual(orders[0]["shipments"][0]["events"],
                         ["InTransit", "Delivered"])

    def test_plan_cdc_block_states_generation_is_off(self):
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        cdc = state_payload.build(self.dir)["detail"]["plan"]["cdc"]
        self.assertEqual(cdc["region"], "UK")
        self.assertEqual(cdc["category"], "Electronics")
        self.assertEqual(cdc["config_source"], "none")
        self.assertFalse(cdc["generate_orders"])

    def test_plan_extras_are_flattened_field_by_field(self):
        """An auto-derived value the operator never saw is worse than one
        they rejected — so weights are listed per article, not summarised."""
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        extras = state_payload.build(self.dir)["detail"]["plan"]["extras"]
        self.assertEqual(extras["gate_c"], "extras")
        labels = [row[0] for row in extras["fields"]]
        self.assertIn("Beoplay Eleven weight", labels)
        values = dict(extras["fields"])
        self.assertEqual(values["Beoplay Eleven weight"], "0.4 kg")

    def test_plan_shipments_carry_unproven_events_and_chain_flag(self):
        """validate_manifest.py's confidence labelling — a shipment may
        list events outside the proven set in `unproven_events`, and flag
        a proven-events-but-unproven-sequence chain via `unproven_chain`.
        The plan card is documented (SKILL.md) to mark both; it can't if
        `_plan_detail` drops them on the floor.
        """
        manifest = json.loads(json.dumps(self.MANIFEST))  # deep copy
        manifest["orders"][0]["shipments"][0]["unproven_events"] = ["Delivered"]
        manifest["orders"][0]["shipments"][0]["unproven_chain"] = True
        (self.dir / "demo-manifest.json").write_text(json.dumps(manifest))
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        shipment = state_payload.build(
            self.dir)["detail"]["plan"]["orders"][0]["shipments"][0]
        self.assertEqual(shipment["unproven_events"], ["Delivered"])
        self.assertTrue(shipment["unproven_chain"])

    def test_plan_shipments_default_unproven_fields_when_absent(self):
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        shipment = state_payload.build(
            self.dir)["detail"]["plan"]["orders"][0]["shipments"][0]
        self.assertEqual(shipment["unproven_events"], [])
        self.assertFalse(shipment["unproven_chain"])

    def test_plan_detail_is_none_when_the_manifest_is_unreadable(self):
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        self.assertIsNone(state_payload.build(self.dir)["detail"]["plan"])


class TestMissingRunState(unittest.TestCase):
    """A poll must degrade, not raise, when run-state.json is unreadable.

    Raising escapes the request handler and the client gets a dropped
    connection rather than a response — the page's only data source, with
    nothing to diagnose from.
    """

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())

    def test_no_run_state_file_still_builds_a_payload(self):
        payload = state_payload.build(self.dir)
        self.assertEqual(payload["phase"], "intake")
        self.assertIsNone(payload["run_id"])
        self.assertEqual(payload["lanes"], {})
        self.assertEqual(payload["orders"], [])
        self.assertEqual(payload["failures"], [])
        self.assertFalse(payload["finished"])
        for key in ("scrape", "template", "seed", "cdc"):
            self.assertIn(key, payload["detail"])

    def test_malformed_run_state_still_builds_a_payload(self):
        (self.dir / "run-state.json").write_text("{ broken")
        payload = state_payload.build(self.dir)
        self.assertIsNone(payload["run_id"])
        self.assertEqual(payload["orders"], [])

    def test_phase_still_flips_without_run_state(self):
        (self.dir / "intake.json").write_text("{}")
        self.assertEqual(state_payload.build(self.dir)["phase"], "building")


if __name__ == "__main__":
    unittest.main()
