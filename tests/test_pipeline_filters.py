"""Tests for pipeline filtering — staffing agency exclusion + role filtering."""
from __future__ import annotations

import unittest

from job_finder.pipeline import JobFinderPipeline, _filter_jobs_by_level


class StaffingAgencyFilterTest(unittest.TestCase):
    """Issue #1: exclude_staffing_agencies setting exists but never filters."""

    def _make_pipeline(self, exclude: bool) -> JobFinderPipeline:
        """Create a pipeline with a custom config (no LLM, no profile)."""
        pipe = JobFinderPipeline(llm=None, profile=None)
        # Override config in-memory to control the setting
        pipe.config = {
            "search_settings": {"exclude_staffing_agencies": exclude},
        }
        return pipe

    def _sample_jobs(self) -> list[dict]:
        return [
            {"title": "Data Engineer", "company": "Robert Half", "url": "http://a"},
            {"title": "Analyst", "company": "TEKsystems", "url": "http://b"},
            {"title": "Developer", "company": "Randstad", "url": "http://c"},
            {"title": "SRE", "company": "Insight Global", "url": "http://d"},
            {"title": "ML Engineer", "company": "Adecco", "url": "http://e"},
            {"title": "Designer", "company": "Kelly Services", "url": "http://f"},
            {"title": "Backend Eng", "company": "ManpowerGroup", "url": "http://g"},
            {"title": "Frontend Eng", "company": "Hays", "url": "http://h"},
            {"title": "Platform Eng", "company": "Kforce", "url": "http://i"},
            {"title": "Infra Eng", "company": "Apex Systems", "url": "http://j"},
            # Real companies — should survive the filter
            {"title": "Staff Eng", "company": "Stripe", "url": "http://k"},
            {"title": "SDE", "company": "Google", "url": "http://l"},
            {"title": "PM", "company": "Anthropic", "url": "http://m"},
        ]

    def test_staffing_agencies_removed_when_enabled(self) -> None:
        pipe = self._make_pipeline(exclude=True)
        jobs = self._sample_jobs()
        filtered = pipe.filter_staffing_agencies(jobs)
        remaining = {j["company"] for j in filtered}
        self.assertEqual(remaining, {"Stripe", "Google", "Anthropic"})

    def test_staffing_agencies_kept_when_disabled(self) -> None:
        pipe = self._make_pipeline(exclude=False)
        jobs = self._sample_jobs()
        filtered = pipe.filter_staffing_agencies(jobs)
        self.assertEqual(len(filtered), len(jobs))

    def test_case_insensitive_match(self) -> None:
        pipe = self._make_pipeline(exclude=True)
        jobs = [
            {"title": "Eng", "company": "ROBERT HALF TECHNOLOGY", "url": "http://x"},
            {"title": "Eng", "company": "randstad digital", "url": "http://y"},
            {"title": "Eng", "company": "Genuine Corp", "url": "http://z"},
        ]
        filtered = pipe.filter_staffing_agencies(jobs)
        remaining = {j["company"] for j in filtered}
        self.assertEqual(remaining, {"Genuine Corp"})


class RoleFilterTest(unittest.TestCase):
    """Bug: JobSpy results (Indeed, LinkedIn, etc.) are never filtered by target roles.

    Custom scrapers use _match_roles() to reject unrelated titles, but the main
    JobSpy search path returns raw results that flow straight into scoring.
    A nurse practitioner profile should NOT see "Lead Software Engineer" or
    "Senior ServiceNow Developer" in results — those come from JobSpy matching
    on broad keywords like "lead" or "senior".
    """

    def _make_pipeline(self, target_roles: list[str]) -> JobFinderPipeline:
        pipe = JobFinderPipeline(llm=None, profile=None)
        pipe.config = {"target_roles": target_roles}
        return pipe

    # --- Nurse practitioner profile: reject tech jobs ---

    def test_nurse_profile_rejects_software_engineer(self) -> None:
        """The exact bug from the screenshot: Capital One Lead Software Engineer."""
        pipe = self._make_pipeline([
            "nurse practitioner", "family nurse practitioner",
            "clinical director", "director of nursing", "nurse manager",
            "advanced practice provider", "APP", "NP",
        ])
        jobs = [
            {"title": "Lead Software Engineer, Full Stack (Java, JavaScript, TypeScript) - Navigator Platform",
             "company": "Capital One", "url": "http://a"},
            {"title": "Senior ServiceNow Developer (Platform)",
             "company": "Capgemini", "url": "http://b"},
            {"title": "Software Engineer 5",
             "company": "Netflix", "url": "http://c"},
            {"title": "Work-From-Home Nurse Practitioner | Flexible Primary & Women's Health",
             "company": "NPHire", "url": "http://d"},
            {"title": "Advanced Practice Provider (APP) - Telemed Intake",
             "company": "ProCare", "url": "http://e"},
            {"title": "Clinical Director - Outpatient",
             "company": "HealthFirst", "url": "http://f"},
        ]
        filtered = pipe.filter_by_role(jobs)
        titles = {j["title"] for j in filtered}
        # Software/tech titles must be filtered out
        self.assertNotIn("Lead Software Engineer, Full Stack (Java, JavaScript, TypeScript) - Navigator Platform", titles)
        self.assertNotIn("Senior ServiceNow Developer (Platform)", titles)
        self.assertNotIn("Software Engineer 5", titles)
        # Nurse titles must survive
        self.assertIn("Work-From-Home Nurse Practitioner | Flexible Primary & Women's Health", titles)
        self.assertIn("Advanced Practice Provider (APP) - Telemed Intake", titles)
        self.assertIn("Clinical Director - Outpatient", titles)

    def test_data_engineer_profile_rejects_nurse_jobs(self) -> None:
        """Symmetric check: tech profile should not see nurse jobs."""
        pipe = self._make_pipeline([
            "data engineer", "senior data engineer", "analytics engineer",
            "data platform engineer",
        ])
        jobs = [
            {"title": "Senior Data Engineer", "company": "Stripe", "url": "http://a"},
            {"title": "Nurse Practitioner - Primary Care", "company": "Kaiser", "url": "http://b"},
            {"title": "Analytics Engineer II", "company": "dbt Labs", "url": "http://c"},
        ]
        filtered = pipe.filter_by_role(jobs)
        titles = {j["title"] for j in filtered}
        self.assertIn("Senior Data Engineer", titles)
        self.assertIn("Analytics Engineer II", titles)
        self.assertNotIn("Nurse Practitioner - Primary Care", titles)

    def test_no_roles_passes_everything(self) -> None:
        """When no target roles configured, everything passes (backward compat)."""
        pipe = self._make_pipeline([])
        jobs = [
            {"title": "Literally Anything", "company": "X", "url": "http://a"},
        ]
        filtered = pipe.filter_by_role(jobs)
        self.assertEqual(len(filtered), 1)

    def test_role_filter_is_case_insensitive(self) -> None:
        pipe = self._make_pipeline(["nurse practitioner"])
        jobs = [
            {"title": "NURSE PRACTITIONER - Remote", "company": "X", "url": "http://a"},
            {"title": "nurse practitioner primary care", "company": "Y", "url": "http://b"},
        ]
        filtered = pipe.filter_by_role(jobs)
        self.assertEqual(len(filtered), 2)

    def test_role_filter_logs_count(self) -> None:
        """Filter should report how many jobs were removed."""
        pipe = self._make_pipeline(["nurse practitioner"])
        jobs = [
            {"title": "Nurse Practitioner", "company": "A", "url": "http://a"},
            {"title": "Software Engineer", "company": "B", "url": "http://b"},
            {"title": "Product Manager", "company": "C", "url": "http://c"},
        ]
        progress_msgs = []
        filtered = pipe.filter_by_role(jobs, progress=progress_msgs.append)
        self.assertEqual(len(filtered), 1)
        # Should have logged removal
        self.assertTrue(any("2" in msg for msg in progress_msgs))


class LevelFilterTest(unittest.TestCase):
    """Explicit current_level should affect pre-scoring job filtering."""

    def test_current_level_filters_even_without_current_title(self) -> None:
        jobs = [
            {"title": "Associate Product Manager", "company": "A", "url": "http://a"},
            {"title": "Senior Product Manager", "company": "B", "url": "http://b"},
            {"title": "Staff Product Manager", "company": "C", "url": "http://c"},
        ]

        filtered = _filter_jobs_by_level(
            jobs,
            {"current_level": "senior"},
        )

        titles = {job["title"] for job in filtered}
        self.assertNotIn("Associate Product Manager", titles)
        self.assertIn("Senior Product Manager", titles)
        self.assertIn("Staff Product Manager", titles)


if __name__ == "__main__":
    unittest.main()
