"""Unit tests for run_server. Stdlib unittest — no pytest.

The server is exercised over real HTTP on an ephemeral port: the routing and
the status codes are the contract the page depends on, and a handler called
directly would not prove either.
"""
import json
import pathlib
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import intake_schema  # noqa: E402
import run_server  # noqa: E402
import run_state  # noqa: E402


class TestRenderPage(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        run_state.init(str(self.dir), "brand-20260819-1546", "retain", "Demo")

    def test_every_placeholder_is_substituted(self):
        html = run_server.render_page(self.dir, {"prospect_name": "Brand"})
        self.assertNotIn("{{", html)
        self.assertIn("#3E39D3", html)
        self.assertIn("Poppins", html)

    def test_context_is_valid_json_in_the_page(self):
        context = {"prospect_name": "Brand", "region": "DE"}
        html = run_server.render_page(self.dir, context)
        blob = html.split("window.__CONTEXT__ = ")[1].split(";</script>")[0]
        self.assertEqual(json.loads(blob)["region"], "DE")

    def test_context_closing_tag_is_escaped(self):
        html = run_server.render_page(
            self.dir, {"prospect_name": "</script><script>alert(1)"})
        self.assertNotIn("</script><script>alert(1)", html)


class TestBuildContext(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())

    def test_context_carries_vocabularies_and_defaults(self):
        context = run_server.build_context(
            self.dir, prospect_name="Brand", region="UK",
            reuse_candidate=None)
        self.assertEqual(context["regions"], list(intake_schema.REGIONS))
        self.assertEqual(context["region_couriers"],
                         intake_schema.REGION_COURIERS)
        self.assertEqual(context["defaults"]["courier"], "royal-mail")
        self.assertIsNone(context["reuse_candidate"])
        self.assertEqual(sorted(context["scenarios"]),
                         sorted(intake_schema.SCENARIOS))


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        (self.dir / "scrape").mkdir()
        (self.dir / "results").mkdir()
        run_state.init(str(self.dir), "brand-20260819-1546", "retain", "Demo")
        context = run_server.build_context(
            self.dir, prospect_name="Brand", region="US",
            reuse_candidate=None)
        # Goes through the same make_server() that serve() uses, so the
        # threading server class the tests exercise is the one that ships.
        self.httpd = run_server.make_server(self.dir, context, port=0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path):
        with urllib.request.urlopen(self.url(path), timeout=5) as response:
            return response.status, response.read()

    def post(self, path, payload):
        request = urllib.request.Request(
            self.url(path), data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def raw_socket(self, timeout=5):
        """A bare socket to the server, for requests urllib cannot produce.

        urllib.request always computes a correct numeric Content-Length, so
        it cannot exercise a malformed or dishonest one — exactly the gap
        that let finding 1 through review undetected.
        """
        sock = socket.create_connection(("127.0.0.1", self.port),
                                        timeout=timeout)
        return sock


class TestRoutes(ServerTestCase):
    def test_root_serves_the_page(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"__CONTEXT__", body)

    def test_state_serves_the_payload(self):
        status, body = self.get("/state")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["phase"], "intake")
        self.assertEqual(payload["run_id"], "brand-20260819-1546")

    def test_state_is_not_cached(self):
        with urllib.request.urlopen(self.url("/state"), timeout=5) as response:
            self.assertIn("no-store", response.headers.get("Cache-Control", ""))

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/nope")
        self.assertEqual(caught.exception.code, 404)

    def test_post_to_unknown_path_is_404(self):
        status, _ = self.post("/nope", {})
        self.assertEqual(status, 404)


class TestSubmit(ServerTestCase):
    def valid_payload(self):
        return intake_schema.default_answers(region="US")

    def test_valid_submission_writes_intake_json(self):
        status, body = self.post("/submit", self.valid_payload())
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        written = json.loads((self.dir / "intake.json").read_text())
        self.assertEqual(written["region"], "US")

    def test_valid_submission_flips_phase_to_building(self):
        self.post("/submit", self.valid_payload())
        _, body = self.get("/state")
        self.assertEqual(json.loads(body)["phase"], "building")

    def test_invalid_submission_is_400_with_the_reason(self):
        payload = self.valid_payload()
        payload["region"] = "ES"
        status, body = self.post("/submit", payload)
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])
        self.assertIn("region", body["error"])

    def test_invalid_submission_writes_nothing(self):
        payload = self.valid_payload()
        payload["orders"] = []
        self.post("/submit", payload)
        self.assertFalse((self.dir / "intake.json").exists())

    def test_malformed_body_is_400_not_a_traceback(self):
        request = urllib.request.Request(
            self.url("/submit"), data=b"{not json",
            headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 400)

    def test_non_numeric_content_length_is_400_not_a_crash(self):
        sock = self.raw_socket()
        sock.sendall(
            b"POST /submit HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: notanumber\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"{}")
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        sock.close()
        status_line = response.split(b"\r\n", 1)[0]
        self.assertIn(b"400", status_line,
                     f"expected a 400 status line, got: {response!r}")

    def test_truncated_body_does_not_wedge_the_server(self):
        # Declare far more bytes than we actually send, and never send them.
        stalled = self.raw_socket(timeout=5)
        stalled.sendall(
            b"POST /submit HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 1000000\r\n"
            b"\r\n")

        # A short client-side timeout: with ThreadingHTTPServer this must
        # return fast. A regression (single-threaded server, no read
        # timeout) would otherwise hang the whole suite instead of failing
        # it, which is exactly why this timeout is short rather than absent.
        status, body = self.get("/state")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["phase"], "intake")

        stalled.close()

    def test_concurrent_submissions_never_produce_a_torn_file(self):
        # Two distinct valid payloads, so whichever one wins is checkable.
        payload_a = intake_schema.default_answers(region="US")
        payload_b = intake_schema.default_answers(region="UK")

        results = {}

        def submit(name, payload):
            results[name] = self.post("/submit", payload)

        t1 = threading.Thread(target=submit, args=("a", payload_a))
        t2 = threading.Thread(target=submit, args=("b", payload_b))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        self.assertTrue(results["a"][0] == 200 and results["b"][0] == 200)

        written = json.loads((self.dir / "intake.json").read_text())
        self.assertIn(written["region"], ("US", "UK"))
        self.assertTrue(written == payload_a or written == payload_b,
                        "intake.json is neither submission whole — torn write")

        # No stray per-request temp files left behind either.
        leftover = list(self.dir.glob("intake.json.*.tmp"))
        self.assertEqual(leftover, [], f"stray temp files: {leftover}")


class TestHandlerErrorGuard(unittest.TestCase):
    """An unexpected exception must come back as an HTTP response.

    Escaping the handler makes socketserver print a traceback and drop the
    connection, so the client sees no status at all — the failure mode that
    killed the page's only data source with nothing diagnosable.
    """

    def setUp(self):
        # Deliberately NO run_state.init(): run-state.json is missing, which
        # is what used to raise FileNotFoundError inside do_GET.
        self.dir = pathlib.Path(tempfile.mkdtemp())
        context = run_server.build_context(
            self.dir, prospect_name="Brand", region="US",
            reuse_candidate=None)
        self.httpd = run_server.make_server(self.dir, context, port=0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def test_state_without_run_state_json_still_answers(self):
        url = f"http://127.0.0.1:{self.port}/state"
        with urllib.request.urlopen(url, timeout=5) as response:
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read())
        self.assertEqual(payload["phase"], "intake")
        self.assertIsNone(payload["run_id"])

    def test_an_unexpected_exception_becomes_a_json_500(self):
        original = run_server.state_payload.build
        run_server.state_payload.build = lambda _dir: (_ for _ in ()).throw(
            RuntimeError("boom"))
        try:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/state", timeout=5)
        finally:
            run_server.state_payload.build = original
        self.assertEqual(caught.exception.code, 500)
        body = json.loads(caught.exception.read())
        self.assertFalse(body["ok"])
        self.assertIn("boom", body["error"])

    def test_an_unexpected_post_exception_becomes_a_json_500(self):
        original = run_server.intake_schema.parse_answers
        run_server.intake_schema.parse_answers = \
            lambda _raw: (_ for _ in ()).throw(RuntimeError("kaboom"))
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/submit", data=b"{}",
                headers={"Content-Type": "application/json"}, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=5)
        finally:
            run_server.intake_schema.parse_answers = original
        self.assertEqual(caught.exception.code, 500)
        self.assertIn("kaboom", json.loads(caught.exception.read())["error"])
        self.assertFalse((self.dir / "intake.json").exists())


class TestIntakeTemplate(unittest.TestCase):
    """The template is HTML, so these check its contract with the server and
    the schema rather than its appearance — a missing hook here is exactly the
    kind of break that renders a silently non-functional form."""

    def setUp(self):
        self.html = run_server.TEMPLATE.read_text()

    def test_no_unsubstituted_placeholder_names_are_invented(self):
        known = {"{{BRAND_PRIMARY}}", "{{BRAND_TEXT}}", "{{BRAND_TINT}}",
                 "{{BRAND_CARD}}", "{{BRAND_FONT}}", "{{BRAND_FONTS_LINK}}",
                 "{{BRAND_LOGO}}", "{{CONTEXT_JSON}}"}
        import re
        found = set(re.findall(r"\{\{[A-Z_]+\}\}", self.html))
        self.assertEqual(found - known, set())

    def test_posts_to_submit(self):
        self.assertIn("/submit", self.html)

    def test_polls_state(self):
        self.assertIn("/state", self.html)

    def test_does_not_hardcode_a_region_list(self):
        for invented in ("correos-es", "dpd-uk", "colissimo-fr", "dhl-de"):
            self.assertNotIn(invented, self.html)

    def test_reads_vocabularies_from_context(self):
        for key in ("regions", "region_couriers", "scenarios", "defaults"):
            self.assertIn(key, self.html)

    def test_has_both_phase_containers(self):
        self.assertIn('id="phase-intake"', self.html)
        self.assertIn('id="phase-building"', self.html)


class TestBuildingTemplate(unittest.TestCase):
    def setUp(self):
        self.html = run_server.TEMPLATE.read_text()

    def test_has_a_panel_per_lane(self):
        for lane in ("scrape", "template", "seed", "orders", "cdc"):
            self.assertIn(f'id="panel-{lane}"', self.html)

    def test_has_a_lane_button_per_lane(self):
        for lane in ("scrape", "template", "seed", "orders", "cdc"):
            self.assertIn(f"toggleLane('{lane}')", self.html)

    def test_renders_seed_exchange_demos(self):
        for demo in ("in_product_even", "cross_product_even",
                     "uneven_upward", "uneven_downward"):
            self.assertIn(demo, self.html)

    def test_surfaces_generate_orders(self):
        self.assertIn("generate_orders", self.html)

    def test_has_no_hardcoded_sample_data_from_the_mockup(self):
        for sample in ("Sarah Mitchell", "James Carter", "Maria Gonzalez",
                       "pl-1041", "pl-1042", "pl-1043"):
            self.assertNotIn(sample, self.html)

    def test_polls_on_an_interval(self):
        self.assertIn("setInterval", self.html)

    def test_preview_link_points_at_the_layout_preview_server(self):
        # branded-template serves $HOME/parcellab-previews/ on 8098; this
        # server serves only /, /state and /submit, so a relative path 404s.
        self.assertIn("http://127.0.0.1:8098/", self.html)

    def test_order_feed_skips_an_unchanged_payload(self):
        self.assertIn("lastOrderFeedJson", self.html)

    def test_no_retired_return_scenario_labels(self):
        for retired in ("manual_return", "return_tracking"):
            self.assertNotIn(retired, self.html)


if __name__ == "__main__":
    unittest.main()
