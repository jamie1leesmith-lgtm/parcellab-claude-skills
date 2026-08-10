import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS / "prepare_fraud_fragment.py"
SOURCE = (SCRIPTS.parent / "skills" / "demo-environment" / "references"
          / "fraud_risk_payloads.json")
NOW = "2026-08-11T12:00:00+00:00"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True,
    )


class TestPrepareFraudFragment(unittest.TestCase):
    def fragment(self, level):
        r = run("--level", level, "--shop-url", "jamie-demo.myshopify.com",
                "--source", str(SOURCE), "--now", NOW)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_tags_match_level(self):
        self.assertEqual(self.fragment("high")["tags"], ["FraudRiskHigh"])
        self.assertEqual(self.fragment("low")["tags"], ["FraudRiskLow"])

    def test_output_shape(self):
        out = self.fragment("medium")
        self.assertEqual(set(out), {"tags", "additional_attributes"})
        ra = out["additional_attributes"]["riskAssessment"]
        self.assertIsInstance(ra, list)
        self.assertGreater(len(ra), 0)

    def test_source_domain_fully_replaced(self):
        blob = json.dumps(self.fragment("high"))
        self.assertNotIn("cdc-demo-store.myshopify.com", blob)
        self.assertIn("jamie-demo.myshopify.com", blob)

    def test_timestamps_freshened(self):
        now = datetime.fromisoformat(NOW)
        for pred in self.fragment("high")["additional_attributes"]["riskAssessment"]:
            for key in ("created_at", "updated_at", "prediction_date"):
                if key in pred and pred[key]:
                    ts = datetime.fromisoformat(pred[key])
                    self.assertLessEqual(now - ts, timedelta(days=7),
                                         f"{key} not freshened: {pred[key]}")
                    self.assertLessEqual(ts, now)

    def test_unknown_level_fails(self):
        r = run("--level", "extreme", "--shop-url", "x.myshopify.com",
                "--source", str(SOURCE))
        self.assertEqual(r.returncode, 1)
        self.assertIn("level", r.stderr.lower())


if __name__ == "__main__":
    unittest.main()
