"""Unit tests for inline_assets. Stdlib unittest — no pytest, no network."""
import base64
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import inline_assets  # noqa: E402

POOL = [
    {"id": "E491096-000", "sku": "E491096-000-57", "name": "Zip-Up Blouson",
     "price": "49.90", "product_type": "Jackets",
     "image_url": "https://img.example/a.jpg",
     "pdp_url": "https://example/a"},
    {"id": "E481610-000", "sku": "E481610-000-58", "name": "Shoulder Bag",
     "price": "14.90", "product_type": "Bags",
     "image_url": "https://img.example/big.jpg",
     "pdp_url": "https://example/b"},
]
TOKENS = {
    "tokens": {"BRAND_NAME": "UNIQLO"},
    "logo": {"type": "inline_svg", "markup": "<svg><title>U</title></svg>"},
    "hero": {"url": "https://img.example/hero.jpg", "alt": "hero"},
}


def fake_fetch(url):
    if "big" in url:
        return (b"x" * (inline_assets.MAX_ASSET_BYTES + 1), "image/jpeg")
    return (b"\xff\xd8imagedata", "image/jpeg")


class TestInlineAssets(unittest.TestCase):
    def test_to_data_uri_round_trips(self):
        uri = inline_assets.to_data_uri(b"abc", "image/png")
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        self.assertEqual(base64.b64decode(uri.split(",", 1)[1]), b"abc")

    def test_should_skip_at_the_boundary(self):
        self.assertFalse(
            inline_assets.should_skip(inline_assets.MAX_ASSET_BYTES))
        self.assertTrue(
            inline_assets.should_skip(inline_assets.MAX_ASSET_BYTES + 1))

    def test_products_are_inlined_by_sku(self):
        assets = inline_assets.build_assets(POOL, TOKENS, fake_fetch)
        entry = assets["products"]["E491096-000-57"]
        self.assertTrue(entry["data_uri"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(entry["name"], "Zip-Up Blouson")
        self.assertEqual(entry["price"], "49.90")

    def test_oversized_asset_is_skipped_not_inlined(self):
        assets = inline_assets.build_assets(POOL, TOKENS, fake_fetch)
        self.assertIsNone(assets["products"]["E481610-000-58"]["data_uri"])
        self.assertIn("E481610-000-58", str(assets["skipped"]))

    def test_hero_and_logo_captured(self):
        assets = inline_assets.build_assets(POOL, TOKENS, fake_fetch)
        self.assertTrue(assets["hero"]["data_uri"].startswith("data:"))
        self.assertIn("<svg", assets["logo_svg"])

    def test_image_logo_is_fetched_and_inlined(self):
        # The common case: the logo is a URL, not inline SVG. Left unfetched,
        # it has no data: URI, so the CSP blocks it and the run page shows a
        # brand with no logo at all (hit live 2026-08-11 on Currys).
        tokens = dict(TOKENS,
                      logo={"type": "image", "url": "https://img.example/l.svg"})
        assets = inline_assets.build_assets(POOL, tokens, fake_fetch)
        self.assertTrue(assets["logo_data_uri"].startswith("data:"))
        self.assertEqual(assets["logo_url"], "https://img.example/l.svg")

    def test_inline_svg_logo_has_no_data_uri_to_fetch(self):
        assets = inline_assets.build_assets(POOL, TOKENS, fake_fetch)
        self.assertIn("<svg", assets["logo_svg"])
        self.assertIsNone(assets["logo_data_uri"])

    def test_logo_fetch_failure_is_recorded_not_raised(self):
        def boom(url):
            raise OSError("connection reset")
        tokens = dict(TOKENS,
                      logo={"type": "image", "url": "https://img.example/l.svg"})
        assets = inline_assets.build_assets(POOL, tokens, boom)
        self.assertIsNone(assets["logo_data_uri"])
        self.assertIn("logo", str(assets["skipped"]))

    def test_local_logo_svg_wins_over_a_blocked_fetch(self):
        # Some brands' CDNs refuse server-side fetches outright (Currys' WAF
        # 403s every user-agent), while the Browser pane — holding a real
        # session — gets the file fine. Dropping it into scrape/logo.svg is the
        # documented escape hatch, so no run loses its logo to a WAF.
        def boom(url):
            raise OSError("HTTP Error 403: Forbidden")
        tokens = dict(TOKENS,
                      logo={"type": "image", "url": "https://img.example/l.svg"})
        assets = inline_assets.build_assets(POOL, tokens, boom,
                                            local_logo="<svg>brand</svg>")
        self.assertTrue(
            assets["logo_data_uri"].startswith("data:image/svg+xml;base64,"))
        self.assertNotIn("logo", str(assets["skipped"]))

    def test_fetch_failure_is_recorded_not_raised(self):
        def boom(url):
            raise OSError("connection reset")
        assets = inline_assets.build_assets(POOL, TOKENS, boom)
        self.assertIsNone(assets["products"]["E491096-000-57"]["data_uri"])
        self.assertEqual(len(assets["skipped"]), 3)  # 2 products + hero


if __name__ == "__main__":
    unittest.main()
