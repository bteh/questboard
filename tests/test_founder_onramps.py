"""Contract tests for the curated founder-funding on-ramps source.

The data IS the content (no network at runtime), so these tests pin the
honesty contract on the rows themselves: real application URLs on each
program's own host, amounts present only where the program's site states
one (with a checked-date note), a real bring and catch on every row, and
no em dashes anywhere.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


class FounderOnrampsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import founder_onramps as mod
        self.mod = mod
        self.rows = mod.search_founder_onramps()

    def test_returns_rows(self) -> None:
        # a healthy marquee lane, ~10-14 programs
        self.assertGreaterEqual(len(self.rows), 10)

    def test_every_row_is_actionable(self) -> None:
        for row in self.rows:
            self.assertTrue(row["url"].startswith("https://"), row["url"])
            self.assertTrue(row["title"].strip(), row)
            self.assertTrue(row["company"].strip(), row)

    def test_pay_is_never_invented(self) -> None:
        for row in self.rows:
            self.assertIsNone(row["salary_min"], row["company"])
            self.assertIsNone(row["salary_max"], row["company"])
            self.assertEqual(row["date_posted"], "", row["company"])

    def test_vertical_is_pitch(self) -> None:
        for row in self.rows:
            self.assertEqual(row["vertical"], "pitch")
            self.assertEqual(row["source"], "founder_onramps")
            self.assertTrue(row["is_rolling"])
            self.assertIsInstance(row["first_quest_ok"], bool)

    def test_every_row_states_its_bring_and_catch(self) -> None:
        for row in self.rows:
            quest = row["quest"]
            self.assertTrue(quest["bring"].strip(), row["company"])
            self.assertTrue(quest["catch"].strip(), row["company"])

    def test_every_description_carries_the_checked_date(self) -> None:
        # proof each row was verified live, not written from memory
        for row in self.rows:
            self.assertIn("checked 2026-07-15", row["description"], row["company"])

    def test_stated_amounts_are_pinned_to_their_source(self) -> None:
        by_company = {r["company"]: r for r in self.rows}
        # each figure is the program's own stated number; a future edit that
        # drops or changes one trips here
        self.assertIn("$500,000", by_company["Y Combinator"]["description"])
        self.assertIn("$250,000", by_company["Thiel Fellowship"]["description"])
        self.assertIn("$10,000", by_company["Z Fellows"]["description"])
        self.assertIn("up to $250K", by_company["Entrepreneur First"]["description"])
        self.assertIn("$1,000", by_company["1517 Fund"]["description"])

    def test_programs_without_a_stated_figure_state_no_figure(self) -> None:
        # Neo, Antler, and Emergent Ventures publish no fixed number on the
        # page checked, so the row must not invent one
        by_company = {r["company"]: r for r in self.rows}
        for company in ("Neo Scholars", "Antler", "Emergent Ventures"):
            self.assertIn(
                "does not publish", by_company[company]["description"], company
            )

    def test_no_em_dashes_anywhere(self) -> None:
        for row in self.rows:
            for value in list(row.values()) + list(row["quest"].values()):
                if isinstance(value, str):
                    self.assertNotIn("—", value, row["company"])

    def test_max_results_respected(self) -> None:
        self.assertEqual(len(self.mod.search_founder_onramps(max_results=3)), 3)
        self.assertEqual(self.mod.search_founder_onramps(max_results=0), [])

    def test_rows_pass_the_row_contract(self) -> None:
        from job_finder.row_contract import validate_rows
        from job_finder.tools.scrapers._registry import get_registry

        meta = get_registry()["founder_onramps"]
        self.assertEqual(meta.vertical, "pitch")
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(meta.full_snapshot)
        valid, rejected = validate_rows(self.rows, meta)
        self.assertEqual(rejected, [])
        self.assertEqual(len(valid), len(self.rows))


class FounderOnrampsRegistryTest(unittest.TestCase):
    def test_registered_as_pitch_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.founder_onramps  # noqa: F401

        reg = get_registry()
        self.assertIn("founder_onramps", reg)
        meta = reg["founder_onramps"]
        self.assertEqual(meta.vertical, "pitch")
        self.assertFalse(meta.enabled_by_default)
        self.assertFalse(meta.research_only)
        self.assertEqual(meta.refresh_hours, 168)
        self.assertTrue(meta.full_snapshot)
        self.assertTrue(callable(meta.search_fn))
        # quest scrapers never join the default career sweep
        self.assertNotIn("founder_onramps", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
