"""Re-scraping an existing job should refresh its classification.

Bug: ``save_application`` matched an existing record by ``job_url`` and only
stamped ``search_run_id`` — it never refreshed ``company_type``. So once the
source-based startup tagging shipped, jobs first seen earlier stayed "Unknown"
forever across re-runs, drowning out correctly-tagged new jobs. Re-scrapes must
pick up an improved classification, but must NOT downgrade a good tier to
"Unknown" (e.g. when a later scrape lacks the source signal).
"""
from __future__ import annotations

import os
import tempfile
import unittest

from job_finder.models import database


class RescrapeRefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        database.init_db(os.path.join(self.tmpdir.name, "job_tracker.db"))

    def tearDown(self) -> None:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()
        self.tmpdir.cleanup()

    def _save(self, url: str, company_type: str):
        return database.save_application(
            job_title="Lead Data Engineer",
            company="Tiny Startup Co",
            location="Remote",
            job_url=url,
            profile="x",
            company_type=company_type,
        )

    def test_rescrape_refreshes_unknown_to_startup(self) -> None:
        url = "https://builtin.com/job/1"
        self._save(url, "Unknown")
        rec = self._save(url, "Early Startup")  # re-scrape, now source-tagged
        self.assertEqual(rec.company_type, "Early Startup")

    def test_rescrape_does_not_downgrade_good_tier_to_unknown(self) -> None:
        url = "https://builtin.com/job/2"
        self._save(url, "Elite Startup")
        rec = self._save(url, "Unknown")  # re-scrape missing the signal
        self.assertEqual(rec.company_type, "Elite Startup")

    def test_rescrape_upgrades_between_known_tiers(self) -> None:
        url = "https://builtin.com/job/3"
        self._save(url, "Growth Stage")
        rec = self._save(url, "Elite Startup")
        self.assertEqual(rec.company_type, "Elite Startup")
