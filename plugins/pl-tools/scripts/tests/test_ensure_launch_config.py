"""Unit tests for ensure_launch_config. Stdlib unittest — no pytest."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "ensure_launch_config.py"


def run(path, entry):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), json.dumps(entry)],
        capture_output=True, text=True,
    )


class TestEnsureLaunchConfig(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = pathlib.Path(self.dir) / "launch.json"

    def test_creates_file_when_missing(self):
        result = run(self.path, {"name": "layout-preview", "port": 8098})
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(self.path.read_text())
        self.assertEqual(len(config["configurations"]), 1)
        self.assertEqual(config["configurations"][0]["name"], "layout-preview")

    def test_preserves_unrelated_existing_entries(self):
        self.path.write_text(json.dumps({
            "version": "0.0.1",
            "configurations": [{"name": "some-other-dev-server", "port": 5173}],
        }))
        result = run(self.path, {"name": "layout-preview", "port": 8098})
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(self.path.read_text())
        names = {c["name"] for c in config["configurations"]}
        self.assertEqual(names, {"some-other-dev-server", "layout-preview"})

    def test_replaces_own_entry_by_name_instead_of_duplicating(self):
        self.path.write_text(json.dumps({
            "version": "0.0.1",
            "configurations": [{"name": "layout-preview", "port": 8097}],
        }))
        result = run(self.path, {"name": "layout-preview", "port": 8098})
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(self.path.read_text())
        self.assertEqual(len(config["configurations"]), 1)
        self.assertEqual(config["configurations"][0]["port"], 8098)


if __name__ == "__main__":
    unittest.main()
