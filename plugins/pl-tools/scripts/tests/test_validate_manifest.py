import copy
import unittest

from validate_manifest import validate


def valid_manifest():
    return {
        "run": {"created_at": "2026-08-11T09:00:00+00:00",
                "run_dir": "/Users/x/parcellab-demo-runs/acme-20260811",
                "skill_version": "abc123"},
        "path": "retain-shopify",
        "brand": {"name": "Acme", "url": "https://acme.example.com",
                  "handle": "acme", "region": "UK", "category": "Fashion"},
        "account": {"id": 1626718, "name": "Jamie Demo",
                    "confirmed_at": "2026-08-11T09:01:00+00:00",
                    "edit_mode_verified": True},
        "cdc": {"selected_account_config_id": None, "config_source": "none",
                "generate_orders": False, "order_types": []},
        "shopify": {"enabled": True, "store": "jamie-demo.myshopify.com",
                    "location_id": "gid://shopify/Location/123"},
        "destination_country": "GBR",
        "products": [
            {"id": f"p{i}", "name": f"Product {i}", "product_type": t,
             "price": "20.00", "options": [{"name": "Size", "values": ["S", "M"]}],
             "image_url": "https://img.example.com/x.jpg", "image_verified": True,
             "pdp_url": "https://acme.example.com/p", "sku": f"sku{i}"}
            for i, t in enumerate(["Shirt", "Shoe", "Hat", "Bag", "Coat"], start=1)
        ],
        "selection": {"core4": ["p1", "p2", "p3", "p4"], "shopify_extra": ["p5"]},
        "brand_tokens": {"tokens": {"BRAND_NAME": "Acme"},
                         "logo": {"type": "url", "value": "https://acme.example.com/l.png"},
                         "hero": {"url": "https://acme.example.com/h.jpg", "alt": "hero"}},
        "orders": [
            {"label": "clean-low", "dir": "orders/01-clean-low",
             "cdc_slot": "fraud_low", "fraud_level": "low",
             "customer": {"name": "Alice Smith", "email": "alice@example.com"},
             "products": ["p1"],
             "shipments": [{"label": "A", "scenario": "happy", "courier": "dpd-uk",
                            "products": ["p1"],
                            "events": ["InTransit", "OutForDelivery", "Delivered"]}]},
            {"label": "split-medium", "dir": "orders/02-split-medium",
             "cdc_slot": "fraud_medium", "fraud_level": "medium",
             "customer": {"name": "Bob Jones", "email": "bob@example.com"},
             "products": ["p2", "p3"],
             "shipments": [
                 {"label": "A", "scenario": "happy", "courier": "dpd-uk",
                  "products": ["p2"],
                  "events": ["InTransit", "OutForDelivery", "Delivered"]},
                 {"label": "B", "scenario": "stuck-delay", "courier": "dpd-uk",
                  "products": ["p3"], "events": ["InTransit", "WarehouseDelay"]}]},
        ],
        "gates": {"order_lifecycle": {"gate_b_answered": True,
                                      "gate_c": "send-as-is", "extras": {}}},
        "approvals": {"products_approved_at": "2026-08-11T09:05:00+00:00",
                      "intake_completed_at": "2026-08-11T09:05:00+00:00"},
    }


def broken(mutator):
    m = valid_manifest()
    mutator(m)
    return m


class TestValidateManifest(unittest.TestCase):
    def test_valid_manifest_passes(self):
        self.assertEqual(validate(valid_manifest()), [])

    def test_bad_path(self):
        errs = validate(broken(lambda m: m.update(path="both")))
        self.assertTrue(any("path" in e for e in errs))

    def test_core4_must_have_four_distinct_types(self):
        errs = validate(broken(
            lambda m: m["selection"].update(core4=["p1", "p2", "p3"])))
        self.assertTrue(any("core4" in e for e in errs))
        m = valid_manifest()
        m["products"][1]["product_type"] = m["products"][0]["product_type"]
        self.assertTrue(any("distinct" in e for e in validate(m)))

    def test_unverified_image_fails(self):
        m = valid_manifest()
        m["products"][0]["image_verified"] = False
        self.assertTrue(any("image" in e for e in validate(m)))

    def test_order_count_bounds(self):
        m = valid_manifest()
        m["orders"] = []
        self.assertTrue(any("orders" in e for e in validate(m)))
        m = valid_manifest()
        m["orders"] = [copy.deepcopy(m["orders"][0]) for _ in range(6)]
        self.assertTrue(any("5" in e for e in validate(m)))

    def test_split_required_for_multi_order_runs(self):
        m = valid_manifest()
        m["orders"][1]["shipments"] = [m["orders"][1]["shipments"][0]]
        self.assertTrue(any("split" in e for e in validate(m)))

    def test_single_order_run_needs_no_split(self):
        m = valid_manifest()
        m["orders"] = [m["orders"][0]]
        self.assertEqual(validate(m), [])

    def test_duplicate_customer_and_slot(self):
        m = valid_manifest()
        m["orders"][1]["customer"] = dict(m["orders"][0]["customer"])
        self.assertTrue(any("customer" in e for e in validate(m)))
        m = valid_manifest()
        m["orders"][1]["cdc_slot"] = "fraud_low"
        self.assertTrue(any("cdc_slot" in e for e in validate(m)))

    def test_fraud_level_required(self):
        m = valid_manifest()
        del m["orders"][0]["fraud_level"]
        self.assertTrue(any("fraud_level" in e for e in validate(m)))

    def test_retain_needs_a_delivered_order(self):
        m = valid_manifest()
        for o in m["orders"]:
            for s in o["shipments"]:
                s["events"] = ["InTransit", "WarehouseDelay"]
                s["scenario"] = "stuck-delay"
        self.assertTrue(any("Delivered" in e for e in validate(m)))

    def test_unproven_event_needs_label(self):
        m = valid_manifest()
        m["orders"][0]["shipments"][0]["events"].append("Delivered-ParcelLocker")
        self.assertTrue(any("unproven" in e for e in validate(m)))
        m["orders"][0]["shipments"][0]["unproven_events"] = ["Delivered-ParcelLocker"]
        self.assertEqual(validate(m), [])

    def test_shopify_consistency(self):
        m = valid_manifest()
        m["shopify"] = {"enabled": False}
        self.assertTrue(any("retain-shopify" in e for e in validate(m)))
        m = valid_manifest()
        m["shopify"]["location_id"] = "123"
        self.assertTrue(any("location" in e for e in validate(m)))

    def test_account_and_gates(self):
        m = valid_manifest()
        m["account"]["edit_mode_verified"] = False
        self.assertTrue(any("edit-mode" in e for e in validate(m)))
        m = valid_manifest()
        m["approvals"]["products_approved_at"] = ""
        self.assertTrue(any("approval" in e for e in validate(m)))


if __name__ == "__main__":
    unittest.main()
