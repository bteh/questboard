"""Contract tests for the TrustedHousesitters index scraper (lookafter kind).

Fixture is a trimmed REAL capture from
https://www.trustedhousesitters.com/house-and-pet-sitting-assignments/united-states/
(live 2026-07-15, HTTP 200): five listing cards kept verbatim inside a
minimal index shell, covering multi-pet, single-pet, dog+cat, and cards
with and without a review label.

Pins the barter honesty contract: salary is always None and no dollar
figure ever appears, the description says the stay is a free trade for
pet and home care, rows link OUT to the /l/ detail URL on
trustedhousesitters.com, dated cards carry event_start/event_end and are
not rolling while an undated card is rolling, and the crawler NEVER fetches
a /l/ detail page or a q= pagination link. No live HTTP inside tests.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURE = ROOT / "tests" / "fixtures" / "trustedhousesitters_index.html"

_UNDATED_CARD = """
<div data-testid="ListingCard__container" aria-label="listing item for Cozy cabin and a lazy hound">
  <a href="/house-and-pet-sitting-assignments/united-states/oregon/bend/l/9999999/?routeParams=x">
    <div data-testid="ListingCard__image"><img src="https://res.cloudinary.com/x/photo.jpg"/></div>
  </a>
  <h3 data-testid="ListingCard__title">Cozy cabin and a lazy hound</h3>
  <span data-testid="ListingCard__location">Bend, OR, US</span>
  <ul data-testid="animals-list">
    <li><span data-testid="Animal__count">1</span><span data-testid="animal-icon-dog"></span></li>
  </ul>
</div>
"""


class _FakeResp:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class TrustedHousesittersCardTest(unittest.TestCase):
    """Unit tests over the real fixture cards via _normalize_card."""

    def setUp(self) -> None:
        from job_finder.tools.scrapers import trustedhousesitters as mod

        self.mod = mod
        soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")
        self.cards = soup.select('div[data-testid="ListingCard__container"]')
        self.rows = [mod._normalize_card(c) for c in self.cards]

    def test_fixture_has_five_cards(self) -> None:
        self.assertEqual(len(self.cards), 5)
        self.assertTrue(all(r is not None for r in self.rows))

    def test_every_row_is_actionable(self) -> None:
        for row in self.rows:
            self.assertTrue(row["url"].startswith("https://"), row["url"])
            self.assertTrue(row["title"].strip(), row)
            self.assertTrue(row["company"].strip(), row)
            self.assertEqual(row["source"], "trustedhousesitters")
            self.assertEqual(row["vertical"], "lookafter")

    def test_salary_is_always_none(self) -> None:
        for row in self.rows:
            self.assertIsNone(row["salary_min"], row["title"])
            self.assertIsNone(row["salary_max"], row["title"])

    def test_description_states_the_barter_no_pay(self) -> None:
        for row in self.rows:
            desc = row["description"]
            self.assertIn("No pay.", desc)
            self.assertIn("free stay", desc)
            # never a dollar figure anywhere on the row or its quest
            for value in list(row.values()) + list(row["quest"].values()):
                if isinstance(value, str):
                    self.assertNotIn("$", value, row["title"])

    def test_quest_catch_is_the_barter_reality(self) -> None:
        for row in self.rows:
            catch = row["quest"]["catch"]
            self.assertIn("No pay.", catch)
            self.assertIn("free stay", catch)

    def test_urls_link_out_to_detail_on_trustedhousesitters(self) -> None:
        for row in self.rows:
            self.assertTrue(row["url"].startswith("https://www.trustedhousesitters.com/"))
            self.assertRegex(row["url"], r"/l/\d+/$")  # clean canonical, q= stripped
            self.assertNotIn("?", row["url"])

    def test_dated_cards_carry_event_window_and_are_not_rolling(self) -> None:
        # every fixture card states a real date range
        for row in self.rows:
            self.assertIn("event_start", row)
            self.assertIn("event_end", row)
            self.assertFalse(row["is_rolling"], row["title"])
            self.assertRegex(row["event_start"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertRegex(row["event_end"], r"^\d{4}-\d{2}-\d{2}$")

    def test_specific_card_values(self) -> None:
        brooklyn = next(r for r in self.rows if "/l/3055672/" in r["url"])
        self.assertEqual(brooklyn["title"], "Plant Filled Apartment in Bushwick with Two Gorgeous Cats")
        self.assertEqual(brooklyn["location"], "Brooklyn, NY, US")
        self.assertEqual(brooklyn["event_start"], "2026-07-31")
        self.assertEqual(brooklyn["event_end"], "2026-08-17")
        self.assertEqual(brooklyn["quest"]["pets"], "2 cats")
        self.assertTrue(brooklyn["quest"]["image"].startswith("https://"))

    def test_multi_species_pet_phrase(self) -> None:
        makawao = next(r for r in self.rows if "/l/2876428/" in r["url"])
        self.assertEqual(makawao["quest"]["pets"], "1 dog and 1 cat")
        self.assertIn("Caring for 1 dog and 1 cat.", makawao["description"])

    def test_undated_card_is_rolling_with_no_event_dates(self) -> None:
        card = BeautifulSoup(_UNDATED_CARD, "html.parser").select_one(
            'div[data-testid="ListingCard__container"]'
        )
        row = self.mod._normalize_card(card)
        self.assertIsNotNone(row)
        self.assertTrue(row["is_rolling"])
        self.assertNotIn("event_start", row)
        self.assertNotIn("event_end", row)
        self.assertIsNone(row["salary_min"])
        self.assertEqual(row["quest"]["pets"], "1 dog")

    def test_no_em_dashes_anywhere(self) -> None:
        em_dash = "\u2014"
        for row in self.rows:
            for value in list(row.values()) + list(row["quest"].values()):
                if isinstance(value, str):
                    self.assertNotIn(em_dash, value, row["title"])

    def test_rows_pass_the_row_contract(self) -> None:
        from job_finder.row_contract import validate_rows
        from job_finder.tools.scrapers._registry import get_registry

        meta = get_registry()["trustedhousesitters"]
        valid, rejected = validate_rows(self.rows, meta)
        self.assertEqual(rejected, [])
        self.assertEqual(len(valid), len(self.rows))


class TrustedHousesittersCrawlTest(unittest.TestCase):
    """Integration tests over search_trustedhousesitters with mocked HTTP."""

    def setUp(self) -> None:
        from job_finder.tools.scrapers import trustedhousesitters as mod

        self.mod = mod
        self.html = FIXTURE.read_text(encoding="utf-8")

    def _run(self, **kw):
        with patch.object(self.mod.requests, "get", return_value=_FakeResp(self.html)) as get, \
             patch.object(self.mod.time, "sleep") as sleep:
            rows = self.mod.search_trustedhousesitters(**kw)
        self.get = get
        self.sleep = sleep
        return rows

    def test_returns_all_fixture_rows(self) -> None:
        rows = self._run()
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({r["url"] for r in rows}), 5)

    def test_crawler_never_fetches_a_detail_or_pagination_url(self) -> None:
        # widen to several region paths so pagination temptation is real
        self._run(region_paths=["united-states", "united-states/new-york/brooklyn"])
        self.assertTrue(self.get.called)
        for call in self.get.call_args_list:
            url = call.args[0] if call.args else call.kwargs.get("url", "")
            self.assertNotIn("/l/", url, f"crawler must never fetch a detail page: {url}")
            self.assertNotIn("q=", url, f"crawler must never build a q= page: {url}")
            self.assertIn("/house-and-pet-sitting-assignments/", url)

    def test_is_index_url_guard_rejects_disallowed(self) -> None:
        base = self.mod._BASE
        self.assertTrue(self.mod._is_index_url(base + "/house-and-pet-sitting-assignments/united-states/"))
        self.assertFalse(self.mod._is_index_url(base + "/house-and-pet-sitting-assignments/united-states/x/l/123/"))
        self.assertFalse(self.mod._is_index_url(base + "/house-and-pet-sitting-assignments/united-states/?q=abc"))

    def test_fetch_index_refuses_a_detail_path(self) -> None:
        # even if a caller sneaks a /l/ path in, no request is issued
        with patch.object(self.mod.requests, "get") as get:
            cards = self.mod._fetch_index("united-states/x/l/123/")
        self.assertEqual(cards, [])
        get.assert_not_called()

    def test_dedupes_across_pages_by_url(self) -> None:
        rows = self._run(region_paths=["united-states", "united-states/california/san-francisco"])
        self.assertEqual(len({r["url"] for r in rows}), len(rows))
        self.assertEqual(len(rows), 5)

    def test_max_results_cap(self) -> None:
        self.assertEqual(len(self._run(max_results=2)), 2)
        self.assertEqual(self._run(max_results=0), [])

    def test_sleeps_between_pages_only(self) -> None:
        self._run(region_paths=["united-states", "united-states/new-york/brooklyn"])
        self.assertEqual(self.sleep.call_count, 1)
        self.assertGreaterEqual(self.sleep.call_args[0][0], 2)

    def test_page_cap_limits_fetches(self) -> None:
        many = [f"united-states/x{i}" for i in range(self.mod._PAGE_CAP + 5)]
        self._run(region_paths=many, max_results=1000)
        self.assertLessEqual(self.get.call_count, self.mod._PAGE_CAP)

    def test_failed_fetch_returns_empty(self) -> None:
        with patch.object(self.mod, "_fetch_index", return_value=[]):
            self.assertEqual(self.mod.search_trustedhousesitters(), [])


class TrustedHousesittersRegistryTest(unittest.TestCase):
    def test_registration_contract(self) -> None:
        import job_finder.tools.scrapers  # noqa: F401  (trigger auto-discovery)
        from job_finder.tools.scrapers._registry import default_scraper_names, get_registry

        meta = get_registry()["trustedhousesitters"]
        self.assertEqual(meta.display_name, "TrustedHousesitters")
        self.assertEqual(meta.vertical, "lookafter")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertEqual(meta.stale_after_days, 14)
        self.assertEqual(meta.allowed_url_hosts, ("trustedhousesitters.com",))
        self.assertFalse(meta.enabled_by_default)
        self.assertFalse(meta.research_only)
        # quest source: never part of the default career sweep
        self.assertNotIn("trustedhousesitters", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
