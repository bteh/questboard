"""Contract tests for the Standing Room Only camera-vertical scraper.

Fixtures are trimmed from live responses captured 2026-07-08:
- standingroomonly_shows.json: https://app.standingroomonly.tv/api/shows
  (5 of 13 live rows: two dated tapings, two standing lists on the 12/31
  placeholder date, one restricted onboarding row)
- standingroomonly_pages.json: https://standingroomonly.tv/wp-json/wp/v2/pages
  (7 of 43 live pages, Elementor bulk stripped: rolling court casting pages,
  a forms.gle-only page, two dated campaign pages incl. the live "Februrary"
  typo, and two platform pages that must be filtered out)

These pin the API datetime parse, standing-list detection, prose event dates,
the CTA page filter, staleness dropping, the no-salary-keys rule, and registry
registration under vertical="camera".
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURES = ROOT / "tests" / "fixtures"

_SALARY_KEYS = ("salary_min", "salary_max", "salary_period", "salary_source")


def _api_shows() -> list[dict]:
    data = json.loads((FIXTURES / "standingroomonly_shows.json").read_text(encoding="utf-8"))
    return data["shows"]


def _pages() -> list[dict]:
    return json.loads((FIXTURES / "standingroomonly_pages.json").read_text(encoding="utf-8"))


def _show(project_id: int) -> dict:
    return next(s for s in _api_shows() if s["project_id"] == project_id)


def _page(slug: str) -> dict:
    return next(p for p in _pages() if p["slug"] == slug)


class ShowDatetimeTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import standingroomonly as mod
        self.mod = mod

    def test_pdt_morning(self) -> None:
        dt = self.mod._parse_show_datetime("7/08/26 9:15 AM PDT")
        self.assertEqual(dt.isoformat(), "2026-07-08T09:15:00-07:00")

    def test_pst_evening(self) -> None:
        dt = self.mod._parse_show_datetime("12/31/26 11:00 PM PST")
        self.assertEqual(dt.isoformat(), "2026-12-31T23:00:00-08:00")

    def test_noon(self) -> None:
        dt = self.mod._parse_show_datetime("12/31/26 12:00 PM PST")
        self.assertEqual(dt.hour, 12)

    def test_unparseable(self) -> None:
        for bad in (None, "", "soon", "7/08/26", "7/08/26 9:15 AM XYZ"):
            self.assertIsNone(self.mod._parse_show_datetime(bad))


class ApiShowNormalizeTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import standingroomonly as mod
        self.mod = mod

    def test_dated_taping_row(self) -> None:
        row = self.mod._normalize_api_show(_show(10574))
        self.assertEqual(row["title"], "We The People w/ Judge Lauren Lake (Culver City)")
        self.assertEqual(row["company"], "Standing Room Only")
        self.assertEqual(row["source"], "standingroomonly")
        self.assertEqual(row["vertical"], "camera")
        self.assertEqual(row["location"], "Culver City")
        self.assertIn("/show/10574/", row["url"])
        self.assertEqual(row["event_start"], "2026-07-09T09:15:00-07:00")
        self.assertNotIn("is_rolling", row)
        self.assertTrue(row["first_quest_ok"])
        self.assertIn("Daytime Court Show", row["description"])

    def test_no_salary_keys_even_when_notes_state_pay(self) -> None:
        # The litigant pool notes say "$20 per Hour" in prose; quest rows never
        # turn prose into salary fields.
        row = self.mod._normalize_api_show(_show(10577))
        for key in _SALARY_KEYS:
            self.assertNotIn(key, row)
        self.assertIn("$20 per Hour", row["description"])

    def test_no_date_posted(self) -> None:
        # The API states no posting date; omitting date_posted is the honest move.
        for pid in (10574, 8366):
            self.assertNotIn("date_posted", self.mod._normalize_api_show(_show(pid)))

    def test_standing_lists_are_rolling_without_event_start(self) -> None:
        for pid in (8366, 7710):  # "Rush Call" title-cased and "RUSH CALLS"
            row = self.mod._normalize_api_show(_show(pid))
            self.assertTrue(row["is_rolling"])
            self.assertNotIn("event_start", row)

    def test_onboarding_row_is_not_a_first_quest(self) -> None:
        row = self.mod._normalize_api_show(_show(10478))
        self.assertTrue(row["is_rolling"])
        self.assertNotIn("first_quest_ok", row)

    def test_quest_extras(self) -> None:
        row = self.mod._normalize_api_show(_show(10577))
        self.assertEqual(row["quest"]["project_id"], 10577)
        self.assertEqual(row["quest"]["datetime_text"], "7/08/26 9:30 AM PDT")
        self.assertTrue(row["quest"]["can_apply"])

    def test_empty_title_returns_none(self) -> None:
        self.assertIsNone(self.mod._normalize_api_show({"public_name": "  "}))


class ProseDateTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import standingroomonly as mod
        self.mod = mod

    def test_ordinal_date(self) -> None:
        got = self.mod._parse_prose_event_date("Date: Wednesday, April 1st, 2026 Time: 12pm")
        self.assertEqual(got, date(2026, 4, 1))

    def test_live_month_typo(self) -> None:
        # The fox page really spells it "Februrary"; without the alias the page
        # would look undated and be emitted as rolling forever.
        got = self.mod._parse_prose_event_date("Date: Februrary 15th, 2026")
        self.assertEqual(got, date(2026, 2, 15))

    def test_no_date(self) -> None:
        self.assertIsNone(self.mod._parse_prose_event_date("Register Now"))
        self.assertIsNone(self.mod._parse_prose_event_date("Watch 2 experts for 3 hours"))


class PageNormalizeTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import standingroomonly as mod
        self.mod = mod

    def test_rolling_casting_page(self) -> None:
        row = self.mod._normalize_page(_page("court"), today=date(2026, 7, 8))
        self.assertEqual(row["title"], "Actors Wanted for Court TV")
        self.assertEqual(row["url"], "https://standingroomonly.tv/court/")
        self.assertTrue(row["is_rolling"])
        self.assertNotIn("event_start", row)
        self.assertTrue(row["first_quest_ok"])
        self.assertIn("non-union", row["description"])
        self.assertNotIn("<h2>", row["description"])
        self.assertEqual(row["quest"]["application_route"], "google_form")
        for key in _SALARY_KEYS:
            self.assertNotIn(key, row)

    def test_forms_gle_only_page_qualifies(self) -> None:
        # pawnstars has no CTA copy at all, just a Google Form button.
        row = self.mod._normalize_page(_page("pawnstars"), today=date(2026, 7, 8))
        self.assertEqual(row["title"], "Pawn Stars Do America")
        self.assertTrue(row["is_rolling"])

    def test_dated_page_future_keeps_event_start(self) -> None:
        row = self.mod._normalize_page(_page("tnt"), today=date(2026, 3, 1))
        self.assertEqual(row["event_start"], "2026-04-01")
        self.assertNotIn("is_rolling", row)
        self.assertEqual(row["location"], "Atlanta, Georgia")

    def test_dated_page_past_is_dropped(self) -> None:
        self.assertIsNone(self.mod._normalize_page(_page("tnt"), today=date(2026, 7, 8)))

    def test_typo_dated_page_past_is_dropped(self) -> None:
        # "Februrary 15th, 2026" must parse (typo alias) so the stale fox page
        # is dropped instead of leaking through as a rolling signup.
        self.assertIsNone(self.mod._normalize_page(_page("fox"), today=date(2026, 7, 8)))

    def test_platform_pages_are_filtered(self) -> None:
        for slug in ("payroll", "home"):
            self.assertIsNone(self.mod._normalize_page(_page(slug), today=date(2026, 1, 1)))

    def test_bad_page_returns_none(self) -> None:
        for bad in ({}, {"slug": "x"}, {"slug": "x", "title": {"rendered": "T"}}):
            self.assertIsNone(self.mod._normalize_page(bad, today=date(2026, 1, 1)))


class SearchTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import standingroomonly as mod
        self.mod = mod

    def _search(self, **kw) -> list[dict]:
        with patch.object(self.mod, "_fetch_api_shows", return_value=_api_shows()):
            with patch.object(self.mod, "_fetch_pages", return_value=_pages()):
                return self.mod.search_standingroomonly(**kw)

    def test_merges_api_and_rolling_pages(self) -> None:
        # Fixture campaign dates (Apr/Feb 2026) are in the past at any real run
        # time, so the dated pages drop and the rolling pages survive.
        rows = self._search()
        titles = [r["title"] for r in rows]
        self.assertEqual(len(rows), 7)  # 5 API rows + court + pawnstars
        self.assertIn("RUSH CALLS", titles)
        self.assertIn("Pawn Stars Do America", titles)
        self.assertNotIn("March Madness Town Hall", titles)
        self.assertNotIn("Payroll", titles)

    def test_duplicate_campaign_pages_dedupe_to_newest(self) -> None:
        rows = self._search()
        court_rows = [r for r in rows if r["title"] == "Actors Wanted for Court TV"]
        self.assertEqual(len(court_rows), 1)
        # court/ was modified after court-2/, so it wins.
        self.assertEqual(court_rows[0]["url"], "https://standingroomonly.tv/court/")

    def test_contract_fields_on_every_row(self) -> None:
        rows = self._search()
        urls = [r["url"] for r in rows]
        self.assertEqual(len(urls), len(set(urls)))
        for row in rows:
            self.assertEqual(row["source"], "standingroomonly")
            self.assertEqual(row["vertical"], "camera")
            self.assertEqual(row["company"], "Standing Room Only")
            self.assertTrue(row["title"])
            self.assertTrue(row["url"])
            self.assertTrue(row.get("is_rolling") or row.get("event_start"))
            for key in _SALARY_KEYS:
                self.assertNotIn(key, row)
            self.assertNotIn("date_posted", row)

    def test_max_results_caps(self) -> None:
        self.assertEqual(len(self._search(max_results=3)), 3)

    def test_degrades_to_empty_when_both_endpoints_fail(self) -> None:
        with patch.object(self.mod, "_fetch_api_shows", return_value=[]):
            with patch.object(self.mod, "_fetch_pages", return_value=[]):
                self.assertEqual(self.mod.search_standingroomonly(), [])

    def test_fetchers_swallow_bad_payloads(self) -> None:
        for bad in (None, {}, {"shows": "nope"}, "nope"):
            with patch.object(self.mod, "_get_json", return_value=bad):
                self.assertEqual(self.mod._fetch_api_shows(), [])
                self.assertEqual(self.mod._fetch_pages(), [])


class RegistryTest(unittest.TestCase):
    def test_registered_as_camera_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.standingroomonly  # noqa: F401

        reg = get_registry()
        self.assertIn("standingroomonly", reg)
        meta = reg["standingroomonly"]
        self.assertEqual(meta.vertical, "camera")
        self.assertEqual(meta.category, "camera")
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))
        # Quest scrapers never join the default career sweep.
        self.assertNotIn("standingroomonly", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
