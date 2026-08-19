"""Unit tests for render_run_page. Stdlib unittest — no pytest."""
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import render_run_page  # noqa: E402
import run_state  # noqa: E402
import pl_brand  # noqa: E402


def at_plan_gate(state):
    """The state a plan-content test means: the ✋ gate is open.

    The plan card is revealed by the plan gate being asked, not by the manifest
    existing — the manifest is written before both gates so the page can render
    what it asks about, and state 2b (the ★ template gate) must not show the
    plan yet. A test about what the plan *contains* therefore has to say which
    gate it is standing at.
    """
    state = dict(state)
    state["timeline"] = list(state.get("timeline", [])) + [
        {"kind": "gate", "name": "plan", "phase": "asked",
         "at": "2026-08-11T18:39:00Z"}]
    return state


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


def a_manifest():
    """A minimal but realistic plan-gate manifest — one order, one shipment.

    Shaped like the payload the intake interview builds, not a synthetic
    dict-of-strings: this is what `_plan_orders`/`_plan_facts` actually receive
    at the plan gate (state 3), the surface a 2026-08-11 live run reported as
    "the renderer had no code to draw" (Currys row, triaged 2026-08-12 — see
    references/comms-diagnosis.md's sibling investigation notes). No test
    exercised `render(..., manifest=...)` before this one.
    """
    return {
        "path": "retain-shopify",
        "destination_country": "GBR",
        "account": {"name": "Currys demo", "id": 1626718},
        "run": {"pace": "standard"},
        "brand": {"name": "Currys", "region": "UK", "category": "electronics"},
        "shopify": {"enabled": True, "store": "currys-demo.myshopify.com"},
        "cdc": {"config_source": "manual", "generate_orders": False},
        "products": [{"id": "p1", "sku": "CUR-1", "name": "Soundbar"}],
        "orders": [
            {"label": "A", "customer": {"name": "Jane Doe"},
             "fraud_level": "low",
             "shipments": [
                 {"label": "A", "products": ["p1"], "scenario": "clean",
                  "events": ["InTransit", "OutForDelivery", "Delivered"]},
             ]},
        ],
    }


class TestRenderRunPage(unittest.TestCase):
    def test_renders_run_id_and_account(self):
        html = render_run_page.render(a_state())
        self.assertIn("uniqlo-20260811-1913", html)
        self.assertIn("Demo - JLS", html)

    def test_no_external_references_anywhere(self):
        # The artifact CSP blocks these; a remote image renders as a broken
        # icon. Google Fonts is the one documented CSP exception, and the
        # brand header deliberately loads Poppins from fonts.googleapis.com —
        # strip that known-safe link before checking for anything else.
        html = render_run_page.render(a_state())
        without_google_fonts = html.replace(pl_brand.GOOGLE_FONTS_LINK, "")
        self.assertNotIn('<img src="http', without_google_fonts)
        self.assertNotIn('<script src="http', without_google_fonts)
        self.assertNotIn('<link rel="stylesheet" href="http', without_google_fonts)

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

    def test_plan_gate_renders_the_order_matrix(self):
        """The plan-gate content a 2026-08-11 run reported as undrawable.

        Every prior test in this file omits `manifest`, so `_plan`/`_plan_orders`
        never ran. Checks the specific columns the row's own description named:
        customer, fraud level, scenario, and the event chain.
        """
        html = render_run_page.render(at_plan_gate(a_state()), manifest=a_manifest())
        self.assertIn("Run plan", html)
        self.assertIn("Jane Doe", html)
        self.assertIn("low", html)
        self.assertIn("clean", html)
        self.assertIn("InTransit → OutForDelivery → Delivered", html)

    def test_plan_gate_renders_the_run_facts(self):
        html = render_run_page.render(at_plan_gate(a_state()), manifest=a_manifest())
        self.assertIn("retain-shopify", html)
        self.assertIn("Currys demo", html)
        self.assertIn("currys-demo.myshopify.com", html)

    def test_no_manifest_omits_the_plan_card_without_crashing(self):
        """Every state before the plan gate calls render() with no manifest —
        this must degrade to nothing, not raise."""
        html = render_run_page.render(a_state())
        self.assertNotIn("Run plan", html)


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
        html = render_run_page.render(at_plan_gate(a_state()), manifest=MANIFEST)
        self.assertIn("Emily Turner", html)
        self.assertIn("happy", html)
        self.assertIn("InTransit", html)
        self.assertIn("low", html)

    def test_selected_products_are_labelled_core_and_extra(self):
        html = render_run_page.render(at_plan_gate(a_state()), manifest=MANIFEST)
        self.assertIn("Jug Kettle", html)
        self.assertIn("core", html)
        self.assertIn("extra", html)

    def test_plan_shows_destination_and_pace(self):
        html = render_run_page.render(at_plan_gate(a_state()), manifest=MANIFEST)
        self.assertIn("GB", html)
        self.assertIn("standard", html)

    def test_standard_pace_is_200_seconds(self):
        # The default gap the driver actually uses. Stated on the page so a
        # reader can predict when the next event lands; kept in a test so the
        # page and run-lifecycle.sh cannot drift apart silently.
        html = render_run_page.render(at_plan_gate(a_state()), manifest=MANIFEST)
        self.assertIn("200s between events", html)

    def test_fast_pace_is_60_seconds(self):
        manifest = dict(MANIFEST, run={"pace": "fast"})
        html = render_run_page.render(at_plan_gate(a_state()), manifest=manifest)
        self.assertIn("60s between events", html)

    def test_products_card_shows_only_the_selected_set(self):
        # The scrape pool holds every candidate; the plan is the chosen subset.
        assets = dict(ASSETS, products=dict(
            ASSETS["products"],
            **{"REJECTED-1": {"name": "Not Chosen", "price": "1.00",
                              "product_type": "Other", "pdp_url": "",
                              "image_url": "", "data_uri": None}}))
        html = render_run_page.render(at_plan_gate(a_state()),
                                      manifest=MANIFEST, assets=assets)
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


class TestGatesCanRenderWhatTheyAsk(unittest.TestCase):
    """The page must show the thing it is asking the user to approve.

    Both approval gates render from data written *after* them: the ★ template
    gate is Phase 0 step 7 and the ✋ plan gate is step 8, while the manifest —
    which `main()` needs to find the template HTML, and which `_plan` renders
    from — is written at step 9. So the page was blank at exactly the two
    moments a decision was asked for (thenorthface 2026-08-12: the user
    approved a template against a page showing nothing).

    The fix writes the manifest before the gates, which makes the reveal
    ordering load-bearing: state 2b says the template gate shows the preview
    and swatches ONLY. That is now derived from the timeline — the plan appears
    once the plan gate has actually been asked.
    """

    def _run_dir(self, brand="The North Face"):
        d = tempfile.mkdtemp()
        run_state.init(d, "thenorthface-20260812-2243", "retain-shopify",
                       "Demo - JLS")
        manifest = dict(MANIFEST, brand=dict(MANIFEST["brand"], name=brand))
        (pathlib.Path(d) / "demo-manifest.json").write_text(
            json.dumps(manifest))
        return d

    def _render_main(self, run_dir):
        argv = sys.argv
        sys.argv = ["render_run_page.py", str(run_dir)]
        try:
            render_run_page.main()
        finally:
            sys.argv = argv
        return (pathlib.Path(run_dir) / "run-page.html").read_text()

    def test_plan_is_hidden_until_the_plan_gate_is_asked(self):
        # State 2b: the template gate shows the preview and swatches only.
        # Deliberately NOT at_plan_gate() — the manifest exists by now, and the
        # manifest alone must not reveal the plan.
        html = render_run_page.render(a_state(), manifest=MANIFEST)
        self.assertNotIn("Run plan", html)

    def test_plan_appears_once_the_plan_gate_is_asked(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", "retain-shopify", "Demo - JLS")
        run_state.mark(d, "gate", "plan", "asked")
        html = render_run_page.render(run_state.load(d), manifest=MANIFEST)
        self.assertIn("Run plan", html)
        self.assertIn("Emily Turner", html)

    def test_plan_stays_visible_after_the_gate_is_answered(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", "retain-shopify", "Demo - JLS")
        run_state.mark(d, "gate", "plan", "asked")
        run_state.mark(d, "gate", "plan", "answered")
        html = render_run_page.render(run_state.load(d), manifest=MANIFEST)
        self.assertIn("Run plan", html)

    def test_template_renders_from_the_run_id_when_no_brand_is_known(self):
        # The template gate can precede a manifest brand; the run id's handle
        # is the same string branded-template names the file with.
        d = tempfile.mkdtemp()
        run_state.init(d, "thenorthface-20260812-2243", "retain-shopify",
                       "Demo - JLS")
        self.assertEqual(
            render_run_page.template_basenames(run_state.load(d), None),
            ["thenorthface"])

    def test_template_prefers_the_manifest_brand_when_present(self):
        d = self._run_dir(brand="Pets at Home")
        state = run_state.load(d)
        manifest = json.loads(
            (pathlib.Path(d) / "demo-manifest.json").read_text())
        names = render_run_page.template_basenames(state, manifest)
        self.assertIn("petsathome", names)

    def test_main_finds_the_template_without_a_manifest(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "zzbrandtest-20260812-0001", "engage", "Demo - JLS")
        previews = pathlib.Path.home() / "parcellab-previews"
        previews.mkdir(parents=True, exist_ok=True)
        stub = previews / "zzbrandtest-parcellab-layout.html"
        stub.write_text("<html><body>STUBTEMPLATE</body></html>")
        try:
            html = self._render_main(d)
        finally:
            stub.unlink()
        self.assertIn("<iframe", html)
        self.assertIn("Email template", html)


class TestMissingAssetsIsLoud(unittest.TestCase):
    """A scrape that succeeded but was never inlined renders an empty page.

    `inline_assets.py` is one bullet inside Phase 0 step 6; skipping it leaves
    `scrape/assets.json` absent, and both `_brand_header` and `_products` open
    with `if not assets: return ""`. The render still "succeeds", so the
    conductor republishes a blank page and only the user notices
    (thenorthface 2026-08-12).
    """

    def _run_dir_with_scrape_ok(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", "engage", "Demo - JLS")
        results = pathlib.Path(d) / "results"
        results.mkdir(parents=True, exist_ok=True)
        (results / "scrape.json").write_text(
            json.dumps({"status": "ok", "error": None}))
        return d

    def test_render_warns_when_scrape_is_ok_but_assets_are_missing(self):
        d = self._run_dir_with_scrape_ok()
        argv, stderr = sys.argv, sys.stderr
        sys.argv = ["render_run_page.py", str(d)]
        sys.stderr = io.StringIO()
        try:
            render_run_page.main()
            captured = sys.stderr.getvalue()
        finally:
            sys.argv, sys.stderr = argv, stderr
        self.assertIn("assets.json", captured)
        self.assertIn("inline_assets.py", captured)

    def test_no_warning_once_assets_exist(self):
        d = self._run_dir_with_scrape_ok()
        scrape = pathlib.Path(d) / "scrape"
        scrape.mkdir(parents=True, exist_ok=True)
        (scrape / "assets.json").write_text(json.dumps(ASSETS))
        argv, stderr = sys.argv, sys.stderr
        sys.argv = ["render_run_page.py", str(d)]
        sys.stderr = io.StringIO()
        try:
            render_run_page.main()
            captured = sys.stderr.getvalue()
        finally:
            sys.argv, sys.stderr = argv, stderr
        self.assertEqual(captured, "")

    def test_no_warning_before_the_scrape_has_finished(self):
        # States 1 and 2 legitimately have no assets yet.
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", "engage", "Demo - JLS")
        argv, stderr = sys.argv, sys.stderr
        sys.argv = ["render_run_page.py", str(d)]
        sys.stderr = io.StringIO()
        try:
            render_run_page.main()
            captured = sys.stderr.getvalue()
        finally:
            sys.argv, sys.stderr = argv, stderr
        self.assertEqual(captured, "")


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



class TestRenderRecordsItself(unittest.TestCase):
    def _run_dir(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "uniqlo-20260811-1913", "engage", "Demo - JLS")
        return d

    def test_main_records_the_render_in_run_state(self):
        run_dir = self._run_dir()
        argv = sys.argv
        sys.argv = ["render_run_page.py", str(run_dir)]
        try:
            self.assertEqual(render_run_page.main(), 0)
        finally:
            sys.argv = argv
        state = run_state.load(run_dir)
        self.assertEqual(len(state["page"]["renders"]), 1)
        self.assertTrue((pathlib.Path(run_dir) / "run-page.html").exists())

    def test_each_render_appends_another_stamp(self):
        run_dir = self._run_dir()
        argv = sys.argv
        sys.argv = ["render_run_page.py", str(run_dir)]
        try:
            render_run_page.main()
            render_run_page.main()
        finally:
            sys.argv = argv
        self.assertEqual(len(run_state.load(run_dir)["page"]["renders"]), 2)


class TestAutoModeBanner(unittest.TestCase):
    def test_auto_mode_shows_the_banner(self):
        manifest = a_manifest()
        manifest["run"]["mode"] = "auto"
        html = render_run_page.render(a_state(), manifest=manifest)
        self.assertIn('<div class="auto-banner">', html)
        self.assertIn("AUTO MODE", html)

    def test_babysit_mode_has_no_banner(self):
        manifest = a_manifest()
        manifest["run"]["mode"] = "babysit"
        html = render_run_page.render(a_state(), manifest=manifest)
        self.assertNotIn('<div class="auto-banner">', html)
        self.assertNotIn("AUTO MODE", html)

    def test_absent_mode_has_no_banner(self):
        # Absent means babysit, matching run.pace's own convention.
        manifest = a_manifest()
        html = render_run_page.render(a_state(), manifest=manifest)
        self.assertNotIn('<div class="auto-banner">', html)

    def test_no_manifest_has_no_banner(self):
        # The template gate (state 2b) renders before a manifest exists.
        html = render_run_page.render(a_state())
        self.assertNotIn('<div class="auto-banner">', html)


class BrandingTests(unittest.TestCase):
    def test_page_uses_the_brand_primary_color(self):
        html = render_run_page.render(a_state())
        self.assertIn(pl_brand.PRIMARY, html)

    def test_page_loads_poppins(self):
        html = render_run_page.render(a_state())
        self.assertIn("Poppins", html)
        self.assertIn("fonts.googleapis.com", html)

    def test_page_shows_the_parcellab_logo(self):
        html = render_run_page.render(a_state())
        self.assertIn(pl_brand.LOGO_SVG.strip()[:40], html)

    def test_auto_banner_keeps_its_orange_on_purpose(self):
        state = a_state()
        manifest = {"run": {"mode": "auto"}}
        html = render_run_page.render(state, manifest)
        self.assertIn("#ff6b35", html)
        self.assertIn(pl_brand.PRIMARY, html)  # brand color is used elsewhere on the page
        banner_start = html.index('class="auto-banner"')
        banner_end = html.index("</div>", banner_start)
        banner_markup = html[banner_start:banner_end]
        self.assertNotIn(pl_brand.PRIMARY, banner_markup)


if __name__ == "__main__":
    unittest.main()
