import json
import subprocess
import unittest
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parent.parent.parent
          / "skills" / "demo-request" / "scripts" / "check_images.mjs")


def run(payload):
    return subprocess.run(
        ["node", str(SCRIPT)],
        input=json.dumps(payload), capture_output=True, text=True,
    )


class TestCheckImages(unittest.TestCase):
    def test_rejects_empty_product_list(self):
        r = run({"products": []})
        self.assertEqual(r.returncode, 1)
        self.assertIn("at least 1", r.stderr)

    def test_accepts_two_products(self):
        # Missing image_url fails fast with no network access.
        r = run({"products": [{"name": "A"}, {"name": "B"}]})
        out = json.loads(r.stdout)
        self.assertEqual(len(out["results"]), 2)
        self.assertFalse(out["ok"])
        self.assertEqual(r.returncode, 1)

    def test_accepts_eleven_products(self):
        # Missing image_url fails fast with no network access.
        r = run({"products": [{"name": f"P{i}"} for i in range(11)]})
        out = json.loads(r.stdout)
        self.assertEqual(len(out["results"]), 11)
        self.assertFalse(out["ok"])
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
