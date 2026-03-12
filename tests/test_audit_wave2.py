"""Wave 2: High-priority issues found in thorough audit.

5. Slug-based company names in Greenhouse/Lever/Ashby
6. preferred_direction is dead config
"""

from __future__ import annotations

import unittest


class SlugCompanyNameTest(unittest.TestCase):
    """ATS scrapers should produce properly-cased company names, not slug artifacts."""

    def test_greenhouse_slug_cleanup(self) -> None:
        """Greenhouse should not leave slug artifacts like 'Openai' or numbered suffixes."""
        # The scraper uses slug.replace("-", " ").title() which gives "Openai" not "OpenAI"
        # and "Notion 2" instead of "Notion"
        from job_finder.tools.scrapers.greenhouse import _clean_company_name
        # This function should exist after the fix
        self.assertEqual(_clean_company_name("openai"), "OpenAI")
        self.assertEqual(_clean_company_name("dbt-labs"), "dbt Labs")

    def test_lever_slug_cleanup(self) -> None:
        from job_finder.tools.scrapers.lever import _clean_company_name
        self.assertEqual(_clean_company_name("notion-2"), "Notion")
        self.assertEqual(_clean_company_name("weights-and-biases"), "Weights and Biases")

    def test_ashby_slug_cleanup(self) -> None:
        from job_finder.tools.scrapers.ashby import _clean_company_name
        self.assertEqual(_clean_company_name("anthropic"), "Anthropic")


class DeadConfigTest(unittest.TestCase):
    """Dead config options should be removed or implemented."""

    def test_preferred_direction_not_in_schema(self) -> None:
        """preferred_direction should either work or be removed from the schema."""
        # After fix, this field should either:
        # a) Be used by scoring (test that it affects scores), OR
        # b) Be removed from the schema
        # For now, just verify it's cleaned up
        from job_finder.config.profile_schema import CareerBaselineConfig
        # If removed, this test passes (field doesn't exist)
        # If kept, there should be pipeline code that reads it
        import inspect
        from job_finder.scoring import dimensions
        source = inspect.getsource(dimensions)
        if hasattr(CareerBaselineConfig, "preferred_direction"):
            # If it exists in schema, it must be used somewhere in scoring
            self.assertIn("preferred_direction", source,
                          "preferred_direction is in schema but not used by scoring")


if __name__ == "__main__":
    unittest.main()
