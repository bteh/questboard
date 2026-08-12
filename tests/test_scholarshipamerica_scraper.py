"""Contract tests for the Scholarship America scholarship feed.

The fixture shape is trimmed from the public WordPress API as observed on
2026-08-05.  The site's Open taxonomy contained past-deadline records, so the
tests pin the independent application-window checks rather than trusting the
taxonomy label.
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

FROZEN_NOW = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)


def _record(
    *,
    title: str = "Howard Hughes Communities™ Scholarship Program",
    link: str = "https://scholarshipamerica.org/scholarship/howardhughes/",
    opened: str = "July 30, 2026 6:00 AM",
    closes: str = "September 3, 2026 3:00 PM",
    award: str = "$5,000",
    status: object = True,
    states: list[int] | None = None,
) -> dict:
    return {
        "id": 34524,
        "link": link,
        "title": {"rendered": title},
        "state": states if states is not None else [146, 40],
        "acf": {
            "scholarship_details_application_status": status,
            "scholarship_details_open_date_time": {
                "date_time": opened,
                "timezone_timezone_select_timezone": "America/Chicago",
            },
            "scholarship_details_close_date_time": {
                "date_time": closes,
                "timezone_timezone_select_timezone": "America/Chicago",
            },
            "scholarship_details_award_amount": award,
            "scholarship_details_hero_description": (
                "<p>Three renewable scholarships for students in participating communities.</p>"
            ),
            "scholarship_content_eligibility": {
                "content": [
                    {
                        "acf_fc_layout": "wysiwyg_basic",
                        "wysiwyg": (
                            "<p>Applicants must be high school seniors or current college "
                            "undergraduates with a 3.0 GPA.</p>"
                        ),
                    }
                ]
            },
            "scholarship_content_requirements": {
                "content": "<p>Upload a current transcript and financial information.</p>"
            },
        },
    }


STATE_TERMS = [
    {"id": 146, "name": "Arizona", "slug": "arizona"},
    {"id": 40, "name": "Texas", "slug": "texas"},
    {"id": 20, "name": "National", "slug": "national"},
]


class ScholarshipAmericaTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import scholarshipamerica as mod

        self.mod = mod

    def _search(self, records: object, **kwargs) -> list[dict]:
        with patch.object(
            self.mod, "_get_json", side_effect=[records, STATE_TERMS]
        ), patch.object(self.mod, "_utcnow", return_value=FROZEN_NOW):
            return self.mod.search_scholarshipamerica(**kwargs)

    def test_current_record_maps_to_an_actionable_scholarship(self) -> None:
        rows = self._search([_record()])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["vertical"], "scholarship")
        self.assertEqual(row["source"], "scholarshipamerica")
        self.assertEqual(row["location"], "Arizona; Texas")
        self.assertEqual(row["date_posted"], "2026-07-30")
        self.assertEqual(row["quest"]["apply_by"], "2026-09-03")
        self.assertEqual(row["quest"]["application_effort"], "involved")
        self.assertTrue(row["quest"]["application_effort_note"])
        self.assertTrue(row["quest"]["criteria"])
        self.assertEqual(row["salary_min"], 5000.0)
        self.assertEqual(row["salary_max"], 5000.0)
        self.assertIn("current transcript", row["quest"]["bring"])
        self.assertNotIn("wysiwyg", row["description"])

    def test_stale_taxonomy_record_drops_by_its_real_deadline(self) -> None:
        # This row still arrived from the API's Open query on Aug 5 even though
        # its application_status flag was true and it closed July 20.
        stale = _record(
            title="Pega Scholars Program",
            link="https://scholarshipamerica.org/scholarship/pegascholars/",
            opened="June 15, 2026 6:00 AM",
            closes="July 20, 2026 3:00 PM",
            award="$2,000",
        )
        self.assertEqual(self._search([stale]), [])

    def test_future_and_inactive_applications_drop(self) -> None:
        future = _record(
            opened="August 15, 2026 6:00 AM",
            closes="October 15, 2026 3:00 PM",
        )
        inactive = _record(status=False)
        self.assertEqual(self._search([future, inactive]), [])

    def test_umbrella_window_drops_instead_of_guessing_subperiods(self) -> None:
        umbrella = _record(
            title="The Families of Freedom Scholarship Fund",
            link="https://scholarshipamerica.org/scholarship/familiesoffreedom/",
            opened="May 5, 2025 6:00 AM",
            closes="August 5, 2030 3:00 PM",
            award="",
            states=[20],
        )
        self.assertEqual(self._search([umbrella]), [])

    def test_award_shapes_never_invent_a_floor_or_ceiling(self) -> None:
        fields, note = self.mod._award_fields("$2,500 - $5,000")
        self.assertEqual(fields["salary_min"], 2500.0)
        self.assertEqual(fields["salary_max"], 5000.0)
        self.assertIsNone(note)

        fields, note = self.mod._award_fields("Up to $5,000")
        self.assertNotIn("salary_min", fields)
        self.assertEqual(fields["salary_max"], 5000.0)
        self.assertIsNone(note)

        fields, note = self.mod._award_fields("At least $5,000")
        self.assertEqual(fields["salary_min"], 5000.0)
        self.assertNotIn("salary_max", fields)
        self.assertIsNone(note)

        fields, note = self.mod._award_fields("$5,000 renewable for four years")
        self.assertEqual(fields, {})
        self.assertEqual(note, "$5,000 renewable for four years")

    def test_national_taxonomy_becomes_reachable_us_location(self) -> None:
        row = self._search([_record(states=[20])])[0]
        self.assertEqual(row["location"], "United States")

    def test_query_uses_public_open_and_visible_taxonomies(self) -> None:
        calls: list[tuple[str, dict]] = []

        # Explicit side effect keeps the assertion independent of URL tricks.
        with patch.object(
            self.mod,
            "_get_json",
            side_effect=lambda url, params=None, **kw: (
                calls.append((url, dict(params or {})))
                or ([_record()] if url == self.mod._API_URL else STATE_TERMS)
            ),
        ), patch.object(self.mod, "_utcnow", return_value=FROZEN_NOW):
            self.mod.search_scholarshipamerica()

        scholarship_params = calls[0][1]
        self.assertEqual(scholarship_params["scholarship-status"], 250)
        self.assertEqual(scholarship_params["listing-status"], 246)
        self.assertEqual(scholarship_params["per_page"], 100)

    def test_bad_payload_and_bad_url_return_empty(self) -> None:
        for bad in (None, {}, "x", 42):
            self.assertEqual(self._search(bad), [])
        self.assertEqual(
            self._search([_record(link="https://example.com/not-the-sponsor-page")]),
            [],
        )

    def test_max_results_caps_rows(self) -> None:
        second = _record(
            title="Second scholarship",
            link="https://scholarshipamerica.org/scholarship/second/",
        )
        self.assertEqual(len(self._search([_record(), second], max_results=1)), 1)


class ScholarshipAmericaRegistryTest(unittest.TestCase):
    def test_registered_as_daily_full_snapshot(self) -> None:
        from job_finder.tools.scrapers import get_registry
        from job_finder.tools.scrapers._registry import default_scraper_names

        meta = get_registry()["scholarshipamerica"]
        self.assertEqual(meta.vertical, "scholarship")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertTrue(meta.full_snapshot)
        self.assertEqual(meta.allowed_url_hosts, ("scholarshipamerica.org",))
        self.assertNotIn("scholarshipamerica", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
