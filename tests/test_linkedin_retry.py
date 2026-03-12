"""Tests for LinkedIn backfill retry logic (Issue #7).

Verifies that _backfill_linkedin_descriptions retries on transient
failures (rate limiting, network errors) and gives up gracefully
after max retries.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock


class LinkedInBackfillRetryTest(unittest.TestCase):
    """Test retry behaviour in _backfill_linkedin_descriptions."""

    def test_linkedin_backfill_retries_on_failure(self) -> None:
        """When a fetch fails once then succeeds, the retry should populate the description."""
        from job_finder.pipeline import _backfill_linkedin_descriptions

        jobs = [
            {
                "title": "Software Engineer",
                "company": "Acme",
                "url": "https://linkedin.com/jobs/view/12345",
                "source": "linkedin",
                "description": "",
            },
        ]

        call_count = 0

        def _mock_get(url: str, **kwargs) -> MagicMock:
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if call_count == 1:
                # First call: simulate rate limit / server error
                resp.status_code = 429
                resp.text = ""
            else:
                # Second call: succeed
                resp.status_code = 200
                resp.text = (
                    '<div class="description__text">'
                    "Full job description text here"
                    "</div>"
                )
            return resp

        with patch("requests.get", side_effect=_mock_get):
            with patch("time.sleep"):
                _backfill_linkedin_descriptions(jobs, max_workers=1)

        # Should have retried and gotten the description
        self.assertIn("Full job description text here", jobs[0].get("description", ""))
        self.assertGreaterEqual(call_count, 2, "Should have retried at least once")

    def test_linkedin_backfill_max_retries(self) -> None:
        """After max retries, give up gracefully without crashing."""
        from job_finder.pipeline import _backfill_linkedin_descriptions

        jobs = [
            {
                "title": "Data Engineer",
                "company": "Beta Inc",
                "url": "https://linkedin.com/jobs/view/67890",
                "source": "linkedin",
                "description": "",
            },
        ]

        call_count = 0

        def _mock_get(url: str, **kwargs) -> MagicMock:
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            # Always fail with server error
            resp.status_code = 500
            resp.text = ""
            return resp

        with patch("requests.get", side_effect=_mock_get):
            with patch("time.sleep"):
                # Should NOT crash
                _backfill_linkedin_descriptions(jobs, max_workers=1)

        # Description should remain empty — no crash
        self.assertFalse(
            jobs[0].get("description"),
            "Description should remain empty after all retries exhausted",
        )
        # Should have tried the initial call + 2 retries = 3 total
        self.assertEqual(call_count, 3, "Should have tried initial + 2 retries")

    def test_linkedin_backfill_no_retry_on_success(self) -> None:
        """When the first fetch succeeds, no retry should be attempted."""
        from job_finder.pipeline import _backfill_linkedin_descriptions

        jobs = [
            {
                "title": "PM",
                "company": "Gamma",
                "url": "https://linkedin.com/jobs/view/11111",
                "source": "linkedin",
                "description": "",
            },
        ]

        call_count = 0

        def _mock_get(url: str, **kwargs) -> MagicMock:
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.text = (
                '<div class="show-more-less-html__markup">'
                "Great job posting"
                "</div>"
            )
            return resp

        with patch("requests.get", side_effect=_mock_get):
            with patch("time.sleep") as mock_sleep:
                _backfill_linkedin_descriptions(jobs, max_workers=1)

        self.assertEqual(call_count, 1, "Should only call once on success")
        mock_sleep.assert_not_called()
        self.assertIn("Great job posting", jobs[0].get("description", ""))

    def test_linkedin_backfill_retries_on_exception(self) -> None:
        """Network exceptions (ConnectionError, Timeout) should also trigger retries."""
        import requests as real_requests
        from job_finder.pipeline import _backfill_linkedin_descriptions

        jobs = [
            {
                "title": "Designer",
                "company": "Delta",
                "url": "https://linkedin.com/jobs/view/22222",
                "source": "linkedin",
                "description": "",
            },
        ]

        call_count = 0

        def _mock_get(url: str, **kwargs) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise real_requests.ConnectionError("Connection refused")
            resp = MagicMock()
            resp.status_code = 200
            resp.text = (
                '<div class="description__text">'
                "Design role description"
                "</div>"
            )
            return resp

        with patch("requests.get", side_effect=_mock_get):
            with patch("time.sleep"):
                _backfill_linkedin_descriptions(jobs, max_workers=1)

        self.assertIn("Design role description", jobs[0].get("description", ""))
        self.assertEqual(call_count, 2)


if __name__ == "__main__":
    unittest.main()
