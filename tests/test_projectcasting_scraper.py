"""Contract tests for the Project Casting scraper (camera vertical).

The fixture feed is a trimmed copy of the real WordPress RSS payload
(fetched live 2026-07-07): two casting-call articles, one with two real
/job/ deep links in its body, one entertainment-news article that must be
filtered out. The job-page fixture carries the real JSON-LD JobPosting
block from projectcasting.com/job/slip-casting-call-for-kid-actors,
including the site's baseSalary-value-0 quirk (structured pay left blank).
All HTTP is mocked; no live calls.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FEED_XML = (ROOT / "tests" / "fixtures" / "projectcasting_feed.xml").read_text(encoding="utf-8")
JOB_HTML = (ROOT / "tests" / "fixtures" / "projectcasting_job.html").read_text(encoding="utf-8")

_KID_ACTORS_URL = "https://projectcasting.com/job/slip-casting-call-for-kid-actors"
_GOLFERS_URL = "https://projectcasting.com/job/slip-casting-call-for-real-golfers"


class ProjectCastingSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import projectcasting as mod
        self.mod = mod

    def _search(
        self,
        job_pages: dict[str, str] | None = None,
        now: datetime | None = None,
        **kw,
    ) -> list[dict]:
        pages = job_pages if job_pages is not None else {_KID_ACTORS_URL: JOB_HTML}
        # Frozen before the fixture posting's 2026-06-13 validThrough so the
        # enriched row counts as live.
        frozen = now or datetime(2026, 6, 1, tzinfo=timezone.utc)
        with patch.object(self.mod, "_fetch_feed", return_value=FEED_XML):
            with patch.object(self.mod, "_fetch_job_page", side_effect=pages.get):
                with patch.object(self.mod, "_utcnow", return_value=frozen):
                    return self.mod.search_projectcasting(**kw)

    def test_news_items_are_filtered_out(self) -> None:
        rows = self._search()
        titles = " ".join(r["title"] for r in rows)
        self.assertNotIn("Finn Wolfhard", titles)

    def test_one_row_per_job_deep_link(self) -> None:
        rows = self._search()
        # SLIP article carries 2 /job/ links -> 2 rows. Intel Pink and
        # Lizard Music carry none -> no rows at all: an article is not a
        # casting call (a scam-alert blog post reached the live board
        # through the old article fallback, 2026-07-10).
        self.assertEqual(len(rows), 2)
        urls = [r["url"] for r in rows]
        self.assertIn(_KID_ACTORS_URL, urls)
        self.assertIn(_GOLFERS_URL, urls)

    def test_contract_fields_on_every_row(self) -> None:
        for r in self._search():
            self.assertTrue(r["title"])
            self.assertTrue(r["company"])
            self.assertTrue(r["url"])
            self.assertEqual(r["source"], "projectcasting")
            self.assertEqual(r["vertical"], "camera")
            self.assertIn("description", r)
            self.assertIn("location", r)

    def test_enriched_row_uses_json_ld_facts(self) -> None:
        rows = self._search()
        row = next(r for r in rows if r["url"] == _KID_ACTORS_URL)
        self.assertEqual(row["title"], '"SLIP" Casting Call for Kid Actors')
        self.assertEqual(row["company"], "Waldron Casting")
        self.assertEqual(row["location"], "New York, United States")
        self.assertEqual(row["date_posted"], "2026-05-14")
        self.assertIn("Sleepy Hollow", row["description"])
        self.assertEqual(row["quest"]["apply_by"], "2026-06-13T00:00")

    def test_zero_base_salary_never_becomes_pay(self) -> None:
        # The real page states $187 in prose but baseSalary value is 0:
        # structured pay was left blank, so no salary fields may appear.
        rows = self._search()
        row = next(r for r in rows if r["url"] == _KID_ACTORS_URL)
        self.assertNotIn("salary_min", row)
        self.assertNotIn("salary_max", row)
        self.assertNotIn("salary_source", row)

    def test_background_call_is_first_quest_ok(self) -> None:
        rows = self._search()
        row = next(r for r in rows if r["url"] == _KID_ACTORS_URL)
        self.assertTrue(row["first_quest_ok"])

    def test_unenriched_job_row_degrades_to_slug_title(self) -> None:
        rows = self._search()
        row = next(r for r in rows if r["url"] == _GOLFERS_URL)
        self.assertEqual(row["title"], "Slip Casting Call for Real Golfers")
        self.assertEqual(row["company"], "Project Casting")
        self.assertNotIn("first_quest_ok", row)

    def test_article_without_job_link_produces_no_row(self) -> None:
        # Every row must point at a /job/ page. An article with no deep
        # link is journalism, not a posting; it gets no row, never a
        # fallback row pointing at itself.
        rows = self._search()
        for r in rows:
            self.assertIn("/job/", r["url"])
        self.assertFalse(any("intel-pink" in r["url"] for r in rows))

    def test_expired_deadline_drops_row(self) -> None:
        # Past the fixture posting's validThrough: the enriched row must go,
        # rows without a stated deadline must stay.
        rows = self._search(now=datetime(2026, 7, 1, tzinfo=timezone.utc))
        urls = [r["url"] for r in rows]
        self.assertNotIn(_KID_ACTORS_URL, urls)
        self.assertIn(_GOLFERS_URL, urls)
        self.assertEqual(len(rows), 1)

    def test_max_results_caps_rows(self) -> None:
        rows = self._search(max_results=1)
        self.assertEqual(len(rows), 1)

    def test_bad_feed_returns_empty(self) -> None:
        for bad in (None, "", "not xml <"):
            with patch.object(self.mod, "_fetch_feed", return_value=bad):
                self.assertEqual(self.mod.search_projectcasting(), [])


class ProjectCastingSalaryTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import projectcasting as mod
        self.mod = mod

    def test_zero_value_is_not_stated(self) -> None:
        posting = {"baseSalary": {"value": {"value": "0", "unitText": "HOUR"}}}
        self.assertEqual(self.mod._ld_salary(posting), (None, None, None))

    def test_stated_single_value(self) -> None:
        posting = {"baseSalary": {"value": {"value": "187", "unitText": "DAY"}}}
        self.assertEqual(self.mod._ld_salary(posting), (187.0, 187.0, "daily"))

    def test_stated_range(self) -> None:
        posting = {"baseSalary": {"value": {"minValue": 150, "maxValue": 200, "unitText": "DAY"}}}
        self.assertEqual(self.mod._ld_salary(posting), (150.0, 200.0, "daily"))

    def test_missing_base_salary(self) -> None:
        self.assertEqual(self.mod._ld_salary({}), (None, None, None))


class ProjectCastingJsonLdTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import projectcasting as mod
        self.mod = mod

    def test_finds_job_posting_among_other_blocks(self) -> None:
        posting = self.mod._find_job_posting(JOB_HTML)
        self.assertIsNotNone(posting)
        self.assertEqual(posting["hiringOrganization"]["name"], "Waldron Casting")

    def test_no_posting_returns_none(self) -> None:
        html = '<script type="application/ld+json">{"@type": "BreadcrumbList"}</script>'
        self.assertIsNone(self.mod._find_job_posting(html))

    def test_invalid_json_is_skipped(self) -> None:
        html = '<script type="application/ld+json">{nope}</script>'
        self.assertIsNone(self.mod._find_job_posting(html))


class ProjectCastingRegistryTest(unittest.TestCase):
    def test_registered_as_camera_quest_source(self) -> None:
        from job_finder.tools.scrapers import get_registry
        import job_finder.tools.scrapers.projectcasting  # noqa: F401
        reg = get_registry()
        self.assertIn("projectcasting", reg)
        meta = reg["projectcasting"]
        self.assertEqual(meta.vertical, "camera")
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))

    def test_not_in_career_default_sweep(self) -> None:
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.projectcasting  # noqa: F401
        self.assertNotIn("projectcasting", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
