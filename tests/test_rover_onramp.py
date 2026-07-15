"""Contract tests for the curated Rover on-ramp (lookafter kind).

Rover is Cloudflare-walled with no public feed, so this is a single
standing row with no runtime network. These tests pin the honesty
contract on that row: the real Rover start URL, no invented pay, a
plain description, and a source-stated bring and catch. No em dashes.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


class RoverOnrampTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import rover_onramp as mod

        self.mod = mod
        self.rows = mod.search_rover_onramp()

    def test_returns_exactly_one_row(self) -> None:
        self.assertEqual(len(self.rows), 1)

    def test_the_row_is_the_rover_start_page(self) -> None:
        row = self.rows[0]
        self.assertEqual(row["title"], "Start earning as a dog sitter or walker on Rover")
        self.assertEqual(row["company"], "Rover")
        self.assertEqual(row["url"], "https://www.rover.com/become-a-sitter/")
        self.assertEqual(row["source"], "rover_onramp")
        self.assertEqual(row["vertical"], "lookafter")
        self.assertTrue(row["description"].strip())

    def test_pay_is_never_invented(self) -> None:
        row = self.rows[0]
        self.assertIsNone(row["salary_min"])
        self.assertIsNone(row["salary_max"])
        self.assertEqual(row["date_posted"], "")
        # Rover sets no fixed pay, so no dollar figure appears anywhere
        for value in list(row.values()) + list(row["quest"].values()):
            if isinstance(value, str):
                self.assertNotIn("$", value)

    def test_standing_quest_flags(self) -> None:
        row = self.rows[0]
        self.assertTrue(row["is_rolling"])
        self.assertTrue(row["first_quest_ok"])

    def test_states_bring_and_catch(self) -> None:
        quest = self.rows[0]["quest"]
        self.assertEqual(quest["bring"], "a profile and a background check")
        catch = quest["catch"]
        self.assertIn("service fee", catch)
        self.assertIn("your own rates", catch)

    def test_no_em_dashes_anywhere(self) -> None:
        em_dash = "\u2014"
        row = self.rows[0]
        for value in list(row.values()) + list(row["quest"].values()):
            if isinstance(value, str):
                self.assertNotIn(em_dash, value)

    def test_max_results_respected(self) -> None:
        self.assertEqual(self.mod.search_rover_onramp(max_results=0), [])
        self.assertEqual(len(self.mod.search_rover_onramp(max_results=5)), 1)

    def test_rows_pass_the_row_contract(self) -> None:
        from job_finder.row_contract import validate_rows
        from job_finder.tools.scrapers._registry import get_registry

        meta = get_registry()["rover_onramp"]
        valid, rejected = validate_rows(self.rows, meta)
        self.assertEqual(rejected, [])
        self.assertEqual(len(valid), 1)

    def test_registration_contract(self) -> None:
        import job_finder.tools.scrapers  # noqa: F401  (trigger auto-discovery)
        from job_finder.tools.scrapers._registry import default_scraper_names, get_registry

        meta = get_registry()["rover_onramp"]
        self.assertEqual(meta.vertical, "lookafter")
        self.assertTrue(meta.full_snapshot)
        self.assertEqual(meta.refresh_hours, 168)
        self.assertEqual(meta.allowed_url_hosts, ("rover.com",))
        self.assertFalse(meta.enabled_by_default)
        self.assertFalse(meta.research_only)
        self.assertNotIn("rover_onramp", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
