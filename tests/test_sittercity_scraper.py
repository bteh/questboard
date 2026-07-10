"""Contract tests for the Sittercity city-page scraper (lookafter kind).

Fixture is a trimmed REAL city page from
https://www.sittercity.com/babysitting-jobs/ca/los-angeles (captured live
2026-07-09, HTTP 200; three job cards kept verbatim). Pins: the family's
own posted rate ("$26–30/hr", en dash theirs) maps to structured hourly
figures, the neighborhood before the bullet becomes the location, the
posted date parses, and the poster's name is credited. No live HTTP
inside tests.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURE = ROOT / "tests" / "fixtures" / "sittercity_city.html"


class SittercityTest(unittest.TestCase):
    def setUp(self) -> None:
        from bs4 import BeautifulSoup
        from job_finder.tools.scrapers import sittercity as mod
        self.mod = mod
        soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")
        self.cards = soup.select("article.job-card")

    def _search(self, cards, **kw) -> list[dict]:
        with patch.object(self.mod, "_fetch_city", return_value=cards):
            return self.mod.search_sittercity(city_paths=["ca/los-angeles"], **kw)

    def test_parses_cards_into_lookafter_rows(self) -> None:
        rows = self._search(self.cards)
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["vertical"], "lookafter")
            self.assertTrue(row["url"].startswith("https://www.sittercity.com/babysitting-jobs/"))
            self.assertTrue(row["title"])

    def test_posted_rate_maps_to_hourly_figures(self) -> None:
        rows = self._search(self.cards)
        first = rows[0]
        self.assertEqual(first["salary_min"], 26.0)
        self.assertEqual(first["salary_max"], 30.0)
        self.assertEqual(first["salary_period"], "hourly")
        self.assertEqual(first["salary_source"], "reported")

    def test_neighborhood_becomes_location(self) -> None:
        rows = self._search(self.cards)
        self.assertEqual(rows[0]["location"], "Culver City, CA")

    def test_posted_date_and_poster_credit(self) -> None:
        rows = self._search(self.cards)
        self.assertEqual(rows[0]["date_posted"], "2026-07-09")
        self.assertIn("via Sittercity", rows[0]["company"])

    def test_empty_city_returns_empty(self) -> None:
        self.assertEqual(self._search([]), [])


if __name__ == "__main__":
    unittest.main()
