"""Unit tests for check_layout_html. Stdlib unittest — no pytest."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "check_layout_html.py"

PL_TOKENS = (
    "{{content}}{{preview}}{{schemaOrgMarkup}}"
    "{{generated/campaignManager/banner}}"
    "{{generated/campaignManager/html}}"
    "{{generated/campaignManager/productRecommendation}}"
)


def build(body):
    """A minimal but structurally valid layout carrying every required token."""
    return (
        "<!doctype html><html><body>"
        + PL_TOKENS
        + body
        + "</body></html>"
    )


def run(html):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
        fh.write(html)
        path = fh.name
    return subprocess.run(
        [sys.executable, str(SCRIPT), path],
        capture_output=True, text=True,
    )


class TestCheckLayoutHtml(unittest.TestCase):
    def test_clean_layout_passes(self):
        r = run(build('<table><tr><td style="color:#000000;">hi</td></tr></table>'))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_double_quote_inside_style_attribute_fails(self):
        # The live 2026-08-11 bug: a quoted font family closes the attribute.
        bad = ('<table><tr><td style="font-family:"Segoe UI", Arial; '
               'color:#000000;">hi</td></tr></table>')
        r = run(build(bad))
        self.assertEqual(r.returncode, 1)
        self.assertIn("style attribute", r.stdout)

    def test_leftover_brand_token_fails(self):
        r = run(build('<table><tr><td style="color:__BRAND_TEXT_PRIMARY__;">'
                      'hi</td></tr></table>'))
        self.assertEqual(r.returncode, 1)
        self.assertIn("__BRAND_", r.stdout)

    def test_missing_parcellab_token_fails(self):
        html = ("<!doctype html><html><body>{{preview}}"
                "<table><tr><td>hi</td></tr></table></body></html>")
        r = run(html)
        self.assertEqual(r.returncode, 1)
        self.assertIn("{{content}}", r.stdout)

    def test_unbalanced_tags_fail(self):
        r = run(build("<table><tr><td>hi</td></tr>"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("table", r.stdout)


if __name__ == "__main__":
    unittest.main()
