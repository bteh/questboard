from __future__ import annotations

import unittest

from job_finder.prompts import (
    build_company_researcher_prompt,
    build_cover_letter_prompt,
    build_scorer_prompt,
)


class PromptDefaultsTest(unittest.TestCase):
    def test_default_scorer_thresholds_match_offline_scorer(self) -> None:
        prompt = build_scorer_prompt({})

        self.assertIn("STRONG_APPLY  ≥ 70", prompt)
        self.assertIn("APPLY         55–69", prompt)
        self.assertIn("MAYBE         40–54", prompt)

    def test_cover_letter_prompt_forbids_invented_company_details(self) -> None:
        prompt = build_cover_letter_prompt({})

        self.assertIn("Do not invent", prompt)
        self.assertIn("company_specific_references", prompt)

    def test_company_research_prompt_prefers_unknown_over_guessing(self) -> None:
        prompt = build_company_researcher_prompt({})

        self.assertIn('return `"Unknown"`, `null`, or `[]` instead of guessing', prompt)
        self.assertIn('"why_join": "<paragraph>"', prompt)


if __name__ == "__main__":
    unittest.main()
