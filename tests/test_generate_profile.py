"""Tests for the LLM-driven profile generation pipeline.

Verifies:
- The system prompt builder produces output containing the security
  header and the schema fields the LLM is supposed to populate
- The pipeline method validates LLM output against the GeneratedProfile
  pydantic schema and rejects malformed responses
- Hallucinated scraper names are stripped (not rejected)
- Scoring weights that don't sum to 1.0 cause rejection
- Missing LLM client gracefully returns None
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from job_finder.pipeline import JobFinderPipeline
from job_finder.prompts import build_generate_profile_prompt


# A reproducible "good" profile that the mocked LLM returns by default.
# Used as the baseline; individual tests mutate it for failure cases.
GOOD_PROFILE = {
    "detected_archetype": "Senior Backend Engineer at fintech startups",
    "confidence": 0.82,
    "reasoning": "Resume shows 5 years of Python/Django at two payments companies plus solid PostgreSQL and Kubernetes experience. Resume language emphasizes scale and reliability over greenfield builds.",
    "closest_template": "tech",
    "career_target": "Senior or staff backend engineer at a Series B+ fintech",
    "seniority_signal": "senior",
    "scoring": {
        "technical_skills": 0.30,
        "leadership_signal": 0.10,
        "career_progression": 0.15,
        "platform_building": 0.15,
        "comp_potential": 0.15,
        "company_trajectory": 0.10,
        "culture_fit": 0.05,
    },
    "keywords": {
        "technical": [
            "Python",
            "Django",
            "PostgreSQL",
            "Kubernetes",
            "payment processing",
            "PCI DSS",
            "Stripe API",
        ],
        "leadership": ["tech lead", "mentor", "code review"],
        "signal_terms": ["fintech", "payments", "scale"],
    },
    "target_roles": [
        "Senior Backend Engineer",
        "Staff Backend Engineer",
        "Payments Platform Engineer",
    ],
    "compensation": {
        "currency": "USD",
        "pay_period": "annual",
        "min_base": 160000,
        "target_total_comp": 240000,
        "include_equity": True,
    },
    "enabled_scrapers": ["indeed", "linkedin", "greenhouse", "lever", "ashby"],
    "recommended_external_boards": [
        "https://efinancialcareers.com",
        "https://wellfound.com",
    ],
    "primary_strengths": [
        "5+ years Python/Django at scale",
        "Direct payments domain experience",
        "Production K8s + PostgreSQL ops",
    ],
    "development_areas": [
        "No people management experience",
        "Limited frontend exposure",
    ],
}


def _pipeline_with_mock_llm(llm_response):
    """Construct a JobFinderPipeline whose chat_json returns the given dict.

    Bypasses the normal LLM init so tests are hermetic — no network, no
    real provider config required.
    """
    p = JobFinderPipeline.__new__(JobFinderPipeline)
    p.llm = MagicMock()
    p.llm.is_configured = True
    p.llm.chat_json.return_value = llm_response
    p.config = {}
    return p


class TestPromptBuilder:
    def test_includes_security_header(self) -> None:
        prompt = build_generate_profile_prompt({})
        assert "CRITICAL SECURITY" in prompt

    def test_mentions_required_schema_fields(self) -> None:
        prompt = build_generate_profile_prompt({})
        for field in [
            "detected_archetype",
            "confidence",
            "reasoning",
            "closest_template",
            "scoring",
            "enabled_scrapers",
            "recommended_external_boards",
        ]:
            assert field in prompt, f"prompt missing schema field: {field}"

    def test_warns_against_generic_output(self) -> None:
        prompt = build_generate_profile_prompt({})
        assert "BE SPECIFIC" in prompt
        # The prompt should explicitly contrast good vs bad examples so the
        # model knows what shape it should produce.
        assert "GOOD" in prompt and "BAD" in prompt


class TestPipelineGenerateProfile:
    def test_returns_none_when_llm_missing(self) -> None:
        p = JobFinderPipeline.__new__(JobFinderPipeline)
        p.llm = None
        p.config = {}
        assert p.generate_profile_from_resume("any resume text") is None

    def test_returns_none_when_llm_unconfigured(self) -> None:
        p = JobFinderPipeline.__new__(JobFinderPipeline)
        p.llm = MagicMock()
        p.llm.is_configured = False
        p.config = {}
        assert p.generate_profile_from_resume("any resume text") is None

    def test_happy_path_returns_validated_dict(self) -> None:
        p = _pipeline_with_mock_llm(GOOD_PROFILE)
        result = p.generate_profile_from_resume(
            "any resume text",
            available_scrapers=["indeed", "linkedin", "greenhouse", "lever", "ashby"],
            available_templates=["tech", "ai-research", "crypto"],
        )
        assert result is not None
        assert result["detected_archetype"] == GOOD_PROFILE["detected_archetype"]
        assert result["confidence"] == 0.82
        assert sorted(result["enabled_scrapers"]) == sorted(GOOD_PROFILE["enabled_scrapers"])

    def test_invalid_shape_returns_none(self) -> None:
        bad = dict(GOOD_PROFILE)
        del bad["scoring"]  # required field
        p = _pipeline_with_mock_llm(bad)
        assert p.generate_profile_from_resume("text", available_scrapers=["indeed"]) is None

    def test_bad_scoring_sum_returns_none(self) -> None:
        bad = json.loads(json.dumps(GOOD_PROFILE))  # deep copy
        bad["scoring"]["technical_skills"] = 0.5  # now sums to 1.20
        p = _pipeline_with_mock_llm(bad)
        assert p.generate_profile_from_resume("text", available_scrapers=["indeed"]) is None

    def test_hallucinated_scrapers_are_stripped_not_rejected(self) -> None:
        bad = json.loads(json.dumps(GOOD_PROFILE))
        bad["enabled_scrapers"] = ["indeed", "fake_scraper_99", "linkedin"]
        p = _pipeline_with_mock_llm(bad)
        result = p.generate_profile_from_resume(
            "text",
            available_scrapers=["indeed", "linkedin", "greenhouse"],
        )
        assert result is not None, "should NOT reject — should strip"
        assert "fake_scraper_99" not in result["enabled_scrapers"]
        assert "indeed" in result["enabled_scrapers"]
        assert "linkedin" in result["enabled_scrapers"]

    def test_llm_returning_none_returns_none(self) -> None:
        p = _pipeline_with_mock_llm(None)
        assert p.generate_profile_from_resume("text", available_scrapers=["indeed"]) is None

    def test_passes_available_scrapers_into_prompt(self) -> None:
        p = _pipeline_with_mock_llm(GOOD_PROFILE)
        p.generate_profile_from_resume(
            "Senior Python engineer",
            available_scrapers=["indeed", "greenhouse", "lever"],
            available_templates=["tech"],
        )
        # Verify the prompt the mock saw included the scraper list and the
        # resume wrapped in a <resume> tag (prompt injection defense).
        call_args = p.llm.chat_json.call_args
        user_msg = call_args[0][1]
        assert "indeed" in user_msg
        assert "greenhouse" in user_msg
        assert "<resume>" in user_msg
        assert "Senior Python engineer" in user_msg
