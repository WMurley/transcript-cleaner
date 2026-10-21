"""design.md reader: harder files still load and stay readable. Synthetic fixtures only."""
import unittest
from pathlib import Path

import theme

HERE = Path(__file__).resolve().parent


def load(name):
    return theme.parse((HERE / "test-fixtures" / name).read_text(encoding="utf-8"))


class PaleAccentDesign(unittest.TestCase):
    def setUp(self):
        self.t = load("pale-accent-design.md")
        self.light = theme._finish(dict(self.t))
        self.dark = theme.derive_other(self.t)

    def test_slash_roles_are_read(self):
        self.assertEqual(self.t["accent"], "#c4f7a1")

    def test_pale_accent_stays_a_fill_with_readable_words(self):
        self.assertEqual(self.light["accent"], "#c4f7a1")
        self.assertGreaterEqual(theme.contrast(self.light["accent_text"], self.light["accent"]), 4.5)
        self.assertEqual(self.light["accent_fg"], self.light["text"])
        self.assertGreaterEqual(theme.contrast(self.light["accent_edge"], self.light["panel"]), 2.6)

    def test_dark_mode_words_are_readable(self):
        for t in (self.light, self.dark):
            self.assertGreaterEqual(theme.contrast(t["accent_fg"], t["panel"]), 3.0)
            self.assertGreaterEqual(theme.contrast(t["muted"], t["panel2"]), 5.0)

    def test_layers_stay_apart(self):
        for t in (self.light, self.dark):
            self.assertGreaterEqual(theme.contrast(t["bg"], t["panel"]), 1.1)
            self.assertGreaterEqual(theme.contrast(t["line_strong"], t["panel"]), 2.6)
        self.assertLess(theme.contrast(self.light["panel2"], self.light["panel"]), 1.3)  # ink border doesn't make insets grey

    def test_fonts_follow_their_roles(self):
        self.assertTrue(self.t["font_heading"].startswith('"Lora"'))
        self.assertTrue(self.t["font_body"].startswith('"Archivo Narrow"'))

    def test_narrow_body_font_gets_a_regular_reading_font(self):
        self.assertNotIn("Narrow", self.t["font_reading"])

    def test_label_tracking_is_not_applied_to_reading_text(self):
        self.assertEqual(self.t["tracking"], "normal")

    def test_no_shadow_rule(self):
        self.assertTrue(self.t["flat"])
        self.assertIn("--shadow:none", theme.to_css(self.t))


class ClayDesign(unittest.TestCase):
    def test_ordinary_design_keeps_its_fonts_and_accent(self):
        t = load("clay-design.md")
        self.assertTrue(t["font_heading"].startswith('"Fraunces"'))
        self.assertTrue(t["font_body"].startswith('"Inter"'))
        self.assertEqual(t["font_reading"], t["font_body"])
        self.assertEqual(t["tracking"], "-0.023em")
        light = theme._finish(dict(t))
        self.assertEqual(light["accent_fg"], light["accent"])


if __name__ == "__main__":
    unittest.main()
