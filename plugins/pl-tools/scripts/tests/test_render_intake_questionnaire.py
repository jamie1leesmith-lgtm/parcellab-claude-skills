"""Stdlib unittest — no pytest."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pl_brand
import render_intake_questionnaire as riq


class RenderTests(unittest.TestCase):
    def test_includes_shopify_question(self):
        html = riq.render("Acme")
        self.assertIn('name="shopify_opp"', html)
        self.assertIn('value="yes"', html)
        self.assertIn('value="no"', html)

    def test_omits_reuse_question_without_a_candidate(self):
        html = riq.render("Acme")
        self.assertNotIn("<legend>Reuse the pool", html)

    def test_includes_reuse_question_with_a_candidate(self):
        html = riq.render("Acme", reuse_candidate="2026-08-10")
        self.assertIn('name="reuse_pool"', html)
        self.assertIn("2026-08-10", html)

    def test_includes_every_default_matrix_row(self):
        html = riq.render("Acme")
        for row in riq.DEFAULT_MATRIX:
            self.assertIn(row["label"], html)

    def test_includes_gate_c_toggle(self):
        html = riq.render("Acme")
        self.assertIn('name="gate_c"', html)
        self.assertIn('value="send-as-is"', html)
        self.assertIn('value="extras"', html)

    def test_includes_mode_selector(self):
        html = riq.render("Acme")
        self.assertIn('name="mode"', html)
        self.assertIn('value="babysit"', html)
        self.assertIn('value="auto"', html)

    def test_escapes_the_prospect_name(self):
        html = riq.render('<script>alert(1)</script>')
        self.assertNotIn('<script>alert(1)</script>', html)

    def test_includes_brand_tokens(self):
        html = riq.render("Acme")
        self.assertIn(pl_brand.PRIMARY, html)
        self.assertIn("Poppins", html)
        self.assertIn("<svg", html)

    def test_has_a_submit_answers_json_target(self):
        html = riq.render("Acme")
        self.assertIn('id="answers-json"', html)
        self.assertIn('id="submitted-banner"', html)


def _valid_answers(**overrides):
    base = {
        "shopify_opp": False,
        "reuse_pool": None,
        "order_matrix": [{"label": "#1", "fraud": "low", "scenario": "happy"}],
        "gate_c": "send-as-is",
        "mode": "babysit",
    }
    base.update(overrides)
    return json.dumps(base)


class ParseAnswersTests(unittest.TestCase):
    def test_valid_answers_round_trip(self):
        answers = riq.parse_answers(_valid_answers())
        self.assertEqual(answers["mode"], "babysit")
        self.assertEqual(answers["order_matrix"][0]["label"], "#1")

    def test_rejects_malformed_json(self):
        with self.assertRaises(ValueError):
            riq.parse_answers("not json")

    def test_rejects_missing_field(self):
        raw = json.loads(_valid_answers())
        del raw["mode"]
        with self.assertRaises(ValueError):
            riq.parse_answers(json.dumps(raw))

    def test_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            riq.parse_answers(_valid_answers(mode="turbo"))

    def test_rejects_unknown_gate_c(self):
        with self.assertRaises(ValueError):
            riq.parse_answers(_valid_answers(gate_c="something-else"))

    def test_rejects_empty_order_matrix(self):
        with self.assertRaises(ValueError):
            riq.parse_answers(_valid_answers(order_matrix=[]))

    def test_rejects_unknown_fraud_level(self):
        with self.assertRaises(ValueError):
            riq.parse_answers(_valid_answers(
                order_matrix=[{"label": "#1", "fraud": "extreme", "scenario": "happy"}]))

    def test_rejects_unknown_scenario(self):
        with self.assertRaises(ValueError):
            riq.parse_answers(_valid_answers(
                order_matrix=[{"label": "#1", "fraud": "low", "scenario": "nonsense"}]))


class CliTests(unittest.TestCase):
    def _script_path(self):
        return str(pathlib.Path(__file__).resolve().parents[1] / "render_intake_questionnaire.py")

    def test_render_subcommand_writes_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(pathlib.Path(tmp) / "questionnaire.html")
            result = subprocess.run(
                [sys.executable, self._script_path(), "render",
                 "--prospect-name", "Acme", "-o", out],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("shopify_opp", pathlib.Path(out).read_text())

    def test_parse_subcommand_prints_normalized_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            answers_file = pathlib.Path(tmp) / "answers.json"
            answers_file.write_text(_valid_answers())
            result = subprocess.run(
                [sys.executable, self._script_path(), "parse", str(answers_file)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["mode"], "babysit")

    def test_parse_subcommand_fails_loud_on_invalid_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            answers_file = pathlib.Path(tmp) / "answers.json"
            answers_file.write_text(_valid_answers(mode="turbo"))
            result = subprocess.run(
                [sys.executable, self._script_path(), "parse", str(answers_file)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ANSWERS INVALID", result.stderr)


if __name__ == "__main__":
    unittest.main()
