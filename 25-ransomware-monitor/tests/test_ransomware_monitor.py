"""Tests for the ransomware feed monitor: pure helpers plus one parsed item."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("mon", pathlib.Path(__file__).resolve().parents[1] / "ransom_rss.py")
mon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mon)


class HelperTest(unittest.TestCase):
    def test_rfc822_month_mapping(self):
        self.assertEqual(mon.parse_rfc822("Mon, 08 Sep 2026 10:00:00 GMT").year, 2026)

    def test_region_from_city_name(self):
        self.assertEqual(mon.find_region("Hacker group hits Heilbronn manufacturer")[0], "de")

    def test_region_code_only_in_brackets(self):
        self.assertEqual(mon.match_token("(DE)")[0], "de")
        self.assertIsNone(mon.match_token("deal")[0])

    def test_group_and_victim_split(self):
        group, victim = mon.extract_group_victim("lockbit3 :: Example GmbH | leak site")
        self.assertTrue(group)
        self.assertTrue(victim)

    def test_truncate_keeps_limit(self):
        self.assertLessEqual(len(mon.truncate_description("x" * 500, 120)), 124)

    def test_strip_html(self):
        self.assertNotIn("<b>", mon.strip_html("<b>Bold</b> text"))


if __name__ == "__main__":
    unittest.main()
