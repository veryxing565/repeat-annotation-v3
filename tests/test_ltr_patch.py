"""Static regression checks; these do not execute either LTR wrapper."""

import re
import unittest
from pathlib import Path

PATCHED = Path(__file__).resolve().parents[1] / "patched_tools"
WRAPPERS = {
    "LTR_FINDER_parallel": 10,
    "LTR_HARVEST_parallel": 30,
}


class LtrTimeoutPatchTests(unittest.TestCase):
    def test_single_thread_fast_path_does_not_bypass_salvage_timeout(self):
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                text = (PATCHED / name / name).read_text(encoding="utf-8")
                code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
                self.assertRegex(code, r"if\s*\(\s*\$threads\s*==\s*1\s*&&\s*\$try1\s*!=\s*0\s*\)")
                self.assertNotRegex(code, r"if\s*\(\s*\$threads\s*==\s*1\s*\)\s*\{")

    def test_salvage_subpieces_are_bounded_and_do_not_recurse_again(self):
        for name, seconds in WRAPPERS.items():
            with self.subTest(wrapper=name):
                text = (PATCHED / name / name).read_text(encoding="utf-8")
                calls = [line for line in text.splitlines()
                         if not line.lstrip().startswith("#") and "my $in=" in line and name in line]
                self.assertEqual(len(calls), 1)
                call = calls[0]
                for option, value in (("size", 50000), ("overlap", 5000), ("time", seconds),
                                      ("try1", 0), ("threads", 1)):
                    self.assertRegex(call, rf"-{option}\s+{value}(?:\s|[`;])")
                self.assertIn("timeout -s KILL", text)
                self.assertRegex(text, r"if\s*\(\s*\$\?\s+ne\s+0\s+and\s+\$try1\s+ne\s+0\s*\)")

    def test_required_text_helpers_and_original_licenses_are_present(self):
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                directory = PATCHED / name
                self.assertTrue((directory / "bin/cut.pl").is_file())
                self.assertIn("$script_path/bin/cut.pl", (directory / name).read_text())
                license_text = (directory / "LICENSE").read_text()
                self.assertIn("MIT License", license_text)
                self.assertIn("Shujun Ou and Ning Jiang", license_text)
        finder = PATCHED / "LTR_FINDER_parallel"
        self.assertTrue((finder / "bin/convert_ltr_finder2.pl").is_file())
        self.assertIn("$script_path/bin/convert_ltr_finder2.pl", (finder / finder.name).read_text())


if __name__ == "__main__":
    unittest.main()
