"""Contract tests for BuiltIn URL construction.

Bug: previously ``_build_search_url`` used ``?location=Los%20Angeles`` as the
city filter, but BuiltIn's website treats that query param as a soft hint —
results were dominated by other cities (e.g. searching LA returned mostly
Toronto). Their actual city filter is path-based: ``/jobs/los-angeles``.

These tests pin the URL shape so the bug can't silently come back.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


class BuiltInUrlTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers.builtin import _build_search_url
        self._build = _build_search_url

    def test_la_uses_path_slug_not_query_param(self) -> None:
        """The original bug: ``?location=Los Angeles`` returned Toronto jobs."""
        url = self._build(["data engineer"], ["Los Angeles, CA"], page=1, max_days_old=14)
        # Path slug must be present
        self.assertIn("/jobs/los-angeles", url)
        # Broken query-param filter must NOT appear
        self.assertNotIn("location=Los", url)
        self.assertNotIn("location=Los%20Angeles", url)
        # Search term + freshness still wired through
        self.assertIn("search=data%20engineer", url)
        self.assertIn("days_since_posted=", url)

    def test_multi_word_city_slug(self) -> None:
        url = self._build(["pm"], ["San Francisco, CA"], page=1, max_days_old=7)
        self.assertIn("/jobs/san-francisco", url)
        self.assertNotIn("location=", url)

    def test_known_cities_resolve_to_slug(self) -> None:
        """All BuiltIn-covered tech metros must produce the slug form."""
        cases = [
            ("Los Angeles, CA", "/jobs/los-angeles"),
            ("San Francisco, CA", "/jobs/san-francisco"),
            ("New York, NY", "/jobs/new-york"),
            ("Boston, MA", "/jobs/boston"),
            ("Seattle, WA", "/jobs/seattle"),
            ("Austin, TX", "/jobs/austin"),
            ("Chicago, IL", "/jobs/chicago"),
        ]
        for loc, expected in cases:
            with self.subTest(loc=loc):
                url = self._build(["engineer"], [loc], page=1, max_days_old=14)
                self.assertIn(expected, url)
                self.assertNotIn("?location=", url)

    def test_unknown_city_falls_back_to_query_param(self) -> None:
        """Cities BuiltIn doesn't have a slug for use the (best-effort) query."""
        url = self._build(["analyst"], ["Tulsa, OK"], page=1, max_days_old=14)
        self.assertNotIn("/jobs/tulsa", url)
        self.assertIn("location=Tulsa", url)

    def test_remote_preserved_as_working_option(self) -> None:
        url = self._build(["engineer"], ["Remote"], page=1, max_days_old=14)
        self.assertIn("working_option=2", url)
        self.assertNotIn("/jobs/remote", url)

    def test_first_known_city_wins_over_remote(self) -> None:
        """Mixed list: city slug filters more, so prefer it."""
        url = self._build(["engineer"], ["Remote", "Los Angeles, CA"], page=1, max_days_old=14)
        self.assertIn("/jobs/los-angeles", url)

    def test_no_location_uses_global_jobs_page(self) -> None:
        url = self._build(["engineer"], None, page=1, max_days_old=14)
        self.assertIn("/jobs?", url)
        self.assertNotIn("location=", url)

    def test_pagination_preserved_with_path_slug(self) -> None:
        url = self._build(["engineer"], ["Boston, MA"], page=3, max_days_old=30)
        self.assertIn("/jobs/boston", url)
        self.assertIn("page=3", url)


if __name__ == "__main__":
    unittest.main()
