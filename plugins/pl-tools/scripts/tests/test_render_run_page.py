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

    def test_declares_utf8_charset(self):
        # Without this the em dashes and middle dots in the page render as
        # mojibake ("â€"", "Â·") when served without a charset header.
        self.assertIn('<meta charset="utf-8">',
                      render_run_page.render(a_state()))


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
    def test_light_swatches_get_dark_text(self):
        # A white swatch with white text is invisible — two were, live.
        assets = dict(ASSETS, tokens={"BODY_BG": "#FFFFFF"})
        html = render_run_page.render(a_state(), assets=assets)
        swatch = html[html.index("BODY_BG") - 200:html.index("BODY_BG")]
        self.assertIn("#111", swatch)

    def test_dark_swatches_get_light_text(self):
        assets = dict(ASSETS, tokens={"CTA_BG": "#000000"})
        html = render_run_page.render(a_state(), assets=assets)
        swatch = html[html.index("CTA_BG") - 200:html.index("CTA_BG")]
        self.assertIn("#fff", swatch)

    def test_swatch_shows_its_hex_value(self):
        html = render_run_page.render(a_state(), assets=ASSETS)
        self.assertIn("#000000", html)

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


IMAGE_LOGO_ASSETS = dict(
    ASSETS, logo_svg=None, logo_url="https://cdn.example/logo.svg",
    logo_data_uri="data:image/svg+xml;base64,bG9nbw==")

MANIFEST = {
    "path": "retain-shopify",
    "brand": {"name": "Currys", "region": "UK", "category": "Electronics"},
    "destination_country": "GB",
    "run": {"pace": "standard"},
    "shopify": {"enabled": True, "store": "demo.myshopify.com"},
    "cdc": {"config_source": "none", "generate_orders": False},
    "products": [
        {"id": "P1", "name": "Jug Kettle", "product_type": "Kettle",
         "price": "99.99", "options": [{"name": "Colour",
                                        "values": ["Black", "White"]}]},
        {"id": "P2", "name": "Sports Earbuds", "product_type": "Earbuds",
         "price": "19.99", "options": []},
    ],
    "selection": {"core4": ["P1"], "shopify_extra": ["P2"]},
    "orders": [
        {"label": "01-clean-low", "fraud_level": "low", "cdc_slot": "fraud_low",
         "customer": {"name": "Emily Turner", "email": "e@example.com"},
         "products": ["P1"],
         "shipments": [{"label": "A", "scenario": "happy", "courier": "dpd",
                        "products": ["P1"],
                        "events": ["InTransit", "Delivered"]}]},
    ],
}


class TestImageLogo(unittest.TestCase):
    def test_brand_header_renders_an_image_logo(self):
        html = render_run_page.render(a_state(), assets=IMAGE_LOGO_ASSETS)
        self.assertIn('src="data:image/svg+xml;base64,bG9nbw=="', html)

    def test_preview_template_keeps_the_brand_logo(self):
        # The logo is not a product, so the products map cannot supply it;
        # unmapped it gets stripped and the email preview shows no brand.
        out = render_run_page.preview_template(
            '<img src="https://cdn.example/logo.svg" width="158"/>',
            IMAGE_LOGO_ASSETS)
        self.assertIn('src="data:image/svg+xml;base64,bG9nbw=="', out)
        self.assertNotIn("data-stripped", out)


class TestPlan(unittest.TestCase):
    def test_orders_render_with_customer_scenario_and_events(self):
        html = render_run_page.render(a_state(), manifest=MANIFEST)
        self.assertIn("Emily Turner", html)
        self.assertIn("happy", html)
        self.assertIn("InTransit", html)
        self.assertIn("low", html)

    def test_selected_products_are_labelled_core_and_extra(self):
        html = render_run_page.render(a_state(), manifest=MANIFEST)
        self.assertIn("Jug Kettle", html)
        self.assertIn("core", html)
        self.assertIn("extra", html)

    def test_plan_shows_destination_and_pace(self):
        html = render_run_page.render(a_state(), manifest=MANIFEST)
        self.assertIn("GB", html)
        self.assertIn("standard", html)

    def test_products_card_shows_only_the_selected_set(self):
        # The scrape pool holds every candidate; the plan is the chosen subset.
        assets = dict(ASSETS, products=dict(
            ASSETS["products"],
            **{"REJECTED-1": {"name": "Not Chosen", "price": "1.00",
                              "product_type": "Other", "pdp_url": "",
                              "image_url": "", "data_uri": None}}))
        html = render_run_page.render(a_state(), manifest=MANIFEST,
                                      assets=assets)
        self.assertNotIn("Not Chosen", html)

    def test_unknown_account_renders_a_dash_not_the_word_none(self):
        # init() stores None until the account is resolved; .get(k, "—") does
        # not fire on a present-but-None value, so the page titled itself
        # "None" (live 2026-08-11).
        state = a_state()
        state["account_name"] = None
        state["path"] = None
        html = render_run_page.render(state)
        self.assertNotIn(">None ", html)
        self.assertIn("—", html)

    def test_no_manifest_still_renders(self):
        html = render_run_page.render(a_state(), assets=ASSETS)
        self.assertIn("uniqlo-20260811-1913", html)


class TestClock(unittest.TestCase):
    def test_running_run_embeds_the_schedule_and_clock(self):
        html = render_run_page.render(a_state())
        self.assertIn("RUN_SCHEDULE", html)
        self.assertIn("gap_seconds", html)

    def test_age_ticker_runs_even_before_any_schedule_exists(self):
        # The page is a snapshot republished by the conductor, so the reader's
        # real question is "how old is this?" — which must be answerable from
        # the moment the run starts, not only once drivers are launched.
        state = a_state()
        state["schedule"] = {}
        html = render_run_page.render(state)
        self.assertIn("setInterval", html)
        self.assertIn("RUN_UPDATED_AT", html)
        self.assertIn("freshness", html)

    def test_finished_run_has_no_clock(self):
        html = render_run_page.render(a_state(finished=True))
        self.assertNotIn("setInterval", html)

    def test_clock_only_ever_promotes_to_expected(self):
        # Contract guard: the script must not be able to write s-confirmed.
        html = render_run_page.render(a_state())
        script = html[html.index("<script>"):]
        self.assertIn("s-expected", script)
        self.assertNotIn("s-confirmed", script)


if __name__ == "__main__":
    unittest.main()
