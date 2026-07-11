"""Contract tests for the UrbanSitter city-page scraper (lookafter kind).

Fixture is trimmed REAL __NEXT_DATA__ from
https://www.urbansitter.com/babysitting-jobs/il/chicago (captured live
2026-07-10, HTTP 200; two jobs kept with their real values, unrelated
props stripped). Pins: null booking.rate emits NO pay fields, a poster-set
rate maps to structured hourly figures, booking.start/end become
event_start/event_end, created becomes date_posted, and titles only
restate payload facts. No live HTTP inside tests.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURE = ROOT / "tests" / "fixtures" / "urbansitter_city.json"


def _wrap_next_data(payload: str) -> str:
    # the live tag verbatim: <script id="__NEXT_DATA__" type="application/json">
    return (
        "<html><body><div>page chrome</div>"
        f'<script id="__NEXT_DATA__" type="application/json">{payload}</script>'
        "</body></html>"
    )


class UrbansitterExtractTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import urbansitter as mod
        self.mod = mod
        self.payload = FIXTURE.read_text(encoding="utf-8")

    def test_extracts_jobs_from_next_data_script(self) -> None:
        jobs = self.mod._extract_jobs(_wrap_next_data(self.payload))
        self.assertEqual([j["id"] for j in jobs], [1469448, 1469286])

    def test_empty_html_returns_empty(self) -> None:
        self.assertEqual(self.mod._extract_jobs(""), [])

    def test_missing_script_tag_returns_empty(self) -> None:
        self.assertEqual(self.mod._extract_jobs("<html><body>nope</body></html>"), [])

    def test_bad_json_returns_empty(self) -> None:
        self.assertEqual(self.mod._extract_jobs(_wrap_next_data("{not json")), [])

    def test_payload_without_jobs_returns_empty(self) -> None:
        no_jobs = json.dumps({"props": {"pageProps": {"city": "chicago"}}})
        self.assertEqual(self.mod._extract_jobs(_wrap_next_data(no_jobs)), [])
        not_a_list = json.dumps({"props": {"pageProps": {"jobs": {"id": 1}}}})
        self.assertEqual(self.mod._extract_jobs(_wrap_next_data(not_a_list)), [])


class UrbansitterRowsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import urbansitter as mod
        self.mod = mod
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.jobs = data["props"]["pageProps"]["jobs"]

    def _search(self, jobs_by_call, city_paths, **kw) -> list[dict]:
        with patch.object(self.mod, "_fetch_city", side_effect=jobs_by_call), \
                patch.object(self.mod.time, "sleep"):
            return self.mod.search_urbansitter(city_paths=city_paths, **kw)

    def test_maps_rows_from_payload_facts(self) -> None:
        rows = self._search([self.jobs], ["il/chicago"])
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["title"], "Sitter for 3 children (6 years, 5 years, 3 years)")
        self.assertEqual(first["location"], "Deerfield, IL")
        self.assertEqual(first["url"], "https://www.urbansitter.com/job/1469448")
        self.assertEqual(first["date_posted"], "2026-07-09")
        self.assertEqual(first["event_start"], "2026-07-11T13:00:00")
        self.assertEqual(first["event_end"], "2026-07-11T21:00:00")
        self.assertEqual(first["company"], "Posted via UrbanSitter")
        self.assertEqual(first["source"], "urbansitter")
        for row in rows:
            self.assertEqual(row["vertical"], "lookafter")
            self.assertTrue(row["description"])

    def test_null_rate_emits_no_pay_fields(self) -> None:
        rows = self._search([self.jobs], ["il/chicago"])
        first = rows[0]  # booking.rate is null in the live payload
        for key in ("salary_min", "salary_max", "salary_period", "salary_source"):
            self.assertNotIn(key, first)

    def test_poster_set_rate_maps_to_hourly_reported(self) -> None:
        rows = self._search([self.jobs], ["il/chicago"])
        second = rows[1]  # booking.rate is 25 in the live payload
        self.assertEqual(second["salary_min"], 25.0)
        self.assertEqual(second["salary_max"], 25.0)
        self.assertEqual(second["salary_period"], "hourly")
        self.assertEqual(second["salary_source"], "reported")

    def test_recurring_is_tagged_never_hidden(self) -> None:
        rows = self._search([self.jobs], ["il/chicago"])
        self.assertEqual(rows[0]["quest"]["schedule"], "one_time")
        second = rows[1]
        self.assertEqual(second["quest"]["schedule"], "recurring")
        self.assertEqual(second["title"], "Recurring sitter for 1 child (7 months)")
        self.assertEqual(second["vertical"], "lookafter")
        self.assertNotIn("event_end", second)  # booking.end is null

    def test_dedupes_across_cities_by_job_url(self) -> None:
        rows = self._search([self.jobs, self.jobs], ["il/chicago", "ny/new-york"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r["url"] for r in rows}), 2)

    def test_max_results_cap(self) -> None:
        rows = self._search([self.jobs], ["il/chicago"], max_results=1)
        self.assertEqual(len(rows), 1)

    def test_empty_cities_return_empty(self) -> None:
        self.assertEqual(self._search([[], []], ["il/chicago", "ny/new-york"]), [])

    def test_sleeps_at_least_crawl_delay_between_cities(self) -> None:
        with patch.object(self.mod, "_fetch_city", return_value=list(self.jobs)), \
                patch.object(self.mod.time, "sleep") as mock_sleep:
            self.mod.search_urbansitter(city_paths=["il/chicago", "ny/new-york"])
        self.assertEqual(mock_sleep.call_count, 1)
        self.assertGreaterEqual(mock_sleep.call_args[0][0], 3)


class UrbansitterRegistryTest(unittest.TestCase):
    def test_registration_contract(self) -> None:
        import job_finder.tools.scrapers  # noqa: F401 (trigger auto-discovery)
        from job_finder.tools.scrapers._registry import default_scraper_names, get_registry

        meta = get_registry()["urbansitter"]
        self.assertEqual(meta.vertical, "lookafter")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertEqual(meta.stale_after_days, 7)
        self.assertEqual(meta.allowed_url_hosts, ("urbansitter.com",))
        self.assertFalse(meta.enabled_by_default)
        self.assertFalse(meta.research_only)
        self.assertNotIn("urbansitter", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
