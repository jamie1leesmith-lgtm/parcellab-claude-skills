import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_auto_defaults import infer_country, infer_category, resolve_auto_fields


class InferCountryTests(unittest.TestCase):
    def test_de_tld(self):
        self.assertEqual(infer_country("https://www.brand.de/shop", []), "DE")

    def test_uk_co_dot_uk_tld(self):
        self.assertEqual(infer_country("https://www.brand.co.uk/shop", []), "UK")

    def test_uk_dot_uk_tld(self):
        self.assertEqual(infer_country("https://brand.uk", []), "UK")

    def test_currency_symbol_fallback_euro(self):
        pool = [{"name": "Tee", "price": "€29.00"}]
        self.assertEqual(infer_country("https://brand.com", pool), "DE")

    def test_currency_symbol_fallback_pound(self):
        pool = [{"name": "Tee", "price": "£29.00"}]
        self.assertEqual(infer_country("https://brand.com", pool), "UK")

    def test_no_signal_defaults_to_us(self):
        pool = [{"name": "Tee", "price": "29.00"}]
        self.assertEqual(infer_country("https://brand.com", pool), "US")

    def test_tld_wins_over_currency(self):
        # a .de site pricing in USD is still a DE site
        pool = [{"name": "Tee", "price": "$29.00"}]
        self.assertEqual(infer_country("https://brand.de", pool), "DE")

    def test_path_locale_gb_segment(self):
        # live-verified 2026-08-13: eu.patagonia.com/gb/en/home has a .com
        # TLD (no signal) but a /gb/ locale segment identifying the UK site.
        self.assertEqual(
            infer_country("https://eu.patagonia.com/gb/en/home", []), "UK"
        )

    def test_path_locale_de_segment(self):
        self.assertEqual(
            infer_country("https://eu.brand.com/de/de/home", []), "DE"
        )

    def test_tld_wins_over_path_locale(self):
        # a .de TLD is decisive even if the path also names a different
        # country's locale segment.
        self.assertEqual(
            infer_country("https://brand.de/gb/en/home", []), "DE"
        )

    def test_path_locale_wins_over_currency(self):
        pool = [{"name": "Tee", "price": "$29.00"}]
        self.assertEqual(
            infer_country("https://eu.brand.com/gb/en/home", pool), "UK"
        )


class InferCategoryTests(unittest.TestCase):
    def test_electronics_match(self):
        pool = [{"name": "Phone case", "product_type": "Electronic Accessory"}]
        self.assertEqual(infer_category(pool), "Electronics")

    def test_home_match(self):
        pool = [{"name": "Vase", "product_type": "Home Decor"}]
        self.assertEqual(infer_category(pool), "Home")

    def test_fashion_match(self):
        pool = [{"name": "Trainer", "product_type": "Shoe"}]
        self.assertEqual(infer_category(pool), "Fashion")

    def test_no_products_defaults_to_fashion(self):
        self.assertEqual(infer_category([]), "Fashion")

    def test_no_type_match_defaults_to_fashion(self):
        pool = [{"name": "Mystery Item", "product_type": "Widget"}]
        self.assertEqual(infer_category(pool), "Fashion")

    def test_majority_type_wins_over_first_seen(self):
        pool = [
            {"name": "Vase", "product_type": "Home Decor"},
            {"name": "Shoe", "product_type": "Sneaker"},
            {"name": "Boot", "product_type": "Boot"},
        ]
        self.assertEqual(infer_category(pool), "Fashion")

    def test_tie_falls_back_to_default_category_not_alphabetical(self):
        # One product matches Electronics; the other has no keyword match,
        # which counts as Fashion per the majority-voting behavior above.
        # That is a 1-1 tie, not a clear match, so it must fall back to
        # DEFAULT_CATEGORY ("Fashion") rather than picking "Electronics"
        # just because it sorts first alphabetically.
        pool = [
            {"name": "Phone case", "product_type": "Electronic Accessory"},
            {"name": "Mystery Item", "product_type": "Widget"},
        ]
        self.assertEqual(infer_category(pool), "Fashion")


class ResolveAutoFieldsTests(unittest.TestCase):
    def setUp(self):
        self.url = "https://brand.de"
        self.pool = [{"name": "Vase", "product_type": "Home Decor", "price": "€10"}]

    def test_defaults_with_no_answers_doc(self):
        result = resolve_auto_fields(self.url, self.pool)
        self.assertEqual(result["destination_country"], {"value": "DE", "source": "inferred"})
        self.assertEqual(result["brand.region"], {"value": "DE", "source": "inferred"})
        self.assertEqual(result["brand.category"], {"value": "Home", "source": "inferred"})
        self.assertEqual(result["run.pace"], {"value": "standard", "source": "default"})
        self.assertEqual(
            result["gates.order_lifecycle.gate_c"], {"value": "send-as-is", "source": "default"}
        )
        self.assertEqual(result["_ignored_doc_keys"], [])

    def test_answers_doc_overrides_known_field(self):
        result = resolve_auto_fields(self.url, self.pool, answers_doc={"run.pace": "fast"})
        self.assertEqual(result["run.pace"], {"value": "fast", "source": "doc"})
        # untouched fields keep their own default/inferred value
        self.assertEqual(result["destination_country"], {"value": "DE", "source": "inferred"})

    def test_answers_doc_can_override_inferred_field(self):
        result = resolve_auto_fields(
            self.url, self.pool, answers_doc={"destination_country": "US"}
        )
        self.assertEqual(result["destination_country"], {"value": "US", "source": "doc"})

    def test_unknown_doc_key_is_ignored_and_reported(self):
        result = resolve_auto_fields(self.url, self.pool, answers_doc={"not_a_field": "x"})
        self.assertEqual(result["_ignored_doc_keys"], ["not_a_field"])
        self.assertEqual(result["run.pace"], {"value": "standard", "source": "default"})

    def test_never_ask_fields_absent(self):
        result = resolve_auto_fields(self.url, self.pool)
        self.assertNotIn("returns_in_scope", result)
        self.assertNotIn("shopify_opp", result)


class CliProductPoolShapeTests(unittest.TestCase):
    """scrape/product-pool.json may be a bare list or {"products": [...]} —
    inline_assets.py already accepts both; the CLI must too (live-verified
    2026-08-13: the Patagonia scrape agent wrote the wrapped shape and the
    CLI crashed with AttributeError: 'str' object has no attribute 'get',
    since iterating a dict yields its keys, not its values)."""

    def _run_cli(self, pool_payload):
        import json
        import subprocess
        import tempfile

        script = Path(__file__).resolve().parents[1] / "resolve_auto_defaults.py"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(pool_payload, f)
            pool_path = f.name

        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--prospect-url",
                "https://brand.com",
                "--product-pool-file",
                pool_path,
            ],
            capture_output=True,
            text=True,
        )
        Path(pool_path).unlink()
        return result

    def test_bare_list_shape(self):
        result = self._run_cli([{"name": "Tee", "price": "$10", "product_type": "Shirt"}])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrapped_products_shape(self):
        result = self._run_cli(
            {"products": [{"name": "Tee", "price": "$10", "product_type": "Shirt"}]}
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
