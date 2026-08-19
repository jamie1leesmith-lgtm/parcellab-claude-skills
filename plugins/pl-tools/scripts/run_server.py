#!/usr/bin/env python3
"""Serve one demo-environment run: the intake form, then live progress.

Replaces both the intake questionnaire Artifact and the separate run-page
Artifact. Artifacts cannot work here at all — the Browser pane runs a fresh
context with no claude.ai session, so a published page shows a sign-in screen
and the documented publish/poll/extract handoff never completes.

The handoff is a file, not a flag in memory: a valid POST /submit writes
`<run dir>/intake.json`, and the conductor waits for that file to appear. A
server restart therefore loses nothing, and the conductor needs no HTTP
client.
"""
import argparse
import json
import os
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import intake_schema
import pl_brand
import state_payload

DEFAULT_PORT = 8097          # 8098 belongs to branded-template's layout-preview
TEMPLATE = pathlib.Path(__file__).resolve().parent / "run_app_template.html"
MAX_BODY_BYTES = 1 << 20     # an intake payload is a few KB; refuse anything wild
REQUEST_TIMEOUT = 30         # seconds a connection may sit idle before we drop it


def _context_json(context):
    """JSON safe to inline in a <script> block.

    A prospect name containing `</script>` would otherwise close the block
    early and inject whatever follows it into the page.
    """
    return json.dumps(context).replace("</", "<\\/")


def render_page(run_dir, context):
    """The page, with brand tokens and this run's context substituted in.

    Plain str.replace rather than str.format or a template engine: the file
    is full of CSS and JS braces, so any brace-based formatter would have to
    escape all of them.
    """
    html = TEMPLATE.read_text()
    for marker, value in (
        ("{{BRAND_PRIMARY}}", pl_brand.PRIMARY),
        ("{{BRAND_TEXT}}", pl_brand.TEXT),
        ("{{BRAND_TINT}}", pl_brand.TINT),
        ("{{BRAND_CARD}}", pl_brand.CARD),
        ("{{BRAND_FONT}}", pl_brand.FONT_FAMILY),
        ("{{BRAND_FONTS_LINK}}", pl_brand.GOOGLE_FONTS_LINK),
        ("{{BRAND_LOGO}}", pl_brand.LOGO_SVG),
        ("{{CONTEXT_JSON}}", _context_json(context)),
    ):
        html = html.replace(marker, value)
    return html


def build_context(run_dir, prospect_name, region, reuse_candidate):
    """Everything the form needs to render itself, baked into the page.

    Kept as one blob rather than a second endpoint: the page needs all of it
    before first paint, so fetching it separately would only add a round trip
    and a loading state.
    """
    return {
        "prospect_name": prospect_name,
        "run_id": pathlib.Path(run_dir).name,
        "reuse_candidate": reuse_candidate,
        "regions": list(intake_schema.REGIONS),
        "region_couriers": dict(intake_schema.REGION_COURIERS),
        # Not sorted() — fraud severity has a real low-to-high order that
        # alphabetising destroys (it reads "high, low, medium"). scenarios,
        # modes and weight_units below have no equivalent severity/ranking
        # to preserve, so they stay alphabetical.
        "fraud_levels": list(intake_schema.FRAUD_LEVELS_ORDERED),
        "scenarios": sorted(intake_schema.SCENARIOS),
        "modes": sorted(intake_schema.MODES),
        "weight_units": sorted(intake_schema.WEIGHT_UNITS),
        "max_orders": intake_schema.MAX_ORDERS,
        "defaults": intake_schema.default_answers(region=region),
    }


def make_handler(run_dir, context):
    run_dir = pathlib.Path(run_dir)

    class Handler(BaseHTTPRequestHandler):
        # A read timeout so a connection that stops sending mid-body cannot
        # hold its thread open forever. ThreadingHTTPServer means a stalled
        # connection no longer blocks other requests either, but a thread
        # leaking on every stalled client would still add up over a run.
        timeout = REQUEST_TIMEOUT

        # Quiet by default: this runs in the background for the whole run and
        # a line per poll would bury anything that matters.
        def log_message(self, *args):
            pass

        def _send(self, status, body, content_type):
            payload = body.encode() if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, status, payload):
            self._send(status, json.dumps(payload), "application/json")

        def _guard(self, handle):
            """Turn any unexpected exception into a JSON 500.

            Without this, an exception escaping do_GET/do_POST reaches
            socketserver, which prints a traceback and drops the connection
            with no response at all — the page's only data source dies and
            the client cannot tell a crash from a network blip. Every
            deliberate status (the 400s, the 404s, the TimeoutError close)
            is raised and answered inside `handle`, so it never reaches here.
            """
            try:
                handle()
            except Exception as exc:                  # noqa: BLE001
                try:
                    self._send_json(500, {"ok": False, "error": str(exc)})
                except OSError:
                    # The client is already gone; nothing left to report to.
                    self.close_connection = True

        def do_GET(self):
            self._guard(self._get)

        def do_POST(self):
            self._guard(self._post)

        def _get(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, render_page(run_dir, context),
                           "text/html; charset=utf-8")
            elif path == "/state":
                self._send_json(200, state_payload.build(run_dir))
            else:
                self._send_json(404, {"ok": False, "error": "not found"})

        def _post(self):
            if self.path.split("?", 1)[0] != "/submit":
                self._send_json(404, {"ok": False, "error": "not found"})
                return

            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                self._send_json(400, {"ok": False,
                                      "error": "invalid Content-Length"})
                return
            if length > MAX_BODY_BYTES:
                self._send_json(400, {"ok": False,
                                      "error": "payload too large"})
                return
            try:
                raw = self.rfile.read(length).decode("utf-8", "replace")
            except TimeoutError:
                # The client declared more bytes than it ever sent. Close
                # rather than hang this thread on a body that will never
                # arrive; ThreadingHTTPServer means other requests are
                # unaffected either way, but this thread should not leak.
                self.close_connection = True
                return

            try:
                answers = intake_schema.parse_answers(raw)
            except ValueError as exc:
                # 400 with the reason, so the page shows it inline and the
                # operator fixes it on the same form.
                self._send_json(400, {"ok": False, "error": str(exc)})
                return

            # Written last and only on success: the file's existence is what
            # tells the conductor intake is done, so it must never appear for
            # a payload that failed validation. Written via a temp file plus
            # atomic replace (matching run_state._write) so a poller can
            # never observe a half-written file. The temp name is unique per
            # request (pid + thread id), not a fixed ".json.tmp": the server
            # is threaded, so two concurrent submissions writing the same
            # fixed temp path could interleave and publish a torn document —
            # the rename is atomic, but only over whichever bytes happen to
            # be in the file at replace() time.
            target = run_dir / "intake.json"
            tmp = target.with_name(
                f"intake.json.{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                tmp.write_text(json.dumps(answers, indent=2))
                tmp.replace(target)
            except OSError:
                # Clean up the partial temp file, then let it propagate: the
                # _guard wrapper turns it into a JSON 500 the page can show,
                # so a full disk or a read-only run dir is reported rather
                # than dropping the connection.
                tmp.unlink(missing_ok=True)
                raise
            self._send_json(200, {"ok": True})

    return Handler


def make_server(run_dir, context, port=0):
    """The single place that decides the server class.

    Both `serve()` and the tests must go through this: constructing
    `HTTPServer` directly in one place and something else in the other would
    leave the threading behaviour untested.
    """
    handler = make_handler(run_dir, context)
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(run_dir, context, port=DEFAULT_PORT):
    httpd = make_server(run_dir, context, port)
    print(f"serving {run_dir} on http://127.0.0.1:{port}", flush=True)
    httpd.serve_forever()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--prospect-name", required=True)
    ap.add_argument("--region", default="US", choices=list(intake_schema.REGIONS))
    ap.add_argument("--reuse-candidate", default=None,
                    help="date of a reusable prior scrape, if one was found")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)

    run_dir = pathlib.Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"run_server: no such run dir {run_dir}", file=sys.stderr)
        return 1

    context = build_context(run_dir, args.prospect_name, args.region,
                            args.reuse_candidate)
    try:
        serve(run_dir, context, args.port)
    except OSError as exc:
        # The conductor's documented response is the chat fallback, so say
        # plainly which port is taken rather than dumping a traceback.
        print(f"run_server: cannot bind port {args.port}: {exc}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
