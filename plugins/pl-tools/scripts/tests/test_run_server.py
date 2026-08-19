"""Unit tests for run_server. Stdlib unittest — no pytest.

The server is exercised over real HTTP on an ephemeral port: the routing and
the status codes are the contract the page depends on, and a handler called
directly would not prove either.
"""
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer

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
        handler = run_server.make_handler(self.dir, context)
        self.httpd = HTTPServer(("127.0.0.1", 0), handler)
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


if __name__ == "__main__":
    unittest.main()
