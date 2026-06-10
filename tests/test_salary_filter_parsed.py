"""Parsed-from-description salaries must flow through the salary filter
and salary_source provenance must survive to the DB record.

Before: scrapers parsed salaries out of descriptions (with salary_source
stamped), but JobSpy jobs never passed through finalize_scraper_jobs, and
the ApplicationRecord had no salary_source column — so provenance died at
the DB boundary and a parsed $60k job could survive a $150k floor.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from job_finder.pipeline import _job_salary_passes
from job_finder.tools.scrapers._utils import finalize_scraper_jobs


class ParsedSalaryFlowsThroughFilterTest(unittest.TestCase):
    def test_parsed_below_floor_is_dropped(self) -> None:
        job = {
            "title": "Engineer",
            "description": "Compensation: $55,000 - $65,000 per year plus benefits.",
        }
        finalize_scraper_jobs([job])
        self.assertEqual(job["salary_source"], "parsed_from_description")
        self.assertFalse(_job_salary_passes(job, 150000))

    def test_parsed_above_floor_passes(self) -> None:
        job = {
            "title": "Engineer",
            "description": "Pay range $160,000 - $190,000 a year.",
        }
        finalize_scraper_jobs([job])
        self.assertEqual(job["salary_source"], "parsed_from_description")
        self.assertTrue(_job_salary_passes(job, 150000))

    def test_unknown_salary_still_kept(self) -> None:
        job = {"title": "Engineer", "description": "We pay competitively."}
        finalize_scraper_jobs([job])
        self.assertIsNone(job["salary_source"])
        self.assertTrue(_job_salary_passes(job, 150000))

    def test_reported_salary_keeps_reported_source(self) -> None:
        job = {"title": "Engineer", "salary_min": 100000.0, "salary_max": 120000.0}
        finalize_scraper_jobs([job])
        self.assertEqual(job["salary_source"], "reported")


class SalarySourceRoundTripsToDbTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.models import database

        self.database = database
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "job_tracker.db")
        database.init_db(self.db_path)

    def tearDown(self) -> None:
        if self.database._SessionLocal is not None:
            self.database._SessionLocal.remove()
        self.tmpdir.cleanup()

    def test_salary_source_round_trips(self) -> None:
        rec = self.database.save_application(
            job_title="Data Engineer",
            company="Acme",
            job_url="https://example.com/jobs/1",
            salary_min=60000.0,
            salary_max=70000.0,
            salary_source="parsed_from_description",
        )
        self.assertIsNotNone(rec)
        fetched = self.database.get_all_applications()[0]
        self.assertEqual(fetched.salary_source, "parsed_from_description")

    def test_salary_source_defaults_to_none(self) -> None:
        self.database.save_application(
            job_title="Data Engineer",
            company="Acme",
            job_url="https://example.com/jobs/2",
        )
        fetched = self.database.get_all_applications()[0]
        self.assertIsNone(fetched.salary_source)

    def test_migrate_db_adds_salary_source_to_legacy_table(self) -> None:
        from sqlalchemy import inspect, text

        engine = self.database._engine
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE applications DROP COLUMN salary_source"))
        cols = {c["name"] for c in inspect(engine).get_columns("applications")}
        self.assertNotIn("salary_source", cols)

        self.database.init_db(self.db_path)  # re-running migration restores it
        cols = {
            c["name"]
            for c in inspect(self.database._engine).get_columns("applications")
        }
        self.assertIn("salary_source", cols)


if __name__ == "__main__":
    unittest.main()
