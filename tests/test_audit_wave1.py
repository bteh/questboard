"""Wave 1: Critical bugs found in thorough audit.

1. max_days_old slider value dropped by pipeline_service
2. _extract_level "executive" keyword inflation
3. Source ranking missing ATS scrapers
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure the backend package is importable from tests
_BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
if os.path.isdir(_BACKEND_DIR) and _BACKEND_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND_DIR))


class MaxDaysOldTest(unittest.TestCase):
    """max_days_old from search UI must reach the pipeline, not be dropped."""

    @patch("app.services.pipeline_service.get_pipeline")
    @patch("app.services.pipeline_service._send_event")
    def test_max_days_old_passed_to_pipeline(self, mock_send, mock_get_pipeline):
        """When start_run receives max_days_old=3, the pipeline must use 3, not 14."""
        import asyncio

        from app.services.pipeline_service import start_run

        mock_pipeline = MagicMock()
        mock_pipeline.config = {"scoring": {"thresholds": {"strong_apply": 70}}}
        mock_pipeline.profile_name = "default"
        mock_pipeline.search_all_jobs.return_value = []
        mock_get_pipeline.return_value = mock_pipeline

        loop = asyncio.new_event_loop()
        try:
            run = start_run(
                roles=["data engineer"],
                locations=["Remote"],
                keywords=[],
                include_remote=True,
                max_days_old=3,
                use_ai=False,
                profile="default",
                mode="search_only",
                loop=loop,
            )
            # Wait for the background thread to finish
            import time
            for _ in range(50):
                if run.status in ("completed", "failed"):
                    break
                time.sleep(0.1)

            # The pipeline's search_all_jobs should have been called
            mock_pipeline.search_all_jobs.assert_called_once()
            # The pipeline's config must have been overridden with max_days_old=3
            self.assertEqual(
                mock_pipeline.config.get("search_settings", {}).get("max_days_old"),
                3,
                "max_days_old=3 must be written into pipeline.config['search_settings']",
            )
        finally:
            loop.close()


class ExtractLevelTest(unittest.TestCase):
    """_extract_level must not inflate titles containing 'executive'."""

    def _extract(self, title: str) -> float:
        from job_finder.pipeline import _extract_level
        return _extract_level(title)

    def test_account_executive_is_not_c_suite(self) -> None:
        """Account Executive should be ~2, not 7."""
        level = self._extract("Account Executive")
        self.assertLessEqual(level, 3.0)

    def test_sales_executive_is_not_c_suite(self) -> None:
        level = self._extract("Sales Executive")
        self.assertLessEqual(level, 3.0)

    def test_executive_assistant_is_not_c_suite(self) -> None:
        level = self._extract("Executive Assistant")
        self.assertLessEqual(level, 2.0)

    def test_chief_executive_officer_is_c_suite(self) -> None:
        """Actual C-suite titles should still score high."""
        level = self._extract("Chief Executive Officer")
        self.assertGreaterEqual(level, 7.0)

    def test_vp_still_high(self) -> None:
        level = self._extract("VP of Engineering")
        self.assertGreaterEqual(level, 6.0)

    def test_senior_data_engineer(self) -> None:
        level = self._extract("Senior Data Engineer")
        self.assertAlmostEqual(level, 3.0, delta=0.5)

    def test_staff_engineer(self) -> None:
        level = self._extract("Staff Data Engineer")
        self.assertAlmostEqual(level, 4.0, delta=0.5)


class SourceRankingTest(unittest.TestCase):
    """ATS scrapers should rank at least as high as Google in dedup."""

    def test_ats_sources_have_nonzero_rank(self) -> None:
        from job_finder.pipeline import _pick_best_job

        # Two identical jobs: one from Greenhouse (rich), one from Google (snippet)
        greenhouse_job = {
            "title": "Data Engineer",
            "company": "Stripe",
            "source": "greenhouse",
            "description": "Full description from Greenhouse API with lots of detail " * 20,
            "url": "https://boards.greenhouse.io/stripe/123",
            "salary_min": 180000,
            "salary_max": 220000,
        }
        google_job = {
            "title": "Data Engineer",
            "company": "Stripe",
            "source": "google",
            "description": "Short snippet",
            "url": "https://google.com/jobs/123",
        }

        best = _pick_best_job([greenhouse_job, google_job])
        # Greenhouse has richer data, should win
        self.assertEqual(best["source"], "greenhouse")

    def test_lever_beats_google(self) -> None:
        from job_finder.pipeline import _pick_best_job

        lever_job = {
            "title": "Data Engineer",
            "company": "Notion",
            "source": "lever",
            "description": "Detailed Lever posting " * 30,
            "url": "https://jobs.lever.co/notion/123",
        }
        google_job = {
            "title": "Data Engineer",
            "company": "Notion",
            "source": "google",
            "description": "Brief",
            "url": "https://google.com/jobs/456",
        }

        best = _pick_best_job([lever_job, google_job])
        self.assertEqual(best["source"], "lever")


if __name__ == "__main__":
    unittest.main()
