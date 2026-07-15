"""Contract tests for the On Camera Audiences scraper (camera kind).

Fixtures are trimmed REAL pages captured live 2026-07-14 (HTTP 200):

- oncamera_audiences_shows.html: 8 show-column cards kept verbatim from
  https://on-camera-audiences.com/shows/ (Jeopardy! appears twice, once in
  the carousel with data-has-current-tapings and once in the grid, to pin
  dedup + merge; Password pins the comma city "Kearny, NJ"; Villa Viewing
  Night pins the empty-city h4).
- oncamera_audiences_show_jeopardy.html / _priceisright.html: the
  server-rendered #show-info, Event Location and Age restriction blocks
  kept verbatim. The TPIR page states prize copy ("win huge cash and
  prizes") and year-less prose dates ("July 24, 7:30 AM"), pinning that
  neither ever becomes pay or an event date.

No live HTTP inside tests.
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

FIXTURES = ROOT / "tests" / "fixtures"
INDEX = (FIXTURES / "oncamera_audiences_shows.html").read_text(encoding="utf-8")
JEOPARDY = (FIXTURES / "oncamera_audiences_show_jeopardy.html").read_text(encoding="utf-8")
TPIR = (FIXTURES / "oncamera_audiences_show_priceisright.html").read_text(encoding="utf-8")

JEOPARDY_URL = "https://on-camera-audiences.com/shows/jeopardy/"
TPIR_URL = "https://on-camera-audiences.com/shows/the-price-is-right/"


class OnCameraAudiencesTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import oncamera_audiences as mod
        self.mod = mod
        self.pages = {JEOPARDY_URL: JEOPARDY, TPIR_URL: TPIR}

    def _search(self, index_html, pages=None, **kw) -> list[dict]:
        pages = self.pages if pages is None else pages
        with patch.object(self.mod, "_fetch_listing", return_value=index_html), \
                patch.object(self.mod, "_fetch_show", side_effect=pages.get) as fetch:
            self.fetch_show = fetch
            return self.mod.search_oncamera_audiences(**kw)

    def _by_slug(self, rows, slug):
        return next(r for r in rows if r["quest"]["slug"] == slug)

    def test_parses_shows_into_camera_rows(self) -> None:
        rows = self._search(INDEX)
        # 8 cards on the fixture, Jeopardy! twice; dedup by URL keeps 7 shows
        self.assertEqual(len(rows), 7)
        for row in rows:
            self.assertEqual(row["vertical"], "camera")
            self.assertEqual(row["source"], "oncamera_audiences")
            self.assertTrue(row["title"].startswith("Be in the audience: "))
            self.assertTrue(row["first_quest_ok"])

    def test_urls_are_show_pages_never_tickets(self) -> None:
        # robots.txt disallows /tickets/*; rows must point at the show page
        for row in self._search(INDEX):
            self.assertTrue(
                row["url"].startswith("https://on-camera-audiences.com/shows/")
            )
            self.assertNotIn("/tickets/", row["url"])

    def test_tickets_link_card_is_dropped(self) -> None:
        bent = INDEX.replace(
            'data-link="https://on-camera-audiences.com/shows/password/"',
            'data-link="https://on-camera-audiences.com/tickets/password/"',
        )
        rows = self._search(bent)
        self.assertEqual(len(rows), 6)
        self.assertFalse(any("/tickets/" in r["url"] for r in rows))

    def test_show_page_states_venue_and_city(self) -> None:
        jeopardy = self._by_slug(self._search(INDEX), "jeopardy")
        self.assertEqual(jeopardy["title"], "Be in the audience: Jeopardy!")
        # company is the venue exactly as the Event Location block states it
        self.assertEqual(jeopardy["company"], "Sony Pictures Studios")
        self.assertEqual(jeopardy["quest"]["venue"], "Sony Pictures Studios")
        self.assertEqual(jeopardy["location"], "Los Angeles")
        self.assertIn("live studio audience", jeopardy["description"])
        # the page title header never leaks into the description
        self.assertFalse(jeopardy["description"].startswith("Jeopardy!"))

    def test_index_only_row_uses_card_fields(self) -> None:
        # no fixture page for Password: the row is built from its card alone
        password = self._by_slug(self._search(INDEX), "password")
        self.assertEqual(password["company"], "Password")
        self.assertEqual(password["location"], "Kearny, NJ")
        self.assertEqual(password["quest"]["age_min"], 16)
        big_brother = self._by_slug(self._search(INDEX), "big-brother")
        self.assertEqual(big_brother["description"], "Be in the room for the eviction.")

    def test_no_pay_is_ever_invented(self) -> None:
        # TPIR prose says "win huge cash and prizes": a game outcome, not comp
        rows = self._search(INDEX)
        tpir = self._by_slug(rows, "the-price-is-right")
        self.assertIn("cash and prizes", tpir["description"])
        for row in rows:
            self.assertNotIn("salary_min", row)
            self.assertNotIn("salary_max", row)
            self.assertNotIn("salary_source", row)

    def test_yearless_prose_dates_never_become_events(self) -> None:
        # TPIR states "(July 24, 7:30 AM)" and a season calendar, all without
        # a year; guessing one would invent a date the source did not state
        rows = self._search(INDEX)
        for row in rows:
            self.assertNotIn("event_start", row)
            self.assertTrue(row["is_rolling"])
            self.assertNotIn("date_posted", row)

    def test_full_stated_date_becomes_event_start(self) -> None:
        dated = JEOPARDY.replace("back taping in July!", "back taping July 24, 2099!")
        rows = self._search(INDEX, pages={JEOPARDY_URL: dated})
        jeopardy = self._by_slug(rows, "jeopardy")
        self.assertEqual(jeopardy["event_start"], "2099-07-24")
        self.assertNotIn("is_rolling", jeopardy)

    def test_past_stated_date_stays_rolling(self) -> None:
        dated = JEOPARDY.replace("back taping in July!", "aired July 24, 2020!")
        rows = self._search(INDEX, pages={JEOPARDY_URL: dated})
        jeopardy = self._by_slug(rows, "jeopardy")
        self.assertNotIn("event_start", jeopardy)
        self.assertTrue(jeopardy["is_rolling"])

    def test_age_prefers_the_show_page_statement(self) -> None:
        rows = self._search(INDEX)
        # Jeopardy! page states "Minimum age is 8 years."
        self.assertEqual(self._by_slug(rows, "jeopardy")["quest"]["age_min"], 8)
        # Villa Viewing Night has no fetched page; the card h4 states 21+
        self.assertEqual(
            self._by_slug(rows, "love-island-premiere-watch-party")["quest"]["age_min"], 21
        )

    def test_carousel_and_grid_cards_merge(self) -> None:
        jeopardy = self._by_slug(self._search(INDEX), "jeopardy")
        # the tapings flag lives only on the carousel copy of the card
        self.assertTrue(jeopardy["quest"]["has_current_tapings"])
        self.assertNotIn(
            "has_current_tapings",
            self._by_slug(self._search(INDEX), "password")["quest"],
        )

    def test_max_results_caps_rows_and_page_fetches(self) -> None:
        rows = self._search(INDEX, max_results=2)
        self.assertEqual(len(rows), 2)
        # show pages are fetched lazily, one per emitted row
        self.assertEqual(self.fetch_show.call_count, 2)

    def test_empty_and_bad_html_return_empty(self) -> None:
        self.assertEqual(self._search("", pages={}), [])
        self.assertEqual(self._search(None, pages={}), [])
        self.assertEqual(self._search("<html><body>maintenance</body></html>", pages={}), [])
        self.assertEqual(self._search('<div class="show-column">junk</div>', pages={}), [])


class RegistryTest(unittest.TestCase):
    def test_registered_as_camera_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        import job_finder.tools.scrapers.oncamera_audiences  # noqa: F401
        reg = get_registry()
        self.assertIn("oncamera_audiences", reg)
        meta = reg["oncamera_audiences"]
        self.assertEqual(meta.vertical, "camera")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertTrue(meta.full_snapshot)
        self.assertEqual(meta.allowed_url_hosts, ("on-camera-audiences.com",))
        self.assertEqual(meta.allowed_url_paths, ("/shows/",))
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))

    def test_not_in_default_career_sweep(self) -> None:
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.oncamera_audiences  # noqa: F401
        self.assertNotIn("oncamera_audiences", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
