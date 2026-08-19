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


if __name__ == "__main__":
    unittest.main()
