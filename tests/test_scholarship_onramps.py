"""The curated scholarship shelf stays inside verified application windows."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


class ScholarshipOnrampsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import scholarship_onramps as mod

        self.mod = mod

    def _search(self, today: date = date(2026, 8, 5), **kwargs) -> list[dict]:
        with patch.object(self.mod, "_today", return_value=today):
            return self.mod.search_scholarship_onramps(**kwargs)

    def test_current_shelf_has_verified_specific_and_discovery_rows(self) -> None:
        rows = self._search()
        self.assertEqual(len(rows), 6)
        self.assertTrue(any("Department of Labor" in row["title"] for row in rows))
        self.assertTrue(any("Coca-Cola" in row["title"] for row in rows))
        self.assertTrue(any("VFW" in row["title"] for row in rows))
        self.assertTrue(any("Schwarzman" in row["title"] for row in rows))
        self.assertTrue(any("Fry" in row["title"] for row in rows))
        self.assertTrue(any("Rogers" in row["title"] for row in rows))
        for row in rows:
            self.assertEqual(row["vertical"], "scholarship")
            self.assertEqual(row["source"], "scholarship_onramps")
            self.assertTrue(row["url"].startswith("https://"))
            self.assertTrue(row["quest"]["bring"])
            self.assertTrue(row["quest"]["catch"])
            self.assertIn(
                row["quest"]["application_effort"],
                {"quick", "some_prep", "involved"},
            )
            self.assertTrue(row["quest"]["application_effort_note"])
            self.assertTrue(row["quest"]["criteria"])

    def test_dated_programs_carry_deadlines_and_vanish_afterward(self) -> None:
        current = self._search()
        coke = next(row for row in current if "Coca-Cola" in row["title"])
        self.assertEqual(coke["quest"]["apply_by"], "2026-09-30")
        self.assertEqual(coke["event_end"], "2026-09-30")
        self.assertEqual(coke["salary_min"], coke["salary_max"])

        october = self._search(date(2026, 10, 1))
        titles = {row["title"] for row in october}
        self.assertFalse(any("Coca-Cola" in title for title in titles))
        self.assertFalse(any("Schwarzman" in title for title in titles))
        self.assertTrue(any("VFW" in title for title in titles))

        after_all = self._search(date(2026, 11, 16))
        self.assertEqual(len(after_all), 3)  # finder + two evergreen VA benefits

    def test_future_rounds_do_not_publish_early(self) -> None:
        before_open = self._search(date(2026, 8, 2))
        self.assertFalse(any("Coca-Cola" in row["title"] for row in before_open))
        self.assertTrue(any("VFW" in row["title"] for row in before_open))

    def test_ceiling_only_awards_never_claim_a_floor(self) -> None:
        rows = self._search()
        vfw = next(row for row in rows if "VFW" in row["title"])
        rogers = next(row for row in rows if "Rogers" in row["title"])
        for row in (vfw, rogers):
            self.assertNotIn("salary_min", row)
            self.assertGreater(row["salary_max"], 0)
            self.assertEqual(row["salary_source"], "reported")

    def test_max_results_caps_rows(self) -> None:
        self.assertEqual(len(self._search(max_results=2)), 2)


class ScholarshipOnrampsRegistryTest(unittest.TestCase):
    def test_registered_as_weekly_full_snapshot(self) -> None:
        from job_finder.tools.scrapers import get_registry
        from job_finder.tools.scrapers._registry import default_scraper_names

        meta = get_registry()["scholarship_onramps"]
        self.assertEqual(meta.vertical, "scholarship")
        self.assertEqual(meta.refresh_hours, 168)
        self.assertTrue(meta.full_snapshot)
        self.assertIn("va.gov", meta.allowed_url_hosts)
        self.assertNotIn("scholarship_onramps", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
