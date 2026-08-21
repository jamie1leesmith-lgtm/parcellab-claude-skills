"""Unit tests for capture_order_messages. Stdlib unittest -- no pytest."""
import json
import pathlib
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import capture_order_messages as com  # noqa: E402


class TestSignatureFor(unittest.TestCase):
    def test_matches_a_real_captured_signature(self):
        # Proven live 2026-08-21 against a real sent email: this exact
        # recipient/signature pair came off a live parcelLab webview URL.
        self.assertEqual(
            com.signature_for("testmail@parcellab.com"),
            "9853149c47c47f788520113fcad563b236afdb33bc2948b55885f5413114eff8",
        )

    def test_case_and_whitespace_insensitive(self):
        plain = com.signature_for("testmail@parcellab.com")
        self.assertEqual(com.signature_for("TESTMAIL@PARCELLAB.COM"), plain)
        self.assertEqual(com.signature_for("  testmail@parcellab.com  "),
                          plain)

    def test_different_recipients_get_different_signatures(self):
        self.assertNotEqual(
            com.signature_for("a@example.com"),
            com.signature_for("b@example.com"),
        )


class TestExtractOrderNumber(unittest.TestCase):
    def test_finds_a_hash_prefixed_order_number(self):
        html = "<p>Hello Jamie Chen,</p><p>Order number: #1098</p>"
        self.assertEqual(com.extract_order_number(html), "1098")

    def test_finds_a_bare_order_number(self):
        html = "<p>Order number: ADH_0QQED</p>"
        self.assertEqual(com.extract_order_number(html), "ADH_0QQED")

    def test_none_when_the_shape_is_not_present(self):
        self.assertIsNone(com.extract_order_number("<p>no order info here</p>"))


class TestCaptureMessages(unittest.TestCase):
    """Exercises the grouping/orchestration logic with the network and CLI
    calls swapped for fakes -- these tests never touch a real account."""

    def test_groups_by_order_number_found_in_content(self):
        emails = [
            {"id": "e1", "recipient": "testmail@parcellab.com",
             "messageType": "parcel_shipped_all_4c46", "subject": "Shipped",
             "createdAt": "2026-08-20T12:40:00.000Z"},
            {"id": "e2", "recipient": "testmail@parcellab.com",
             "messageType": "delivered_to_recipient_address_dbc2",
             "subject": "Delivered", "createdAt": "2026-08-20T13:00:00.000Z"},
        ]
        contents = {
            "e1": "Order number: #1098",
            "e2": "Order number: #1097",
        }

        def fake_list(account_id, page_size, max_pages):
            return emails

        def fake_fetch(email_id, signature):
            return {"content": contents[email_id], "subject": "x"}

        by_order = com.capture_messages(
            1626102, ["1098", "1097"], since_iso="2026-08-20T00:00:00.000Z",
            list_emails=fake_list, fetch_content=fake_fetch)

        self.assertEqual(len(by_order["1098"]), 1)
        self.assertEqual(by_order["1098"][0]["message_type"],
                          "parcel_shipped_all_4c46")
        self.assertEqual(len(by_order["1097"]), 1)

    def test_ignores_emails_for_orders_outside_this_run(self):
        emails = [{"id": "e1", "recipient": "testmail@parcellab.com",
                   "messageType": "x", "subject": "x",
                   "createdAt": "2026-08-20T12:40:00.000Z"}]

        def fake_list(account_id, page_size, max_pages):
            return emails

        def fake_fetch(email_id, signature):
            return {"content": "Order number: #9999", "subject": "x"}

        by_order = com.capture_messages(
            1626102, ["1098"], since_iso="2026-08-20T00:00:00.000Z",
            list_emails=fake_list, fetch_content=fake_fetch)

        self.assertEqual(by_order, {"1098": []})

    def test_filters_out_emails_created_before_since(self):
        emails = [{"id": "e1", "recipient": "testmail@parcellab.com",
                   "messageType": "x", "subject": "x",
                   "createdAt": "2026-08-01T00:00:00.000Z"}]

        def fake_list(account_id, page_size, max_pages):
            return emails

        def fake_fetch(email_id, signature):
            raise AssertionError("must not fetch an email before --since")

        by_order = com.capture_messages(
            1626102, ["1098"], since_iso="2026-08-20T00:00:00.000Z",
            list_emails=fake_list, fetch_content=fake_fetch)

        self.assertEqual(by_order, {"1098": []})

    def test_a_failed_fetch_is_skipped_not_fatal(self):
        emails = [
            {"id": "e1", "recipient": "testmail@parcellab.com",
             "messageType": "x", "subject": "x",
             "createdAt": "2026-08-20T12:40:00.000Z"},
            {"id": "e2", "recipient": "testmail@parcellab.com",
             "messageType": "y", "subject": "y",
             "createdAt": "2026-08-20T12:41:00.000Z"},
        ]

        def fake_list(account_id, page_size, max_pages):
            return emails

        def fake_fetch(email_id, signature):
            if email_id == "e1":
                raise RuntimeError("simulated 429 exhausted")
            return {"content": "Order number: #1098", "subject": "y"}

        by_order = com.capture_messages(
            1626102, ["1098"], since_iso="2026-08-20T00:00:00.000Z",
            list_emails=fake_list, fetch_content=fake_fetch)

        self.assertEqual(len(by_order["1098"]), 1)
        self.assertEqual(by_order["1098"][0]["message_type"], "y")

    def test_messages_are_sorted_oldest_to_newest(self):
        emails = [
            {"id": "e2", "recipient": "testmail@parcellab.com",
             "messageType": "second", "subject": "x",
             "createdAt": "2026-08-20T13:00:00.000Z"},
            {"id": "e1", "recipient": "testmail@parcellab.com",
             "messageType": "first", "subject": "x",
             "createdAt": "2026-08-20T12:40:00.000Z"},
        ]

        def fake_list(account_id, page_size, max_pages):
            return emails

        def fake_fetch(email_id, signature):
            return {"content": "Order number: #1098", "subject": "x"}

        by_order = com.capture_messages(
            1626102, ["1098"], since_iso="2026-08-20T00:00:00.000Z",
            list_emails=fake_list, fetch_content=fake_fetch)

        self.assertEqual([m["message_type"] for m in by_order["1098"]],
                          ["first", "second"])


class TestMergeIntoLinkedOrders(unittest.TestCase):
    def _write(self, entries):
        d = pathlib.Path(tempfile.mkdtemp())
        path = d / "linked-orders.json"
        path.write_text(json.dumps(entries))
        return path

    def test_writes_messages_onto_matching_orders(self):
        path = self._write([{"order_number": "1098", "name": "Order A"}])
        gaps = com.merge_into_linked_orders(
            path, {"1098": [{"message_type": "shipped", "subject": "x",
                              "rendered_html": "<p>x</p>",
                              "sent_at": "2026-08-20T12:00:00.000Z"}]})

        self.assertEqual(gaps, [])
        written = json.loads(path.read_text())
        self.assertEqual(len(written[0]["messages"]), 1)

    def test_reports_a_gap_for_an_order_with_no_captured_messages(self):
        path = self._write([{"order_number": "1098", "name": "Order A"},
                             {"order_number": "1097", "name": "Order B"}])
        gaps = com.merge_into_linked_orders(
            path, {"1098": [{"message_type": "shipped", "subject": "x",
                              "rendered_html": "<p>x</p>",
                              "sent_at": "2026-08-20T12:00:00.000Z"}],
                   "1097": []})

        self.assertEqual(gaps, ["1097"])

    def test_overwrites_rather_than_appends_on_a_second_call(self):
        path = self._write([{"order_number": "1098", "name": "Order A",
                              "messages": [{"message_type": "stale"}]}])
        com.merge_into_linked_orders(
            path, {"1098": [{"message_type": "fresh", "subject": "x",
                              "rendered_html": "<p>x</p>",
                              "sent_at": "2026-08-20T12:00:00.000Z"}]})

        written = json.loads(path.read_text())
        self.assertEqual([m["message_type"] for m in written[0]["messages"]],
                          ["fresh"])


class TestFetchRenderedContentBackoff(unittest.TestCase):
    def test_retries_on_429_then_succeeds(self):
        calls = []

        class FakeHTTPError(Exception):
            code = 429

        attempts = {"n": 0}

        def fake_urlopen(url, timeout):
            attempts["n"] += 1
            if attempts["n"] < 3:
                import urllib.error
                raise urllib.error.HTTPError(url, 429, "rate limited", {}, None)
            import io
            return io.BytesIO(json.dumps({"content": "ok"}).encode())

        sleeps = []
        original_urlopen = com.urllib.request.urlopen
        com.urllib.request.urlopen = fake_urlopen
        try:
            result = com.fetch_rendered_content(
                "e1", "sig", retries=5, backoff_seconds=0,
                sleep=lambda s: sleeps.append(s))
        finally:
            com.urllib.request.urlopen = original_urlopen

        self.assertEqual(result, {"content": "ok"})
        self.assertEqual(attempts["n"], 3)
        self.assertEqual(len(sleeps), 2)

    def test_gives_up_after_exhausting_retries(self):
        def fake_urlopen(url, timeout):
            import urllib.error
            raise urllib.error.HTTPError(url, 429, "rate limited", {}, None)

        original_urlopen = com.urllib.request.urlopen
        com.urllib.request.urlopen = fake_urlopen
        try:
            with self.assertRaises(RuntimeError):
                com.fetch_rendered_content("e1", "sig", retries=2,
                                            backoff_seconds=0,
                                            sleep=lambda s: None)
        finally:
            com.urllib.request.urlopen = original_urlopen


if __name__ == "__main__":
    unittest.main()
