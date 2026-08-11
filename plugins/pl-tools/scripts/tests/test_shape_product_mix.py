import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shape_product_mix import (
    build_mix,
    build_variants,
    normalise_price,
    resolve_options,
    shape_prices,
)

SCRIPT = Path(__file__).resolve().parents[1] / "shape_product_mix.py"


def d(value):
    return Decimal(value)


def prices(*values):
    return [d(v) for v in values]


class NormalisePriceTests(unittest.TestCase):
    def test_strips_currency_symbols(self):
        self.assertEqual(normalise_price("£129.99"), d("129.99"))
        self.assertEqual(normalise_price("$28.00"), d("28.00"))

    def test_handles_decimal_comma(self):
        self.assertEqual(normalise_price("€64,50"), d("64.50"))

    def test_handles_thousands_comma(self):
        self.assertEqual(normalise_price("1,299.00"), d("1299.00"))

    def test_pads_to_two_decimal_places(self):
        self.assertEqual(normalise_price("129.9"), d("129.90"))
        self.assertEqual(normalise_price(28), d("28.00"))

    def test_rounds_half_up(self):
        self.assertEqual(normalise_price("10.005"), d("10.01"))

    def test_rejects_unparseable(self):
        with self.assertRaises(ValueError):
            normalise_price("Price on request")

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            normalise_price("")


class ShapePricesTests(unittest.TestCase):
    def test_natural_pair_with_dearer_product_is_untouched(self):
        original = prices("28.00", "28.00", "64.00", "90.00")
        new, adjusted, roles = shape_prices(list(original))
        self.assertEqual(new, original)
        self.assertEqual(adjusted, [])
        self.assertEqual(sorted(roles["pair"]), [0, 1])
        self.assertEqual(roles["higher"], 3)

    def test_all_distinct_converges_closest_eligible_pair_downward(self):
        new, adjusted, roles = shape_prices(prices("28.00", "32.00", "64.00", "90.00"))
        self.assertEqual(new, prices("28.00", "28.00", "64.00", "90.00"))
        self.assertEqual(adjusted, [1])
        self.assertEqual(sorted(roles["pair"]), [0, 1])

    def test_pair_can_be_the_middle_two_when_that_gap_is_smallest(self):
        new, adjusted, roles = shape_prices(prices("10.00", "100.00", "105.00", "110.00"))
        self.assertEqual(new, prices("10.00", "100.00", "100.00", "110.00"))
        self.assertEqual(adjusted, [2])
        self.assertEqual(sorted(roles["pair"]), [1, 2])
        self.assertEqual(roles["lower"], 0)

    def test_all_identical_leaves_pair_and_nudges_the_dearest(self):
        new, adjusted, roles = shape_prices(prices("50.00", "50.00", "50.00", "50.00"))
        self.assertEqual(adjusted, [3])
        self.assertEqual(new[3], d("60.00"))
        self.assertEqual(new[:3], prices("50.00", "50.00", "50.00"))

    def test_dearest_tied_with_pair_is_nudged_above_it(self):
        new, _, roles = shape_prices(prices("90.00", "90.00", "90.00", "10.00"))
        self.assertGreater(new[roles["higher"]], new[roles["pair"][0]])
        self.assertEqual(roles["lower"], 3)

    def test_pair_never_includes_the_dearest_product(self):
        for case in (
            prices("28.00", "32.00", "64.00", "90.00"),
            prices("10.00", "100.00", "105.00", "110.00"),
            prices("50.00", "50.00", "50.00", "50.00"),
            prices("5.00", "5.00", "5.00", "900.00"),
        ):
            new, _, roles = shape_prices(list(case))
            self.assertNotIn(roles["higher"], roles["pair"], case)
            self.assertGreater(new[roles["higher"]], new[roles["pair"][0]], case)

    def test_result_always_supports_even_and_upward_uneven(self):
        for case in (
            prices("28.00", "32.00", "64.00", "90.00"),
            prices("50.00", "50.00", "50.00", "50.00"),
            prices("28.00", "28.00", "64.00", "90.00"),
            prices("5.00", "500.00", "501.00", "999.00"),
            prices("90.00", "90.00", "90.00", "10.00"),
        ):
            new, _, roles = shape_prices(list(case))
            i, j = roles["pair"]
            self.assertEqual(new[i], new[j], case)
            self.assertGreater(new[roles["higher"]], new[i], case)

    def test_lower_is_none_when_nothing_sits_below_the_pair(self):
        _, _, roles = shape_prices(prices("28.00", "28.00", "64.00", "90.00"))
        self.assertIsNone(roles["lower"])

    def test_rejects_anything_other_than_four(self):
        with self.assertRaises(ValueError):
            shape_prices(prices("28.00", "28.00", "64.00"))
        with self.assertRaises(ValueError):
            shape_prices(prices("28.00", "28.00", "64.00", "90.00", "99.00"))


class ResolveOptionsTests(unittest.TestCase):
    def test_two_axes_are_both_kept(self):
        product = {"options": [
            {"name": "Size", "values": ["S", "M", "L"]},
            {"name": "Colour", "values": ["Black", "Navy"]},
        ]}
        axes = resolve_options(product)
        self.assertEqual([a["name"] for a in axes], ["Size", "Colour"])

    def test_single_value_axis_is_dropped(self):
        product = {"options": [
            {"name": "Size", "values": ["S", "M"]},
            {"name": "Colour", "values": ["Black"]},
        ]}
        self.assertEqual([a["name"] for a in resolve_options(product)], ["Size"])

    def test_no_usable_axis_falls_back_to_size(self):
        self.assertEqual(resolve_options({}), [{"name": "Size", "values": ["S", "M", "L"]}])
        self.assertEqual(
            resolve_options({"options": [{"name": "Colour", "values": ["Black"]}]}),
            [{"name": "Size", "values": ["S", "M", "L"]}],
        )

    def test_values_are_capped_at_three(self):
        product = {"options": [{"name": "Size", "values": ["XS", "S", "M", "L", "XL"]}]}
        self.assertEqual(resolve_options(product)[0]["values"], ["XS", "S", "M"])

    def test_duplicate_values_are_removed_in_order(self):
        product = {"options": [{"name": "Size", "values": ["S", "S", "M"]}]}
        self.assertEqual(resolve_options(product)[0]["values"], ["S", "M"])

    def test_every_axis_returned_has_at_least_two_values(self):
        for product in ({}, {"options": []}, {"options": [{"name": "X", "values": ["only"]}]}):
            for axis in resolve_options(product):
                self.assertGreaterEqual(len(axis["values"]), 2, product)

    def test_four_axes_are_truncated_to_three(self):
        product = {"options": [
            {"name": "Size", "values": ["S", "M"]},
            {"name": "Colour", "values": ["Black", "Navy"]},
            {"name": "Material", "values": ["Cotton", "Wool"]},
            {"name": "Fit", "values": ["Regular", "Slim"]},
        ]}
        axes = resolve_options(product)
        self.assertEqual([a["name"] for a in axes], ["Size", "Colour", "Material"])

    def test_exactly_three_axes_are_kept_unchanged(self):
        product = {"options": [
            {"name": "Size", "values": ["S", "M"]},
            {"name": "Colour", "values": ["Black", "Navy"]},
            {"name": "Material", "values": ["Cotton", "Wool"]},
        ]}
        axes = resolve_options(product)
        self.assertEqual([a["name"] for a in axes], ["Size", "Colour", "Material"])


class BuildVariantsTests(unittest.TestCase):
    def test_two_axes_produce_the_cartesian_product(self):
        options = [
            {"name": "Size", "values": ["S", "M", "L"]},
            {"name": "Colour", "values": ["Black", "Navy"]},
        ]
        variants = build_variants(options, d("28.00"), 25, "gid://shopify/Location/1")
        self.assertEqual(len(variants), 6)
        self.assertEqual(
            variants[0]["option_values"],
            [{"option_name": "Size", "name": "S"}, {"option_name": "Colour", "name": "Black"}],
        )

    def test_every_variant_carries_price_stock_and_location(self):
        options = [{"name": "Size", "values": ["S", "M"]}]
        variants = build_variants(options, d("28.00"), 25, "gid://shopify/Location/1")
        for variant in variants:
            self.assertEqual(variant["price"], "28.00")
            self.assertEqual(variant["quantity"], 25)
            self.assertEqual(variant["location_id"], "gid://shopify/Location/1")


class BuildMixTests(unittest.TestCase):
    def payload(self, price_values, types=None, options=None):
        types = types or ["Jumper", "Jeans", "Shoes", "Jacket"]
        return {
            "products": [
                {"name": f"Product {i}", "product_type": types[i], "price": p,
                 "image_url": f"https://x/{i}.jpg", "pdp_url": f"https://x/p/{i}",
                 "options": options if options is not None else [
                     {"name": "Size", "values": ["S", "M", "L"]},
                     {"name": "Colour", "values": ["Black", "Navy"]},
                 ]}
                for i, p in enumerate(price_values)
            ],
            "location_id": "gid://shopify/Location/1",
            "prospect_handle": "acme",
            "stock_per_variant": 25,
        }

    def test_every_variant_of_every_product_has_non_zero_stock(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00", "90.00"]))
        for product in result["products"]:
            self.assertGreaterEqual(product["variant_count"], 2)
            for variant in product["variants"]:
                self.assertGreater(variant["quantity"], 0)

    def test_every_product_has_at_least_two_variants_even_with_no_options(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00", "90.00"], options=[]))
        for product in result["products"]:
            self.assertGreaterEqual(product["variant_count"], 2)

    def test_tags_include_seed_and_prospect(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00", "90.00"]))
        for product in result["products"]:
            self.assertIn("pl-demo-seed", product["tags"])
            self.assertIn("pl-prospect-acme", product["tags"])

    def test_natural_pair_produces_no_adjustments(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00", "90.00"]))
        self.assertEqual(result["adjustments"], [])
        self.assertTrue(all(not p["adjusted"] for p in result["products"]))

    def test_adjustment_reports_from_and_to_and_keeps_original(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00", "90.00"]))
        self.assertEqual(len(result["adjustments"]), 1)
        self.assertEqual(result["adjustments"][0]["from"], "32.00")
        self.assertEqual(result["adjustments"][0]["to"], "28.00")
        adjusted = [p for p in result["products"] if p["adjusted"]][0]
        self.assertEqual(adjusted["original_price"], "32.00")
        self.assertEqual(adjusted["price"], "28.00")

    def test_reports_all_four_demos(self):
        result = build_mix(self.payload(["10.00", "100.00", "105.00", "110.00"]))
        demos = result["demos"]
        self.assertIn("→", demos["in_product_even"]["swap"])
        self.assertEqual(len(demos["cross_product_even"]), 2)
        self.assertEqual(demos["uneven_upward"]["balance"], "10.00")
        self.assertEqual(demos["uneven_downward"]["refund"], "90.00")

    def test_downward_demo_is_null_when_unavailable(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00", "90.00"]))
        self.assertIsNone(result["demos"]["uneven_downward"])

    def test_upward_balance_is_always_positive(self):
        for values in (["28.00", "32.00", "64.00", "90.00"],
                       ["50.00", "50.00", "50.00", "50.00"],
                       ["90.00", "90.00", "90.00", "10.00"]):
            result = build_mix(self.payload(values))
            self.assertGreater(Decimal(result["demos"]["uneven_upward"]["balance"]), 0, values)

    def test_duplicate_product_types_warn_but_do_not_fail(self):
        result = build_mix(self.payload(
            ["28.00", "28.00", "64.00", "90.00"],
            types=["Jumper", "Jumper", "Shoes", "Jacket"],
        ))
        self.assertTrue(any("Jumper" in w for w in result["warnings"]))
        self.assertEqual(len(result["products"]), 4)

    def test_distinct_types_produce_no_warnings(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00", "90.00"]))
        self.assertEqual(result["warnings"], [])

    def test_rejects_wrong_product_count(self):
        payload = self.payload(["28.00", "28.00", "64.00", "90.00"])
        payload["products"] = payload["products"][:3]
        with self.assertRaises(ValueError):
            build_mix(payload)

    def test_rejects_zero_stock(self):
        payload = self.payload(["28.00", "28.00", "64.00", "90.00"])
        payload["stock_per_variant"] = 0
        with self.assertRaises(ValueError):
            build_mix(payload)

    def test_prices_are_serialised_as_strings(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00", "90.00"]))
        for product in result["products"]:
            self.assertIsInstance(product["price"], str)

    def test_rejects_missing_location_id(self):
        payload = self.payload(["28.00", "28.00", "64.00", "90.00"])
        del payload["location_id"]
        with self.assertRaises(ValueError):
            build_mix(payload)

    def test_rejects_none_location_id(self):
        payload = self.payload(["28.00", "28.00", "64.00", "90.00"])
        payload["location_id"] = None
        with self.assertRaises(ValueError):
            build_mix(payload)

    def test_rejects_empty_location_id(self):
        payload = self.payload(["28.00", "28.00", "64.00", "90.00"])
        payload["location_id"] = "   "
        with self.assertRaises(ValueError):
            build_mix(payload)

    def test_variant_count_cannot_exceed_27(self):
        # 4 axes x 3 values each would be 81 variants and >3 options per product,
        # which Shopify itself refuses -- resolve_options caps axes at 3, so the
        # worst case is 3 axes x 3 values = 27.
        options = [
            {"name": "Size", "values": ["S", "M", "L"]},
            {"name": "Colour", "values": ["Black", "Navy", "Red"]},
            {"name": "Material", "values": ["Cotton", "Wool", "Linen"]},
            {"name": "Fit", "values": ["Regular", "Slim", "Loose"]},
        ]
        result = build_mix(self.payload(
            ["28.00", "28.00", "64.00", "90.00"], options=options
        ))
        for product in result["products"]:
            self.assertLessEqual(product["variant_count"], 27)
            self.assertEqual(product["variant_count"], 27)


class CliTests(unittest.TestCase):
    def run_script(self, payload):
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload), capture_output=True, text=True,
        )

    def payload(self, price_values):
        return {
            "products": [
                {"name": f"P{i}", "product_type": f"T{i}", "price": p,
                 "image_url": f"https://x/{i}.jpg", "pdp_url": f"https://x/{i}",
                 "options": [{"name": "Size", "values": ["S", "M"]}]}
                for i, p in enumerate(price_values)
            ],
            "location_id": "gid://shopify/Location/1",
            "prospect_handle": "acme",
        }

    def test_reads_stdin_and_writes_json_to_stdout(self):
        proc = self.run_script(self.payload(["28.00", "32.00", "64.00", "90.00"]))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(json.loads(proc.stdout)["products"]), 4)

    def test_defaults_stock_when_omitted(self):
        proc = self.run_script(self.payload(["28.00", "32.00", "64.00", "90.00"]))
        product = json.loads(proc.stdout)["products"][0]
        self.assertGreater(product["variants"][0]["quantity"], 0)

    def test_exits_non_zero_on_unparseable_price(self):
        proc = self.run_script(self.payload(["Price on request", "32.00", "64.00", "90.00"]))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("shape_product_mix", proc.stderr)


class TestExtrasFile(unittest.TestCase):
    def payload(self):
        return {
            "products": [
                {"name": "Jumper", "product_type": "Jumper", "price": "50.00",
                 "options": [], "image_url": "https://x/i.jpg", "pdp_url": "https://x/p"},
                {"name": "Jeans", "product_type": "Jeans", "price": "60.00",
                 "options": [], "image_url": "https://x/i.jpg", "pdp_url": "https://x/p"},
                {"name": "Shoes", "product_type": "Shoes", "price": "80.00",
                 "options": [], "image_url": "https://x/i.jpg", "pdp_url": "https://x/p"},
                {"name": "Coat", "product_type": "Coat", "price": "120.00",
                 "options": [], "image_url": "https://x/i.jpg", "pdp_url": "https://x/p"},
            ],
            "location_id": "gid://shopify/Location/1",
            "prospect_handle": "acme",
        }

    def extras(self):
        return [
            {"name": "Scarf", "product_type": "Scarf", "price": "22.50",
             "options": [{"name": "Colour", "values": ["Red", "Blue"]}],
             "image_url": "https://x/s.jpg", "pdp_url": "https://x/s"},
        ]

    def test_extras_appended_at_own_price(self):
        out = build_mix(self.payload(), extras=self.extras())
        self.assertEqual(len(out["products"]), 5)
        scarf = out["products"][-1]
        self.assertEqual(scarf["name"], "Scarf")
        self.assertEqual(scarf["price"], "22.50")
        self.assertEqual(scarf["original_price"], "22.50")
        self.assertFalse(scarf["adjusted"])
        self.assertEqual(scarf["options"][0]["name"], "Colour")
        self.assertEqual(scarf["variant_count"], 2)
        self.assertIn("pl-prospect-acme", scarf["tags"])

    def test_demos_ignore_extras(self):
        base = build_mix(self.payload())
        with_extras = build_mix(self.payload(), extras=self.extras())
        self.assertEqual(base["demos"], with_extras["demos"])
        self.assertEqual(base["adjustments"], with_extras["adjustments"])

    def richer_extras(self):
        # Two axes (Colour x Size) => variant_count 6, more than any core-4 product
        # (all of which fall back to the default 3-value Size axis => variant_count 3).
        # This is the case that would make an extra win a naive max()-over-everything
        # showcase pick.
        return [
            {"name": "Beanie", "product_type": "Beanie", "price": "18.00",
             "options": [
                 {"name": "Colour", "values": ["Red", "Blue"]},
                 {"name": "Size", "values": ["S", "M", "L"]},
             ],
             "image_url": "https://x/b.jpg", "pdp_url": "https://x/b"},
        ]

    def test_demos_ignore_extras_even_when_extra_has_more_variants(self):
        base = build_mix(self.payload())
        with_extras = build_mix(self.payload(), extras=self.richer_extras())
        self.assertEqual(with_extras["products"][-1]["variant_count"], 6)
        self.assertEqual(base["demos"], with_extras["demos"])
        self.assertEqual(base["adjustments"], with_extras["adjustments"])
        core4_names = {p["name"] for p in base["products"]}
        self.assertIn(with_extras["demos"]["in_product_even"]["product"], core4_names)

    def test_extras_bad_price_fails_loud(self):
        bad = [{"name": "X", "product_type": "X", "price": "??", "options": []}]
        with self.assertRaises(ValueError):
            build_mix(self.payload(), extras=bad)


class TestExtrasFileCli(unittest.TestCase):
    """--extras-file through argparse, which the in-process tests never touch."""

    def payload(self):
        return {
            "products": [
                {"name": f"P{i}", "product_type": f"T{i}", "price": p,
                 "image_url": f"https://x/{i}.jpg", "pdp_url": f"https://x/{i}",
                 "options": [{"name": "Size", "values": ["S", "M"]}]}
                for i, p in enumerate(["28.00", "32.00", "64.00", "90.00"])
            ],
            "location_id": "gid://shopify/Location/1",
            "prospect_handle": "acme",
        }

    def run_script(self, extras_path):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--extras-file", str(extras_path)],
            input=json.dumps(self.payload()), capture_output=True, text=True,
        )

    def write(self, tmpdir, content):
        path = Path(tmpdir) / "extras.json"
        path.write_text(content)
        return path

    def test_valid_extras_file_end_to_end(self):
        extras = [
            {"name": "Scarf", "product_type": "Scarf", "price": "22.50",
             "options": [{"name": "Colour", "values": ["Red", "Blue"]}],
             "image_url": "https://x/s.jpg", "pdp_url": "https://x/s"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = self.run_script(self.write(tmpdir, json.dumps(extras)))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(len(out["products"]), 5)
        scarf = out["products"][-1]
        self.assertEqual(scarf["name"], "Scarf")
        self.assertEqual(scarf["price"], "22.50")
        self.assertEqual(scarf["variant_count"], 2)

    def test_non_array_extras_file_exits_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = self.run_script(self.write(tmpdir, json.dumps({"name": "Scarf"})))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--extras-file must contain a JSON array", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_missing_extras_file_exits_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = self.run_script(Path(tmpdir) / "nope.json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("shape_product_mix", proc.stderr)


if __name__ == "__main__":
    unittest.main()
