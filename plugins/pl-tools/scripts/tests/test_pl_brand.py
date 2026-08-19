"""Stdlib unittest — no pytest."""
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pl_brand

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class BrandTokenTests(unittest.TestCase):
    def test_colors_are_hex(self):
        for token in (pl_brand.PRIMARY, pl_brand.TEXT, pl_brand.TINT, pl_brand.CARD):
            self.assertRegex(token, HEX_RE)

    def test_primary_is_the_parcellab_indigo(self):
        self.assertEqual(pl_brand.PRIMARY, "#3E39D3")

    def test_font_family_names_poppins(self):
        self.assertIn("Poppins", pl_brand.FONT_FAMILY)

    def test_google_fonts_link_loads_poppins(self):
        self.assertIn("fonts.googleapis.com", pl_brand.GOOGLE_FONTS_LINK)
        self.assertIn("Poppins", pl_brand.GOOGLE_FONTS_LINK)

    def test_logo_svg_is_recolorable(self):
        self.assertTrue(pl_brand.LOGO_SVG.strip().startswith("<svg"))
        self.assertIn("currentColor", pl_brand.LOGO_SVG)
        self.assertNotIn('fill="black"', pl_brand.LOGO_SVG)


if __name__ == "__main__":
    unittest.main()
