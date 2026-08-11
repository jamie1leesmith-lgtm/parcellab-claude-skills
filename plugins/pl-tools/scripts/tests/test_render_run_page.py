"""Unit tests for render_run_page. Stdlib unittest — no pytest."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import render_run_page  # noqa: E402
import run_state  # noqa: E402


def a_state(finished=False):
    d = tempfile.mkdtemp()
    run_state.init(d, "uniqlo-20260811-1913", "engage", "Demo - JLS")
    run_state.set_lane(d, "scrape", "ok")
    run_state.set_lane(d, "template", "published", layout_id=20701,
                       store="JLS Order")
    run_state.set_lane(d, "orders", "running")
    run_state.add_order(d, "Clean delivery", "UNQ-1786473062", [
        {"label": "A", "tracking_number": "15221962690914",
         "courier": "dpd-uk",
         "planned": ["InTransit", "OutForDelivery", "Delivered"]},
    ])
    run_state.confirm_event(d, "15221962690914", "InTransit",
                            "2026-08-11T18:43:27Z", 204)
    run_state.set_schedule(d, "2026-08-11T18:40:27Z", 180)
    if finished:
        run_state.finish(d)
    return run_state.load(d)


class TestRenderRunPage(unittest.TestCase):
    def test_renders_run_id_and_account(self):
        html = render_run_page.render(a_state())
        self.assertIn("uniqlo-20260811-1913", html)
        self.assertIn("Demo - JLS", html)

    def test_no_external_references_anywhere(self):
        # The artifact CSP blocks these; a remote image renders as a broken icon.
        html = render_run_page.render(a_state())
        self.assertNotIn('<img src="http', html)
        self.assertNotIn('<script src="http', html)
        self.assertNotIn('<link rel="stylesheet" href="http', html)

    def test_confirmed_event_renders_confirmed(self):
        html = render_run_page.render(a_state())
        self.assertIn("s-confirmed", html)
        self.assertIn("InTransit", html)

    def test_unconfirmed_planned_event_is_not_marked_confirmed(self):
        html = render_run_page.render(a_state())
        delivered = html[html.index("Delivered"):]
        self.assertNotIn("s-confirmed", delivered[:200])

    def test_lane_status_appears(self):
        html = render_run_page.render(a_state())
        self.assertIn("published", html)
        self.assertIn("20701", html)

    def test_failure_renders_as_failed(self):
        state = a_state()
        state["failures"].append({"lane": "cdc", "detail": "500 from API",
                                  "at": "2026-08-11T19:00:00Z"})
        html = render_run_page.render(state)
        self.assertIn("s-failed", html)
        self.assertIn("500 from API", html)

    def test_state_of_confirmed(self):
        confirmed = [{"status": "InTransit", "at": "x", "http": 204}]
        self.assertEqual(
            render_run_page.state_of("InTransit", confirmed), "confirmed")

    def test_state_of_pending(self):
        self.assertEqual(render_run_page.state_of("Delivered", []), "pending")

    def test_dark_mode_and_theme_overrides_present(self):
        html = render_run_page.render(a_state())
        self.assertIn("prefers-color-scheme: dark", html)
        self.assertIn('data-theme="dark"', html)

    def test_wide_tables_scroll_inside_themselves(self):
        self.assertIn("overflow-x", render_run_page.render(a_state()))


ASSETS = {
    "logo_svg": "<svg><title>UNIQLO</title></svg>",
    "hero": {"alt": "hero", "data_uri": "data:image/jpeg;base64,aGVybw=="},
    "tokens": {"BRAND_NAME": "UNIQLO", "CTA_BG": "#000000"},
    "products": {
        "E491096-000-57": {"name": "Zip-Up Blouson", "price": "49.90",
                           "product_type": "Jackets",
                           "pdp_url": "https://example/a",
                           "image_url": "https://img.example/a.jpg",
                           "data_uri": "data:image/jpeg;base64,aW1n"},
        "E481610-000-58": {"name": "Shoulder Bag", "price": "14.90",
                           "product_type": "Bags",
                           "pdp_url": "https://example/b",
                           "image_url": "https://img.example/b.jpg",
                           "data_uri": None},
    },
    "skipped": [{"asset": "E481610-000-58", "reason": "too big"}],
}


class TestShowcase(unittest.TestCase):
    def test_logo_svg_is_inlined(self):
        html = render_run_page.render(a_state(), assets=ASSETS)
        self.assertIn("<svg><title>UNIQLO</title></svg>", html)

    def test_product_with_data_uri_renders_an_image(self):
        html = render_run_page.render(a_state(), assets=ASSETS)
        self.assertIn('src="data:image/jpeg;base64,aW1n"', html)
        self.assertIn("Zip-Up Blouson", html)

    def test_product_without_data_uri_renders_text_card_not_broken_image(self):
        html = render_run_page.render(a_state(), assets=ASSETS)
        self.assertIn("Shoulder Bag", html)
        self.assertNotIn("https://img.example/b.jpg", html)
        self.assertNotIn('<img src="http', html)

    def test_template_is_embedded_as_iframe_srcdoc(self):
        html = render_run_page.render(
            a_state(), assets=ASSETS,
            template_html='<html><body><img src="https://img.example/a.jpg"/>'
                          '</body></html>')
        self.assertIn("<iframe", html)
        self.assertIn("srcdoc=", html)

    def test_preview_template_swaps_remote_images_for_data_uris(self):
        out = render_run_page.preview_template(
            '<img src="https://img.example/a.jpg" width="600"/>', ASSETS)
        self.assertIn('src="data:image/jpeg;base64,aW1n"', out)
        self.assertNotIn("https://img.example/a.jpg", out)

    def test_preview_template_strips_unknown_remote_images(self):
        # Anything left pointing at http would render as a broken icon.
        out = render_run_page.preview_template(
            '<img src="https://unknown.example/z.jpg"/>', {"products": {},
                                                           "hero": {}})
        self.assertNotIn("https://unknown.example/z.jpg", out)


if __name__ == "__main__":
    unittest.main()
