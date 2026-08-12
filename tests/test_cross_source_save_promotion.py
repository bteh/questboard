"""Cross-source persistence keeps the live official application target."""

from __future__ import annotations

import os
import tempfile
import unittest

from job_finder.models import database


class CrossSourceSavePromotionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        database.init_db(os.path.join(self.tmpdir.name, "job_tracker.db"))

    def tearDown(self) -> None:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()
        self.tmpdir.cleanup()

    def test_live_official_url_replaces_dead_aggregator_in_place(self) -> None:
        description = (
            "Lead a data engineering team, own the data platform, production "
            "pipelines, architecture, and people development."
        )
        old = database.save_application(
            job_title="Senior Data Engineering Manager",
            company="YipitData",
            location="US Remote",
            job_url="https://builtin.com/job/senior-data-engineering-manager/9686694",
            source="builtin",
            description=description,
            is_remote=True,
            salary_max=215000,
            date_posted="2026-07-18",
            date_confidence="exact",
            search_run_id="old-run",
        )
        session = database.get_session()
        stored = session.query(database.ApplicationRecord).filter_by(id=old.id).one()
        stored.url_status = "dead"
        session.commit()

        refreshed = database.save_application(
            job_title="Senior Data Engineering Manager",
            company="Yipitdata",
            location="US Remote",
            job_url="https://job-boards.greenhouse.io/yipitdata/jobs/8080900",
            source="greenhouse",
            description=description + " Apply directly with the employer.",
            is_remote=True,
            date_posted="2026-07-22T23:59:42-04:00",
            date_confidence="exact",
            search_run_id="new-run",
        )

        self.assertEqual(refreshed.id, old.id)
        self.assertEqual(database.get_session().query(database.ApplicationRecord).count(), 1)
        self.assertEqual(refreshed.source, "greenhouse")
        self.assertEqual(
            refreshed.job_url,
            "https://job-boards.greenhouse.io/yipitdata/jobs/8080900",
        )
        self.assertEqual(refreshed.url_status, "unknown")
        self.assertEqual(refreshed.salary_max, 215000)
        self.assertEqual(refreshed.date_posted, "2026-07-22T23:59:42-04:00")
        self.assertEqual(refreshed.search_run_id, "new-run")
        self.assertEqual(refreshed.first_seen_run_id, "old-run")

    def test_same_company_and_title_in_distinct_cities_remain_separate(self) -> None:
        first = database.save_application(
            job_title="Data Engineering Manager",
            company="Acme",
            location="Los Angeles, CA",
            job_url="https://www.linkedin.com/jobs/view/1",
            source="linkedin",
            description="Lead the Los Angeles data engineering organization.",
        )
        second = database.save_application(
            job_title="Data Engineering Manager",
            company="Acme",
            location="New York, NY",
            job_url="https://job-boards.greenhouse.io/acme/jobs/2",
            source="greenhouse",
            description="Lead the New York data engineering organization.",
        )

        self.assertNotEqual(second.id, first.id)
        self.assertEqual(database.get_session().query(database.ApplicationRecord).count(), 2)


if __name__ == "__main__":
    unittest.main()
