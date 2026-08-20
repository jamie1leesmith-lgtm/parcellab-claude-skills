"""Unit tests for approval_schema. Stdlib unittest — no pytest."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import approval_schema  # noqa: E402


class TestParseDecision(unittest.TestCase):
    def test_approved_needs_no_note(self):
        out = approval_schema.parse_decision(json.dumps(
            {"decision": "approved"}))
        self.assertEqual(out["decision"], "approved")
        self.assertIsNone(out["note"])
        self.assertTrue(out["at"].endswith("Z"))

    def test_approved_keeps_an_optional_note(self):
        out = approval_schema.parse_decision(json.dumps(
            {"decision": "approved", "note": "looks good"}))
        self.assertEqual(out["note"], "looks good")

    def test_changes_requested_keeps_its_note(self):
        out = approval_schema.parse_decision(json.dumps(
            {"decision": "changes_requested",
             "note": "footer address should be the UK entity"}))
        self.assertEqual(out["decision"], "changes_requested")
        self.assertEqual(out["note"],
                         "footer address should be the UK entity")

    def test_changes_requested_without_a_note_is_rejected(self):
        """A rejection with no reason forces the chat round-trip this
        feature exists to avoid."""
        with self.assertRaises(ValueError) as caught:
            approval_schema.parse_decision(json.dumps(
                {"decision": "changes_requested"}))
        self.assertIn("note", str(caught.exception))

    def test_changes_requested_with_a_blank_note_is_rejected(self):
        for blank in ("", "   ", "\n\t "):
            with self.assertRaises(ValueError):
                approval_schema.parse_decision(json.dumps(
                    {"decision": "changes_requested", "note": blank}))

    def test_note_is_stripped(self):
        out = approval_schema.parse_decision(json.dumps(
            {"decision": "changes_requested", "note": "  fix the footer  "}))
        self.assertEqual(out["note"], "fix the footer")

    def test_note_over_the_limit_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            approval_schema.parse_decision(json.dumps(
                {"decision": "changes_requested",
                 "note": "x" * (approval_schema.MAX_NOTE + 1)}))
        self.assertIn("2000", str(caught.exception))

    def test_note_at_exactly_the_limit_is_allowed(self):
        out = approval_schema.parse_decision(json.dumps(
            {"decision": "changes_requested",
             "note": "x" * approval_schema.MAX_NOTE}))
        self.assertEqual(len(out["note"]), approval_schema.MAX_NOTE)

    def test_unknown_decision_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            approval_schema.parse_decision(json.dumps({"decision": "maybe"}))
        self.assertIn("approved", str(caught.exception))

    def test_missing_decision_is_rejected(self):
        with self.assertRaises(ValueError):
            approval_schema.parse_decision(json.dumps({"note": "hi"}))

    def test_unknown_top_level_key_is_rejected(self):
        """Stricter than intake_schema on purpose: a typo'd field on a
        two-key schema should fail loudly, not be silently ignored."""
        with self.assertRaises(ValueError) as caught:
            approval_schema.parse_decision(json.dumps(
                {"decision": "approved", "notes": "typo"}))
        self.assertIn("notes", str(caught.exception))

    def test_non_string_note_is_rejected(self):
        with self.assertRaises(ValueError):
            approval_schema.parse_decision(json.dumps(
                {"decision": "approved", "note": 7}))

    def test_non_object_body_is_rejected(self):
        with self.assertRaises(ValueError):
            approval_schema.parse_decision(json.dumps([1, 2]))

    def test_invalid_json_is_rejected(self):
        with self.assertRaises(ValueError):
            approval_schema.parse_decision("{not json")


if __name__ == "__main__":
    unittest.main()
