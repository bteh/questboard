"""Contract tests for the curated flip on-ramps source.

The data IS the content (no network at runtime), so these tests pin the
honesty contract on the rows themselves: real start URLs, a fee statement
in the platform's own terms, no invented pay or dates, and no em dashes
anywhere.
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

_FEE_STATEMENT_RE = re.compile(r"[$%]|free|no fee", re.IGNORECASE)


class FlipOnrampsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import flip_onramps as mod
        self.mod = mod
        self.rows = mod.search_flip_onramps()

    def test_returns_rows(self) -> None:
        self.assertGreater(len(self.rows), 0)

    def test_every_row_is_actionable(self) -> None:
        for row in self.rows:
            self.assertTrue(row["url"].startswith("http"), row["url"])
            self.assertTrue(row["title"].strip(), row)
            self.assertTrue(row["company"].strip(), row)

    def test_pay_is_never_invented(self) -> None:
        for row in self.rows:
            self.assertIsNone(row["salary_min"], row["company"])
            self.assertIsNone(row["salary_max"], row["company"])
            self.assertEqual(row["date_posted"], "", row["company"])

    def test_description_states_the_fee(self) -> None:
        for row in self.rows:
            self.assertRegex(row["description"], _FEE_STATEMENT_RE)

    def test_vertical_is_flip(self) -> None:
        for row in self.rows:
            self.assertEqual(row["vertical"], "flip")
            self.assertEqual(row["source"], "flip_onramps")
            self.assertTrue(row["is_rolling"])
            self.assertIsInstance(row["first_quest_ok"], bool)

    def test_every_row_states_its_bring_and_catch(self) -> None:
        for row in self.rows:
            quest = row["quest"]
            self.assertTrue(quest["bring"], row["company"])
            catch = quest["catch"]
            self.assertTrue(catch, row["company"])
            # the catch is the fee as stated: a figure or an explicit no-fee
            self.assertTrue(
                any(m in catch for m in ("%", "$")) or "no " in catch.lower(),
                f"{row['company']}: {catch}",
            )

    def test_no_em_dashes_anywhere(self) -> None:
        for row in self.rows:
            for value in list(row.values()) + list(row["quest"].values()):
                if isinstance(value, str):
                    self.assertNotIn("\u2014", value, row["company"])

    def test_max_results_respected(self) -> None:
        self.assertEqual(len(self.mod.search_flip_onramps(max_results=3)), 3)
        self.assertEqual(self.mod.search_flip_onramps(max_results=0), [])

    def test_rows_pass_the_row_contract(self) -> None:
        from job_finder.row_contract import validate_rows
        from job_finder.tools.scrapers._registry import get_registry

        meta = get_registry()["flip_onramps"]
        self.assertEqual(meta.vertical, "flip")
        self.assertFalse(meta.enabled_by_default)
        valid, rejected = validate_rows(self.rows, meta)
        self.assertEqual(rejected, [])
        self.assertEqual(len(valid), len(self.rows))

    def test_no_fee_platforms_are_included_as_equals(self) -> None:
        companies = {row["company"] for row in self.rows}
        self.assertIn("Facebook Marketplace", companies)
        self.assertIn("Vinted", companies)


if __name__ == "__main__":
    unittest.main()
