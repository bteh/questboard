"""Recall regression tests — protect startup/founding-role discovery.

User reported "few relevant jobs compared to LinkedIn, also no startups,
founding [roles]". These tests pin down the three confirmed root causes so
they don't regress:

1. Greenhouse/Lever/Ashby ATS scrapers must ship with non-empty default
   company lists (otherwise zero startups surface without a watchlist).
2. The role-relevance filter must accept founding-role aliases ("Founding
   Engineer", "Member of Technical Staff", "MTS", etc.) regardless of
   target_roles — these don't word-overlap with normal job titles.
3. Jobs with no posted salary must survive the salary filter (most startup
   listings don't post comp).

Per global CLAUDE.md: bug → write a failing test first, then fix.
"""
from __future__ import annotations

import unittest

from job_finder.pipeline import JobFinderPipeline, _filter_jobs_by_level, _job_salary_passes
from job_finder.tools.scrapers._utils import _match_roles


# --- 1. ATS seed company lists ------------------------------------------------


class AtsSeedCompanyListsTest(unittest.TestCase):
    """Greenhouse/Lever/Ashby must populate a default company list at import.

    Without seeds, a fresh user with an empty watchlist gets zero jobs from
    these three scrapers — and they're where startups list. This is the
    single biggest recall hole.
    """

    # Thresholds reflect verified-alive slug counts from periodic health checks,
    # not aspirational targets. Lever's active board pool is genuinely smaller
    # than Greenhouse/Ashby — many former Lever users migrated to other ATSes.

    def test_greenhouse_has_seed_companies(self) -> None:
        from job_finder.tools.scrapers import greenhouse
        self.assertGreater(
            len(greenhouse._GREENHOUSE_COMPANIES), 50,
            "Greenhouse scraper has no default companies — fresh users get zero startup jobs",
        )

    def test_lever_has_seed_companies(self) -> None:
        from job_finder.tools.scrapers import lever
        self.assertGreater(
            len(lever._LEVER_COMPANIES), 5,
            "Lever scraper has no default companies — fresh users get zero startup jobs",
        )

    def test_ashby_has_seed_companies(self) -> None:
        from job_finder.tools.scrapers import ashby
        self.assertGreater(
            len(ashby._ASHBY_COMPANIES), 30,
            "Ashby scraper has no default companies — fresh users get zero startup jobs",
        )


# --- 2. Founding-role aliases survive role filter -----------------------------


class FoundingRoleSurvivesRoleFilterTest(unittest.TestCase):
    """"Founding Engineer" / "Member of Technical Staff" must survive the role
    filter even when target_roles is something like ["software engineer"].

    These titles don't word-overlap with normal target roles, so the strict
    `_match_roles` matcher drops them. We need an explicit founding-alias
    bypass that's on by default (user direction: global default).
    """

    _SOFTWARE_ROLES = ["software engineer", "senior software engineer", "backend engineer"]

    def test_founding_engineer_passes_match_roles_by_default(self) -> None:
        self.assertTrue(
            _match_roles("Founding Engineer", self._SOFTWARE_ROLES),
            "Founding Engineer is a flagship startup role and must always pass",
        )

    def test_member_of_technical_staff_passes_match_roles(self) -> None:
        self.assertTrue(
            _match_roles("Member of Technical Staff", self._SOFTWARE_ROLES),
            "MTS is the standard staff-engineer title at AI labs (Anthropic, OpenAI, etc.)",
        )

    def test_mts_acronym_passes_match_roles(self) -> None:
        self.assertTrue(
            _match_roles("MTS, Backend Systems", self._SOFTWARE_ROLES),
        )

    def test_founding_designer_passes(self) -> None:
        self.assertTrue(
            _match_roles("Founding Designer", ["product designer", "ux designer"]),
        )

    def test_first_engineering_hire_passes(self) -> None:
        self.assertTrue(
            _match_roles("First Engineering Hire", self._SOFTWARE_ROLES),
        )

    def test_founding_alias_can_be_disabled(self) -> None:
        """Strict mode (include_founding=False) restores old behavior."""
        self.assertFalse(
            _match_roles("Founding Engineer", self._SOFTWARE_ROLES, include_founding=False),
        )

    def test_founding_aliases_pass_through_pipeline_role_filter(self) -> None:
        """End-to-end: pipeline.filter_by_role must keep founding titles."""
        pipe = JobFinderPipeline(llm=None, profile=None)
        pipe.config = {"target_roles": self._SOFTWARE_ROLES}
        jobs = [
            {"title": "Founding Engineer", "company": "Acme AI", "url": "http://a"},
            {"title": "Member of Technical Staff", "company": "Anthropic", "url": "http://b"},
            {"title": "Senior Software Engineer", "company": "Stripe", "url": "http://c"},
            {"title": "Marketing Manager", "company": "X", "url": "http://d"},
        ]
        kept_titles = {j["title"] for j in pipe.filter_by_role(jobs)}
        self.assertIn("Founding Engineer", kept_titles)
        self.assertIn("Member of Technical Staff", kept_titles)
        self.assertIn("Senior Software Engineer", kept_titles)
        self.assertNotIn("Marketing Manager", kept_titles)


# --- 3. No-salary jobs survive salary filter ----------------------------------


class NoSalaryJobsSurviveSalaryFilterTest(unittest.TestCase):
    """Most startup listings don't post salary. They must pass through.

    The current implementation already does this (verified by reading
    pipeline._job_salary_passes). This test guards against future
    regression where someone "tightens" the filter.
    """

    def test_no_salary_data_passes(self) -> None:
        job = {"title": "Founding Engineer", "salary_min": None, "salary_max": None}
        self.assertTrue(_job_salary_passes(job, hard_floor=120_000))

    def test_explicit_below_floor_fails(self) -> None:
        job = {"title": "Junior Eng", "salary_min": 50_000, "salary_max": 70_000}
        self.assertFalse(_job_salary_passes(job, hard_floor=120_000))

    def test_above_floor_passes(self) -> None:
        job = {"title": "Senior Eng", "salary_min": 180_000, "salary_max": 220_000}
        self.assertTrue(_job_salary_passes(job, hard_floor=120_000))


# --- 4. Founding-role title doesn't get level-filtered out --------------------


class FoundingRoleLevelFilterTest(unittest.TestCase):
    """LEVEL_MAP maps "founding" → 4, so founding titles already pass the
    level filter for senior/staff profiles. Verify this stays correct.

    For junior/mid profiles, the level filter caps at current_level + 2.0,
    so a level-4 founding title only just barely clears for mid (2 + 2 = 4)
    and gets dropped for junior (1 + 2 = 3 < 4). We verify senior/staff
    behavior here; junior/mid is intentional (founding is too senior).
    """

    def test_founding_engineer_kept_at_senior_profile(self) -> None:
        jobs = [{"title": "Founding Engineer", "company": "Startup", "url": "x"}]
        kept = _filter_jobs_by_level(jobs, {"current_level": "senior"})
        self.assertEqual(len(kept), 1, "Founding Engineer must survive at senior profile")

    def test_member_of_technical_staff_kept_at_staff_profile(self) -> None:
        jobs = [{"title": "Member of Technical Staff", "company": "Lab", "url": "x"}]
        kept = _filter_jobs_by_level(jobs, {"current_level": "staff"})
        self.assertEqual(len(kept), 1, "MTS must survive at staff profile")


if __name__ == "__main__":
    unittest.main()
