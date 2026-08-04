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


class TestDecode(unittest.TestCase):
    def test_valid_pair(self):
        self.assertEqual(plc.decode(b64("1626718:secrettoken")),
                         ("1626718", "secrettoken"))

    def test_token_containing_colon_splits_once(self):
        self.assertEqual(plc.decode(b64("1626718:abc:def")),
                         ("1626718", "abc:def"))

    def test_surrounding_whitespace_stripped(self):
        self.assertEqual(plc.decode(b64(" 1626718 : secret ")),
                         ("1626718", "secret"))

    def test_base64_without_colon_is_rejected(self):
        self.assertIsNone(plc.decode(b64("noseparator")))

    def test_non_base64_is_rejected(self):
        self.assertIsNone(plc.decode("this-is-a-raw-token"))

    def test_empty_is_rejected(self):
        self.assertIsNone(plc.decode(""))

    def test_non_numeric_account_is_rejected(self):
        self.assertIsNone(plc.decode(b64("notanumber:secret")))

    def test_empty_token_is_rejected(self):
        self.assertIsNone(plc.decode(b64("1626718:")))


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
