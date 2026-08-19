"""Stdlib unittest — no pytest."""
import pathlib
import sys
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
        self.assertNotIn('name="reuse_pool"', html)

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


if __name__ == "__main__":
    unittest.main()
