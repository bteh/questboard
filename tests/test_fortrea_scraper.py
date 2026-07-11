"""Contract tests for the Fortrea Clinical Trials browse-table scraper (body kind).

Fixture is a trimmed REAL browse page from
https://www.fortreaclinicaltrials.com/en-us/clinical-research/browse-studies
(captured live 2026-07-10, HTTP 200; three table rows kept verbatim).
Pins: title composes population + protocol, the stated range maps to
min/max and "up to $X" to a ceiling only, extra stipend sentences ride
verbatim in quest.pay_note, the study window becomes event_start/end,
and no row ever carries date_posted (the site states none; the window
is the event, not the post date). No live HTTP inside tests.
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

FIXTURE = ROOT / "tests" / "fixtures" / "fortrea_studies.html"


class FortreaTest(unittest.TestCase):
    def setUp(self) -> None:
        from bs4 import BeautifulSoup
        from job_finder.tools.scrapers import fortrea as mod
        self.mod = mod
        soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")
        self.rows = soup.select("div.view-content table tbody tr")

    def _search(self, rows, **kw) -> list[dict]:
        with patch.object(self.mod, "_fetch_rows", return_value=rows):
            return self.mod.search_fortrea(**kw)

    def test_parses_table_into_body_rows(self) -> None:
        rows = self._search(self.rows)
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["vertical"], "body")
            self.assertEqual(row["company"], "Fortrea")
            self.assertTrue(
                row["url"].startswith("https://www.fortreaclinicaltrials.com/")
            )

    def test_title_composes_population_and_protocol(self) -> None:
        rows = self._search(self.rows)
        self.assertEqual(rows[0]["title"], "Healthy Adults, age 18-55 needed (781667)")
        # entity unescapes; the protocol group suffix is kept as stated
        self.assertEqual(
            rows[2]["title"],
            "Healthy Men & Women of Non-childbearing potential, "
            "age 18-65 needed. (781681 4)",
        )
        self.assertEqual(rows[2]["quest"]["protocol"], "781681 4")

    def test_url_location_and_regimen(self) -> None:
        rows = self._search(self.rows)
        self.assertEqual(
            rows[1]["url"],
            "https://www.fortreaclinicaltrials.com/en-us/clinical-research/"
            "781667-healthy-adults-18-55-see-if-you-qualify",
        )
        self.assertEqual(rows[0]["location"], "Daytona Beach, Florida")
        self.assertEqual(rows[1]["location"], "Madison, Wisconsin")
        self.assertEqual(
            rows[0]["description"], "1 stay of 2 nights & 9-11 follow-up visits"
        )

    def test_study_window_maps_to_event_dates(self) -> None:
        rows = self._search(self.rows)
        self.assertEqual(rows[0]["event_start"], "2026-07-19")
        self.assertEqual(rows[0]["event_end"], "2026-11-16")
        self.assertEqual(rows[2]["event_end"], "2027-01-21")

    def test_range_pay_maps_to_min_max_with_verbatim_note(self) -> None:
        rows = self._search(self.rows)
        self.assertEqual(rows[0]["salary_min"], 12941.0)
        self.assertEqual(rows[0]["salary_max"], 14289.0)
        self.assertEqual(rows[0]["salary_source"], "reported")
        self.assertEqual(
            rows[0]["quest"]["pay_note"],
            "Stipend now includes $100 per follow-up visit for travel assistance",
        )
        # same note without the period after the range (row 2 as captured)
        self.assertEqual(rows[1]["salary_min"], 12041.0)
        self.assertEqual(rows[1]["salary_max"], 13189.0)
        self.assertEqual(
            rows[1]["quest"]["pay_note"],
            "Stipend now includes $100 per follow-up visit for travel assistance",
        )

    def test_single_amount_sets_min_and_max(self) -> None:
        rows = self._search(self.rows)
        self.assertEqual(rows[2]["salary_min"], 14836.0)
        self.assertEqual(rows[2]["salary_max"], 14836.0)
        self.assertNotIn("pay_note", rows[2]["quest"])

    def test_up_to_maps_to_ceiling_only(self) -> None:
        fields, note = self.mod._parse_compensation("Up to $5,000 for time and travel")
        self.assertEqual(fields["salary_max"], 5000.0)
        self.assertEqual(fields["salary_source"], "reported")
        self.assertNotIn("salary_min", fields)
        self.assertEqual(note, "for time and travel")

    def test_unparseable_pay_emits_no_salary_keys(self) -> None:
        fields, note = self.mod._parse_compensation("Compensation varies by cohort")
        self.assertEqual(fields, {})
        self.assertEqual(note, "Compensation varies by cohort")

    def test_no_date_posted_key_ever(self) -> None:
        for row in self._search(self.rows):
            self.assertNotIn("date_posted", row)

    def test_max_results_cap(self) -> None:
        self.assertEqual(len(self._search(self.rows, max_results=2)), 2)

    def test_empty_table_returns_empty(self) -> None:
        self.assertEqual(self._search([]), [])


class FortreaFetchTest(unittest.TestCase):
    """The fetch asks the US browse URL for HTML and degrades to [] on
    bad HTML or a network failure; nothing raises."""

    def setUp(self) -> None:
        from job_finder.tools.scrapers import fortrea as mod
        self.mod = mod

    def _resp(self, body: str):
        class _R:
            text = body
            def raise_for_status(self) -> None:
                return None
        return _R()

    def test_fetches_us_browse_page_as_html(self) -> None:
        captured: dict = {}

        def fake_get(url, headers=None, timeout=None):
            captured["url"] = url
            captured["accept"] = (headers or {}).get("Accept", "")
            return self._resp("<html></html>")

        with patch.object(self.mod.requests, "get", side_effect=fake_get):
            rows = self.mod._fetch_rows()
        self.assertEqual(
            captured["url"],
            "https://www.fortreaclinicaltrials.com/en-us/clinical-research/browse-studies",
        )
        self.assertIn("en-us", captured["url"])  # never the en-gb variant
        self.assertEqual(captured["accept"], "text/html")
        self.assertEqual(rows, [])

    def test_tableless_html_returns_empty(self) -> None:
        with patch.object(
            self.mod.requests, "get",
            return_value=self._resp("<html><p>Down for maintenance</p></html>"),
        ):
            self.assertEqual(self.mod._fetch_rows(), [])

    def test_network_failure_returns_empty(self) -> None:
        with patch.object(
            self.mod.requests, "get", side_effect=Exception("connection reset")
        ):
            self.assertEqual(self.mod._fetch_rows(), [])


class FortreaRegistryTest(unittest.TestCase):
    def test_registration_contract(self) -> None:
        from job_finder.tools.scrapers import fortrea  # noqa: F401  (registers)
        from job_finder.tools.scrapers._registry import (
            default_scraper_names,
            get_registry,
        )

        meta = get_registry()["fortrea"]
        self.assertEqual(meta.display_name, "Fortrea Clinical Trials")
        self.assertEqual(meta.vertical, "body")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertTrue(meta.full_snapshot)
        self.assertIsNone(meta.stale_after_days)
        self.assertEqual(meta.allowed_url_hosts, ("fortreaclinicaltrials.com",))
        self.assertFalse(meta.enabled_by_default)
        self.assertFalse(meta.research_only)
        # body lane, never swept into the career pipeline
        self.assertNotIn("fortrea", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
