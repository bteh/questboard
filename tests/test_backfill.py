"""Tests for DB score backfill mechanism (Issue #6).

Verifies that unscored records (NULL overall_score) can be backfilled
with keyword scores without re-running the full pipeline.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from job_finder.models import database
from job_finder.models.database import ApplicationRecord


class BackfillScoresTest(unittest.TestCase):
    """Test the backfill_scores function in database.py."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        database.init_db(os.path.join(self.tmpdir.name, "job_tracker.db"))

    def tearDown(self) -> None:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()
        self.tmpdir.cleanup()

    def test_backfill_scores_unscored_jobs(self) -> None:
        """Unscored records should receive scores after backfill."""
        # Create unscored records (search_only mode saves with NULL scores)
        database.save_application(
            job_title="Software Engineer",
            company="Acme Corp",
            location="San Francisco, CA",
            job_url="https://example.com/acme-swe",
            description="Build Python microservices with AWS and Docker.",
            profile="test",
        )
        database.save_application(
            job_title="Data Engineer",
            company="Beta Inc",
            location="Remote",
            job_url="https://example.com/beta-de",
            description="Design data pipelines using Spark and SQL.",
            profile="test",
        )

        # Verify they start with no scores
        all_apps = database.get_all_applications(profile="test")
        for app in all_apps:
            self.assertIsNone(app.overall_score)

        # Run backfill with a mock resume
        fake_resume = "Experienced software engineer with Python, AWS, SQL, Docker."
        with patch(
            "job_finder.tools.resume_parser_tool.parse_resume",
            return_value=fake_resume,
        ):
            count = database.backfill_scores(profile="test")

        # Verify scores were assigned
        self.assertEqual(count, 2)
        scored_apps = database.get_all_applications(profile="test")
        for app in scored_apps:
            self.assertIsNotNone(app.overall_score)
            self.assertGreater(app.overall_score, 0)
            self.assertIsNotNone(app.recommendation)
            self.assertIn(app.recommendation, ("STRONG_APPLY", "APPLY", "MAYBE", "SKIP"))

    def test_backfill_skips_already_scored(self) -> None:
        """Records that already have scores should not be re-scored."""
        # Create a scored record
        database.save_application(
            job_title="Frontend Engineer",
            company="Gamma LLC",
            location="New York, NY",
            job_url="https://example.com/gamma-fe",
            description="React and TypeScript development.",
            overall_score=75.0,
            technical_score=80.0,
            leadership_score=50.0,
            platform_building_score=40.0,
            comp_potential_score=60.0,
            company_trajectory_score=55.0,
            culture_fit_score=65.0,
            career_progression_score=70.0,
            recommendation="APPLY",
            profile="test",
        )
        # Create an unscored record
        database.save_application(
            job_title="Backend Engineer",
            company="Delta Co",
            location="Remote",
            job_url="https://example.com/delta-be",
            description="Python and PostgreSQL backend services.",
            profile="test",
        )

        fake_resume = "Senior backend engineer with Python, PostgreSQL, Docker."
        with patch(
            "job_finder.tools.resume_parser_tool.parse_resume",
            return_value=fake_resume,
        ):
            count = database.backfill_scores(profile="test")

        # Only the unscored record should have been scored
        self.assertEqual(count, 1)

        # Verify the already-scored record was not changed
        all_apps = database.get_all_applications(profile="test")
        gamma = [a for a in all_apps if a.company == "Gamma LLC"][0]
        self.assertEqual(gamma.overall_score, 75.0)
        self.assertEqual(gamma.technical_score, 80.0)
        self.assertEqual(gamma.recommendation, "APPLY")

    def test_backfill_returns_count(self) -> None:
        """backfill_scores should return the number of records scored."""
        # No unscored records → 0
        fake_resume = "Some resume text."
        with patch(
            "job_finder.tools.resume_parser_tool.parse_resume",
            return_value=fake_resume,
        ):
            count = database.backfill_scores(profile="test")
        self.assertEqual(count, 0)

        # Add 3 unscored records
        for i in range(3):
            database.save_application(
                job_title=f"Engineer {i}",
                company=f"Company {i}",
                job_url=f"https://example.com/job-{i}",
                description=f"Python developer role number {i}.",
                profile="test",
            )

        with patch(
            "job_finder.tools.resume_parser_tool.parse_resume",
            return_value=fake_resume,
        ):
            count = database.backfill_scores(profile="test")
        self.assertEqual(count, 3)

    def test_backfill_continues_on_error(self) -> None:
        """If scoring one record fails, others should still be scored."""
        database.save_application(
            job_title="Good Job",
            company="Good Co",
            job_url="https://example.com/good",
            description="Python engineer role.",
            profile="test",
        )
        database.save_application(
            job_title="Bad Job",
            company="Bad Co",
            job_url="https://example.com/bad",
            description="",  # empty description — should still not crash
            profile="test",
        )

        fake_resume = "Python developer with experience."
        with patch(
            "job_finder.tools.resume_parser_tool.parse_resume",
            return_value=fake_resume,
        ):
            count = database.backfill_scores(profile="test")

        # Both should be scored (empty description gets low score but doesn't crash)
        self.assertEqual(count, 2)

    def test_backfill_uses_progress_callback(self) -> None:
        """Progress callback should be called during backfill."""
        database.save_application(
            job_title="DevOps Engineer",
            company="Infra Inc",
            job_url="https://example.com/devops",
            description="Kubernetes and Terraform.",
            profile="test",
        )

        messages: list[str] = []
        fake_resume = "DevOps engineer with Kubernetes and Terraform."
        with patch(
            "job_finder.tools.resume_parser_tool.parse_resume",
            return_value=fake_resume,
        ):
            database.backfill_scores(
                profile="test",
                progress=messages.append,
            )

        self.assertTrue(len(messages) > 0, "Progress callback should have been called")


if __name__ == "__main__":
    unittest.main()
