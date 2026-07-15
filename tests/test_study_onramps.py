"""Contract tests for the curated LA study on-ramps source.

The data IS the content (no network at runtime), so these tests pin the
honesty contract on the rows themselves: real registration URLs, an
LA-area city per row, the facility's own pay and process language, no
invented figures or dates, and no em dashes anywhere.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

_PROCESS_RE = re.compile(r"sign.?up|register|invit|email", re.IGNORECASE)
# no facility stated a figure on its own site on the last live check, so a
# dollar figure anywhere in a row means someone invented one
_DOLLAR_FIGURE_RE = re.compile(r"\$\s*\d")


class StudyOnrampsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import study_onramps as mod
        self.mod = mod
        self.rows = mod.search_study_onramps()

    def test_returns_rows(self) -> None:
        self.assertGreater(len(self.rows), 0)

    def test_every_row_is_actionable(self) -> None:
        for row in self.rows:
            self.assertTrue(row["url"].startswith("http"), row["url"])
            self.assertTrue(row["title"].strip(), row)
            self.assertTrue(row["company"].strip(), row)
            self.assertTrue(row["location"].strip(), row["company"])

    def test_pay_is_never_invented(self) -> None:
        for row in self.rows:
            self.assertIsNone(row["salary_min"], row["company"])
            self.assertIsNone(row["salary_max"], row["company"])
            self.assertEqual(row["date_posted"], "", row["company"])
            for value in list(row.values()) + list(row["quest"].values()):
                if isinstance(value, str):
                    self.assertNotRegex(value, _DOLLAR_FIGURE_RE, row["company"])

    def test_description_states_the_process(self) -> None:
        for row in self.rows:
            self.assertRegex(row["description"], _PROCESS_RE)

    def test_vertical_is_study(self) -> None:
        for row in self.rows:
            self.assertEqual(row["vertical"], "study")
            self.assertEqual(row["source"], "study_onramps")
            self.assertTrue(row["is_rolling"])
            self.assertTrue(row["first_quest_ok"])

    def test_every_row_states_its_bring_and_catch(self) -> None:
        for row in self.rows:
            quest = row["quest"]
            self.assertTrue(quest["bring"], row["company"])
            catch = quest["catch"]
            self.assertTrue(catch, row["company"])
            # the honest catch: studies come by email after you register,
            # and a screener decides who gets picked
            self.assertIn("email", catch.lower(), row["company"])
            self.assertIn("screener", catch.lower(), row["company"])

    def test_no_em_dashes_anywhere(self) -> None:
        for row in self.rows:
            for value in list(row.values()) + list(row["quest"].values()):
                if isinstance(value, str):
                    self.assertNotIn("\u2014", value, row["company"])

    def test_max_results_respected(self) -> None:
        self.assertEqual(len(self.mod.search_study_onramps(max_results=3)), 3)
        self.assertEqual(self.mod.search_study_onramps(max_results=0), [])

    def test_rows_pass_the_row_contract(self) -> None:
        from job_finder.row_contract import validate_rows
        from job_finder.tools.scrapers._registry import get_registry

        meta = get_registry()["study_onramps"]
        self.assertEqual(meta.vertical, "study")
        self.assertFalse(meta.enabled_by_default)
        valid, rejected = validate_rows(self.rows, meta)
        self.assertEqual(rejected, [])
        self.assertEqual(len(valid), len(self.rows))

    def test_every_row_is_an_la_area_city(self) -> None:
        la_area = {"Los Angeles", "Irvine", "Culver City", "Calabasas"}
        for row in self.rows:
            self.assertIn(row["location"], la_area, row["company"])


if __name__ == "__main__":
    unittest.main()
