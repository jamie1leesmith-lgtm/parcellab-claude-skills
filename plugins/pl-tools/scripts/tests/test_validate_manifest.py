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
                "generate_orders": False, "orders": []},
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

    def test_pre_gate_allows_an_unstamped_product_approval(self):
        """Phase 0 step 7 validates BEFORE the gate that stamps this.

        The manifest moved ahead of both gates so the run page could render
        what it asks about, which put validation before the moment products are
        actually approved. Requiring the stamp there forces a conductor to
        either fake a timestamp or skip validation — live 2026-08-12 the run
        carried `null` through the gates and validated a temp copy instead.
        """
        m = valid_manifest()
        m["approvals"]["products_approved_at"] = None
        self.assertEqual(
            [e for e in validate(m, pre_gate=True) if "approval" in e], [])

    def test_pre_gate_still_enforces_everything_else(self):
        # A structural error must not be waved through by the softer mode.
        m = valid_manifest()
        m["approvals"]["products_approved_at"] = None
        m["brand"]["region"] = "FR"
        self.assertTrue(
            any("brand.region" in e for e in validate(m, pre_gate=True)))

    def test_pre_gate_still_requires_intake_completion(self):
        # Intake IS finished by step 7; only the approval stamp is not.
        m = valid_manifest()
        m["approvals"]["intake_completed_at"] = ""
        self.assertTrue(
            any("intake" in e for e in validate(m, pre_gate=True)))

    def test_post_gate_is_the_default_and_still_demands_the_stamp(self):
        m = valid_manifest()
        m["approvals"]["products_approved_at"] = None
        self.assertTrue(any("approval" in e for e in validate(m)))

    def test_bad_brand_region(self):
        m = valid_manifest()
        m["brand"]["region"] = "FR"
        self.assertTrue(any("brand.region" in e for e in validate(m)))

    def test_bad_brand_category(self):
        m = valid_manifest()
        m["brand"]["category"] = "Toys"
        self.assertTrue(any("brand.category" in e for e in validate(m)))

    def test_empty_brand_name(self):
        m = valid_manifest()
        m["brand"]["name"] = ""
        self.assertTrue(any("brand.name" in e for e in validate(m)))

    def test_unproven_sequence_needs_chain_label(self):
        # happy-with-delay: every event is individually proven, but the chain
        # is not (status-codes.md) — so it still needs the label.
        m = valid_manifest()
        m["orders"][0]["shipments"][0]["events"] = ["WarehouseDelay", "InTransit", "OutForDelivery", "Delivered"]
        m["orders"][0]["shipments"][0]["scenario"] = "custom"
        errs = validate(m)
        self.assertTrue(any("unproven_chain" in e for e in errs))
        m["orders"][0]["shipments"][0]["unproven_chain"] = True
        self.assertEqual(validate(m), [])

    def test_order_products_must_be_ids_not_indices(self):
        # selection[] and orders[].products must use the same reference style.
        # An integer index resolves to a real-but-wrong product for a careless
        # consumer, so it has to fail loudly rather than validate clean.
        m = valid_manifest()
        m["orders"][0]["products"] = [0]
        errs = validate(m)
        self.assertTrue(any("not indices" in e for e in errs), errs)

    def test_order_products_reject_unknown_id(self):
        m = valid_manifest()
        m["orders"][0]["products"] = ["p99"]
        self.assertTrue(any("unknown product p99" in e for e in validate(m)))

    def test_recovered_chain_is_proven(self):
        # Proven live 2026-08-11 (order STU-1786455234, account 1626718);
        # validating it clean is what keeps Beat 1 from labelling it unproven.
        m = valid_manifest()
        m["orders"][0]["shipments"][0]["events"] = ["InTransit", "WarehouseDelay", "OutForDelivery", "Delivered"]
        m["orders"][0]["shipments"][0]["scenario"] = "recovered"
        self.assertEqual(validate(m), [])

    def test_pace_optional_and_enum(self):
        self.assertEqual(validate(valid_manifest()), [])  # absent is fine
        m = valid_manifest()
        m["run"]["pace"] = "fast"
        self.assertEqual(validate(m), [])
        m["run"]["pace"] = "leisurely"
        self.assertTrue(any("pace" in e for e in validate(m)))

    def test_run_mode_absent_is_valid(self):
        m = valid_manifest()
        m["run"].pop("mode", None)
        self.assertEqual(validate(m, pre_gate=True), [])

    def test_run_mode_auto_is_valid(self):
        m = valid_manifest()
        m["run"]["mode"] = "auto"
        self.assertEqual(validate(m, pre_gate=True), [])

    def test_run_mode_babysit_is_valid(self):
        m = valid_manifest()
        m["run"]["mode"] = "babysit"
        self.assertEqual(validate(m, pre_gate=True), [])

    def test_run_mode_invalid_value_rejected(self):
        m = valid_manifest()
        m["run"]["mode"] = "yolo"
        self.assertTrue(any("run.mode" in e for e in validate(m, pre_gate=True)))

    def test_gate_c_value_must_be_known(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(gate_c="maybe")))
        self.assertTrue(any("gate C" in e for e in errs))

    def test_gate_c_extras_requires_non_empty_extras(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras", extras={})))
        self.assertTrue(any("extras" in e for e in errs))

    def test_send_as_is_rejects_populated_extras(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="send-as-is",
                extras={"announced_delivery_date": "2026-08-15"})))
        self.assertTrue(any("send-as-is" in e for e in errs))

    def test_promise_date_rejects_full_iso(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"announced_delivery_date": "2026-08-15T10:00:00Z"})))
        self.assertTrue(any("YYYY-MM-DD" in e for e in errs))

    def test_promise_date_accepts_plain_date(self):
        m = valid_manifest()
        m["gates"]["order_lifecycle"].update(
            gate_c="extras", extras={"announced_delivery_date": "2026-08-15"})
        self.assertEqual(validate(m), [])

    def test_article_weight_unit_enum(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"article_weights": {
                    "p1": {"weight": 300, "weight_unit": "stone"}}})))
        self.assertTrue(any("weight_unit" in e for e in errs))

    def test_article_weight_must_be_a_positive_number(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"article_weights": {
                    "p1": {"weight": "300", "weight_unit": "g"}}})))
        self.assertTrue(any("weight" in e for e in errs))

    def test_article_weight_rejects_zero(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"article_weights": {
                    "p1": {"weight": 0, "weight_unit": "g"}}})))
        self.assertTrue(any("positive" in e for e in errs))

    def test_article_weight_rejects_bool(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"article_weights": {
                    "p1": {"weight": True, "weight_unit": "g"}}})))
        self.assertTrue(any("positive" in e for e in errs))

    def test_non_dict_extras_reports_instead_of_raising(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras", extras=["announced_delivery_date"])))
        self.assertTrue(any("extras must be an object" in e for e in errs))

    def test_non_dict_article_weights_reports_instead_of_raising(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras", extras={"article_weights": ["p1"]})))
        self.assertTrue(
            any("article_weights must be an object" in e for e in errs))

    def test_non_dict_article_weight_entry_reports_instead_of_raising(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"article_weights": {"p1": "300g"}})))
        self.assertTrue(
            any("article_weights[p1] must be an object" in e for e in errs))

    def test_article_weight_key_must_be_a_known_product_id(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"article_weights": {
                    "sku1": {"weight": 300, "weight_unit": "g"}}})))
        self.assertTrue(any("unknown product" in e for e in errs))

    def test_article_weights_accepted_when_well_formed(self):
        m = valid_manifest()
        m["gates"]["order_lifecycle"].update(
            gate_c="extras",
            extras={"article_weights": {"p1": {"weight": 300,
                                               "weight_unit": "g"}}})
        self.assertEqual(validate(m), [])


if __name__ == "__main__":
    unittest.main()
