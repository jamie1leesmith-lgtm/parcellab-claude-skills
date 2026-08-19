"""Unit tests for intake_schema. Stdlib unittest — no pytest."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import intake_schema  # noqa: E402
import validate_manifest  # noqa: E402


def _valid():
    return {
        "shopify_opp": True,
        "reuse_pool": None,
        "region": "DE",
        "courier": "dhl-germany",
        "orders": [
            {"label": "#1", "fraud": "low", "split": False,
             "scenario": "happy", "courier": None},
            {"label": "#2", "fraud": "medium", "split": True,
             "parcels": [
                 {"label": "A", "scenario": "happy", "courier": None},
                 {"label": "B", "scenario": "stuck-delay", "courier": "ups"},
             ]},
        ],
        "gate_c": "send-as-is",
        "extras": {},
        "mode": "babysit",
    }


class TestVocabularies(unittest.TestCase):
    def test_regions_match_validate_manifest(self):
        self.assertEqual(tuple(intake_schema.REGIONS), ("US", "UK", "DE"))

    def test_every_region_has_a_courier_default(self):
        for region in intake_schema.REGIONS:
            self.assertIn(region, intake_schema.REGION_COURIERS)

    def test_split_is_not_a_scenario(self):
        self.assertNotIn("split", intake_schema.SCENARIOS)

    def test_scenario_vocabulary_is_the_documented_one(self):
        self.assertEqual(
            set(intake_schema.SCENARIOS),
            {"happy", "stuck-delay", "recovered", "locker",
             "manual_return", "return_tracking", "custom"})

    def test_fraud_levels_ordered_matches_the_set(self):
        # The tuple is the display order (low-to-high severity); the
        # frozenset is the validity check. A level added to only one of
        # them would otherwise silently disappear from either the UI or
        # from validation rather than failing loudly.
        self.assertEqual(set(intake_schema.FRAUD_LEVELS_ORDERED),
                         intake_schema.FRAUD_LEVELS)


class TestVocabularyParityWithValidateManifest(unittest.TestCase):
    """intake_schema and validate_manifest deliberately duplicate their
    extras-checking logic (see task-1 fix round 1) — these tests are the
    agreed mitigation against the two vocabularies drifting apart."""

    def test_regions_matches_brand_regions(self):
        self.assertEqual(set(intake_schema.REGIONS),
                         set(validate_manifest.BRAND_REGIONS))

    def test_fraud_levels_match(self):
        self.assertEqual(set(intake_schema.FRAUD_LEVELS),
                         set(validate_manifest.FRAUD_LEVELS))

    def test_modes_match(self):
        self.assertEqual(set(intake_schema.MODES),
                         set(validate_manifest.MODES))

    def test_gate_c_values_match(self):
        self.assertEqual(set(intake_schema.GATE_C_VALUES),
                         set(validate_manifest.GATE_C_VALUES))

    def test_weight_units_match(self):
        self.assertEqual(set(intake_schema.WEIGHT_UNITS),
                         set(validate_manifest.WEIGHT_UNITS))

    def test_promise_date_fields_match(self):
        self.assertEqual(set(intake_schema.PROMISE_DATE_FIELDS),
                         set(validate_manifest.PROMISE_DATE_FIELDS))


class TestDefaultAnswers(unittest.TestCase):
    def test_defaults_parse_clean(self):
        defaults = intake_schema.default_answers(region="UK")
        parsed = intake_schema.parse_answers(json.dumps(defaults))
        self.assertEqual(parsed["region"], "UK")
        self.assertEqual(parsed["courier"], "royal-mail")

    def test_defaults_include_a_split_order_when_multiple(self):
        defaults = intake_schema.default_answers()
        self.assertGreaterEqual(len(defaults["orders"]), 2)
        self.assertTrue(any(o["split"] for o in defaults["orders"]))


class TestParseAnswers(unittest.TestCase):
    def test_valid_payload_round_trips(self):
        parsed = intake_schema.parse_answers(json.dumps(_valid()))
        self.assertTrue(parsed["shopify_opp"])
        self.assertEqual(len(parsed["orders"]), 2)
        self.assertEqual(parsed["orders"][1]["parcels"][1]["scenario"],
                         "stuck-delay")

    def test_rejects_malformed_json(self):
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            intake_schema.parse_answers("{nope")

    def test_rejects_unknown_region(self):
        payload = _valid()
        payload["region"] = "ES"
        with self.assertRaisesRegex(ValueError, "region"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_rejects_split_used_as_a_scenario(self):
        payload = _valid()
        payload["orders"][0]["scenario"] = "split"
        with self.assertRaisesRegex(ValueError, "scenario"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_rejects_zero_orders(self):
        payload = _valid()
        payload["orders"] = []
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_rejects_more_than_five_orders(self):
        payload = _valid()
        one = {"label": "#x", "fraud": "low", "split": False,
               "scenario": "happy", "courier": None}
        payload["orders"] = [dict(one, label=f"#{i}") for i in range(6)]
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_rejects_duplicate_order_labels(self):
        payload = _valid()
        payload["orders"][1]["label"] = "#1"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_split_order_requires_exactly_two_parcels(self):
        payload = _valid()
        payload["orders"][1]["parcels"] = [
            {"label": "A", "scenario": "happy", "courier": None}]
        with self.assertRaisesRegex(ValueError, "two parcels"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_multi_order_run_needs_at_least_one_split(self):
        payload = _valid()
        payload["orders"][1] = {"label": "#2", "fraud": "medium",
                                "split": False, "scenario": "happy",
                                "courier": None}
        with self.assertRaisesRegex(ValueError, "at least one split"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_single_order_run_needs_no_split(self):
        payload = _valid()
        payload["orders"] = [payload["orders"][0]]
        parsed = intake_schema.parse_answers(json.dumps(payload))
        self.assertEqual(len(parsed["orders"]), 1)

    def test_send_as_is_rejects_populated_extras(self):
        payload = _valid()
        payload["extras"] = {"announced_delivery_date": "2026-09-01"}
        with self.assertRaisesRegex(ValueError, "send-as-is"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_extras_gate_rejects_empty_extras(self):
        payload = _valid()
        payload["gate_c"] = "extras"
        with self.assertRaisesRegex(ValueError, "empty"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_extras_rejects_unknown_key(self):
        payload = _valid()
        payload["gate_c"] = "extras"
        payload["extras"] = {"teleportation": True}
        with self.assertRaisesRegex(ValueError, "unknown extras"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_promise_date_must_be_plain_date(self):
        payload = _valid()
        payload["gate_c"] = "extras"
        payload["extras"] = {"announced_delivery_date": "2026-09-01T10:00:00Z"}
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_weight_unit_must_be_known(self):
        payload = _valid()
        payload["gate_c"] = "extras"
        payload["extras"] = {"article_weights": {"SKU1": {"weight": 300,
                                                          "weight_unit": "stone"}}}
        with self.assertRaisesRegex(ValueError, "weight_unit"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_rejects_unknown_mode(self):
        payload = _valid()
        payload["mode"] = "yolo"
        with self.assertRaisesRegex(ValueError, "mode"):
            intake_schema.parse_answers(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
