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

    def test_defaults(self):
        result = resolve_auto_fields(self.url, self.pool)
        self.assertEqual(result["destination_country"], {"value": "DE", "source": "inferred"})
        self.assertEqual(result["brand.region"], {"value": "DE", "source": "inferred"})
        self.assertEqual(result["brand.category"], {"value": "Home", "source": "inferred"})
        self.assertEqual(result["run.pace"], {"value": "standard", "source": "default"})
        self.assertEqual(
            result["gates.order_lifecycle.gate_c"], {"value": "send-as-is", "source": "default"}
        )

    def test_shopify_opp_is_never_in_resolved_fields(self):
        result = resolve_auto_fields(self.url, self.pool)
        self.assertNotIn("shopify_opp", result)


class ResolveAutoFieldsNoPoolTests(unittest.TestCase):
    """The intake-time call demo-environment makes before the scrape lane has
    produced a pool — resolve_auto_fields(url, None). Country/region still
    resolve from the URL alone; category must be genuinely absent, not
    defaulted, since infer_category([]) would silently return "Fashion" for
    every brand with no signal to back it."""

    def test_succeeds_with_no_pool(self):
        result = resolve_auto_fields("https://brand.de", None)
        self.assertIsInstance(result, dict)

    def test_destination_country_and_region_present_for_de_url(self):
        result = resolve_auto_fields("https://brand.de", None)
        self.assertEqual(
            result["destination_country"], {"value": "DE", "source": "inferred"}
        )
        self.assertEqual(
            result["brand.region"], {"value": "DE", "source": "inferred"}
        )

    def test_brand_category_absent_when_no_pool(self):
        result = resolve_auto_fields("https://brand.de", None)
        self.assertNotIn("brand.category", result)

    def test_static_defaults_still_present_when_no_pool(self):
        result = resolve_auto_fields("https://brand.de", None)
        self.assertEqual(result["run.pace"], {"value": "standard", "source": "default"})
        self.assertEqual(
            result["gates.order_lifecycle.gate_c"],
            {"value": "send-as-is", "source": "default"},
        )

    def test_empty_pool_list_is_not_the_same_as_no_pool(self):
        # A pool that exists and is genuinely empty still returns
        # brand.category (falling back to DEFAULT_CATEGORY) — only a
        # missing pool (None) omits the key.
        result = resolve_auto_fields("https://brand.de", [])
        self.assertIn("brand.category", result)
        self.assertEqual(
            result["brand.category"], {"value": "Fashion", "source": "inferred"}
        )


class CliNoPoolFileTests(unittest.TestCase):
    """--product-pool-file is optional now — the CLI must not exit 2 when
    it's omitted, and must not print a brand.category key in that case."""

    def _run_cli(self, extra_args=()):
        import subprocess

        script = Path(__file__).resolve().parents[1] / "resolve_auto_defaults.py"
        return subprocess.run(
            [sys.executable, str(script), "--prospect-url",
             "https://example.de", *extra_args],
            capture_output=True,
            text=True,
        )

    def test_no_product_pool_file_succeeds(self):
        result = self._run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_product_pool_file_output_has_no_category(self):
        import json

        result = self._run_cli()
        payload = json.loads(result.stdout)
        self.assertNotIn("brand.category", payload)
        self.assertEqual(payload["destination_country"]["value"], "DE")


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
