"""Unit tests for pl_credentials pure functions. Stdlib unittest — no pytest."""
import base64
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pl_credentials as plc


def b64(raw):
    return base64.b64encode(raw.encode()).decode()


class TestMergeEnv(unittest.TestCase):
    def test_unrelated_env_keys_preserved(self):
        before = {"env": {"ONYX_API_TOKEN": "keep-me"}}
        after = plc.merge_env(before, {"PARCELLAB_ACCOUNT_ID": "1"})
        self.assertEqual(after["env"]["ONYX_API_TOKEN"], "keep-me")
        self.assertEqual(after["env"]["PARCELLAB_ACCOUNT_ID"], "1")

    def test_non_env_settings_preserved(self):
        before = {"theme": "auto", "enabledPlugins": {"onyx@x": True}}
        after = plc.merge_env(before, {"PARCELLAB_ACCOUNT_ID": "1"})
        self.assertEqual(after["theme"], "auto")
        self.assertEqual(after["enabledPlugins"], {"onyx@x": True})

    def test_missing_env_block_created(self):
        after = plc.merge_env({}, {"PARCELLAB_ACCOUNT_ID": "1"})
        self.assertEqual(after["env"], {"PARCELLAB_ACCOUNT_ID": "1"})

    def test_does_not_mutate_input(self):
        before = {"env": {"A": "1"}}
        plc.merge_env(before, {"B": "2"})
        self.assertEqual(before, {"env": {"A": "1"}})

    def test_idempotent(self):
        once = plc.merge_env({}, {"PARCELLAB_ACCOUNT_ID": "1"})
        twice = plc.merge_env(once, {"PARCELLAB_ACCOUNT_ID": "1"})
        self.assertEqual(once, twice)


class TestExistingAccount(unittest.TestCase):
    def test_prefers_canonical_key(self):
        self.assertEqual(plc.existing_account(
            {"PARCELLAB_ACCOUNT_ID": "1", "PARCELLAB_USER_ID": "2"}), "1")

    def test_falls_back_to_legacy_alias(self):
        self.assertEqual(plc.existing_account({"PARCELLAB_USER_ID": "2"}), "2")

    def test_none_when_neither_present(self):
        self.assertIsNone(plc.existing_account({}))


class TestRunCdcToken(unittest.TestCase):
    def test_writes_token_and_default_base_url(self):
        updated, message = plc.run_cdc_token({}, prompt=lambda _: "secrettoken")
        self.assertEqual(updated["env"]["CDC_DEMO_API_TOKEN"], "secrettoken")
        self.assertEqual(updated["env"]["CDC_DEMO_API_BASE_URL"], plc.CDC_DEFAULT_BASE_URL)

    def test_unrelated_env_keys_preserved(self):
        before = {"env": {"PARCELLAB_ACCOUNT_ID": "1626718"}}
        updated, _ = plc.run_cdc_token(before, prompt=lambda _: "secrettoken")
        self.assertEqual(updated["env"]["PARCELLAB_ACCOUNT_ID"], "1626718")

    def test_empty_input_raises_without_changes(self):
        with self.assertRaises(ValueError):
            plc.run_cdc_token({}, prompt=lambda _: "")

    def test_whitespace_only_input_raises(self):
        with self.assertRaises(ValueError):
            plc.run_cdc_token({}, prompt=lambda _: "   ")

    def test_surrounding_whitespace_stripped(self):
        updated, _ = plc.run_cdc_token({}, prompt=lambda _: "  secrettoken  ")
        self.assertEqual(updated["env"]["CDC_DEMO_API_TOKEN"], "secrettoken")

    def test_idempotent(self):
        once, _ = plc.run_cdc_token({}, prompt=lambda _: "secrettoken")
        twice, _ = plc.run_cdc_token(once, prompt=lambda _: "secrettoken")
        self.assertEqual(once, twice)

    def test_message_never_contains_the_raw_token(self):
        _, message = plc.run_cdc_token({}, prompt=lambda _: "supersecretvalue")
        self.assertNotIn("supersecretvalue", message)


class TestReadWriteSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_absent_file_returns_empty_dict(self):
        self.assertEqual(plc.read_settings(self.path), {})

    def test_empty_file_returns_empty_dict(self):
        self.path.write_text("")
        self.assertEqual(plc.read_settings(self.path), {})

    def test_invalid_json_raises_and_leaves_file_untouched(self):
        self.path.write_text("{not json")
        with self.assertRaises(ValueError):
            plc.read_settings(self.path)
        self.assertEqual(self.path.read_text(), "{not json")

    def test_write_creates_parent_directory(self):
        nested = pathlib.Path(self.tmp.name) / "a" / "b" / "settings.json"
        plc.write_settings(nested, {"env": {}})
        self.assertTrue(nested.exists())

    def test_write_output_is_valid_json_with_trailing_newline(self):
        plc.write_settings(self.path, {"env": {"X": "1"}})
        text = self.path.read_text()
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(json.loads(text), {"env": {"X": "1"}})

    def test_round_trip(self):
        plc.write_settings(self.path, {"env": {"X": "1"}, "theme": "auto"})
        self.assertEqual(plc.read_settings(self.path),
                         {"env": {"X": "1"}, "theme": "auto"})


if __name__ == "__main__":
    unittest.main()
